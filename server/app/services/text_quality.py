from __future__ import annotations

import re
import unicodedata
from typing import Any

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")

MOJIBAKE_MARKERS = (
    "鐖",
    "绗",
    "闆",
    "鍙",
    "浣",
    "杩",
    "鎴",
    "瀹",
    "鍝",
    "鍟",
    "鏄",
    "涓",
    "€",
    "�",
)

EMOTION_TERMS = (
    "爽",
    "笑",
    "鹅叫",
    "打脸",
    "反转",
    "高能",
    "甜",
    "燃",
    "破防",
    "上头",
    "离谱",
    "心疼",
    "扎心",
    "紧张",
    "惊",
    "懵",
    "名场面",
    "解气",
    "心动",
    "好磕",
    "稳了",
    "气炸",
    "泪目",
    "站",
    "冲",
    "敢",
    "信",
    "猜",
    "来",
)


BLOCKED_TITLE_TERMS = (
    "酸鸡",
    "贱",
    "垃圾",
    "蠢",
    "傻",
    "废物",
    "狗血",
    "撕逼",
    "绿茶",
    "白莲",
    "小三",
    "渣男",
    "舔狗",
    "怼死",
    "骂爆",
)


def repair_mojibake(text: str) -> str:
    if not text or not looks_like_mojibake(text):
        return text

    try:
        repaired = text.encode("gb18030").decode("utf-8")
    except UnicodeError:
        return text

    return repaired if text_quality_score(repaired) > text_quality_score(text) else text


def repair_mojibake_in_value(value: Any) -> Any:
    if isinstance(value, str):
        return repair_mojibake(value)
    if isinstance(value, list):
        return [repair_mojibake_in_value(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_mojibake_in_value(item) for key, item in value.items()}
    return value


def is_usable_interaction_copy(text: str, *, max_chars: int) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > max_chars:
        return False
    if not contains_cjk(stripped) or contains_latin(stripped):
        return False
    if looks_like_mojibake(stripped) or has_private_or_replacement_char(stripped):
        return False
    return any(term in stripped for term in EMOTION_TERMS)


def is_usable_title_copy(text: str, *, max_chars: int) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > max_chars:
        return False
    if not contains_cjk(stripped) or contains_latin(stripped):
        return False
    if looks_like_mojibake(stripped) or has_private_or_replacement_char(stripped):
        return False
    return not contains_blocked_title_term(stripped)


def contains_blocked_title_term(text: str) -> bool:
    return any(term in text for term in BLOCKED_TITLE_TERMS)


def contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def contains_latin(text: str) -> bool:
    return bool(LATIN_RE.search(text))


def looks_like_mojibake(text: str) -> bool:
    marker_count = sum(1 for marker in MOJIBAKE_MARKERS if marker in text)
    return marker_count >= 1 or has_private_or_replacement_char(text)


def has_private_or_replacement_char(text: str) -> bool:
    return any(char == "\ufffd" or unicodedata.category(char) == "Co" for char in text)


def text_quality_score(text: str) -> int:
    cjk_count = len(CJK_RE.findall(text))
    latin_count = len(LATIN_RE.findall(text))
    marker_count = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    private_count = sum(1 for char in text if unicodedata.category(char) == "Co")
    return cjk_count * 2 - latin_count - marker_count * 8 - private_count * 20
