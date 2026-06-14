"""
湖北 school 元数据推断（Phase 19）。

仅普通类本科批 / 专科批；艺体类标记 unsupported。
"""

from __future__ import annotations

from normalizers.admission_category import normalize_admission_category
from normalizers.school_batch import normalize_school_batch

IMPORTABLE_ADMISSION_CATEGORIES = frozenset({"普通类"})

_ORDINARY_MARKERS = (
    "普通类",
    "普通批",
    "平行志愿",
    "投档情况",
    "投档线",
    "院校专业组",
    "本科普通批",
    "高职高专普通批",
)


def infer_admission_category(title_or_filename: str) -> str | None:
    text = title_or_filename or ""
    if any(k in text for k in ("艺术", "美术", "音乐", "舞蹈", "播音", "体育")):
        if "普通类" in text or "普通批" in text:
            return "普通类"
        if "艺术" in text or "美术" in text or "音乐" in text:
            return "unsupported"
        if "体育" in text:
            return "unsupported"
    if "普通类" in text or "普通批" in text or any(k in text for k in _ORDINARY_MARKERS):
        return "普通类"
    if any(k in text for k in ("技能高考", "单招", "对口", "征集志愿")):
        return "unsupported"
    return None


def infer_subject_type(title_or_filename: str) -> str | None:
    text = title_or_filename or ""
    if "首选物理" in text or "物理科目" in text or ("物理" in text and "历史" not in text):
        return "物理类"
    if "首选历史" in text or "历史科目" in text or "历史" in text:
        return "历史类"
    return None


def infer_batch(title_or_filename: str, source_title: str | None = None) -> str:
    text = " ".join(t for t in (source_title or "", title_or_filename or "") if t)
    if "高职高专普通批" in text or "高职高专" in text:
        return "专科批"
    if "专科批" in text or ("专科" in text and "本科" not in text):
        return "专科批"
    if "本科普通批" in text or "本科批" in text or "本科" in text:
        return "本科批"
    return "本科批"


def infer_school_metadata(
    title: str,
    source_title: str | None = None,
) -> dict[str, str]:
    from crawlers.discovery import infer_school_metadata_from_title

    primary = title or ""
    category = infer_admission_category(primary)
    if category is None and source_title:
        category = infer_admission_category(source_title)
    if category == "unsupported":
        category = "艺术类"
    if category is None:
        fallback = infer_school_metadata_from_title(primary, source_title=source_title)
        category = fallback["admission_category"]
    else:
        category = normalize_admission_category(category) or category

    batch = normalize_school_batch(infer_batch(primary, source_title=source_title)) or "本科批"
    return {"admission_category": category, "batch": batch}


def is_importable_category(admission_category: str | None) -> bool:
    return (admission_category or "") in IMPORTABLE_ADMISSION_CATEGORIES
