"""Deterministic, local-first digital-human avatar specification generation."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _pick(text: str, choices: tuple[tuple[str, tuple[str, ...]], ...], fallback: str) -> str:
    return next((value for value, words in choices if _contains(text, words)), fallback)


def build_digital_human_spec(description: str) -> dict[str, Any]:
    """Map untrusted natural language to a closed, render-safe avatar parameter set."""

    normalized = description.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    presentation = _pick(
        normalized,
        (("feminine", ("女性", "女生", "女孩", "姐姐", "女士", "girl", "woman")),
         ("masculine", ("男性", "男生", "男孩", "哥哥", "先生", "boy", "man"))),
        "neutral",
    )
    skin_tone = _pick(
        normalized,
        (("#6F4436", ("深色皮肤", "深肤", "dark skin")),
         ("#A96F52", ("小麦色", "古铜色", "tan")),
         ("#F3C7A5", ("白皙", "浅肤", "fair"))),
        ("#E7AC84", "#C98563", "#F0BE98")[seed % 3],
    )
    hair_style = _pick(
        normalized,
        (("bald", ("光头", "无发", "bald")),
         ("bun", ("丸子头", "发髻", "盘发", "bun")),
         ("curly", ("卷发", "卷毛", "curly")),
         ("long", ("长发", "披肩", "long hair")),
         ("short", ("短发", "寸头", "short hair"))),
        "long" if presentation == "feminine" else "short",
    )
    hair_color = _pick(
        normalized,
        (("#E8D7B2", ("金发", "金色头发", "blonde")),
         ("#B7BCC8", ("银发", "银色头发", "银色短发", "银色长发", "白发", "silver hair")),
         ("#B94B6B", ("粉发", "粉色头发", "pink hair")),
         ("#365A8D", ("蓝发", "蓝色头发", "blue hair")),
         ("#8C3F2F", ("红发", "红色头发", "red hair")),
         ("#674536", ("棕发", "褐色头发", "brown hair"))),
        "#262522",
    )
    eye_color = _pick(
        normalized,
        (("#4F79A7", ("蓝眼", "蓝色眼睛", "blue eyes")),
         ("#4F7D62", ("绿眼", "绿色眼睛", "green eyes")),
         ("#8D6849", ("棕色眼睛", "brown eyes"))),
        "#3D342F",
    )
    outfit = _pick(
        normalized,
        (("suit", ("西装", "商务", "职业装", "suit")),
         ("hoodie", ("卫衣", "帽衫", "hoodie")),
         ("dress", ("连衣裙", "裙装", "dress")),
         ("jacket", ("夹克", "机车", "jacket"))),
        "tshirt",
    )
    outfit_color = _pick(
        normalized,
        (("#D95D69", ("红色衣", "红衣")), ("#3478A8", ("蓝色衣", "蓝衣")),
         ("#6655A5", ("紫色衣", "紫衣")), ("#262D35", ("黑色衣", "黑衣")),
         ("#F1EEE7", ("白色衣", "白衣")),
         ("#2E8B68", ("绿色衣", "绿色卫衣", "绿色西装", "绿色夹克", "绿衣"))),
        ("#2E8B68", "#466A96", "#8C5AA5", "#D06C55")[seed % 4],
    )
    accessory = _pick(
        normalized,
        (("headphones", ("耳机", "headphone")), ("glasses", ("眼镜", "glasses")),
         ("earrings", ("耳环", "耳饰", "earring"))),
        "none",
    )
    expression = _pick(
        normalized,
        (("cool", ("酷", "冷峻", "高冷", "cool")),
         ("confident", ("自信", "坚定", "confident")),
         ("calm", ("温柔", "平静", "沉稳", "calm"))),
        "smile",
    )
    background = _pick(
        normalized,
        (("#FFF0E8", ("暖色背景", "橙色背景")), ("#EAF1FF", ("蓝色背景", "科技感")),
         ("#F1EAFE", ("紫色背景", "梦幻")), ("#E7F5EC", ("绿色背景", "自然"))),
        ("#E7F5EC", "#EAF1FF", "#F1EAFE", "#FFF0E8")[seed % 4],
    )
    name_match = re.search(r"(?:叫|名字是|名为)\s*([\w\u3400-\u9fff·-]{1,20})", description)
    display_name = name_match.group(1) if name_match else "Hi 数字人"
    return {
        "version": 1,
        "name": display_name,
        "presentation": presentation,
        "skin_tone": skin_tone,
        "hair_style": hair_style,
        "hair_color": hair_color,
        "eye_color": eye_color,
        "outfit": outfit,
        "outfit_color": outfit_color,
        "accent_color": "#B7E561",
        "accessory": accessory,
        "expression": expression,
        "background": background,
        "seed": seed,
    }
