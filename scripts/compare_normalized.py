"""
比较两个标准化 CSV 文件的结构与数据质量。

用法:
    python scripts/compare_normalized.py file_a.csv file_b.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _null_rate(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {}
    return {col: float(df[col].isna().mean()) for col in df.columns}


def _duplicate_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(1 - len(df.drop_duplicates()) / len(df))


def compare_csv(path_a: Path, path_b: Path) -> str:
    """比较两个 CSV，返回报告文本。"""
    df_a = pd.read_csv(path_a)
    df_b = pd.read_csv(path_b)

    lines: list[str] = []
    lines.append(f"A: {path_a}  ({len(df_a)} 行, {len(df_a.columns)} 列)")
    lines.append(f"B: {path_b}  ({len(df_b)} 行, {len(df_b.columns)} 列)")
    lines.append("")

    cols_a = set(df_a.columns)
    cols_b = set(df_b.columns)
    lines.append("列结构:")
    lines.append(f"  仅 A 有: {sorted(cols_a - cols_b) or '无'}")
    lines.append(f"  仅 B 有: {sorted(cols_b - cols_a) or '无'}")
    lines.append(f"  共有:   {sorted(cols_a & cols_b)}")
    lines.append("")

    lines.append("空值率:")
    rate_a = _null_rate(df_a)
    rate_b = _null_rate(df_b)
    for col in sorted(cols_a | cols_b):
        ra = rate_a.get(col, float("nan"))
        rb = rate_b.get(col, float("nan"))
        lines.append(f"  {col}: A={ra:.1%}  B={rb:.1%}")
    lines.append("")

    lines.append("重复率:")
    lines.append(f"  A: {_duplicate_rate(df_a):.1%}")
    lines.append(f"  B: {_duplicate_rate(df_b):.1%}")
    lines.append("")

    lines.append("数据量:")
    lines.append(f"  A: {len(df_a)} 行")
    lines.append(f"  B: {len(df_b)} 行")
    lines.append(f"  差值: {len(df_a) - len(df_b):+d}")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 3:
        print("用法: python scripts/compare_normalized.py <csv_a> <csv_b>")
        sys.exit(1)

    path_a = Path(sys.argv[1])
    path_b = Path(sys.argv[2])
    if not path_a.exists() or not path_b.exists():
        print("文件不存在")
        sys.exit(1)

    print(compare_csv(path_a, path_b))


if __name__ == "__main__":
    main()
