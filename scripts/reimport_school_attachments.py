#!/usr/bin/env python3
"""重新导入 data/raw 下已下载的 school Excel（应用 admission_category / batch 元数据）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawlers.discovery import infer_school_metadata_from_title, infer_subject_type_from_title
from db.database import SessionLocal
from importers.file_import import import_file_to_db

RAW = ROOT / "data" / "raw" / "jiangsu"


def main() -> int:
    files = sorted(
        list(RAW.glob("*/school/attachments/*.xls"))
        + list(RAW.glob("*/school/attachments/*.xlsx"))
    )
    if not files:
        print("未找到 school 附件")
        return 1

    session = SessionLocal()
    total_inserted = 0
    total_skipped = 0
    total_failed = 0

    try:
        for path in files:
            year = int(path.parent.parent.parent.name)
            meta = infer_school_metadata_from_title(path.stem, source_title=path.stem)
            subject_type = infer_subject_type_from_title(path.stem)
            stats = import_file_to_db(
                session,
                path,
                "school",
                year,
                "江苏",
                subject_type=subject_type,
                admission_category=meta["admission_category"],
                batch=meta["batch"],
                write_debug_on_failure=False,
            )
            total_inserted += stats.inserted
            total_skipped += stats.skipped
            total_failed += stats.failed
            print(
                f"[{year}] {meta['admission_category']}/{meta['batch']} "
                f"+{stats.inserted} skip={stats.skipped} fail={stats.failed} | {path.name[:50]}"
            )
    finally:
        session.close()

    print(f"\n合计: inserted={total_inserted} skipped={total_skipped} failed={total_failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
