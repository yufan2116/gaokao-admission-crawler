"""
Excel 结构探查：预览 sheet、识别表头行（不修改数据库）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from parsers.parse_excel import detect_header_row

PREVIEW_ROWS = 20
PREVIEW_COLS = 15


def inspect_excel_file(file_path: str | Path) -> dict[str, Any]:
    """
    探查 Excel 文件结构。

    Returns:
        含 sheets 列表的字典，每项含 name / header_row / preview / non_null_counts
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    xl = pd.ExcelFile(path, engine=engine)
    report: dict[str, Any] = {"file": str(path), "sheets": []}

    for sheet_name in xl.sheet_names:
        df_raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine=engine)
        header_row = detect_header_row(df_raw)
        preview = df_raw.iloc[:PREVIEW_ROWS, :PREVIEW_COLS]
        non_null = df_raw.notna().sum()

        report["sheets"].append(
            {
                "name": sheet_name,
                "shape": df_raw.shape,
                "header_row": header_row,
                "preview": preview,
                "non_null_counts": non_null,
            }
        )

    return report


def format_inspect_report(report: dict[str, Any]) -> str:
    """将探查结果格式化为可读文本。"""
    lines: list[str] = []
    lines.append(f"文件: {report['file']}")
    lines.append(f"Sheet 数量: {len(report['sheets'])}")
    lines.append("")

    for sheet in report["sheets"]:
        lines.append("=" * 80)
        lines.append(f"Sheet: {sheet['name']}  (行×列: {sheet['shape'][0]}×{sheet['shape'][1]})")
        lines.append(f"推测表头行索引: {sheet['header_row']} (0-based)")
        lines.append("")
        lines.append("前 20 行 × 15 列预览:")
        lines.append(sheet["preview"].to_string())
        lines.append("")
        lines.append("各列非空数量 (前 15 列):")
        counts = sheet["non_null_counts"].iloc[:PREVIEW_COLS]
        for col_idx, cnt in counts.items():
            lines.append(f"  列 {col_idx}: {int(cnt)}")
        lines.append("")

    return "\n".join(lines)
