"""
全国扩展扫描控制器（Phase 17）。

批量遍历已注册省份，按 Source Adapter 访问状态决定 discover / download / import。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import BASE_DIR
from configs.province_data_availability import get_province_data_availability
from configs.release import SOURCE_AWARE_PROVINCES, STRUCTURED_PROVINCES
from crawlers.discovery import (
    _build_year_summary,
    run_discover_and_download,
    run_discover_download_import,
    run_discover_only,
)
from normalizers.province import normalize_province
from province_registry import PROVINCES, get_province_plugin, list_registered_provinces
from sources.base import AccessStatus

logger = logging.getLogger(__name__)

ACCESSIBLE_FOR_SCAN = frozenset(
    {
        AccessStatus.AVAILABLE.value,
        AccessStatus.PARTIAL.value,
        AccessStatus.UNKNOWN.value,
    }
)

SKIP_ACCESS_STATUSES = frozenset(
    {
        AccessStatus.WAF_BLOCKED.value,
        AccessStatus.VERIFICATION_REQUIRED.value,
        AccessStatus.CONNECTION_RESET.value,
        AccessStatus.UNSUPPORTED_ARCHIVE.value,
        AccessStatus.UNSUPPORTED_PDF.value,
    }
)


def national_scan_report_path(year: int, data_type: str) -> Path:
    return BASE_DIR / "data" / "cleaned" / f"national_scan_{year}_{data_type}.json"


def _get_availability_meta(province: str, year: int) -> dict[str, Any]:
    for row in get_province_data_availability():
        if row.get("province") == province and row.get("year") == year:
            return row
    return {}


def _aggregate_year_summaries(summaries: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "discovered_pages": 0,
        "downloaded_files": 0,
        "imported": 0,
        "skipped": 0,
        "failed": 0,
    }
    for row in summaries:
        totals["discovered_pages"] += int(row.get("discovered_pages") or 0)
        totals["downloaded_files"] += int(row.get("downloaded_files") or 0)
        totals["imported"] += int(row.get("imported") or 0)
        totals["skipped"] += int(row.get("skipped") or 0)
        totals["failed"] += int(row.get("failed") or 0)
    return totals


def _scan_single_province(
    province: str,
    *,
    year: int,
    data_type: str,
    dry_run: bool,
    import_enabled: bool,
    max_pages: int,
) -> dict[str, Any]:
    province = normalize_province(province)
    meta = _get_availability_meta(province, year)
    machine_readable = bool(meta.get("machine_readable", False))
    query_mode = meta.get("query_mode") or "mixed"

    item: dict[str, Any] = {
        "province": province,
        "machine_readable": machine_readable,
        "query_mode": query_mode,
        "discovered_pages": 0,
        "downloaded_files": 0,
        "imported": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        plugin = get_province_plugin(province)
        adapter = plugin.source_adapter
        checked = adapter.check_availability()
        status = adapter.get_status()
        access_status = status.value
        item["access_status"] = access_status
        item["checked_availability"] = checked.value

        if access_status in SKIP_ACCESS_STATUSES:
            item["status"] = "skipped_due_to_access_status"
            item["skip_reason"] = access_status
            return item

        if access_status not in ACCESSIBLE_FOR_SCAN:
            item["status"] = "skipped_due_to_access_status"
            item["skip_reason"] = access_status
            return item

        years = [year]
        if dry_run:
            discover_result = run_discover_only(
                years, province, data_type, max_pages=max_pages
            )
            summaries = discover_result.get("summary") or []
            totals = _aggregate_year_summaries(summaries)
            item.update(totals)
            item["status"] = "ok"
            item["dry_run"] = True
            if any(s.get("error") for s in summaries):
                item["status"] = "partial"
            return item

        if import_enabled:
            result = run_discover_download_import(
                years=years,
                province=province,
                data_type=data_type,
                max_pages=max_pages,
                dry_run=False,
            )
            summaries = result.get("summary") or []
        else:
            report_paths, _ = run_discover_and_download(
                years, province, data_type, max_pages=max_pages
            )
            summaries = []
            for y in years:
                path = report_paths.get(y)
                sources: list[dict[str, Any]] = []
                report: dict[str, Any] | None = None
                if path and path.exists():
                    report = json.loads(path.read_text(encoding="utf-8"))
                    sources = report.get("sources") or []
                summaries.append(_build_year_summary(y, sources, report))

        totals = _aggregate_year_summaries(summaries)
        item.update(totals)
        errors = [s.get("error") for s in summaries if s.get("error")]
        if errors:
            item["status"] = "partial"
            item["error"] = "; ".join(str(e) for e in errors if e)
        elif totals["failed"] > 0:
            item["status"] = "failed"
        else:
            item["status"] = "ok"
        return item

    except Exception as exc:
        logger.exception("national-scan 省份失败 [%s]: %s", province, exc)
        item.setdefault("access_status", "unknown")
        item["status"] = "failed"
        item["error"] = str(exc)
        return item


def run_national_scan(
    *,
    year: int = 2024,
    data_type: str = "school",
    provinces: list[str] | None = None,
    dry_run: bool = False,
    import_enabled: bool = True,
    max_pages: int = 50,
) -> dict[str, Any]:
    """
    全国批量扫描：按省份 access_status 决定 discover / download / import。

    blocked 省份不强行请求，标记 skipped_due_to_access_status。
    """
    started_at = datetime.now(timezone.utc)
    target_provinces = provinces or list_registered_provinces()
    unknown: list[str] = []
    for name in target_provinces:
        norm = normalize_province(name)
        if norm not in PROVINCES:
            unknown.append(name)
    if unknown:
        raise ValueError(f"未注册省份: {', '.join(unknown)}")

    items: list[dict[str, Any]] = []
    for province in target_provinces:
        norm = normalize_province(province)
        logger.info(
            "national-scan [%s] year=%s type=%s dry_run=%s import=%s",
            norm,
            year,
            data_type,
            dry_run,
            import_enabled,
        )
        items.append(
            _scan_single_province(
                norm,
                year=year,
                data_type=data_type,
                dry_run=dry_run,
                import_enabled=import_enabled,
                max_pages=max_pages,
            )
        )

    finished_at = datetime.now(timezone.utc)
    skipped = sum(1 for i in items if i.get("status") == "skipped_due_to_access_status")
    failed = sum(1 for i in items if i.get("status") == "failed")
    structured = sum(1 for i in items if i["province"] in STRUCTURED_PROVINCES)
    source_aware = sum(1 for i in items if i["province"] in SOURCE_AWARE_PROVINCES)

    report: dict[str, Any] = {
        "year": year,
        "data_type": data_type,
        "dry_run": dry_run,
        "import_enabled": import_enabled and not dry_run,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "summary": {
            "total_provinces": len(items),
            "structured": structured,
            "source_aware": source_aware,
            "skipped": skipped,
            "failed": failed,
        },
        "items": items,
    }

    out_path = national_scan_report_path(year, data_type)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(out_path)
    return report


def print_national_scan_summary(report: dict[str, Any]) -> None:
    """CLI 表格输出。"""
    print("\n========== National Scan Summary ==========")
    print(f"year={report['year']} type={report['data_type']} dry_run={report['dry_run']}")
    s = report["summary"]
    print(
        f"provinces={s['total_provinces']} structured={s['structured']} "
        f"source_aware={s['source_aware']} skipped={s['skipped']} failed={s['failed']}"
    )
    print(
        f"{'province':<6} {'access':<22} {'status':<28} {'pages':<6} "
        f"{'dl':<4} {'imp':<5} {'skip':<6} {'fail':<5}"
    )
    print("-" * 95)
    for row in report.get("items", []):
        print(
            f"{row.get('province', ''):<6} "
            f"{row.get('access_status', ''):<22} "
            f"{row.get('status', ''):<28} "
            f"{row.get('discovered_pages', 0):<6} "
            f"{row.get('downloaded_files', 0):<4} "
            f"{row.get('imported', 0):<5} "
            f"{row.get('skipped', 0):<6} "
            f"{row.get('failed', 0):<5}"
        )
    if report.get("report_path"):
        print(f"\nreport: {report['report_path']}")
    print("===========================================\n")
