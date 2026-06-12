"""
按固定顺序批量导入江苏省 2024 年已下载 Excel。

用法:
    python scripts/import_jiangsu_2024.py

文件路径见 configs/jiangsu_2024_files.py。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import BASE_DIR  # noqa: E402
from configs.jiangsu_2024_files import JIANGSU_2024_IMPORT_FILES, JIANGSU_2024_META  # noqa: E402
from db.database import SessionLocal  # noqa: E402
from importers.excel_import import import_excel_to_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("import_jiangsu_2024")


def main() -> int:
    year = JIANGSU_2024_META["year"]
    province = JIANGSU_2024_META["province"]

    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    missing: list[str] = []

    session = SessionLocal()
    try:
        for entry in JIANGSU_2024_IMPORT_FILES:
            rel_path = entry["path"]
            abs_path = BASE_DIR / rel_path
            record_type = entry["type"]
            subject_type = entry.get("subject_type")
            title = entry.get("title", rel_path)

            label = f"[{record_type}] {title}"
            if subject_type:
                label += f" ({subject_type})"

            if not abs_path.exists():
                logger.warning("missing: %s → %s", label, rel_path)
                missing.append(rel_path)
                continue

            try:
                stats = import_excel_to_db(
                    session,
                    abs_path,
                    record_type=record_type,
                    default_year=year,
                    default_province=province,
                    subject_type=subject_type,
                )
            except Exception as exc:
                logger.error("failed: %s → %s", label, exc)
                failed.append(rel_path)
                continue

            if stats.inserted == 0 and stats.failed > 0:
                logger.error(
                    "failed: %s → inserted=0 failed=%d",
                    label,
                    stats.failed,
                )
                failed.append(rel_path)
                continue

            if stats.inserted == 0:
                logger.info(
                    "skipped: %s → inserted=0 skipped=%d",
                    label,
                    stats.skipped,
                )
                skipped.append(rel_path)
            else:
                logger.info(
                    "imported: %s → inserted=%d skipped=%d failed=%d",
                    label,
                    stats.inserted,
                    stats.skipped,
                    stats.failed,
                )
                imported.append(rel_path)
    finally:
        session.close()

    print("\n========== Import Summary ==========")
    print(f"imported ({len(imported)}):")
    for p in imported:
        print(f"  + {p}")
    print(f"skipped ({len(skipped)}):")
    for p in skipped:
        print(f"  ~ {p}")
    print(f"failed ({len(failed)}):")
    for p in failed:
        print(f"  ! {p}")
    print(f"missing ({len(missing)}):")
    for p in missing:
        print(f"  ? {p}")
    print("====================================")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
