"""
图片文件完整性校验（Phase 20.15）。

检测损坏/截断图片，供 OCR 批量流程跳过而不拉低 audit 通过率。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CLEANED_DIR
from parsers.image_sort import list_image_files
from province_registry import get_province_plugin

logger = logging.getLogger(__name__)

CORRUPTED_IMAGE_STATUS = "corrupted_image"


def image_verify_report_path(province_slug: str, year: int, data_type: str) -> Path:
    return CLEANED_DIR / f"image_verify_{province_slug}_{year}_{data_type}.json"


def is_image_corruption_error(exc: BaseException) -> bool:
    """异常是否由图片损坏/截断引起。"""
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "truncated",
            "corrupt",
            "broken",
            "cannot identify",
            "image file is truncated",
            "bad png",
            "bad jpeg",
            "not a png",
            "encoder error",
        )
    )


def verify_image_file(image_path: str | Path) -> dict[str, Any]:
    """
    检查单张图片能否被 PIL 打开且 verify/load 通过。

    不启用 LOAD_TRUNCATED_IMAGES，不尝试修复。
    """
    path = Path(image_path)
    result: dict[str, Any] = {
        "filename": path.name,
        "local_path": str(path.resolve()),
        "file_size_bytes": None,
        "ok": False,
        "corrupted": False,
        "truncated": False,
        "width": None,
        "height": None,
        "error": None,
    }
    if not path.is_file():
        result["corrupted"] = True
        result["error"] = "file_not_found"
        return result

    try:
        result["file_size_bytes"] = path.stat().st_size
    except OSError as exc:
        result["corrupted"] = True
        result["error"] = str(exc)
        return result

    try:
        from PIL import Image
    except ImportError:
        result["ok"] = True
        result["error"] = "pillow_not_installed_skip_verify"
        return result

    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            result["width"] = im.size[0]
            result["height"] = im.size[1]
        result["ok"] = True
    except OSError as exc:
        msg = str(exc)
        result["corrupted"] = True
        result["truncated"] = "truncat" in msg.lower()
        result["error"] = msg
    except Exception as exc:
        result["corrupted"] = True
        result["error"] = str(exc)

    return result


def is_corrupted_image(image_path: str | Path) -> bool:
    return verify_image_file(image_path)["corrupted"]


def _discovery_download_index(
    province_slug: str,
    year: int,
    data_type: str,
) -> dict[str, dict[str, Any]]:
    """按文件名索引 discovery 下载记录（用于重新下载建议）。"""
    report_path = CLEANED_DIR / f"discovery_{province_slug}_{year}_{data_type}.json"
    if not report_path.is_file():
        return {}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in data.get("downloads") or []:
        local = row.get("local_path")
        if not local:
            continue
        name = Path(str(local)).name
        index[name] = {
            "source_url": row.get("url"),
            "page_url": row.get("page_url"),
            "source_title": row.get("source_title"),
            "local_path": str(Path(local)),
        }
    return index


def run_verify_images(
    directory: str | Path,
    *,
    province: str | None = None,
    year: int | None = None,
    data_type: str = "school",
    limit: int | None = None,
) -> dict[str, Any]:
    """按自然序校验目录内图片。"""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"目录不存在: {dir_path}")

    province_slug = "unknown"
    province_norm = province
    if province:
        plugin = get_province_plugin(province)
        province_slug = plugin.province_slug
        province_norm = plugin.province_name

    if year is None:
        for part in dir_path.parts:
            if part.isdigit() and len(part) == 4:
                year = int(part)
                break
    if year is None:
        year = 0

    images = list_image_files(dir_path)
    if limit is not None and limit > 0:
        images = images[:limit]

    download_index = _discovery_download_index(province_slug, year, data_type)
    per_image: list[dict[str, Any]] = []
    corrupted_count = 0
    for path in images:
        item = verify_image_file(path)
        src = download_index.get(path.name)
        if src:
            item["source_url"] = src.get("source_url")
            item["page_url"] = src.get("page_url")
            item["source_title"] = src.get("source_title")
        if item.get("corrupted"):
            corrupted_count += 1
        per_image.append(item)

    report: dict[str, Any] = {
        "province": province_norm,
        "province_slug": province_slug,
        "year": year,
        "data_type": data_type,
        "directory": str(dir_path.resolve()),
        "limit": limit,
        "image_count": len(per_image),
        "ok_count": sum(1 for r in per_image if r.get("ok")),
        "corrupted_count": corrupted_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": per_image,
        "report_path": str(image_verify_report_path(province_slug, year, data_type)),
    }

    out = Path(report["report_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def corrupted_audit_item(
    image_path: str | Path,
    *,
    error: str | None = None,
    truncated: bool | None = None,
) -> dict[str, Any]:
    """OCR 审计用的损坏图片占位结果（无 suspicious_flags）。"""
    path = Path(image_path)
    verify = verify_image_file(path) if error is None else {}
    return {
        "filename": path.name,
        "local_path": str(path.resolve()),
        "ocr_status": CORRUPTED_IMAGE_STATUS,
        "corrupted": True,
        "truncated": truncated if truncated is not None else verify.get("truncated", False),
        "parsed_rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "min_score_min": None,
        "min_score_max": None,
        "field_quality": {},
        "warnings": [],
        "suspicious_flags": [],
        "message": error or verify.get("error") or "corrupted_image",
    }


def format_verify_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"图片完整性校验 [{report.get('province')} {report.get('year')} {report.get('data_type')}]",
        f"directory: {report.get('directory')}",
        f"image_count: {report.get('image_count')} ok: {report.get('ok_count')} corrupted: {report.get('corrupted_count')}",
        "",
    ]
    for row in report.get("images") or []:
        flag = "OK" if row.get("ok") else "CORRUPT"
        size = row.get("file_size_bytes")
        wh = f"{row.get('width')}x{row.get('height')}" if row.get("width") else "-"
        lines.append(
            f"  [{flag}] {row.get('filename')} size={size} {wh} "
            f"truncated={row.get('truncated')} error={row.get('error') or ''}"
        )
        if row.get("source_url"):
            lines.append(f"       source_url: {row.get('source_url')}")
    lines.append(f"\nreport: {report.get('report_path')}")
    return lines
