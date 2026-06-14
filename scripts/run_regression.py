"""
MVP+ 回归测试（Phase 16）。

用法:
    python scripts/run_regression.py

输出:
    data/cleaned/regression_report.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.release import STABLE_VERSION_ID, STABLE_VERSION_LABEL  # noqa: E402
from config import BASE_DIR  # noqa: E402
from db.database import SessionLocal  # noqa: E402
from normalizers.province import normalize_province  # noqa: E402
from validators.data_quality import DataQualityReport, run_data_quality_check  # noqa: E402

REPORT_PATH = BASE_DIR / "data" / "cleaned" / "regression_report.json"

DATA_QUALITY_CASES: list[tuple[str, int]] = [
    ("江苏", 2024),
    ("浙江", 2024),
    ("山东", 2024),
    ("广东", 2024),
]

API_CASES: list[dict[str, Any]] = [
    {"name": "health", "method": "GET", "path": "/health", "expect_status": 200},
    {
        "name": "province_availability",
        "method": "GET",
        "path": "/province-availability",
        "expect_status": 200,
        "min_items": 1,
    },
    {
        "name": "schools_jiangsu_2024",
        "method": "GET",
        "path": "/schools",
        "params": {"province": "江苏", "year": 2024},
        "expect_status": 200,
        "min_total": 1,
    },
    {
        "name": "schools_zhejiang_2024",
        "method": "GET",
        "path": "/schools",
        "params": {"province": "浙江", "year": 2024},
        "expect_status": 200,
        "min_total": 1,
    },
    {
        "name": "schools_by_rank_shandong_2024",
        "method": "GET",
        "path": "/schools/by-rank",
        "params": {
            "province": "山东",
            "year": 2024,
            "subject_type": "综合改革",
            "rank": 50000,
        },
        "expect_status": 200,
    },
    {
        "name": "schools_guangdong_2024",
        "method": "GET",
        "path": "/schools",
        "params": {"province": "广东", "year": 2024},
        "expect_status": 200,
        "min_total": 1,
    },
]

DASHBOARD_CASES: list[dict[str, Any]] = [
    {
        "name": "home_stats_total",
        "check": "school_total_non_negative",
    },
    {
        "name": "province_availability_rows",
        "check": "province_availability_nonempty",
    },
    {
        "name": "national_overview",
        "check": "national_overview_smoke",
    },
]

NATIONAL_SCAN_DRY_RUN_CASE = {
    "name": "national_scan_dry_run",
    "year": 2024,
    "data_type": "school",
}


def _serialize_report(report: DataQualityReport) -> dict[str, Any]:
    data = asdict(report)
    data["school_min_score_range"] = list(report.school_min_score_range)
    for key, val in list(data.get("rank_score_ranges", {}).items()):
        data["rank_score_ranges"][key] = list(val)
    return data


def run_data_quality_tests() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    session = SessionLocal()
    try:
        for province, year in DATA_QUALITY_CASES:
            province_norm = normalize_province(province)
            entry: dict[str, Any] = {
                "name": f"data_quality_{province_norm}_{year}",
                "command": f"python main.py data-quality --province {province} --year {year}",
                "province": province_norm,
                "year": year,
            }
            try:
                report = run_data_quality_check(session, year=year, province=province_norm)
                school_count = report.table_counts.get("school_admission_line", 0)
                entry["report"] = _serialize_report(report)
                entry["school_count"] = school_count
                entry["passed"] = school_count > 0
                if not entry["passed"]:
                    entry["error"] = "school_admission_line 记录数为 0"
            except Exception as exc:
                entry["passed"] = False
                entry["error"] = str(exc)
            results.append(entry)
    finally:
        session.close()
    return results


def run_api_tests() -> list[dict[str, Any]]:
    from fastapi.testclient import TestClient

    from app.api import app

    client = TestClient(app)
    results: list[dict[str, Any]] = []
    for case in API_CASES:
        entry: dict[str, Any] = {
            "name": case["name"],
            "method": case["method"],
            "path": case["path"],
            "params": case.get("params"),
        }
        try:
            if case["method"] == "GET":
                response = client.get(case["path"], params=case.get("params"))
            else:
                response = client.request(case["method"], case["path"], params=case.get("params"))
            entry["status_code"] = response.status_code
            body = response.json() if response.headers.get("content-type", "").startswith(
                "application/json"
            ) else {}
            entry["passed"] = response.status_code == case.get("expect_status", 200)
            if entry["passed"] and "min_total" in case:
                total = body.get("total", 0)
                entry["total"] = total
                entry["passed"] = total >= case["min_total"]
                if not entry["passed"]:
                    entry["error"] = f"total={total} < min_total={case['min_total']}"
            if entry["passed"] and "min_items" in case:
                items = body.get("items") or []
                entry["item_count"] = len(items)
                entry["passed"] = len(items) >= case["min_items"]
                if not entry["passed"]:
                    entry["error"] = f"items={len(items)} < min_items={case['min_items']}"
            if entry["passed"] and case["name"] == "health":
                entry["passed"] = body.get("status") == "ok"
            if entry["passed"] and case["name"] == "province_availability":
                entry["passed"] = all("access_status" in item for item in body.get("items", []))
                if not entry["passed"]:
                    entry["error"] = "缺少 access_status 字段"
        except Exception as exc:
            entry["passed"] = False
            entry["error"] = str(exc)
        results.append(entry)
    return results


def run_dashboard_tests() -> list[dict[str, Any]]:
    from dashboard.data_access import get_home_stats, get_national_overview, get_province_availability

    results: list[dict[str, Any]] = []
    for case in DASHBOARD_CASES:
        entry: dict[str, Any] = {"name": case["name"], "check": case["check"]}
        try:
            if case["check"] == "school_total_non_negative":
                stats = get_home_stats()
                total = int(stats["school_total"])
                entry["school_total"] = total
                entry["passed"] = total >= 0
                if total == 0:
                    entry["warning"] = "school 记录数为 0，请确认 gaokao.db 已入库"
            elif case["check"] == "province_availability_nonempty":
                df = get_province_availability()
                entry["row_count"] = len(df)
                entry["passed"] = len(df) > 0 and "Access Status" in df.columns
                if not entry["passed"]:
                    entry["error"] = "Province Availability 为空或缺少 Access Status 列"
            elif case["check"] == "national_overview_smoke":
                overview = get_national_overview()
                entry["structured_count"] = overview["structured_count"]
                entry["source_aware_count"] = overview["source_aware_count"]
                entry["passed"] = (
                    overview["structured_count"] == 4
                    and overview["source_aware_count"] == 7
                    and overview["school_total"] >= 0
                    and len(overview["access_status_distribution"]) >= 1
                )
                if not entry["passed"]:
                    entry["error"] = "National Overview 指标异常"
            else:
                entry["passed"] = False
                entry["error"] = f"未知检查: {case['check']}"
        except Exception as exc:
            entry["passed"] = False
            entry["error"] = str(exc)
        results.append(entry)
    return results


def run_national_scan_dry_run_test() -> dict[str, Any]:
    from services.national_scan import national_scan_report_path, run_national_scan

    entry: dict[str, Any] = {
        "name": NATIONAL_SCAN_DRY_RUN_CASE["name"],
        "command": "python main.py national-scan --year 2024 --type school --dry-run",
    }
    try:
        report = run_national_scan(
            year=NATIONAL_SCAN_DRY_RUN_CASE["year"],
            data_type=NATIONAL_SCAN_DRY_RUN_CASE["data_type"],
            dry_run=True,
            import_enabled=False,
            max_pages=5,
        )
        summary = report.get("summary") or {}
        skipped = int(summary.get("skipped") or 0)
        entry["summary"] = summary
        entry["report_path"] = str(national_scan_report_path(2024, "school"))
        entry["passed"] = (
            summary.get("total_provinces") == 11
            and len(report.get("items") or []) == 11
            and skipped >= 3
            and all(item.get("access_status") for item in report.get("items", []))
            and Path(entry["report_path"]).exists()
        )
        if not entry["passed"]:
            entry["error"] = (
                f"total={summary.get('total_provinces')} skipped={skipped} "
                f"failed={summary.get('failed')}"
            )
    except Exception as exc:
        entry["passed"] = False
        entry["error"] = str(exc)
    return entry


def _summarize(section: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(1 for r in section if r.get("passed"))
    failed = sum(1 for r in section if not r.get("passed"))
    return {"passed": passed, "failed": failed, "total": len(section)}


def build_report() -> dict[str, Any]:
    dq = run_data_quality_tests()
    api = run_api_tests()
    dash = run_dashboard_tests()
    national = run_national_scan_dry_run_test()
    summary = {
        "data_quality": _summarize(dq),
        "api": _summarize(api),
        "dashboard": _summarize(dash),
        "national_scan": {"passed": 1 if national.get("passed") else 0, "failed": 0 if national.get("passed") else 1, "total": 1},
    }
    total_failed = (
        summary["data_quality"]["failed"]
        + summary["api"]["failed"]
        + summary["dashboard"]["failed"]
        + summary["national_scan"]["failed"]
    )
    total_passed = (
        summary["data_quality"]["passed"]
        + summary["api"]["passed"]
        + summary["dashboard"]["passed"]
        + summary["national_scan"]["passed"]
    )
    return {
        "version": STABLE_VERSION_ID,
        "version_label": STABLE_VERSION_LABEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            **summary,
            "passed": total_passed,
            "failed": total_failed,
            "total": total_passed + total_failed,
        },
        "overall": "pass" if total_failed == 0 else "fail",
        "data_quality": dq,
        "api_tests": api,
        "dashboard_tests": dash,
        "national_scan_dry_run": national,
    }


def main() -> int:
    report = build_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Regression report: {report['overall'].upper()}")
    print(f"  data_quality: {report['summary']['data_quality']}")
    print(f"  api:          {report['summary']['api']}")
    print(f"  dashboard:    {report['summary']['dashboard']}")
    print(f"  national_scan: {report['summary']['national_scan']}")
    print(f"Written to {REPORT_PATH}")

    for section_key in ("data_quality", "api_tests", "dashboard_tests"):
        for item in report[section_key]:
            if not item.get("passed"):
                label = item.get("name") or item.get("command", section_key)
                print(f"  FAIL: {label} — {item.get('error') or item.get('warning', '')}")
    ns = report.get("national_scan_dry_run") or {}
    if not ns.get("passed"):
        print(f"  FAIL: {ns.get('name')} — {ns.get('error') or ns.get('warning', '')}")

    return 0 if report["overall"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
