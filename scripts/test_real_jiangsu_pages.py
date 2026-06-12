#!/usr/bin/env python3
"""
用 data/raw/jiangsu 已下载的 HTML 回归测试 parse_html_tables。

用法:
    python scripts/test_real_jiangsu_pages.py
    python scripts/test_real_jiangsu_pages.py --type rank
    python scripts/test_real_jiangsu_pages.py --type control --year 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import RAW_DIR
from parsers.parse_html_tables import parse_html_tables


def _iter_html_files(data_type: str, year: int | None) -> list[Path]:
    root = RAW_DIR / "jiangsu"
    if not root.exists():
        return []

    files: list[Path] = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir():
            continue
        if year is not None and year_dir.name != str(year):
            continue
        type_dir = year_dir / data_type
        if not type_dir.is_dir():
            continue
        for path in sorted(type_dir.glob("*.html")):
            if path.is_file():
                files.append(path)
    return files


def _print_file_report(path: Path, data_type: str, year: int | None) -> None:
    inferred_year = year
    if inferred_year is None:
        try:
            inferred_year = int(path.parent.parent.name)
        except ValueError:
            inferred_year = None

    df = parse_html_tables(
        path,
        data_type=data_type,
        default_year=inferred_year,
        default_province="江苏",
    )

    print(f"\n{'=' * 60}")
    print(f"文件: {path.relative_to(BASE_DIR)}")
    print(f"解析行数: {len(df)}")

    if df.empty:
        print("subject_type 分布: (无)")
        print("score 范围: (无)")
        print("前 5 行: (无)")
        return

    if "subject_type" in df.columns:
        dist = df["subject_type"].value_counts().to_dict()
        print(f"subject_type 分布: {dist}")
    else:
        print("subject_type 分布: (列不存在)")

    if "score" in df.columns:
        scores = pd.to_numeric(df["score"], errors="coerce").dropna()
        if not scores.empty:
            print(f"score 范围: {int(scores.min())} ~ {int(scores.max())}")
        else:
            print("score 范围: (无有效分数)")
    else:
        print("score 范围: (列不存在)")

    print("前 5 行:")
    print(df.head(5).to_string(index=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="江苏真实 HTML 页面解析回归测试")
    parser.add_argument("--type", choices=["rank", "control"], default=None, help="仅测试指定类型")
    parser.add_argument("--year", type=int, default=None, help="仅测试指定年份")
    args = parser.parse_args()

    types = [args.type] if args.type else ["rank", "control"]
    total_files = 0

    for data_type in types:
        files = _iter_html_files(data_type, args.year)
        print(f"\n>>> 扫描 {data_type} HTML: {len(files)} 个文件")
        if not files:
            print(f"  (未找到 data/raw/jiangsu/*/{data_type}/*.html)")
            continue
        for path in files:
            total_files += 1
            _print_file_report(path, data_type, args.year)

    if total_files == 0:
        print("\n未找到可测试的 HTML 文件。请先运行 discover-download-import 下载页面。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
