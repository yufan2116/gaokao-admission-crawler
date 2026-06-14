"""省份 metadata 模块动态加载（Phase 18）。"""

from __future__ import annotations

import importlib
from typing import Any

IMPORTABLE_ADMISSION_CATEGORIES = frozenset({"普通类"})


def load_metadata_module(slug: str) -> Any | None:
    try:
        return importlib.import_module(f"provinces.{slug}.metadata")
    except ModuleNotFoundError:
        return None


def infer_subject_type_for_slug(slug: str, title: str) -> str | None:
    mod = load_metadata_module(slug)
    if mod is None:
        return None
    fn = getattr(mod, "infer_subject_type", None)
    if callable(fn):
        return fn(title)
    for name in dir(mod):
        if name.startswith("infer_") and name.endswith("_subject_type"):
            candidate = getattr(mod, name)
            if callable(candidate):
                return candidate(title)
    return None


def infer_school_metadata_for_slug(
    slug: str,
    title: str,
    *,
    source_title: str | None = None,
) -> dict[str, str] | None:
    mod = load_metadata_module(slug)
    if mod is None:
        return None
    fn = getattr(mod, "infer_school_metadata", None)
    if not callable(fn):
        fn = getattr(mod, f"infer_{slug}_school_metadata", None)
    if callable(fn):
        return fn(title, source_title=source_title)
    infer_category = getattr(mod, "infer_admission_category", None)
    infer_batch_fn = getattr(mod, "infer_batch", None)
    if not callable(infer_category) or not callable(infer_batch_fn):
        return None
    from normalizers.admission_category import normalize_admission_category
    from normalizers.school_batch import normalize_school_batch

    category = infer_category(title) or (
        infer_category(source_title) if source_title else None
    )
    batch = normalize_school_batch(infer_batch_fn(title, source_title=source_title)) or "本科批"
    if category:
        category = normalize_admission_category(category) or category
    return {"admission_category": category or "普通类", "batch": batch}


def is_importable_category_for_slug(slug: str, admission_category: str | None) -> bool:
    mod = load_metadata_module(slug)
    if mod is None:
        return True
    fn = getattr(mod, "is_importable_category", None)
    if callable(fn):
        return fn(admission_category)
    prefixed = getattr(mod, f"is_{slug}_importable_category", None)
    if callable(prefixed):
        return prefixed(admission_category)
    return (admission_category or "") in IMPORTABLE_ADMISSION_CATEGORIES
