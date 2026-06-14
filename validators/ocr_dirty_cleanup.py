"""
OCR 脏数据清理（Phase 20.6）。

仅删除 OCR 实验来源且校名明显无效的记录；默认 dry-run。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from config import CLEANED_DIR
from db.models import SchoolAdmissionLine
from normalizers.school_name import is_invalid_school_name
from parsers.parse_image_table import OCR_SOURCE_PREFIX
from province_registry import get_province_plugin

SAMPLE_LIMIT = 20


def cleanup_report_path(province_slug: str, year: int) -> Path:
    return CLEANED_DIR / f"ocr_dirty_cleanup_{province_slug}_{year}.json"


def is_ocr_dirty_school_record(
    row: SchoolAdmissionLine,
    *,
    source_prefix: str = OCR_SOURCE_PREFIX,
) -> bool:
    """
    判定 school_admission_line 是否为 OCR 脏记录。

    调用方需已按 province/year/source_url 过滤。
    """
    source_url = row.source_url or ""
    if not source_url.startswith(source_prefix):
        return False

    name = (row.school_name or "").strip()
    code = (row.school_code or "").strip()

    if is_invalid_school_name(name):
        return True
    if len(name) <= 1:
        return True
    if re.fullmatch(r"\d+", name):
        return True
    if code.startswith("A0010") and re.fullmatch(r"\d+", name):
        return True
    return False


def find_dirty_ocr_school_rows(
    session: Session,
    *,
    province: str,
    year: int,
    source_prefix: str = OCR_SOURCE_PREFIX,
) -> list[SchoolAdmissionLine]:
    """查询并筛选 OCR 脏记录。"""
    candidates = (
        session.query(SchoolAdmissionLine)
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            SchoolAdmissionLine.source_url.like(f"{source_prefix}%"),
        )
        .order_by(SchoolAdmissionLine.id)
        .all()
    )
    return [row for row in candidates if is_ocr_dirty_school_record(row, source_prefix=source_prefix)]


def _row_sample(row: SchoolAdmissionLine) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_url": row.source_url,
        "school_code": row.school_code,
        "school_name": row.school_name,
        "major_group": row.major_group,
        "min_score": row.min_score,
    }


def _count_by_source(rows: list[SchoolAdmissionLine]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = row.source_url or "(null)"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def run_ocr_dirty_cleanup(
    session: Session,
    *,
    province: str,
    year: int,
    source_prefix: str = OCR_SOURCE_PREFIX,
    confirm_delete: bool = False,
) -> dict[str, Any]:
    """dry-run 或确认删除 OCR 脏数据。"""
    plugin = get_province_plugin(province)
    province_norm = plugin.province_name
    province_slug = plugin.province_slug

    matched = find_dirty_ocr_school_rows(
        session,
        province=province_norm,
        year=year,
        source_prefix=source_prefix,
    )
    dry_run = not confirm_delete
    deleted_count = 0
    by_source_url = _count_by_source(matched)
    samples = [_row_sample(row) for row in matched[:SAMPLE_LIMIT]]

    if confirm_delete and matched:
        ids = [row.id for row in matched]
        deleted_count = (
            session.query(SchoolAdmissionLine)
            .filter(SchoolAdmissionLine.id.in_(ids))
            .delete(synchronize_session=False)
        )
        session.commit()

    report: dict[str, Any] = {
        "province": province_norm,
        "province_slug": province_slug,
        "year": year,
        "source_prefix": source_prefix,
        "dry_run": dry_run,
        "matched_count": len(matched),
        "deleted_count": deleted_count,
        "by_source_url": by_source_url,
        "samples": samples,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "report_path": str(cleanup_report_path(province_slug, year)),
    }

    if confirm_delete:
        CLEANED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = cleanup_report_path(province_slug, year)
        if len(matched) > 0 or deleted_count > 0:
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(out_path)
        elif out_path.is_file():
            report["report_path"] = str(out_path)
            report["note"] = "无匹配记录，保留既有报告"

    return report


def format_cleanup_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"OCR 脏数据清理 [{report.get('province')} {report.get('year')}]",
        f"dry_run: {report.get('dry_run')}",
        f"matched_count: {report.get('matched_count')}",
        f"deleted_count: {report.get('deleted_count')}",
        "",
        "## 按 source_url 分组",
    ]
    for url, cnt in (report.get("by_source_url") or {}).items():
        lines.append(f"  {cnt}\t{url}")
    lines.append("")
    lines.append("## sample rows")
    for row in report.get("samples") or []:
        lines.append(f"  {row}")
    if report.get("dry_run"):
        lines.append("")
        lines.append("未删除。确认后请加 --confirm-delete 执行删除。")
    elif report.get("report_path"):
        lines.append("")
        lines.append(f"报告: {report.get('report_path')}")
    return lines
