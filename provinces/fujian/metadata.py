"""
福建 school 元数据推断（Phase 14）。

仅普通类入库；艺体类标记 skipped_unsupported_category。
"""

from __future__ import annotations

from normalizers.admission_category import normalize_admission_category
from normalizers.school_batch import normalize_school_batch

FUJIAN_ART_MARKERS: tuple[str, ...] = (
    "音乐类",
    "美术与设计类",
    "舞蹈类",
    "播音与主持类",
    "表(导)演类",
    "书法类",
    "戏曲类",
)

IMPORTABLE_ADMISSION_CATEGORIES = frozenset({"普通类"})


def infer_fujian_admission_category(title: str) -> str | None:
    """从附件名 / 标题识别招生类别。"""
    text = title or ""
    if "普通类" in text:
        return "普通类"
    if "体育类" in text or ("体育" in text and "普通类" not in text):
        return "体育类"
    for marker in FUJIAN_ART_MARKERS:
        if marker in text:
            return "艺术类"
    if "艺术类" in text or "艺术" in text:
        return "艺术类"
    return None


def infer_fujian_subject_type(title: str) -> str | None:
    """历史科目组 / 物理科目组 → 历史类 / 物理类。"""
    text = title or ""
    if "物理科目组" in text or ("物理" in text and "历史" not in text):
        return "物理类"
    if "历史科目组" in text or "历史" in text:
        return "历史类"
    return None


def infer_fujian_batch(title: str, source_title: str | None = None) -> str:
    text = " ".join(t for t in (source_title or "", title or "") if t)
    if any(kw in text for kw in ("高职专科批", "高职（专科）批", "高职(专科)批")):
        return "专科批"
    if "专科批" in text and "本科批" not in text:
        return "专科批"
    if "专科" in text and "本科" not in text:
        return "专科批"
    if "本科批" in text or "本科" in text:
        return "本科批"
    return "本科批"


def infer_fujian_school_metadata(
    title: str,
    source_title: str | None = None,
) -> dict[str, str]:
    """推断福建 school 的 admission_category 与 batch。"""
    from crawlers.discovery import infer_school_metadata_from_title

    primary = title or ""
    category = infer_fujian_admission_category(primary)
    if category is None and source_title:
        category = infer_fujian_admission_category(source_title)
    if category is None:
        fallback = infer_school_metadata_from_title(primary, source_title=source_title)
        category = fallback["admission_category"]
    else:
        category = normalize_admission_category(category) or category

    batch = normalize_school_batch(
        infer_fujian_batch(primary, source_title=source_title)
    ) or "本科批"
    return {
        "admission_category": category,
        "batch": batch,
    }


def is_fujian_importable_category(admission_category: str | None) -> bool:
    return (admission_category or "") in IMPORTABLE_ADMISSION_CATEGORIES
