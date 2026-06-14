"""
OCR 预计算（Phase 20.9）。

仅执行 OCR 推理并写入磁盘缓存，不 normalize / validate / 入库。
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
    get_ocr_engine,
    load_ocr_cache,
    ocr_engine_available,
    run_ocr_inference,
)
from parsers.parse_image_table import _prepare_image_for_ocr
from province_registry import get_province_plugin
from validators.image_verify import is_corrupted_image, verify_image_file

logger = logging.getLogger(__name__)


def precompute_report_path(province_slug: str, year: int, data_type: str) -> Path:
    return CLEANED_DIR / f"ocr_precompute_{province_slug}_{year}_{data_type}.json"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def precompute_single_image(
    image_path: Path,
    *,
    use_cache: bool = True,
    ocr_engine: str = "paddle",
) -> dict[str, Any]:
    """对单张图片预计算 OCR（仅推理 + 缓存）。"""
    entry: dict[str, Any] = {
        "filename": image_path.name,
        "cache_hit": False,
        "cache_miss": False,
        "ocr_seconds": 0.0,
        "status": "ok",
    }
    t0 = time.perf_counter()
    try:
        if use_cache and load_ocr_cache(image_path, ocr_engine) is not None:
            entry["cache_hit"] = True
            entry["cache_miss"] = False
            entry["ocr_seconds"] = round(time.perf_counter() - t0, 3)
            entry["status"] = "ok"
            return entry

        prepared = _prepare_image_for_ocr(image_path)
        result = run_ocr_inference(
            image_path, prepared, use_cache=use_cache, engine=ocr_engine
        )
        entry["cache_hit"] = result.cache_hit
        entry["cache_miss"] = result.cache_miss
        entry["ocr_seconds"] = round(time.perf_counter() - t0, 3)
        if not result.items:
            entry["status"] = "no_text"
        else:
            entry["status"] = "ok"
        if result.cache_path:
            entry["cache_path"] = result.cache_path
    except Exception as exc:
        entry["ocr_seconds"] = round(time.perf_counter() - t0, 3)
        entry["status"] = "failed"
        entry["error"] = str(exc)
        logger.exception("OCR 预计算失败 [%s]: %s", image_path.name, exc)
    return entry


def run_ocr_precompute(
    image_dir: str | Path,
    *,
    province: str,
    year: int,
    data_type: str = "school",
    limit: int | None = 20,
    use_cache: bool = True,
    ocr_engine: str = "paddle",
) -> dict[str, Any]:
    """
    扫描目录内图片，预计算 OCR 缓存。

    已有 cache 的图片跳过推理；可中断后重跑。
    """
    if data_type != "school":
        raise ValueError(f"ocr-precompute 暂仅支持 school，当前 type={data_type}")
    from parsers.ocr_engine import is_hybrid_engine_mode

    if is_hybrid_engine_mode(ocr_engine):
        raise ValueError("ocr-precompute 不支持 hybrid；请分别对 paddle / rapidocr 预计算缓存")
    if not ocr_engine_available(ocr_engine):
        missing = "rapidocr_not_installed" if ocr_engine == "rapidocr" else "PaddleOCR 未安装"
        raise RuntimeError(missing)

    plugin = get_province_plugin(province)
    province_norm = plugin.province_name
    province_slug = plugin.province_slug
    directory = Path(image_dir)

    all_images = list_image_files(directory)
    selected = all_images if limit is None else all_images[:limit]

    report_path = precompute_report_path(province_slug, year, data_type)
    total_start = time.perf_counter()
    per_image: list[dict[str, Any]] = []
    processed = 0
    cache_hits = 0
    cache_misses = 0
    failed = 0
    skipped_corrupted = 0

    needs_engine = any(
        (not use_cache or load_ocr_cache(p, ocr_engine) is None)
        and not is_corrupted_image(p)
        for p in selected
    )
    if needs_engine:
        get_ocr_engine(ocr_engine)

    report: dict[str, Any] = {
        "province": province_norm,
        "province_slug": province_slug,
        "year": year,
        "data_type": data_type,
        "image_dir": str(directory.resolve()),
        "total_images": len(all_images),
        "selected_images": len(selected),
        "limit": limit,
        "use_cache": use_cache,
        "ocr_engine": ocr_engine,
        "processed": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "failed": 0,
        "skipped_corrupted_image": 0,
        "total_seconds": 0.0,
        "per_image": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "report_path": str(report_path),
        "status": "in_progress",
    }
    _write_report(report_path, report)

    for index, image_path in enumerate(selected, start=1):
        if is_corrupted_image(image_path):
            verify = verify_image_file(image_path)
            logger.warning("OCR 预计算跳过损坏图片 [%s]: %s", image_path.name, verify.get("error"))
            entry = {
                "filename": image_path.name,
                "status": "skipped_corrupted",
                "corrupted": True,
                "truncated": verify.get("truncated"),
                "error": verify.get("error"),
                "cache_hit": False,
                "cache_miss": False,
                "ocr_seconds": 0.0,
            }
            per_image.append(entry)
            processed += 1
            skipped_corrupted += 1
            report.update(
                {
                    "processed": processed,
                    "skipped_corrupted_image": skipped_corrupted,
                    "per_image": per_image,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            _write_report(report_path, report)
            continue

        cached = use_cache and load_ocr_cache(image_path, ocr_engine) is not None
        if cached:
            logger.info(
                "OCR 预计算 [%d/%d] %s cache_hit，跳过推理",
                index,
                len(selected),
                image_path.name,
            )
        else:
            logger.info(
                "OCR 预计算 [%d/%d] %s cache_miss，开始 PaddleOCR（CPU 较慢，请耐心等待）…",
                index,
                len(selected),
                image_path.name,
            )
            print(
                f"[{index}/{len(selected)}] {image_path.name} cache_miss → PaddleOCR 推理中…",
                flush=True,
            )

        entry = precompute_single_image(
            image_path, use_cache=use_cache, ocr_engine=ocr_engine
        )
        per_image.append(entry)
        processed += 1
        if entry.get("cache_hit"):
            cache_hits += 1
        if entry.get("cache_miss"):
            cache_misses += 1
        if entry.get("status") == "failed":
            failed += 1

        report.update(
            {
                "processed": processed,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "failed": failed,
                "skipped_corrupted_image": skipped_corrupted,
                "total_seconds": round(time.perf_counter() - total_start, 3),
                "per_image": per_image,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_report(report_path, report)
        logger.info(
            "OCR 预计算 [%s] status=%s cache_hit=%s ocr_seconds=%s",
            entry["filename"],
            entry["status"],
            entry.get("cache_hit"),
            entry.get("ocr_seconds"),
        )

    report["status"] = "completed"
    report["skipped_corrupted_image"] = skipped_corrupted
    report["total_seconds"] = round(time.perf_counter() - total_start, 3)
    _write_report(report_path, report)
    return report


def format_precompute_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"OCR 预计算 [{report.get('province')} {report.get('year')} {report.get('data_type')}]",
        f"image_dir: {report.get('image_dir')}",
        f"total_images: {report.get('total_images')} selected: {report.get('selected_images')} limit: {report.get('limit')}",
        f"processed: {report.get('processed')}",
        f"cache_hits: {report.get('cache_hits')} cache_misses: {report.get('cache_misses')} failed: {report.get('failed')}",
        f"skipped_corrupted_image: {report.get('skipped_corrupted_image', 0)}",
        f"total_seconds: {report.get('total_seconds')}",
        f"report: {report.get('report_path')}",
        "",
    ]
    for row in report.get("per_image") or []:
        lines.append(
            f"  {row.get('filename')}\tstatus={row.get('status')}\t"
            f"hit={row.get('cache_hit')}\tocr={row.get('ocr_seconds')}s"
        )
    return lines
