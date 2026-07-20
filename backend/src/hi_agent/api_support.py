"""Small shared helpers for tenant-scoped API modules."""

from __future__ import annotations

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .errors import NotFoundError


def get_owned[ModelT](db: Session, model: type[ModelT], item_id: str, label: str) -> ModelT:
    item = db.get(model, item_id)
    if item is None:
        raise NotFoundError(label, item_id)
    return item


def commit_model[ModelT](db: Session, item: ModelT) -> ModelT:
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def apply_model[ModelT](item: ModelT, payload: BaseModel) -> ModelT:
    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(item, key, value)
    return item


def request_owner_id(request: Request) -> str:
    return str(request.state.user.id)
