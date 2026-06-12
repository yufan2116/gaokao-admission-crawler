"""
科类 / 选科类型标准化。
"""

from __future__ import annotations

from typing import Any

SUBJECT_TYPE_ALIASES: dict[str, str] = {
    "物理": "物理类",
    "物理类": "物理类",
    "理科": "物理类",
    "理工": "物理类",
    "历史": "历史类",
    "历史类": "历史类",
    "文科": "历史类",
    "文史": "历史类",
    "综合改革": "综合改革",
    "综合": "综合改革",
    "不分文理": "综合改革",
}


def _is_legacy_subject_mode(subject_mode: Any) -> bool:
    return subject_mode is not None and str(subject_mode) == "legacy"


def normalize_subject_type(
    value: str | None,
    *,
    subject_mode: Any = None,
) -> str:
    """统一科类名称；legacy 模式保留文科/理科。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if _is_legacy_subject_mode(subject_mode):
        if "文科" in text:
            return "文科"
        if "理科" in text:
            return "理科"
        return text
    for key, standard in SUBJECT_TYPE_ALIASES.items():
        if key in text or text == key:
            return standard
    return text
