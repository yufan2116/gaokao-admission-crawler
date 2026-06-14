"""
OCR 质量门禁（Phase 20.1 / 20.4 / 20.5）。

单张/批量审计不入库；批量 discover-download-import OCR 需审计通过标记。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import CLEANED_DIR
from importers.pipeline import run_parsed_pipeline
from normalizers.school_name import is_invalid_school_name
from parsers.image_sort import list_image_files
from parsers.parse_image_table import (
    OCR_PREVIEW_DIR,
    HUBEI_HEADER_MARKERS,
    _cluster_rows,
    parse_image_table,
)
from province_registry import get_province_plugin
from validators.image_verify import (
    CORRUPTED_IMAGE_STATUS,
    corrupted_audit_item,
    is_corrupted_image,
    is_image_corruption_error,
    verify_image_file,
)

logger = logging.getLogger(__name__)

OCR_AUDIT_PASS_RATIO = 0.80
MIN_SCORE_LOW = 100.0
MIN_SCORE_HIGH = 750.0
EMPTY_FIELD_RATE_THRESHOLD = 0.20
KEY_FIELD_MIN_NON_NULL_RATE = 0.80
MIN_PARSED_ROWS = 5
HUBEI_COLUMN_TOLERANCE = (4, 6)
INVALID_SCHOOL_NAME_RATE_THRESHOLD = 0.20

SCHOOL_KEY_FIELDS = ("school_name", "major_group", "min_score")
AUDIT_SAMPLE_COLUMNS = ("school_code", "school_name", "major_group", "min_score", "notes")


def ocr_batch_audit_report_path(province_slug: str, year: int, data_type: str) -> Path:
    return CLEANED_DIR / f"ocr_batch_audit_{province_slug}_{year}_{data_type}.json"


def ocr_audit_pass_flag_path(province_slug: str, year: int, data_type: str) -> Path:
    return CLEANED_DIR / f"ocr_audit_pass_{province_slug}_{year}_{data_type}.flag"


def preview_csv_path_for_image(image_path: Path) -> Path:
    return OCR_PREVIEW_DIR / f"{image_path.stem}.csv"


def _null_rate(series: pd.Series) -> float:
    if series.empty:
        return 1.0
    empty = series.isna() | (series.astype(str).str.strip() == "")
    return float(empty.sum()) / len(series)


def _non_null_rate(series: pd.Series) -> float:
    return 1.0 - _null_rate(series)


def _school_name_invalid_rate(series: pd.Series) -> float:
    non_empty = series.dropna().astype(str).str.strip()
    non_empty = non_empty[non_empty != ""]
    if non_empty.empty:
        return 0.0
    invalid = sum(1 for v in non_empty if is_invalid_school_name(v))
    return float(invalid) / len(non_empty)


def _min_score_range(df: pd.DataFrame) -> tuple[float | None, float | None]:
    if df.empty or "min_score" not in df.columns:
        return None, None
    scores = pd.to_numeric(df["min_score"], errors="coerce").dropna()
    if scores.empty:
        return None, None
    return float(scores.min()), float(scores.max())


def detect_raw_column_count_irregular(
    ocr_items: list[dict[str, Any]],
    *,
    province: str,
) -> bool:
    """原始 OCR 行内单元格数量是否偏离湖北表格预期（仅作 warning，不作 suspicious）。"""
    if not ocr_items:
        return True
    if province != "湖北":
        return False

    rows = _cluster_rows(ocr_items)
    col_counts: list[int] = []
    for row in rows:
        text = " ".join(cell["text"] for cell in row)
        if any(marker in text for marker in HUBEI_HEADER_MARKERS):
            continue
        if "湖北省" in text and "投档" in text:
            continue
        if any(kw in text for kw in ("说明", "备注：", "合计", "单位：", "末位投档")):
            continue
        if len(row) >= 3:
            col_counts.append(len(row))

    if not col_counts:
        return True

    lo, hi = HUBEI_COLUMN_TOLERANCE
    bad = sum(1 for c in col_counts if c < lo or c > hi)
    return bad / len(col_counts) > 0.30


def school_key_fields_complete(
    df: pd.DataFrame,
    *,
    threshold: float = KEY_FIELD_MIN_NON_NULL_RATE,
) -> bool:
    """school 关键字段非空率是否均达标。"""
    if df.empty:
        return False
    for field in SCHOOL_KEY_FIELDS:
        if field not in df.columns:
            return False
        if _non_null_rate(df[field]) < threshold:
            return False
    return True


def compute_field_quality(df: pd.DataFrame, *, data_type: str) -> dict[str, Any]:
    """normalize/validate 后关键字段质量摘要。"""
    quality: dict[str, Any] = {}
    if data_type != "school" or df.empty:
        return quality
    for field in SCHOOL_KEY_FIELDS:
        if field in df.columns:
            quality[f"{field}_non_null_rate"] = round(_non_null_rate(df[field]), 4)
        else:
            quality[f"{field}_non_null_rate"] = 0.0
    if "school_name" in df.columns:
        quality["school_name_invalid_rate"] = round(_school_name_invalid_rate(df["school_name"]), 4)
    lo, hi = _min_score_range(df)
    quality["min_score_min"] = lo
    quality["min_score_max"] = hi
    return quality


def compute_warnings(
    *,
    ocr_items: list[dict[str, Any]] | None,
    province: str,
) -> list[str]:
    warnings: list[str] = []
    if ocr_items is not None and detect_raw_column_count_irregular(ocr_items, province=province):
        warnings.append("raw_column_count_irregular")
    return warnings


def compute_suspicious_flags(
    *,
    ocr_status: str,
    parsed_rows: int,
    valid_rows: int,
    normalized_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    data_type: str = "school",
    province: str = "",
) -> list[str]:
    flags: list[str] = []

    if ocr_status not in ("parsed",):
        flags.append(f"ocr_status_{ocr_status}")

    if parsed_rows < MIN_PARSED_ROWS:
        flags.append("too_few_parsed_rows")

    if valid_rows == 0:
        flags.append("no_valid_rows")

    score_df = valid_df if not valid_df.empty else normalized_df
    lo, hi = _min_score_range(score_df)
    if lo is not None and hi is not None:
        if lo < MIN_SCORE_LOW or hi > MIN_SCORE_HIGH:
            flags.append("min_score_out_of_range")

    ref_df = valid_df if not valid_df.empty else normalized_df
    if not ref_df.empty:
        if "school_name" in ref_df.columns:
            if _null_rate(ref_df["school_name"]) > EMPTY_FIELD_RATE_THRESHOLD:
                flags.append("high_school_name_null_rate")
            if _school_name_invalid_rate(ref_df["school_name"]) > INVALID_SCHOOL_NAME_RATE_THRESHOLD:
                flags.append("invalid_school_name_pattern")
        if "major_group" in ref_df.columns:
            if _null_rate(ref_df["major_group"]) > EMPTY_FIELD_RATE_THRESHOLD:
                flags.append("high_major_group_null_rate")

    if data_type == "school":
        key_df = valid_df if not valid_df.empty else normalized_df
        if not school_key_fields_complete(key_df):
            flags.append("column_count_anomaly")

    return flags


def _load_ocr_items(raw_json_path: str | None) -> list[dict[str, Any]] | None:
    if not raw_json_path:
        return None
    path = Path(raw_json_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def _audit_sample_rows(
    valid_df: pd.DataFrame,
    parsed_df: pd.DataFrame,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """入库前样本行（normalize + validate 后）。"""
    if valid_df.empty:
        return []
    rows: list[dict[str, Any]] = []
    valid_reset = valid_df.reset_index(drop=True)
    parsed_reset = parsed_df.reset_index(drop=True) if not parsed_df.empty else parsed_df
    for pos in range(min(len(valid_reset), limit)):
        row = valid_reset.iloc[pos]
        record: dict[str, Any] = {}
        for col in AUDIT_SAMPLE_COLUMNS:
            val = row[col] if col in valid_reset.columns else None
            if (val is None or (isinstance(val, float) and pd.isna(val))) and not parsed_reset.empty:
                if col in parsed_reset.columns and pos < len(parsed_reset):
                    val = parsed_reset.iloc[pos][col]
            record[col] = None if val is None or (isinstance(val, float) and pd.isna(val)) else val
        rows.append(record)
    return rows


def audit_from_parse_result(
    path: Path,
    parse_result: Any,
    *,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None = None,
    batch: str | None = None,
    subject_mode: Any = None,
) -> dict[str, Any]:
    """对已有 parse_result 做 normalize + validate 审计（不入库）。"""
    parsed_rows = len(parse_result.df)
    normalized_df = pd.DataFrame()
    valid_df = pd.DataFrame()
    invalid_rows = 0

    if parse_result.status == "parsed" and not parse_result.df.empty:
        pipeline = run_parsed_pipeline(
            parse_result.df,
            data_type=data_type,
            year=year,
            province=province,
            subject_type=subject_type,
            source_path=path,
            batch=batch,
            subject_mode=subject_mode,
        )
        normalized_df = pipeline.normalized_df
        valid_df = pipeline.valid_df
        invalid_rows = pipeline.validation.failed_count
    elif parse_result.status == "parsed":
        invalid_rows = 0

    ocr_items = _load_ocr_items(parse_result.raw_ocr_json_path)
    quality_df = valid_df if not valid_df.empty else normalized_df
    field_quality = compute_field_quality(quality_df, data_type=data_type)
    warnings = compute_warnings(ocr_items=ocr_items, province=province)
    suspicious = compute_suspicious_flags(
        ocr_status=parse_result.status,
        parsed_rows=parsed_rows,
        valid_rows=len(valid_df),
        normalized_df=normalized_df,
        valid_df=valid_df,
        data_type=data_type,
        province=province,
    )

    score_lo = field_quality.get("min_score_min")
    score_hi = field_quality.get("min_score_max")

    return {
        "filename": path.name,
        "ocr_status": parse_result.status,
        "parsed_rows": parsed_rows,
        "valid_rows": len(valid_df),
        "invalid_rows": invalid_rows,
        "min_score_min": score_lo,
        "min_score_max": score_hi,
        "min_score_range": [score_lo, score_hi],
        "field_quality": field_quality,
        "warnings": warnings,
        "sample_rows": _audit_sample_rows(valid_df, parse_result.df),
        "preview_csv_path": str(preview_csv_path_for_image(path))
        if preview_csv_path_for_image(path).exists()
        else None,
        "raw_json_path": parse_result.raw_ocr_json_path,
        "suspicious_flags": suspicious,
        "message": parse_result.message or "",
        "hybrid": getattr(parse_result, "hybrid", None),
    }


def _is_corrupted_audit_result(result: dict[str, Any]) -> bool:
    return bool(result.get("corrupted")) or result.get("ocr_status") == CORRUPTED_IMAGE_STATUS


def _enrich_corrupted_source(result: dict[str, Any], path: Path, province_slug: str, year: int, data_type: str) -> None:
    from validators.image_verify import _discovery_download_index

    src = _discovery_download_index(province_slug, year, data_type).get(path.name)
    if src:
        result["source_url"] = src.get("source_url")
        result["page_url"] = src.get("page_url")
        result["redownload_hint"] = {
            "source_url": src.get("source_url"),
            "page_url": src.get("page_url"),
            "local_path": result.get("local_path") or str(path.resolve()),
        }


def audit_ocr_image(
    image_path: str | Path,
    *,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None = None,
    batch: str | None = None,
    page_title: str | None = None,
    subject_mode: Any = None,
    ocr_engine: str = "paddle",
    use_ocr_cache: bool = True,
    allow_slow_paddle_fallback: bool = False,
) -> dict[str, Any]:
    """OCR + normalize + validate，不入库。"""
    path = Path(image_path)
    verify = verify_image_file(path)
    if verify.get("corrupted"):
        return corrupted_audit_item(
            path,
            error=verify.get("error"),
            truncated=verify.get("truncated"),
        )

    parse_result = parse_image_table(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        ocr_engine=ocr_engine,
        use_ocr_cache=use_ocr_cache,
        allow_slow_paddle_fallback=allow_slow_paddle_fallback,
    )

    result = audit_from_parse_result(
        path,
        parse_result,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        subject_mode=subject_mode,
    )
    if parse_result.hybrid is not None:
        result["hybrid"] = parse_result.hybrid
    return result


def _iter_image_files(directory: Path) -> list[Path]:
    return list_image_files(directory)


def run_ocr_batch_audit(
    directory: str | Path,
    *,
    province: str,
    year: int,
    data_type: str = "school",
    subject_type: str | None = None,
    batch: str | None = None,
    limit: int | None = None,
    subject_mode: Any = None,
    ocr_engine: str = "paddle",
    use_ocr_cache: bool = True,
    allow_slow_paddle_fallback: bool = False,
) -> dict[str, Any]:
    """批量抽样 OCR 审计，不入库；达标时写入 pass flag。"""
    from parsers.ocr_engine import is_hybrid_engine_mode

    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"目录不存在: {dir_path}")

    plugin = get_province_plugin(province)
    province_norm = plugin.province_name
    province_slug = plugin.province_slug

    images = _iter_image_files(dir_path)
    if limit is not None and limit > 0:
        images = images[:limit]

    results: list[dict[str, Any]] = []
    for img in images:
        logger.info("OCR 审计 [%s]", img.name)
        if is_corrupted_image(img):
            verify = verify_image_file(img)
            item = corrupted_audit_item(
                img,
                error=verify.get("error"),
                truncated=verify.get("truncated"),
            )
            _enrich_corrupted_source(item, img, province_slug, year, data_type)
            results.append(item)
            continue
        try:
            item = audit_ocr_image(
                img,
                data_type=data_type,
                province=province_norm,
                year=year,
                subject_type=subject_type,
                batch=batch,
                subject_mode=subject_mode,
                ocr_engine=ocr_engine,
                use_ocr_cache=use_ocr_cache,
                allow_slow_paddle_fallback=allow_slow_paddle_fallback,
            )
            results.append(item)
        except Exception as exc:
            if is_image_corruption_error(exc):
                logger.warning("OCR 审计跳过损坏图片 [%s]: %s", img.name, exc)
                item = corrupted_audit_item(img, error=str(exc), truncated="truncat" in str(exc).lower())
                _enrich_corrupted_source(item, img, province_slug, year, data_type)
            else:
                logger.exception("OCR 审计失败 [%s]: %s", img.name, exc)
                item = {
                    "filename": img.name,
                    "ocr_status": "audit_error",
                    "parsed_rows": 0,
                    "valid_rows": 0,
                    "invalid_rows": 0,
                    "min_score_min": None,
                    "min_score_max": None,
                    "field_quality": {},
                    "warnings": [],
                    "suspicious_flags": ["audit_error"],
                    "message": str(exc),
                }
            results.append(item)

    corrupted_count = sum(1 for r in results if _is_corrupted_audit_result(r))
    eligible = [r for r in results if not _is_corrupted_audit_result(r)]
    audited = len(results)
    audited_eligible = len(eligible)
    clean = sum(1 for r in eligible if not r.get("suspicious_flags"))
    clean_ratio = (clean / audited_eligible) if audited_eligible else 0.0
    audit_passed = audited_eligible > 0 and clean_ratio >= OCR_AUDIT_PASS_RATIO

    report_path = ocr_batch_audit_report_path(province_slug, year, data_type)
    flag_path = ocr_audit_pass_flag_path(province_slug, year, data_type)

    hybrid_summary: dict[str, Any] | None = None
    if is_hybrid_engine_mode(ocr_engine):
        hybrid_summary = {
            "rapidocr_selected": sum(
                1
                for r in results
                if (r.get("hybrid") or {}).get("engine_selected") == "rapidocr"
            ),
            "paddle_selected": sum(
                1
                for r in results
                if (r.get("hybrid") or {}).get("engine_selected") == "paddle"
            ),
            "fallback_required_but_no_cache": sum(
                1 for r in results if r.get("ocr_status") == "fallback_required_but_no_cache"
            ),
            "hybrid_failed": sum(
                1
                for r in results
                if not _is_corrupted_audit_result(r)
                and r.get("ocr_status")
                not in ("parsed", "fallback_required_but_no_cache")
            ),
        }

    report: dict[str, Any] = {
        "province": province_norm,
        "province_slug": province_slug,
        "year": year,
        "data_type": data_type,
        "directory": str(dir_path.resolve()),
        "limit": limit,
        "ocr_engine": ocr_engine,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images_audited": audited,
        "images_audited_eligible": audited_eligible,
        "corrupted_count": corrupted_count,
        "clean_images": clean,
        "clean_ratio": round(clean_ratio, 4),
        "pass_threshold": OCR_AUDIT_PASS_RATIO,
        "audit_passed": audit_passed,
        "report_path": str(report_path),
        "flag_path": str(flag_path),
        "images": results,
    }
    if hybrid_summary is not None:
        report["hybrid_summary"] = hybrid_summary

    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if audit_passed:
        flag_payload = {
            "passed_at": report["generated_at"],
            "province": province_norm,
            "province_slug": province_slug,
            "year": year,
            "data_type": data_type,
            "clean_ratio": report["clean_ratio"],
            "images_audited": audited,
            "batch_audit_report": str(report_path),
        }
        flag_path.write_text(json.dumps(flag_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("OCR 审计通过，已写入 %s", flag_path)
    else:
        logger.warning(
            "OCR 审计未通过: clean_ratio=%.1f%% (需要 >= %.0f%%)",
            clean_ratio * 100,
            OCR_AUDIT_PASS_RATIO * 100,
        )

    return report


def assert_bulk_ocr_import_allowed(
    province: str,
    years: list[int],
    data_type: str,
    *,
    enable_ocr: bool,
    ocr_require_audit_pass: bool,
) -> None:
    """discover-download-import 批量 OCR 入库前置检查。"""
    if not enable_ocr:
        return

    if not ocr_require_audit_pass:
        raise ValueError(
            "批量 OCR 入库需要同时指定 --enable-ocr 与 --ocr-require-audit-pass。"
            "请先运行抽样审计，例如:\n"
            "  python main.py ocr-batch-audit data/raw/hubei/2024/school/attachments "
            "--province 湖北 --year 2024 --subject-type 物理类 --batch 本科批 --limit 5"
        )

    plugin = get_province_plugin(province)
    slug = plugin.province_slug
    missing: list[str] = []
    for year in years:
        flag = ocr_audit_pass_flag_path(slug, year, data_type)
        if not flag.exists():
            missing.append(str(flag))

    if missing:
        raise ValueError(
            "未找到 OCR 审计通过标记，拒绝批量 OCR 入库:\n  "
            + "\n  ".join(missing)
            + "\n请先运行 ocr-batch-audit 并确保 suspicious_flags 为空比例 >= 80%"
        )


def format_single_audit_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        f"ocr_status: {result.get('ocr_status')}",
        f"parsed_rows: {result.get('parsed_rows')}",
        f"valid_rows: {result.get('valid_rows')}",
        f"invalid_rows: {result.get('invalid_rows')}",
        f"min_score_range: {result.get('min_score_range')}",
        f"field_quality: {result.get('field_quality')}",
        f"warnings: {result.get('warnings')}",
        f"preview_csv_path: {result.get('preview_csv_path')}",
        f"raw_json_path: {result.get('raw_json_path')}",
    ]
    flags = result.get("suspicious_flags") or []
    if flags:
        lines.append(f"suspicious_flags: {', '.join(flags)}")
    hybrid = result.get("hybrid")
    if hybrid:
        lines.append(f"hybrid engine_selected: {hybrid.get('engine_selected')}")
        lines.append(f"hybrid fallback_used: {hybrid.get('fallback_used')}")
        if hybrid.get("fallback_reason"):
            lines.append(f"hybrid fallback_reason: {hybrid.get('fallback_reason')}")
        lines.append(
            f"hybrid rapidocr: {hybrid.get('rapidocr_seconds')}s "
            f"valid={hybrid.get('rapidocr_valid_rows')} accepted={hybrid.get('rapidocr_accepted')}"
        )
    lines.append("sample_rows:")
    for row in result.get("sample_rows") or []:
        lines.append(f"  {row}")
    return lines


detect_column_count_anomaly = detect_raw_column_count_irregular
