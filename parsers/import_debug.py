"""
导入失败时的 parser 调试输出（Phase 7.4）。
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

from config import BASE_DIR, CLEANED_DIR
from normalizers import normalize_dataframe
from parsers.parse_excel import (
    detect_header_row,
    list_excel_sheet_names,
    parse_excel,
    parse_excel_all_sheets,
    _read_raw_sheet,
)
from parsers.parse_html_tables import parse_html_tables

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
HTML_EXTENSIONS = {".html", ".htm"}


def _parse_for_debug(
    path: Path,
    record_type: str,
    default_year: int | None,
    default_province: str,
    subject_type: str | None,
) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in EXCEL_EXTENSIONS:
        if record_type in ("rank", "control"):
            return parse_excel_all_sheets(
                path, record_type, default_year, default_province, subject_type
            )
        return parse_excel(
            path, record_type, default_year=default_year,
            default_province=default_province, subject_type_hint=subject_type,
        )
    if ext in HTML_EXTENSIONS:
        return parse_html_tables(
            path, record_type, default_year, default_province, subject_type
        )
    raise ValueError(f"unsupported: {ext}")

logger = logging.getLogger(__name__)

DEBUG_DIR = CLEANED_DIR / "debug"


def _safe_debug_name(path: Path) -> str:
    stem = path.stem.replace(" ", "_")
    for ch in '<>:"/\\|?*':
        stem = stem.replace(ch, "_")
    return stem[:80] or "unknown"


def _excel_raw_preview(path: Path, max_rows: int = 30) -> tuple[pd.DataFrame, int, str]:
    """返回首个有效 sheet 的原始预览与 header_row。"""
    sheet_names = list_excel_sheet_names(path)
    sheet_name = sheet_names[0] if sheet_names else 0
    df_raw = _read_raw_sheet(path, sheet_name)
    header_row = detect_header_row(df_raw)
    preview = df_raw.iloc[: max_rows + header_row + 1]
    return preview, header_row, str(sheet_name)


def _html_raw_preview(path: Path, max_rows: int = 30) -> tuple[pd.DataFrame, int, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[:max_rows]
    preview = pd.DataFrame({"line_no": range(1, len(lines) + 1), "content": lines})
    return preview, 0, "html_text"


def write_import_debug_preview(
    file_path: str | Path,
    record_type: str,
    default_year: int | None = None,
    default_province: str = "江苏",
    subject_type: str | None = None,
    error_message: str | None = None,
) -> Path | None:
    """
    生成 debug CSV：元数据 + 原始预览 + 标准化前后列名。

    保存至 data/cleaned/debug/{文件名}_preview.csv
    """
    path = Path(file_path)
    if not path.exists():
        return None

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DEBUG_DIR / f"{_safe_debug_name(path)}_preview.csv"

    parsed_cols: list[str] = []
    normalized_cols: list[str] = []
    header_row = -1
    sheet_label = ""
    raw_preview = pd.DataFrame()

    try:
        ext = path.suffix.lower()
        if ext in EXCEL_EXTENSIONS:
            raw_preview, header_row, sheet_label = _excel_raw_preview(path)
        elif ext in HTML_EXTENSIONS:
            raw_preview, header_row, sheet_label = _html_raw_preview(path)
        else:
            raw_preview = pd.DataFrame({"note": [f"unsupported ext: {ext}"]})

        try:
            parsed_df = _parse_for_debug(
                path, record_type, default_year, default_province, subject_type
            )
            parsed_cols = list(parsed_df.columns)
            normalized_df = normalize_dataframe(
                parsed_df,
                data_type=record_type,
                year=default_year,
                province=default_province,
                subject_type=subject_type,
            )
            normalized_cols = list(normalized_df.columns)
        except Exception as parse_exc:
            parsed_cols = [f"(parse failed: {parse_exc})"]
            normalized_cols = []
    except Exception as exc:
        raw_preview = pd.DataFrame({"error": [str(exc)]})

    try:
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["section", "key", "value"])
            writer.writerow(["meta", "file_path", str(path.relative_to(BASE_DIR))])
            writer.writerow(["meta", "record_type", record_type])
            writer.writerow(["meta", "sheet", sheet_label])
            writer.writerow(["meta", "header_row", header_row])
            writer.writerow(["meta", "error_message", error_message or ""])
            writer.writerow(["meta", "parsed_columns", "|".join(parsed_cols)])
            writer.writerow(["meta", "normalized_columns", "|".join(normalized_cols)])
            writer.writerow([])
            writer.writerow(["--- raw preview (first 30 rows) ---"])
            if not raw_preview.empty:
                raw_preview.to_csv(f, index=False)
        logger.info("已生成导入调试文件: %s", out_path)
        return out_path
    except OSError as exc:
        logger.warning("写入调试文件失败: %s", exc)
        return None
