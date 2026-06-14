"""
Hybrid OCR 策略（Phase 20.13）：rapidocr-first + quality gate + paddle fallback。

不单独存储 hybrid cache；复用 rapidocr / paddle 分 engine 缓存。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from parsers.ocr_engine import (
    load_ocr_cache,
    normalize_ocr_engine_mode,
    ocr_engine_available,
    run_ocr_inference,
)
from parsers.parse_image_table import (
    ImageTableParseResult,
    _prepare_image_for_ocr,
    parse_image_table,
)
from validators.ocr_quality_gate import (
    MIN_SCORE_HIGH,
    MIN_SCORE_LOW,
    audit_from_parse_result,
)

logger = logging.getLogger(__name__)

HYBRID_ENGINE_MODE = "hybrid"
HYBRID_MIN_VALID_ROWS = 40
HYBRID_PADDLE_VALID_RATIO = 0.80
HYBRID_MIN_NON_NULL_RATE = 0.95
HYBRID_MAX_SCHOOL_NAME_INVALID_RATE = 0.05


def is_hybrid_engine_mode(engine: str | None) -> bool:
    return normalize_ocr_engine_mode(engine) == HYBRID_ENGINE_MODE


def paddle_cache_available(image_path: Path, *, use_ocr_cache: bool) -> bool:
    if not use_ocr_cache:
        return False
    return load_ocr_cache(image_path, "paddle") is not None


@dataclass
class HybridOcrMetadata:
    engine_selected: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    rapidocr_seconds: float | None = None
    rapidocr_valid_rows: int | None = None
    rapidocr_accepted: bool = False
    rapidocr_rejection_reasons: list[str] = field(default_factory=list)
    paddle_cache_hit: bool | None = None
    paddle_baseline_valid_rows: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_selected": self.engine_selected,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "rapidocr_seconds": self.rapidocr_seconds,
            "rapidocr_valid_rows": self.rapidocr_valid_rows,
            "rapidocr_accepted": self.rapidocr_accepted,
            "rapidocr_rejection_reasons": self.rapidocr_rejection_reasons,
            "paddle_cache_hit": self.paddle_cache_hit,
            "paddle_baseline_valid_rows": self.paddle_baseline_valid_rows,
        }


def evaluate_rapidocr_hybrid_gate(
    audit: dict[str, Any],
    *,
    data_type: str,
    paddle_baseline_valid_rows: int | None,
) -> tuple[bool, list[str]]:
    """RapidOCR 结果是否满足 hybrid 质量门槛。"""
    reasons: list[str] = []

    if audit.get("ocr_status") != "parsed":
        reasons.append(f"ocr_status_{audit.get('ocr_status')}")

    valid_rows = int(audit.get("valid_rows") or 0)
    if paddle_baseline_valid_rows is not None and paddle_baseline_valid_rows > 0:
        needed = HYBRID_PADDLE_VALID_RATIO * paddle_baseline_valid_rows
        if valid_rows < needed:
            reasons.append(
                f"valid_rows_below_paddle_baseline "
                f"({valid_rows} < {needed:.0f}, baseline={paddle_baseline_valid_rows})"
            )
    elif valid_rows < HYBRID_MIN_VALID_ROWS:
        reasons.append(f"valid_rows_below_min ({valid_rows} < {HYBRID_MIN_VALID_ROWS})")

    suspicious = audit.get("suspicious_flags") or []
    if suspicious:
        reasons.append(f"suspicious_flags={suspicious}")

    field_quality = audit.get("field_quality") or {}
    invalid_rate = field_quality.get("school_name_invalid_rate")
    if invalid_rate is not None and float(invalid_rate) >= HYBRID_MAX_SCHOOL_NAME_INVALID_RATE:
        reasons.append(f"school_name_invalid_rate={invalid_rate}")

    lo = audit.get("min_score_min")
    hi = audit.get("min_score_max")
    if lo is None or hi is None:
        reasons.append("min_score_range_missing")
    elif float(lo) < MIN_SCORE_LOW or float(hi) > MIN_SCORE_HIGH:
        reasons.append(f"min_score_out_of_range [{lo}, {hi}]")

    if data_type == "school":
        for fld in ("school_name", "major_group", "min_score"):
            rate = field_quality.get(f"{fld}_non_null_rate")
            if rate is None or float(rate) < HYBRID_MIN_NON_NULL_RATE:
                reasons.append(
                    f"{fld}_non_null_rate={rate} < {HYBRID_MIN_NON_NULL_RATE}"
                )

    return len(reasons) == 0, reasons


def _attach_hybrid(
    result: ImageTableParseResult,
    meta: HybridOcrMetadata,
) -> ImageTableParseResult:
    result.hybrid = meta.to_dict()
    return result


def _time_rapidocr_inference(
    path: Path,
    *,
    use_ocr_cache: bool,
) -> tuple[float, bool]:
    if not ocr_engine_available("rapidocr"):
        return 0.0, False
    prepared = _prepare_image_for_ocr(path)
    t0 = time.perf_counter()
    ocr_result = run_ocr_inference(
        path, prepared, use_cache=use_ocr_cache, engine="rapidocr"
    )
    return round(time.perf_counter() - t0, 3), ocr_result.cache_hit


def _paddle_baseline_valid_rows(
    path: Path,
    *,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None,
    batch: str | None,
    page_title: str | None,
    subject_mode: Any,
    use_ocr_cache: bool,
) -> int | None:
    if not paddle_cache_available(path, use_ocr_cache=use_ocr_cache):
        return None
    parse_result = parse_image_table(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=True,
        ocr_engine="paddle",
    )
    audit = audit_from_parse_result(
        path,
        parse_result,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        subject_mode=subject_mode,
    )
    return int(audit.get("valid_rows") or 0)


def run_hybrid_image_parse(
    image_path: str | Path,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None = None,
    batch: str | None = None,
    *,
    page_title: str | None = None,
    subject_mode: Any = None,
    use_ocr_cache: bool = True,
    allow_slow_paddle_fallback: bool = False,
) -> ImageTableParseResult:
    """
    rapidocr-first → quality gate → paddle fallback（优先 cache）。
    """
    path = Path(image_path)
    meta = HybridOcrMetadata()

    if not ocr_engine_available("rapidocr"):
        return ImageTableParseResult(
            status="rapidocr_not_installed",
            parser_used="hybrid",
            hybrid=meta.to_dict(),
        )

    meta.rapidocr_seconds, _ = _time_rapidocr_inference(path, use_ocr_cache=use_ocr_cache)

    rapid_parse = parse_image_table(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=use_ocr_cache,
        ocr_engine="rapidocr",
    )
    rapid_audit = audit_from_parse_result(
        path,
        rapid_parse,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        subject_mode=subject_mode,
    )
    meta.rapidocr_valid_rows = int(rapid_audit.get("valid_rows") or 0)
    meta.paddle_baseline_valid_rows = _paddle_baseline_valid_rows(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=use_ocr_cache,
    )

    accepted, rejection_reasons = evaluate_rapidocr_hybrid_gate(
        rapid_audit,
        data_type=data_type,
        paddle_baseline_valid_rows=meta.paddle_baseline_valid_rows,
    )
    meta.rapidocr_accepted = accepted
    meta.rapidocr_rejection_reasons = rejection_reasons

    if accepted and rapid_parse.status == "parsed":
        meta.engine_selected = "rapidocr"
        meta.fallback_used = False
        rapid_parse.parser_used = "hybrid:rapidocr"
        return _attach_hybrid(rapid_parse, meta)

    meta.fallback_used = True
    meta.fallback_reason = "; ".join(rejection_reasons) if rejection_reasons else "rapidocr_rejected"

    has_paddle_cache = paddle_cache_available(path, use_ocr_cache=use_ocr_cache)
    if not has_paddle_cache and not allow_slow_paddle_fallback:
        meta.engine_selected = None
        return ImageTableParseResult(
            status="fallback_required_but_no_cache",
            parser_used="hybrid",
            message=(
                "RapidOCR 未通过质量门槛且 Paddle 无磁盘缓存；"
                "加 --allow-slow-paddle-fallback 才允许 live Paddle"
            ),
            hybrid=meta.to_dict(),
        )

    if not ocr_engine_available("paddle"):
        return ImageTableParseResult(
            status="ocr_not_installed",
            parser_used="hybrid",
            message="Hybrid fallback 需要 PaddleOCR",
            hybrid=meta.to_dict(),
        )

    paddle_parse = parse_image_table(
        path,
        data_type=data_type,
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=use_ocr_cache,
        ocr_engine="paddle",
    )
    meta.engine_selected = "paddle"
    meta.paddle_cache_hit = has_paddle_cache
    paddle_parse.parser_used = "hybrid:paddle"
    return _attach_hybrid(paddle_parse, meta)
