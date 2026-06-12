"""
Excel 解析本地测试脚本。

用法:
    python scripts/test_parse_excel.py path/to/sample.xlsx
"""

import sys
from pathlib import Path

# 将项目根目录加入 path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers.parse_excel import parse_excel_file, save_cleaned_csv  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/test_parse_excel.py <excel_path> [year]")
        sys.exit(1)

    excel_path = Path(sys.argv[1])
    default_year = int(sys.argv[2]) if len(sys.argv) > 2 else None

    df = parse_excel_file(excel_path, default_year=default_year)
    print(f"解析行数: {len(df)}")
    print(f"列名: {list(df.columns)}")
    if not df.empty:
        print(df.head().to_string())
        out = save_cleaned_csv(df, f"{excel_path.stem}_test.csv")
        print(f"已保存: {out}")


if __name__ == "__main__":
    main()
