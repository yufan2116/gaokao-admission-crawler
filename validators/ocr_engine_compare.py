"""
OCR 引擎质量对比（Phase 20.12）。

对同一张图分别跑 paddle / rapidocr，比较速度与结构化质量；不入库、不改库。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CLEANED_DIR
from parsers.image_sort import list_image_files
from parsers.ocr_engine import (
    load_ocr_cache,
    normalize_ocr_engine,
    ocr_engine_available,
    run_ocr_inference,
)
from parsers.parse_image_table import _prepare_image_for_ocr
from province_registry import get_province_plugin
from validators.ocr_quality_gate import (
    MIN_SCORE_HIGH,
    MIN_SCORE_LOW,
    audit_ocr_image,
)

logger = logging.getLogger(__name__)

DEFAULT_ENGINES = ("paddle", "rapidocr")
RAPIDOCR_VALID_ROW_RATIO = 0.80
RAPIDOCR_MAX_SCHOOL_NAME_INVALID_RATE = 0.05


def compare_output_path(image_path: Path) -> Path:
    return CLEANED_DIR / f"ocr_compare_{image_path.name}.json"


def batch_compare_output_path(province_slug: str, year: int, data_type: str) -> Path:
    return CLEANED_DIR / f"ocr_engine_comparison_{province_slug}_{year}_{data_type}.json"


def _paddle_cache_available(image_path: Path, *, use_ocr_cache: bool) -> bool:
    if not use_ocr_cache:
        return False
    return load_ocr_cache(image_path, "paddle") is not None


def _score_range_reasonable(lo: float | None, hi: float | None) -> bool:
    if lo is None or hi is None:
        return False
    return MIN_SCORE_LOW <= lo <= MIN_SCORE_HIGH and MIN_SCORE_LOW <= hi <= MIN_SCORE_HIGH


def _flatten_engine_result(
    engine: str,
    audit: dict[str, Any],
    *,
    ocr_seconds: float | None,
    cache_hit: bool,
    status: str | None = None,
) -> dict[str, Any]:
    field_quality = audit.get("field_quality") or {}
    return {
        "engine": engine,
        "status": status or audit.get("ocr_status") or "unknown",
        "ocr_seconds": round(ocr_seconds, 3) if ocr_seconds is not None else None,
        "cache_hit": cache_hit,
        "parsed_rows": audit.get("parsed_rows", 0),
        "valid_rows": audit.get("valid_rows", 0),
        "invalid_rows": audit.get("invalid_rows", 0),
        "school_name_non_null_rate": field_quality.get("school_name_non_null_rate"),
        "major_group_non_null_rate": field_quality.get("major_group_non_null_rate"),
        "min_score_non_null_rate": field_quality.get("min_score_non_null_rate"),
        "school_name_invalid_rate": field_quality.get("school_name_invalid_rate"),
        "min_score_min": audit.get("min_score_min"),
        "min_score_max": audit.get("min_score_max"),
        "sample_rows": audit.get("sample_rows") or [],
        "warnings": audit.get("warnings") or [],
        "suspicious_flags": audit.get("suspicious_flags") or [],
        "message": audit.get("message") or "",
    }


def _skipped_paddle_result(*, message: str) -> dict[str, Any]:
    return {
        "engine": "paddle",
        "status": "paddle_baseline_missing",
        "ocr_seconds": None,
        "cache_hit": False,
        "parsed_rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "school_name_non_null_rate": None,
        "major_group_non_null_rate": None,
        "min_score_non_null_rate": None,
        "school_name_invalid_rate": None,
        "min_score_min": None,
        "min_score_max": None,
        "sample_rows": [],
        "warnings": [],
        "suspicious_flags": ["paddle_baseline_missing"],
        "message": message,
    }


def _skipped_engine_result(engine: str, *, status: str, message: str) -> dict[str, Any]:
    return {
        "engine": engine,
        "status": status,
        "ocr_seconds": None,
        "cache_hit": False,
        "parsed_rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "school_name_non_null_rate": None,
        "major_group_non_null_rate": None,
        "min_score_non_null_rate": None,
        "school_name_invalid_rate": None,
        "min_score_min": None,
        "min_score_max": None,
        "sample_rows": [],
        "warnings": [],
        "suspicious_flags": [status],
        "message": message,
    }


def evaluate_engine_on_image(
    image_path: str | Path,
    engine: str,
    *,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None = None,
    batch: str | None = None,
    use_ocr_cache: bool = True,
    skip_slow_paddle: bool = True,
) -> dict[str, Any]:
    """单 engine：OCR + normalize + validate，返回对比指标（不入库）。"""
    path = Path(image_path)
    engine_key = normalize_ocr_engine(engine)

    if engine_key == "paddle" and skip_slow_paddle and not _paddle_cache_available(
        path, use_ocr_cache=use_ocr_cache
    ):
        return _skipped_paddle_result(
            message="Paddle 无磁盘缓存且 skip_slow_paddle=True，跳过慢速 live 推理",
        )

    if not ocr_engine_available(engine_key):
        missing = "rapidocr_not_installed" if engine_key == "rapidocr" else "ocr_not_installed"
        return _skipped_engine_result(
            engine_key,
            status=missing,
            message=f"{engine_key} 未安装或不可用",
        )

    prepared = _prepare_image_for_ocr(path)
    t0 = time.perf_counter()
    ocr_result = run_ocr_inference(
        path, prepared, use_cache=use_ocr_cache, engine=engine_key
    )
    ocr_seconds = time.perf_counter() - t0

    audit = audit_ocr_image(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        ocr_engine=engine_key,
        use_ocr_cache=use_ocr_cache,
    )
    return _flatten_engine_result(
        engine_key,
        audit,
        ocr_seconds=ocr_seconds,
        cache_hit=ocr_result.cache_hit,
    )


def _score_range_match(paddle: dict[str, Any], rapidocr: dict[str, Any]) -> bool | None:
    if paddle.get("status") == "paddle_baseline_missing":
        return None
    pl, ph = paddle.get("min_score_min"), paddle.get("min_score_max")
    rl, rh = rapidocr.get("min_score_min"), rapidocr.get("min_score_max")
    if any(v is None for v in (pl, ph, rl, rh)):
        return False
    return float(rl) <= float(ph) and float(pl) <= float(rh)


def compute_comparison(
    paddle: dict[str, Any],
    rapidocr: dict[str, Any],
) -> dict[str, Any]:
    """paddle vs rapidocr 差异指标。"""
    paddle_valid = int(paddle.get("valid_rows") or 0)
    rapid_valid = int(rapidocr.get("valid_rows") or 0)

    if paddle.get("status") == "paddle_baseline_missing":
        row_count_ratio = None
    elif paddle_valid > 0:
        row_count_ratio = round(rapid_valid / paddle_valid, 4)
    else:
        row_count_ratio = None

    score_match = _score_range_match(paddle, rapidocr)

    acceptable = False
    reasons: list[str] = []
    if paddle.get("status") == "paddle_baseline_missing":
        reasons.append("paddle_baseline_missing")
    elif paddle_valid == 0:
        reasons.append("paddle_zero_valid_rows")
    else:
        if rapid_valid < RAPIDOCR_VALID_ROW_RATIO * paddle_valid:
            reasons.append(
                f"valid_rows_ratio_low ({rapid_valid}/{paddle_valid}="
                f"{rapid_valid / paddle_valid:.2%} < {RAPIDOCR_VALID_ROW_RATIO:.0%})"
            )
        if rapidocr.get("suspicious_flags"):
            reasons.append(f"suspicious_flags={rapidocr.get('suspicious_flags')}")
        rl, rh = rapidocr.get("min_score_min"), rapidocr.get("min_score_max")
        if not _score_range_reasonable(
            float(rl) if rl is not None else None,
            float(rh) if rh is not None else None,
        ):
            reasons.append("min_score_range_unreasonable")
        invalid_rate = rapidocr.get("school_name_invalid_rate")
        if invalid_rate is not None and float(invalid_rate) >= RAPIDOCR_MAX_SCHOOL_NAME_INVALID_RATE:
            reasons.append(f"school_name_invalid_rate={invalid_rate}")

        if not reasons:
            acceptable = True

    speedup: float | None = None
    speedup_note: str | None = None
    ps = paddle.get("ocr_seconds")
    rs = rapidocr.get("ocr_seconds")
    if paddle.get("cache_hit"):
        speedup_note = "paddle_used_cache_speedup_not_comparable"
    elif ps and rs and float(rs) > 0:
        speedup = round(float(ps) / float(rs), 2)

    return {
        "row_count_ratio": row_count_ratio,
        "score_range_match": score_match,
        "rapidocr_acceptable": acceptable,
        "rapidocr_acceptable_reasons": reasons,
        "ocr_speedup_paddle_over_rapidocr": speedup,
        "ocr_speedup_note": speedup_note,
        "paddle_baseline_missing": paddle.get("status") == "paddle_baseline_missing",
    }


def compare_engines_on_image(
    image_path: str | Path,
    *,
    engines: list[str] | tuple[str, ...] = DEFAULT_ENGINES,
    data_type: str = "school",
    province: str = "湖北",
    year: int = 2024,
    subject_type: str | None = None,
    batch: str | None = None,
    use_ocr_cache: bool = True,
    skip_slow_paddle: bool = True,
) -> dict[str, Any]:
    """对单张图跑多个 engine 并生成对比报告。"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    engine_keys = [normalize_ocr_engine(e) for e in engines]
    results: dict[str, dict[str, Any]] = {}
    for engine_key in engine_keys:
        logger.info("OCR 引擎对比 [%s] engine=%s", path.name, engine_key)
        results[engine_key] = evaluate_engine_on_image(
            path,
            engine_key,
            data_type=data_type,
            province=province,
            year=year,
            subject_type=subject_type,
            batch=batch,
            use_ocr_cache=use_ocr_cache,
            skip_slow_paddle=skip_slow_paddle,
        )

    comparison: dict[str, Any] | None = None
    if "paddle" in results and "rapidocr" in results:
        comparison = compute_comparison(results["paddle"], results["rapidocr"])

    report: dict[str, Any] = {
        "filename": path.name,
        "image_path": str(path.resolve()),
        "province": province,
        "year": year,
        "data_type": data_type,
        "subject_type": subject_type,
        "batch": batch,
        "use_ocr_cache": use_ocr_cache,
        "skip_slow_paddle": skip_slow_paddle,
        "engines": engine_keys,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "comparison": comparison,
        "report_path": str(compare_output_path(path)),
    }

    out = compare_output_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _engine_success(result: dict[str, Any]) -> bool:
    status = result.get("status")
    if status in ("paddle_baseline_missing", "ocr_not_installed", "rapidocr_not_installed"):
        return False
    if status != "parsed":
        return False
    return int(result.get("valid_rows") or 0) > 0


