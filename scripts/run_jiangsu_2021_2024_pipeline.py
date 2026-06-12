"""
江苏 2021-2024 全量跑数流水线（Phase 7.4）。

依次：init-db → rank/control/school 发现下载导入 → 各年 data-quality。

用法:
    python scripts/run_jiangsu_2021_2024_pipeline.py
    python scripts/run_jiangsu_2021_2024_pipeline.py --dry-run
    python scripts/run_jiangsu_2021_2024_pipeline.py --reset-db
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import BASE_DIR, CLEANED_DIR, DEFAULT_PROVINCE  # noqa: E402
from crawlers.discovery import run_discover_download_import  # noqa: E402
from db.database import SessionLocal  # noqa: E402
from db.init_db import init_database  # noqa: E402
from validators.data_quality import run_data_quality_check  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")

YEARS = [2021, 2022, 2023, 2024]
DATA_TYPES = ["rank", "control", "school"]
MAX_PAGES = 100

PIPELINE_REPORT = CLEANED_DIR / "pipeline_report_jiangsu_2021_2024.json"
IMPORT_ERRORS_REPORT = CLEANED_DIR / "import_errors_jiangsu_2021_2024.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_record(
    step: str,
    *,
    year: int | None = None,
    data_type: str | None = None,
    status: str = "ok",
    discovered_pages: int = 0,
    downloaded_files: int = 0,
    imported: int = 0,
    skipped: int = 0,
    failed: int = 0,
    error_message: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "step": step,
        "year": year,
        "type": data_type,
        "status": status,
        "discovered_pages": discovered_pages,
        "downloaded_files": downloaded_files,
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "error_message": error_message,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if extra:
        rec.update(extra)
    return rec


def _aggregate_summary(summary: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "discovered_pages": 0,
        "downloaded_files": 0,
        "imported": 0,
        "skipped": 0,
        "failed": 0,
    }
    for row in summary:
        totals["discovered_pages"] += row.get("discovered_pages", 0)
        totals["downloaded_files"] += row.get("downloaded_files", 0)
        totals["imported"] += row.get("imported", 0)
        totals["skipped"] += row.get("skipped", 0)
        totals["failed"] += row.get("failed", 0)
    return totals


def reset_database() -> None:
    """删除 SQLite 文件前释放 SQLAlchemy 连接池。"""
    from db.database import engine

    engine.dispose()
    db_path = BASE_DIR / "gaokao.db"
    for suffix in ("-wal", "-shm", ""):
        p = Path(str(db_path) + suffix) if suffix else db_path
        if not p.exists():
            continue
        try:
            p.unlink()
            logger.info("已删除: %s", p)
        except PermissionError as exc:
            raise PermissionError(
                f"无法删除 {p}：文件被占用。请关闭占用 gaokao.db 的进程"
                f"（如 uvicorn / 其他 Python），然后重试。"
            ) from exc


def run_init_db_step(steps: list[dict]) -> None:
    started = _utc_now()
    try:
        init_database()
        steps.append(
            _step_record(
                "init-db",
                status="ok",
                started_at=started,
                finished_at=_utc_now(),
            )
        )
    except Exception as exc:
        steps.append(
            _step_record(
                "init-db",
                status="failed",
                error_message=str(exc),
                started_at=started,
                finished_at=_utc_now(),
            )
        )
        raise


def run_discover_step(
    steps: list[dict],
    data_type: str,
    dry_run: bool,
    max_pages: int,
    all_import_errors: list[dict],
) -> None:
    step_name = "discover-only" if dry_run else "discover-download-import"
    started = _utc_now()
    try:
        result = run_discover_download_import(
            years=YEARS,
            province=DEFAULT_PROVINCE,
            data_type=data_type,
            max_pages=max_pages,
            dry_run=dry_run,
        )
        totals = _aggregate_summary(result.get("summary") or [])
        status = "ok"
        if any(row.get("error") for row in result.get("summary") or []):
            status = "partial"
        if totals["failed"] > 0:
            status = "partial"

        steps.append(
            _step_record(
                step_name,
                data_type=data_type,
                status=status,
                started_at=started,
                finished_at=_utc_now(),
                **totals,
                extra={
                    "per_year": result.get("summary"),
                    "combined_report": result.get("combined_report_path"),
                },
            )
        )
        if not dry_run:
            all_import_errors.extend(result.get("import_errors") or [])
    except Exception as exc:
        logger.exception("步骤失败 [%s]: %s", data_type, exc)
        steps.append(
            _step_record(
                step_name,
                data_type=data_type,
                status="failed",
                error_message=str(exc),
                started_at=started,
                finished_at=_utc_now(),
            )
        )


def run_data_quality_step(steps: list[dict], year: int) -> None:
    started = _utc_now()
    try:
        session = SessionLocal()
        try:
            report = run_data_quality_check(session, year, DEFAULT_PROVINCE)
        finally:
            session.close()

        status = "ok"
        if report.rank_subject_coverage:
            status = "partial"
        if report.rank_monotonic_violations:
            status = "partial"

        steps.append(
            _step_record(
                "data-quality",
                year=year,
                status=status,
                started_at=started,
                finished_at=_utc_now(),
                extra={
                    "table_counts": report.table_counts,
                    "rank_missing_subjects": report.rank_subject_coverage,
                    "rank_monotonic_violations": len(report.rank_monotonic_violations),
                    "control_batches": report.control_batches,
                },
            )
        )
    except Exception as exc:
        steps.append(
            _step_record(
                "data-quality",
                year=year,
                status="failed",
                error_message=str(exc),
                started_at=started,
                finished_at=_utc_now(),
            )
        )


def save_reports(
    steps: list[dict],
    import_errors: list[dict],
    *,
    dry_run: bool,
    reset_db: bool,
    started_at: str,
) -> Path:
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "province": DEFAULT_PROVINCE,
        "years": YEARS,
        "dry_run": dry_run,
        "reset_db": reset_db,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "steps": steps,
    }
    PIPELINE_REPORT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("流水线报告: %s", PIPELINE_REPORT)

    IMPORT_ERRORS_REPORT.write_text(
        json.dumps(
            {
                "generated_at": _utc_now(),
                "errors": import_errors,
                "total": len(import_errors),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if import_errors:
        logger.warning("导入错误 %d 条: %s", len(import_errors), IMPORT_ERRORS_REPORT)
    else:
        logger.info("导入错误报告: %s (无错误)", IMPORT_ERRORS_REPORT)

    return PIPELINE_REPORT


def main() -> int:
    parser = argparse.ArgumentParser(description="江苏 2021-2024 全量跑数流水线")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅发现公告，不下载、不导入、不 init-db",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="运行前删除 gaokao.db 并重新 init-db",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"列表页扫描上限（默认 {MAX_PAGES}）",
    )
    args = parser.parse_args()

    started_at = _utc_now()
    steps: list[dict] = []
    import_errors: list[dict] = []

    if args.dry_run:
        logger.info("=== DRY-RUN：仅发现，不下载/导入 ===")
        for data_type in DATA_TYPES:
            run_discover_step(steps, data_type, True, args.max_pages, import_errors)
    else:
        if args.reset_db:
            logger.info("=== 重置数据库 ===")
            reset_database()

        run_init_db_step(steps)

        for data_type in DATA_TYPES:
            logger.info("=== discover-download-import: %s ===", data_type)
            run_discover_step(steps, data_type, False, args.max_pages, import_errors)

        for year in YEARS:
            logger.info("=== data-quality: %s ===", year)
            run_data_quality_step(steps, year)

    report_path = save_reports(
        steps,
        import_errors,
        dry_run=args.dry_run,
        reset_db=args.reset_db,
        started_at=started_at,
    )

    failed_steps = [s for s in steps if s.get("status") == "failed"]
    print("\n========== Pipeline Summary ==========")
    print(f"report: {report_path}")
    print(f"import_errors: {IMPORT_ERRORS_REPORT} ({len(import_errors)} items)")
    print(f"steps: {len(steps)} total, {len(failed_steps)} failed")
    for s in steps:
        print(
            f"  [{s.get('status')}] {s.get('step')} "
            f"type={s.get('type')} year={s.get('year')} "
            f"disc={s.get('discovered_pages')} imp={s.get('imported')} "
            f"fail={s.get('failed')}"
        )
    print("======================================")

    return 1 if failed_steps else 0


if __name__ == "__main__":
    sys.exit(main())
