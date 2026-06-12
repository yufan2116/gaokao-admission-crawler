"""
广东 school 招生类别与批次推断（Phase 13.1）。

从 PDF 文件名 / 公告标题识别 admission_category；当前阶段仅普通类入库。
"""

from __future__ import annotations

from normalizers.admission_category import normalize_admission_category
from normalizers.school_batch import normalize_school_batch

# 艺术类细分文件名标记 → 统一 admission_category=艺术类
GUANGDONG_ART_TYPE_MARKERS: tuple[str, ...] = (
    "音乐类",
    "美术与设计类",
    "舞蹈类",
    "播音与主持类",
    "表(导)演类",
    "书法类",
    "戏曲类",
)

IMPORTABLE_ADMISSION_CATEGORIES = frozenset({"普通类"})


def infer_guangdong_admission_category(title: str) -> str | None:
    """
    从附件名 / 标题识别招生类别。

    普通类 → 普通类；体育类 → 体育类；艺体细分 → 艺术类。
    无法识别时返回 None。
    """
    text = title or ""
    if "普通类" in text:
        return "普通类"
    if "体育类" in text:
        return "体育类"
    for marker in GUANGDONG_ART_TYPE_MARKERS:
        if marker in text:
            return "艺术类"
    if "艺术类" in text:
        return "艺术类"
    return None


def infer_guangdong_school_metadata(
    title: str,
    source_title: str | None = None,
) -> dict[str, str]:
    """推断广东 school 的 admission_category 与 batch。"""
    from crawlers.discovery import infer_school_metadata_from_title

    primary = title or ""
    category = infer_guangdong_admission_category(primary)
    if category is None and source_title:
        category = infer_guangdong_admission_category(source_title)
    if category is None:
        fallback = infer_school_metadata_from_title(primary, source_title=source_title)
        category = fallback["admission_category"]
    else:
        category = normalize_admission_category(category) or category

    batch_meta = infer_school_metadata_from_title(primary, source_title=source_title)
    return {
        "admission_category": category,
        "batch": normalize_school_batch(batch_meta["batch"]) or "本科批",
    }


def is_guangdong_importable_category(admission_category: str | None) -> bool:
    """当前阶段是否允许入库（仅普通类）。"""
    return (admission_category or "") in IMPORTABLE_ADMISSION_CATEGORIES