def _batch_aggregate(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    speedups: list[float] = []
    ratios: list[float] = []
    acceptable_count = 0
    paddle_success = 0
    rapidocr_success = 0

    for item in comparisons:
        paddle = (item.get("results") or {}).get("paddle") or {}
        rapid = (item.get("results") or {}).get("rapidocr") or {}
        comp = item.get("comparison") or {}

        if _engine_success(paddle):
            paddle_success += 1
        if _engine_success(rapid):
            rapidocr_success += 1
        if comp.get("rapidocr_acceptable"):
            acceptable_count += 1

        sp = comp.get("ocr_speedup_paddle_over_rapidocr")
        if sp is not None:
            speedups.append(float(sp))
        ratio = comp.get("row_count_ratio")
        if ratio is not None:
            ratios.append(float(ratio))

    return {
        "image_count": len(comparisons),
        "avg_speedup": round(sum(speedups) / len(speedups), 2) if speedups else None,
        "avg_row_count_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
        "rapidocr_acceptable_count": acceptable_count,
        "paddle_success_count": paddle_success,
        "rapidocr_success_count": rapidocr_success,
    }


def run_ocr_compare_batch(
    directory: str | Path,
    *,
    province: str,
    year: int,
    data_type: str = "school",
    subject_type: str | None = None,
    batch: str | None = None,
    limit: int | None = 5,
    engines: list[str] | tuple[str, ...] = DEFAULT_ENGINES,
    use_ocr_cache: bool = True,
    skip_slow_paddle: bool = True,
) -> dict[str, Any]:
    """批量 OCR 引擎对比。"""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"目录不存在: {dir_path}")

    plugin = get_province_plugin(province)
    province_norm = plugin.province_name
    province_slug = plugin.province_slug

    images = list_image_files(dir_path)
    if limit is not None and limit > 0:
        images = images[:limit]

    per_image: list[dict[str, Any]] = []
    for img in images:
        try:
            item = compare_engines_on_image(
                img,
                engines=engines,
                data_type=data_type,
                province=province_norm,
                year=year,
                subject_type=subject_type,
                batch=batch,
                use_ocr_cache=use_ocr_cache,
                skip_slow_paddle=skip_slow_paddle,
            )
        except Exception as exc:
            logger.exception("OCR 对比失败 [%s]: %s", img.name, exc)
            item = {
                "filename": img.name,
                "error": str(exc),
                "results": {},
                "comparison": None,
            }
        per_image.append(item)

    aggregate = _batch_aggregate(per_image)
    report_path = batch_compare_output_path(province_slug, year, data_type)
    report: dict[str, Any] = {
        "province": province_norm,
        "province_slug": province_slug,
        "year": year,
        "data_type": data_type,
        "directory": str(dir_path.resolve()),
        "limit": limit,
        "engines": [normalize_ocr_engine(e) for e in engines],
        "use_ocr_cache": use_ocr_cache,
        "skip_slow_paddle": skip_slow_paddle,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": aggregate,
        "comparisons": per_image,
        "report_path": str(report_path),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def format_compare_lines(report: dict[str, Any]) -> list[str]:
    """单图对比 CLI 输出。"""
    lines = [
        f"OCR 引擎对比 [{report.get('filename')}]",
        f"use_ocr_cache: {report.get('use_ocr_cache')}  skip_slow_paddle: {report.get('skip_slow_paddle')}",
    ]
    for engine, result in (report.get("results") or {}).items():
        lines.append(
            f"  {engine}: status={result.get('status')} ocr={result.get('ocr_seconds')}s "
            f"cache_hit={result.get('cache_hit')} valid={result.get('valid_rows')}/"
            f"{result.get('parsed_rows')}"
        )
    comp = report.get("comparison") or {}
    if comp:
        lines.extend(
            [
                "",
                f"row_count_ratio: {comp.get('row_count_ratio')}",
                f"score_range_match: {comp.get('score_range_match')}",
                f"rapidocr_acceptable: {comp.get('rapidocr_acceptable')}",
            ]
        )
        reasons = comp.get("rapidocr_acceptable_reasons") or []
        if reasons:
            lines.append(f"  reasons: {', '.join(reasons)}")
        if comp.get("ocr_speedup_paddle_over_rapidocr") is not None:
            lines.append(f"  speedup (paddle/rapidocr): {comp.get('ocr_speedup_paddle_over_rapidocr')}x")
    lines.append(f"\nreport: {report.get('report_path')}")
    return lines


def format_batch_compare_lines(report: dict[str, Any]) -> list[str]:
    """批量对比 CLI 输出。"""
    summary = report.get("summary") or {}
    lines = [
        f"OCR 批量引擎对比 [{report.get('province')} {report.get('year')} {report.get('data_type')}]",
        f"images: {summary.get('image_count')}",
        f"avg_speedup: {summary.get('avg_speedup')}",
        f"avg_row_count_ratio: {summary.get('avg_row_count_ratio')}",
        f"rapidocr_acceptable_count: {summary.get('rapidocr_acceptable_count')}",
        f"paddle_success_count: {summary.get('paddle_success_count')}",
        f"rapidocr_success_count: {summary.get('rapidocr_success_count')}",
        "",
    ]
    for item in report.get("comparisons") or []:
        comp = item.get("comparison") or {}
        paddle = (item.get("results") or {}).get("paddle") or {}
        rapid = (item.get("results") or {}).get("rapidocr") or {}
        lines.append(
            f"  {item.get('filename')}: paddle valid={paddle.get('valid_rows')} "
            f"rapid valid={rapid.get('valid_rows')} "
            f"ratio={comp.get('row_count_ratio')} acceptable={comp.get('rapidocr_acceptable')}"
        )
    lines.append(f"\nreport: {report.get('report_path')}")
    return lines
