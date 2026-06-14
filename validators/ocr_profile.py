"""
OCR 流程耗时剖析（Phase 20.7 / 20.8）。

只统计各阶段耗时，不修改解析/入库逻辑。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CLEANED_DIR
from importers.pipeline import enriched_rows_for_db
from normalizers import normalize_dataframe
from parsers.ocr_engine import (
    get_ocr_engine,
    is_hybrid_engine_mode,
    ocr_engine_available,
    run_ocr_inference,
    uses_ocr_engine_singleton,
)
from parsers.parse_image_table import (
    OCR_SOURCE_PREFIX,
    _cluster_rows,
    _infer_batch_from_context,
    _infer_subject_from_context,
    _prepare_image_for_ocr,
    _rows_to_hubei_dataframe,
    parse_image_table,
)
from validators.ocr_quality_gate import audit_from_parse_result
from validators.validate import validate_dataframe

PROFILE_OUTPUT = CLEANED_DIR / "ocr_profile.json"


def profile_ocr_image(
    session,
    image_path: str | Path,
    *,
    province: str = "湖北",
    year: int = 2024,
    subject_type: str | None = "物理类",
    batch: str | None = "本科批",
    subject_mode: object | None = None,
    page_title: str | None = None,
    commit_database: bool = False,
    use_ocr_cache: bool = True,
    ocr_engine: str = "paddle",
    allow_slow_paddle_fallback: bool = False,
) -> dict[str, Any]:
    """
    对单张图片统计 OCR 全流程耗时（秒）。

    默认 database 阶段用 rollback，避免污染库；commit_database=True 时真正 commit。
    """
    if is_hybrid_engine_mode(ocr_engine):
        return _profile_hybrid_ocr_image(
            session,
            image_path,
            province=province,
            year=year,
            subject_type=subject_type,
            batch=batch,
            subject_mode=subject_mode,
            page_title=page_title,
            commit_database=commit_database,
            use_ocr_cache=use_ocr_cache,
            allow_slow_paddle_fallback=allow_slow_paddle_fallback,
        )

    from db.repository import insert_school_admission_lines

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    from parsers.ocr_engine import ocr_engine_available

    if not ocr_engine_available(ocr_engine):
        missing = "rapidocr_not_installed" if ocr_engine == "rapidocr" else "PaddleOCR 未安装"
        raise RuntimeError(missing)

    total_start = time.perf_counter()

    t0 = time.perf_counter()
    prepared = _prepare_image_for_ocr(path)
    image_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    ocr_result = run_ocr_inference(
        path, prepared, use_cache=use_ocr_cache, engine=ocr_engine
    )
    ocr_items = ocr_result.items
    ocr_seconds = time.perf_counter() - t0

    ocr_text = " ".join(item["text"] for item in ocr_items)
    resolved_subject = _infer_subject_from_context(
        subject_type=subject_type,
        filename=path.stem,
        page_title=page_title,
        ocr_text=ocr_text,
        subject_mode=subject_mode,
    )
    resolved_batch = _infer_batch_from_context(
        batch=batch,
        filename=path.stem,
        page_title=page_title,
        ocr_text=ocr_text,
    )

    t0 = time.perf_counter()
    rows = _cluster_rows(ocr_items)
    clustering_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    if province == "湖北":
        parsed_df = _rows_to_hubei_dataframe(
            rows,
            year=year,
            province=province,
            subject_type=resolved_subject,
            batch=resolved_batch,
        )
    else:
        raise ValueError(f"OCR profile 暂仅支持湖北 school，当前 province={province}")

    dataframe_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    normalized_df = normalize_dataframe(
        parsed_df,
        data_type="school",
        year=year,
        province=province,
        subject_type=resolved_subject,
        batch=resolved_batch,
        subject_mode=subject_mode,
    )
    normalize_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    validation = validate_dataframe(normalized_df, "school")
    validate_seconds = time.perf_counter() - t0

    valid_df = validation.valid_df
    inserted = skipped = failed = 0
    t0 = time.perf_counter()
    if not valid_df.empty:
        source_url = f"{OCR_SOURCE_PREFIX}{path.resolve()}"
        valid_rows = enriched_rows_for_db(valid_df, "school", source_url)
        from db.database import SessionLocal

        db_session = SessionLocal()
        try:
            result = insert_school_admission_lines(db_session, valid_rows)
            inserted, skipped, failed = result.inserted, result.skipped, result.failed
            if commit_database:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()
    database_seconds = time.perf_counter() - t0

    total_seconds = time.perf_counter() - total_start

    return {
        "image": path.name,
        "image_path": str(path.resolve()),
        "parsed_rows": len(parsed_df),
        "valid_rows": len(valid_df),
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
        "database_committed": commit_database,
        "use_ocr_cache": use_ocr_cache,
        "ocr_engine": ocr_engine,
        "cache_hit": ocr_result.cache_hit,
        "cache_miss": ocr_result.cache_miss,
        "parser_used": ocr_result.parser_used,
        "ocr_engine_recreated": ocr_result.ocr_engine_recreated,
        "ocr_cache_path": ocr_result.cache_path,
        "image_seconds": round(image_seconds, 3),
        "ocr_seconds": round(ocr_seconds, 3),
        "clustering_seconds": round(clustering_seconds, 3),
        "dataframe_seconds": round(dataframe_seconds, 3),
        "normalize_seconds": round(normalize_seconds, 3),
        "validate_seconds": round(validate_seconds, 3),
        "database_seconds": round(database_seconds, 3),
        "total_seconds": round(total_seconds, 3),
    }


def _profile_hybrid_ocr_image(
    session,
    image_path: str | Path,
    *,
    province: str = "湖北",
    year: int = 2024,
    subject_type: str | None = "物理类",
    batch: str | None = "本科批",
    subject_mode: object | None = None,
    page_title: str | None = None,
    commit_database: bool = False,
    use_ocr_cache: bool = True,
    allow_slow_paddle_fallback: bool = False,
) -> dict[str, Any]:
    from db.repository import insert_school_admission_lines
    from importers.pipeline import run_parsed_pipeline

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not ocr_engine_available("rapidocr"):
        raise RuntimeError("rapidocr_not_installed")

    total_start = time.perf_counter()
    t0 = time.perf_counter()
    parse_result = parse_image_table(
        path,
        data_type="school",
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        page_title=page_title,
        subject_mode=subject_mode,
        use_ocr_cache=use_ocr_cache,
        ocr_engine="hybrid",
        allow_slow_paddle_fallback=allow_slow_paddle_fallback,
    )
    parse_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    audit = audit_from_parse_result(
        path,
        parse_result,
        data_type="school",
        province=province,
        year=year,
        subject_type=subject_type,
        batch=batch,
        subject_mode=subject_mode,
    )
    validate_seconds = time.perf_counter() - t0

    inserted = skipped = failed = 0
    t0 = time.perf_counter()
    if parse_result.status == "parsed" and not parse_result.df.empty:
        pipeline = run_parsed_pipeline(
            parse_result.df,
            data_type="school",
            year=year,
            province=province,
            subject_type=subject_type,
            source_path=path,
            batch=batch,
            subject_mode=subject_mode,
        )
        valid_df = pipeline.valid_df
        if not valid_df.empty:
            source_url = f"{OCR_SOURCE_PREFIX}{path.resolve()}"
            valid_rows = enriched_rows_for_db(valid_df, "school", source_url)
            from db.database import SessionLocal

            db_session = SessionLocal()
            try:
                result = insert_school_admission_lines(db_session, valid_rows)
                inserted, skipped, failed = result.inserted, result.skipped, result.failed
                if commit_database:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()
    database_seconds = time.perf_counter() - t0
    total_seconds = time.perf_counter() - total_start

    hybrid = parse_result.hybrid or {}
    return {
        "image": path.name,
        "image_path": str(path.resolve()),
        "parsed_rows": audit.get("parsed_rows", 0),
        "valid_rows": audit.get("valid_rows", 0),
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
        "database_committed": commit_database,
        "use_ocr_cache": use_ocr_cache,
        "ocr_engine": "hybrid",
        "parser_used": parse_result.parser_used,
        "ocr_status": parse_result.status,
        "image_seconds": 0.0,
        "ocr_seconds": hybrid.get("rapidocr_seconds"),
        "parse_seconds": round(parse_seconds, 3),
        "validate_seconds": round(validate_seconds, 3),
        "database_seconds": round(database_seconds, 3),
        "total_seconds": round(total_seconds, 3),
        "rapidocr_seconds": hybrid.get("rapidocr_seconds"),
        "rapidocr_valid_rows": hybrid.get("rapidocr_valid_rows"),
        "rapidocr_accepted": hybrid.get("rapidocr_accepted"),
        "fallback_used": hybrid.get("fallback_used"),
        "fallback_reason": hybrid.get("fallback_reason"),
        "engine_selected": hybrid.get("engine_selected"),
        "paddle_cache_hit": hybrid.get("paddle_cache_hit"),
        "paddle_baseline_valid_rows": hybrid.get("paddle_baseline_valid_rows"),
    }


def warmup_paddle_engine(ocr_engine: str = "paddle") -> None:
    """预加载 OCR 引擎，避免首张图模型加载计入 profile。"""
    from parsers.ocr_engine import ocr_engine_available, get_ocr_engine

    if ocr_engine_available(ocr_engine):
        get_ocr_engine(ocr_engine)


def run_ocr_profile_batch(
    session,
    image_paths: list[str | Path],
    *,
    province: str = "湖北",
    year: int = 2024,
    subject_type: str | None = "物理类",
    batch: str | None = "本科批",
    commit_database: bool = False,
    use_ocr_cache: bool = True,
    run_label: str | None = None,
    ocr_engine: str = "paddle",
    allow_slow_paddle_fallback: bool = False,
) -> dict[str, Any]:
    """连续 profile 多张图片，写入 ocr_profile.json。"""
    if not is_hybrid_engine_mode(ocr_engine):
        warmup_paddle_engine(ocr_engine)
    profiles: list[dict[str, Any]] = []
    for image_path in image_paths:
        profiles.append(
            profile_ocr_image(
                session,
                image_path,
                province=province,
                year=year,
                subject_type=subject_type,
                batch=batch,
                commit_database=commit_database,
                use_ocr_cache=use_ocr_cache,
                ocr_engine=ocr_engine,
                allow_slow_paddle_fallback=allow_slow_paddle_fallback,
            )
        )

    cache_hits = sum(1 for p in profiles if p.get("cache_hit"))
    cache_misses = sum(1 for p in profiles if p.get("cache_miss"))
    any_engine_recreated = any(p.get("ocr_engine_recreated") for p in profiles)

    report: dict[str, Any] = {
        "province": province,
        "year": year,
        "run_label": run_label,
        "image_count": len(profiles),
        "use_ocr_cache": use_ocr_cache,
        "ocr_engine": ocr_engine,
        "ocr_engine_singleton": uses_ocr_engine_singleton(),
        "ocr_engine_recreated": any_engine_recreated,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "profiles": profiles,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "report_path": str(PROFILE_OUTPUT),
    }
    PROFILE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def format_profile_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"OCR 耗时剖析 [{report.get('province')} {report.get('year')}]",
        f"images: {report.get('image_count')}",
        f"use_ocr_cache: {report.get('use_ocr_cache')}",
        f"ocr_engine: {report.get('ocr_engine')}",
        f"ocr_engine_singleton: {report.get('ocr_engine_singleton')}",
        f"ocr_engine_recreated: {report.get('ocr_engine_recreated')}",
        f"cache_hits: {report.get('cache_hits')} cache_misses: {report.get('cache_misses')}",
        f"report: {report.get('report_path')}",
        "",
    ]
    for p in report.get("profiles") or []:
        lines.append(f"## {p.get('image')}")
        lines.append(f"  total_seconds: {p.get('total_seconds')}")
        lines.append(
            f"  parser_used: {p.get('parser_used')} "
            f"cache_hit={p.get('cache_hit')} cache_miss={p.get('cache_miss')}"
        )
        lines.append(f"  image: {p.get('image_seconds')}s")
        lines.append(f"  ocr: {p.get('ocr_seconds')}s")
        lines.append(f"  clustering: {p.get('clustering_seconds')}s")
        lines.append(f"  dataframe: {p.get('dataframe_seconds')}s")
        lines.append(f"  normalize: {p.get('normalize_seconds')}s")
        lines.append(f"  validate: {p.get('validate_seconds')}s")
        lines.append(f"  database: {p.get('database_seconds')}s")
        lines.append(
            f"  rows: parsed={p.get('parsed_rows')} valid={p.get('valid_rows')}"
        )
        if p.get("ocr_engine") == "hybrid":
            lines.append(
                f"  hybrid: selected={p.get('engine_selected')} "
                f"rapidocr={p.get('rapidocr_seconds')}s valid={p.get('rapidocr_valid_rows')} "
                f"accepted={p.get('rapidocr_accepted')} fallback={p.get('fallback_used')}"
            )
            if p.get("fallback_reason"):
                lines.append(f"  fallback_reason: {p.get('fallback_reason')}")
            lines.append(f"  paddle_cache_hit: {p.get('paddle_cache_hit')}")
        lines.append("")
    return lines
