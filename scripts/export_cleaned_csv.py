"""
从 SQLite 按省份分目录导出 CSV。

用法:
    python scripts/export_cleaned_csv.py
    python scripts/export_cleaned_csv.py --type school --years 2024
    python main.py export-csv --type school --provinces 江苏 湖北 --years 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import EXPORT_CSV_DIR  # noqa: E402
from services.province_csv_export import export_province_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="按省份分目录导出 CSV")
    parser.add_argument(
        "--type",
        dest="record_types",
        action="append",
        choices=["school", "major", "control", "rank"],
        help="数据类型，可重复；默认 school",
    )
    parser.add_argument(
        "--provinces",
        nargs="*",
        default=None,
        help="省份列表，默认全部",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=None,
        help="年份列表，默认全部",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EXPORT_CSV_DIR),
        help=f"输出目录，默认 {EXPORT_CSV_DIR}",
    )
    parser.add_argument(
        "--merge-years",
        action="store_true",
        help="不按年份拆分文件",
    )
    args = parser.parse_args()

    report = export_province_csv(
        output_dir=Path(args.output_dir),
        record_types=args.record_types or ["school"],
        provinces=args.provinces,
        years=args.years,
        split_by_year=not args.merge_years,
    )
    for line in report.to_lines():
        print(line)
    if not report.total_rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
