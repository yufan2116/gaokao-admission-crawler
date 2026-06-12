"""
科类推断：CLI 参数 > 文件名 > Excel 内容。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from typing import Any

from normalizers.subject_type import normalize_subject_type


def infer_subject_from_filename(stem: str, *, subject_mode: Any = None) -> str | None:
    """从文件名推断科类。"""
    return _infer_subject_type_from_text(stem, subject_mode=subject_mode)


def _infer_subject_type_from_text(
    text: str,
    *,
    subject_mode: Any = None,
) -> str | None:
    if not text:
        return None
    if subject_mode is not None and str(subject_mode) == "legacy":
        if "文科" in text:
            return "文科"
        if "理科" in text:
            return "理科"
        return None
    if "历史" in text or "文科" in text:
        return "历史类"
    if "物理" in text or "理科" in text:
        return "物理类"
    return None


def infer_subject_from_dataframe(df: pd.DataFrame) -> str | None:
    """从 Excel 内容推断科类（subject_type 列众数）。"""
    if "subject_type" not in df.columns:
        return None
    values = df["subject_type"].dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return None
    mode_val = values.mode()
    if mode_val.empty:
        return None
    normalized = normalize_subject_type(mode_val.iloc[0])
    return normalized or None


def resolve_subject_type(
    subject_type_hint: str | None,
    path: Path,
    sheet_name: str | int,
    df: pd.DataFrame,
    *,
    prefer_sheet: bool = False,
    subject_mode: Any = None,
) -> str | None:
    """
    解析科类。

    prefer_sheet=False（默认）：CLI > 文件名 > Excel 内容 > sheet 名
    prefer_sheet=True（rank 多 sheet）：sheet 名 > 文件名 > CLI > Excel 内容
    """
    if prefer_sheet:
        if isinstance(sheet_name, str):
            from_sheet = _infer_subject_type_from_text(sheet_name, subject_mode=subject_mode)
            if from_sheet:
                return from_sheet
        from_filename = infer_subject_from_filename(path.stem, subject_mode=subject_mode)
        if from_filename:
            return from_filename
        if subject_type_hint and str(subject_type_hint).strip():
            return normalize_subject_type(subject_type_hint, subject_mode=subject_mode)
        from_df = infer_subject_from_dataframe(df)
        if from_df:
            return from_df
        return None

    if subject_type_hint and str(subject_type_hint).strip():
        return normalize_subject_type(subject_type_hint, subject_mode=subject_mode)

    from_filename = infer_subject_from_filename(path.stem, subject_mode=subject_mode)
    if from_filename:
        return from_filename

    from_df = infer_subject_from_dataframe(df)
    if from_df:
        return from_df

    if isinstance(sheet_name, str):
        from_sheet = _infer_subject_type_from_text(sheet_name, subject_mode=subject_mode)
        if from_sheet:
            return from_sheet

    return None
