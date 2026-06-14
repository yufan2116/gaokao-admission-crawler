"""
通用文件导入：按扩展名选择 parser（Excel / HTML）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from importers.excel_import import ImportStats, RECORD_TYPES
from importers.pipeline import enriched_rows_for_db, run_parsed_pipeline
from parsers.import_debug import write_import_debug_preview
from parsers.parse_doc import is_image_based_doc
from parsers.parse_excel import parse_excel, parse_excel_all_sheets
from parsers.parse_html_tables import parse_html_tables
from parsers.parse_pdf_tables import parse_pdf_tables
from parsers.parse_image_table import (
    OCR_SOURCE_PREFIX,
    is_image_table_file,
    parse_image_table,
)

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
HTML_EXTENSIONS = {".html", ".htm"}
DOC_EXTENSIONS = {".doc"}
ARCHIVE_EXTENSIONS = {".rar"}
UNSUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
PDF_EXTENSIONS = {".pdf"}


class UnsupportedImportFormatError(Exception):
    """不支持的导入格式（如 PDF/图片）。"""


def _parse_file_to_dataframe(
    path: Path,
    record_type: str,
    default_year: int | None,
    default_province: str,
    subject_type: str | None,
    subject_mode: object | None = None,
) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in DOC_EXTENSIONS:
        if is_image_based_doc(path):
            raise UnsupportedImportFormatError(
                "图片型 Word .doc 暂不支持导入（河南公开 RAR 常见格式，不做 OCR）"
            )
        raise UnsupportedImportFormatError(f"暂不支持导入: {ext}")
    if ext in ARCHIVE_EXTENSIONS:
        raise UnsupportedImportFormatError(f"压缩包请解压后再导入: {ext}")
    if ext in EXCEL_EXTENSIONS:
        if record_type in ("rank", "control"):
            return parse_excel_all_sheets(
                path,
                data_type=record_type,
                default_year=default_year,
                default_province=default_province,
                subject_type_hint=subject_type,
            )
        return parse_excel(
            path,
            data_type=record_type,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type,
            subject_mode=subject_mode,
        )
    if ext in HTML_EXTENSIONS:
        if record_type not in ("control", "rank"):
            raise ValueError(f"HTML 导入暂仅支持 control/rank，当前 type={record_type}")
        return parse_html_tables(
            path,
            data_type=record_type,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type,
        )
    if ext in PDF_EXTENSIONS:
        if record_type not in ("school", "control", "rank"):
            raise ValueError(f"PDF 导入暂仅支持 school/control/rank，当前 type={record_type}")
        pdf_result = parse_pdf_tables(
            path,
            data_type=record_type,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type,
            subject_mode=subject_mode,
        )
        if not pdf_result.ok:
            raise UnsupportedImportFormatError(
                f"PDF 表格不可机器读取: {pdf_result.status}（{pdf_result.message}）"
            )
        return pdf_result.df
    if ext in UNSUPPORTED_EXTENSIONS:
        raise UnsupportedImportFormatError(
            f"图片导入需要 --enable-ocr（实验功能）: {ext}"
        )
    raise ValueError(f"未知文件类型: {ext}")


def import_image_with_ocr_to_db(
    session,
    file_path: str | Path,
    record_type: str,
    *,
    default_year: int | None = None,
    default_province: str = "江苏",
    subject_type: str | None = None,
    batch: str | None = None,
    page_title: str | None = None,
    subject_mode: object | None = None,
    write_debug_on_failure: bool = True,
    ocr_engine: str = "paddle",
    use_ocr_cache: bool = True,
) -> ImportStats:
    """实验性 OCR 图片导入：parse_image_table → normalize → validate → 入库。"""
    from db.repository import insert_school_admission_lines

    if record_type != "school":
        raise UnsupportedImportFormatError("OCR 图片导入暂仅支持 school")

    path = Path(file_path)
    result = parse_image_table(
        path,
        data_type=record_type,
        province=default_province,
        year=default_year or 0,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=use_ocr_cache,
        ocr_engine=ocr_engine,
    )
    stats = ImportStats()
    if result.status == "ocr_not_installed":
        raise UnsupportedImportFormatError(
            "PaddleOCR 未安装。可选安装: pip install paddleocr paddlepaddle"
        )
    if result.status == "rapidocr_not_installed":
        raise UnsupportedImportFormatError(
            "RapidOCR 未安装。可选安装: pip install rapidocr-onnxruntime"
        )
    if result.status != "parsed":
        msg = result.message or result.status
        if write_debug_on_failure:
            write_import_debug_preview(
                path,
                record_type,
                default_year,
                default_province,
                subject_type,
                error_message=msg,
            )
        logger.warning("OCR 解析未成功 [%s]: %s", path.name, msg)
        stats.failed = 1
        stats.errors.append(msg)
        return stats

    pipeline = run_parsed_pipeline(
        result.df,
        data_type=record_type,
        year=default_year,
        province=default_province,
        subject_type=subject_type,
        source_path=path,
        batch=batch,
        subject_mode=subject_mode,
    )
    stats.validation_failed = pipeline.validation.failed_count
    stats.failed = pipeline.validation.failed_count
    stats.errors.extend(pipeline.validation.errors)

    valid_df = pipeline.valid_df
    if valid_df.empty:
        msg = result.message or "OCR 校验后无有效行"
        stats.errors.append(msg)
        return stats

    source_url = f"{OCR_SOURCE_PREFIX}{path.resolve()}"
    valid_rows = enriched_rows_for_db(valid_df, record_type, source_url)
    insert_result = insert_school_admission_lines(session, valid_rows)
    stats.inserted = insert_result.inserted
    stats.skipped = insert_result.skipped
    stats.failed += insert_result.failed
    stats.errors.extend(insert_result.errors)
    logger.info(
        "OCR 导入完成 [%s]: inserted=%d ocr_raw=%s",
        path.name,
        stats.inserted,
        result.raw_ocr_json_path,
    )
    return stats


def import_file_to_db(
    session,
    file_path: str | Path,
    record_type: str,
    default_year: int | None = None,
    default_province: str = "江苏",
    subject_type: str | None = None,
    admission_category: str | None = None,
    batch: str | None = None,
    subject_mode: object | None = None,
    *,
    write_debug_on_failure: bool = True,
) -> ImportStats:
    """根据扩展名 parse → normalize → validate → 入库。"""
    from db.repository import (
        insert_major_admission_lines,
        insert_province_control_lines,
        insert_school_admission_lines,
        insert_score_rank_rows,
    )

    if record_type not in RECORD_TYPES:
        raise ValueError(f"不支持的 type: {record_type}")

    path = Path(file_path)
    source_url = str(path.resolve()) if path.exists() else None

    def _maybe_debug(msg: str) -> None:
        if write_debug_on_failure:
            write_import_debug_preview(
                path,
                record_type,
                default_year,
                default_province,
                subject_type,
                error_message=msg,
            )

    try:
        parsed_df = _parse_file_to_dataframe(
            path, record_type, default_year, default_province, subject_type, subject_mode
        )
    except UnsupportedImportFormatError:
        raise
    except Exception as exc:
        _maybe_debug(str(exc))
        raise

    pipeline = run_parsed_pipeline(
        parsed_df,
        data_type=record_type,
        year=default_year,
        province=default_province,
        subject_type=subject_type,
        source_path=path,
        admission_category=admission_category,
        batch=batch,
        subject_mode=subject_mode,
    )

    stats = ImportStats()
    stats.validation_failed = pipeline.validation.failed_count
    stats.failed = pipeline.validation.failed_count
    stats.errors.extend(pipeline.validation.errors)

    valid_df = pipeline.valid_df
    if valid_df.empty:
        msg = "校验后无有效行可入库"
        if stats.errors:
            msg = "; ".join(stats.errors[:5])
        _maybe_debug(msg)
        logger.warning("校验后无有效行可入库: %s", path)
        return stats

    valid_rows = enriched_rows_for_db(valid_df, record_type, source_url)
    inserters = {
        "control": insert_province_control_lines,
        "school": insert_school_admission_lines,
        "major": insert_major_admission_lines,
        "rank": insert_score_rank_rows,
    }
    insert_result = inserters[record_type](session, valid_rows)

    stats.inserted = insert_result.inserted
    stats.skipped = insert_result.skipped
    stats.failed += insert_result.failed
    stats.errors.extend(insert_result.errors)
    return stats


def is_importable_file(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in DOC_EXTENSIONS and is_image_based_doc(path):
        return False
    return ext in EXCEL_EXTENSIONS or ext in HTML_EXTENSIONS or ext in PDF_EXTENSIONS


def is_download_only_file(path: Path) -> bool:
    return path.suffix.lower() in UNSUPPORTED_EXTENSIONS
