"""
Excel 结构探查脚本。

用法:
    python scripts/inspect_excel.py path/to/file.xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers.inspect_excel import format_inspect_report, inspect_excel_file  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/inspect_excel.py <excel_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    try:
        report = inspect_excel_file(path)
        print(format_inspect_report(report))
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(1)
    except Exception as exc:
        print(f"探查失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
