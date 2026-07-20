"""Local authentication core with replaceable development identity providers."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import ensure_builtin_agents, ensure_builtin_prompt_templates, ensure_default_project, get_db
from .errors import ConflictError, HiAgentError
from .models import AuthAuditLog, AuthSession, OtpChallenge, User, UserIdentity, WechatChallenge, now_utc
from .schemas import (
    AuthConfig,
    AuthResult,
    OtpIssued,
    OtpRequest,
    PhoneLogin,
    PhoneRegister,
    UserRead,
    WechatChallengeCreate,
    WechatChallengeRead,
    WechatComplete,
    WechatMockAuthorize,
)

SESSION_COOKIE = "hi_agent_session"
CSRF_COOKIE = "hi_agent_csrf"
public_auth_router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _secret_file(settings: Settings) -> Path:
    return settings.data_dir / ".auth-pepper"


def _pepper(settings: Settings) -> bytes:
    if value := settings.resolve_secret("HI_AGENT_AUTH_PEPPER"):
        return value.encode()
    path = _secret_file(settings)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        os.chmod(path, 0o600)
    return path.read_bytes().strip()


def _digest(settings: Settings, value: str) -> str:
    return hmac.new(_pepper(settings), value.encode(), hashlib.sha256).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _expired(value: datetime) -> bool:
    return _as_utc(value) <= now_utc()


def _phone(value: str) -> str:
    cleaned = "".join(character for character in value.strip() if character.isdigit() or character == "+")
    if cleaned.startswith("+86"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("86") and len(cleaned) == 13:
        cleaned = cleaned[2:]
    if len(cleaned) != 11 or not cleaned.startswith("1") or not cleaned.isdigit():
        raise HiAgentError("PHONE_INVALID", "请输入有效的中国大陆手机号", status_code=422)
    return f"+86{cleaned}"


def _audit(db: Session, action: str, result: str, user_id: str | None = None, **detail: object) -> None:
    db.add(AuthAuditLog(user_id=user_id, action=action, result=result, detail=detail))


def _user_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


def _set_session(response: Response, db: Session, settings: Settings, user: User) -> AuthResult:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(days=settings.auth_session_days)
    db.add(AuthSession(user_id=user.id, token_hash=_digest(settings, token), expires_at=expires))
    user.last_login_at = now_utc()
    user.status = "active"
    _audit(db, "session.created", "success", user.id)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.auth_session_days * 86400,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=settings.auth_session_days * 86400,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return AuthResult(user=_user_read(user), csrf_token=csrf)


def current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if not token:
        raise HiAgentError("AUTH_REQUIRED", "请先登录", status_code=401)
    settings = _settings(request)
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _digest(settings, token)))
    if auth_session is None or auth_session.revoked_at is not None or _expired(auth_session.expires_at):
        raise HiAgentError("SESSION_EXPIRED", "登录状态已失效，请重新登录", status_code=401)
    user = db.get(User, auth_session.user_id)
    if user is None or user.status not in {"active", "pending_claim"}:
        raise HiAgentError("ACCOUNT_DISABLED", "账号不可用", status_code=403)
    auth_session.last_seen_at = now_utc()
    db.info["owner_id"] = user.id
    request.state.user = user
    return user


def require_csrf(
    request: Request,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HiAgentError("CSRF_INVALID", "请求安全校验失败，请刷新页面后重试", status_code=403)


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HiAgentError("ADMIN_REQUIRED", "此操作仅限管理员", status_code=403)
    return user


@public_auth_router.get("/config", response_model=AuthConfig)
def auth_config(request: Request) -> AuthConfig:
    settings = _settings(request)
    return AuthConfig(
        mode=settings.auth_mode,
        mock_phone_enabled=settings.mock_auth_enabled,
        mock_wechat_enabled=settings.mock_auth_enabled,
        provider_notice=(
            "当前为开发模拟认证：验证码和微信授权不会连接外部服务。"
            if settings.mock_auth_enabled
            else "生产模式未配置身份提供商。"
        ),
    )


@public_auth_router.post("/phone/code", response_model=OtpIssued)
def issue_phone_code(request: Request, payload: OtpRequest, db: Session = Depends(get_db)) -> OtpIssued:
    settings = _settings(request)
    if not settings.mock_auth_enabled:
        raise HiAgentError("SMS_PROVIDER_NOT_CONFIGURED", "短信服务尚未配置", status_code=503)
    phone = _phone(payload.phone)
    latest = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.purpose == payload.purpose)
        .order_by(OtpChallenge.created_at.desc())
    )
    if latest and (now_utc() - _as_utc(latest.created_at)).total_seconds() < settings.auth_otp_resend_seconds:
        raise HiAgentError("OTP_RATE_LIMITED", "验证码发送过于频繁，请稍后再试", status_code=429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OtpChallenge(
        phone=phone,
        purpose=payload.purpose,
        code_hash=_digest(settings, f"{phone}:{payload.purpose}:{code}"),
        expires_at=now_utc() + timedelta(seconds=settings.auth_otp_ttl_seconds),
    )
    db.add(challenge)
    _audit(db, "otp.issued", "success", phone_tail=phone[-4:], purpose=payload.purpose, provider="mock")
    db.commit()
    return OtpIssued(
        challenge_id=challenge.id,
        expires_in=settings.auth_otp_ttl_seconds,
        resend_after=settings.auth_otp_resend_seconds,
        debug_code=code,
    )


def _consume_code(db: Session, settings: Settings, phone_text: str, purpose: str, code: str) -> str:
    phone = _phone(phone_text)
    challenge = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.purpose == purpose, OtpChallenge.used_at.is_(None))
        .order_by(OtpChallenge.created_at.desc())
    )
    if challenge is None or _expired(challenge.expires_at):
        raise HiAgentError("OTP_EXPIRED", "验证码不存在或已过期", status_code=400)
    if challenge.attempts >= settings.auth_otp_max_attempts:
        raise HiAgentError("OTP_LOCKED", "验证码尝试次数过多，请重新获取", status_code=429)
    expected = _digest(settings, f"{phone}:{purpose}:{code}")
    if not secrets.compare_digest(challenge.code_hash, expected):
        challenge.attempts += 1
        db.commit()
        raise HiAgentError("OTP_INVALID", "验证码错误", status_code=400)
    challenge.used_at = now_utc()
    return phone


@public_auth_router.post("/phone/register", response_model=AuthResult)
def register_phone(
    request: Request, response: Response, payload: PhoneRegister, db: Session = Depends(get_db)
) -> AuthResult:
    settings = _settings(request)
    phone = _consume_code(db, settings, payload.phone, "register", payload.code)
    if db.scalar(select(User).where(User.phone == phone)):
        raise ConflictError("PHONE_ALREADY_REGISTERED", "该手机号已经注册")
    if db.scalar(select(User).where(User.username == payload.username.strip())):
        raise ConflictError("USERNAME_TAKEN", "用户名已被使用")
    user = db.scalar(select(User).where(User.status == "pending_claim", User.role == "admin"))
    if user is None:
        user = User(username=payload.username.strip(), phone=phone)
        db.add(user)
        db.flush()
    else:
        user.username = payload.username.strip()
        user.phone = phone
        user.status = "active"
    ensure_default_project(db, user.id)
    ensure_builtin_prompt_templates(db, user.id)
    ensure_builtin_agents(db, user.id)
    db.add(UserIdentity(user_id=user.id, provider="phone", subject=phone, profile={"phone_tail": phone[-4:]}))
    _audit(db, "phone.register", "success", user.id, phone_tail=phone[-4:])
    return _set_session(response, db, settings, user)


@public_auth_router.post("/phone/login", response_model=AuthResult)
def login_phone(request: Request, response: Response, payload: PhoneLogin, db: Session = Depends(get_db)) -> AuthResult:
    settings = _settings(request)
    phone = _consume_code(db, settings, payload.phone, "login", payload.code)
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        raise HiAgentError("ACCOUNT_NOT_FOUND", "该手机号尚未注册", status_code=404)
    _audit(db, "phone.login", "success", user.id, phone_tail=phone[-4:])
    return _set_session(response, db, settings, user)


@public_auth_router.post("/wechat/challenges", response_model=WechatChallengeRead)
def create_wechat_challenge(
    request: Request, payload: WechatChallengeCreate, db: Session = Depends(get_db)
) -> WechatChallengeRead:
    settings = _settings(request)
    if not settings.mock_auth_enabled:
        raise HiAgentError("WECHAT_PROVIDER_NOT_CONFIGURED", "微信开放平台尚未配置", status_code=503)
    ticket = secrets.token_urlsafe(40)
    challenge = WechatChallenge(
        ticket_hash=_digest(settings, ticket),
        purpose=payload.purpose,
        expires_at=now_utc() + timedelta(minutes=5),
    )
    db.add(challenge)
    db.commit()
    return WechatChallengeRead(
        challenge_id=challenge.id, ticket=ticket, status=challenge.status, expires_in=300, mock=True
    )


def _wechat_challenge(db: Session, settings: Settings, challenge_id: str, ticket: str) -> WechatChallenge:
    challenge = db.get(WechatChallenge, challenge_id)
    if (
        challenge is None
        or _expired(challenge.expires_at)
        or not secrets.compare_digest(challenge.ticket_hash, _digest(settings, ticket))
    ):
        raise HiAgentError("WECHAT_CHALLENGE_INVALID", "二维码已失效，请刷新后重试", status_code=400)
    return challenge


@public_auth_router.post("/wechat/challenges/{challenge_id}/mock-authorize")
def mock_authorize_wechat(
    request: Request,
    challenge_id: str,
    payload: WechatMockAuthorize,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = _settings(request)
    if not settings.mock_auth_enabled:
        raise HiAgentError("MOCK_AUTH_DISABLED", "生产模式禁止模拟授权", status_code=403)
    challenge = _wechat_challenge(db, settings, challenge_id, payload.ticket)
    subject = hashlib.sha256(f"hi-agent-mock-wechat:{payload.mock_account}".encode()).hexdigest()
    challenge.profile = {
        "subject": subject,
        "nickname": payload.nickname,
        "avatar_url": "",
        "provider": "wechat-mock",
    }
    challenge.status = "authorized"
    db.commit()
    return {"status": "authorized"}


@public_auth_router.post("/wechat/challenges/{challenge_id}/complete", response_model=AuthResult)
def complete_wechat(
    request: Request,
    response: Response,
    challenge_id: str,
    payload: WechatComplete,
    db: Session = Depends(get_db),
) -> AuthResult:
    settings = _settings(request)
    challenge = _wechat_challenge(db, settings, challenge_id, payload.ticket)
    if challenge.status != "authorized" or challenge.consumed_at is not None:
        raise HiAgentError("WECHAT_NOT_AUTHORIZED", "尚未完成微信授权", status_code=409)
    subject = str(challenge.profile.get("subject", ""))
    identity = db.scalar(select(UserIdentity).where(UserIdentity.provider == "wechat", UserIdentity.subject == subject))
    if challenge.purpose == "login":
        if identity is None:
            raise HiAgentError("WECHAT_NOT_REGISTERED", "该微信账号尚未注册", status_code=404)
        user = db.get(User, identity.user_id)
        assert user is not None
    else:
        if identity is not None:
            raise ConflictError("WECHAT_ALREADY_REGISTERED", "该微信账号已经注册")
        nickname = str(challenge.profile.get("nickname") or "微信用户")
        username = nickname
        suffix = 1
        while db.scalar(select(User).where(User.username == username)):
            suffix += 1
            username = f"{nickname}{suffix}"
        user = db.scalar(select(User).where(User.status == "pending_claim", User.role == "admin"))
        if user is None:
            user = User(username=username)
            db.add(user)
            db.flush()
        else:
            user.username = username
            user.status = "active"
        user.wechat_nickname = nickname
        user.avatar_url = str(challenge.profile.get("avatar_url") or "") or None
        ensure_default_project(db, user.id)
        ensure_builtin_prompt_templates(db, user.id)
        ensure_builtin_agents(db, user.id)
        db.add(UserIdentity(user_id=user.id, provider="wechat", subject=subject, profile=challenge.profile))
    challenge.consumed_at = now_utc()
    challenge.status = "consumed"
    _audit(db, f"wechat.{challenge.purpose}", "success", user.id, provider="mock")
    return _set_session(response, db, settings, user)


@public_auth_router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return _user_read(user)


@public_auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    user: CurrentUser,
    _: Annotated[None, Depends(require_csrf)],
    db: Session = Depends(get_db),
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    if token:
        auth_session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == _digest(_settings(request), token))
        )
        if auth_session:
            auth_session.revoked_at = now_utc()
            _audit(db, "session.revoked", "success", user.id)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
