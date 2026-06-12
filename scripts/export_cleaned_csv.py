"""
从 SQLite 导出清洗后的 CSV（占位：下一阶段实现入库后可导出）。

当前可用于导出 parse-excel 生成的 cleaned CSV 列表。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CLEANED_DIR  # noqa: E402


def main() -> None:
    cleaned_dir = CLEANED_DIR
    if not cleaned_dir.exists():
        print(f"目录不存在: {cleaned_dir}")
        sys.exit(1)

    csv_files = sorted(cleaned_dir.glob("*.csv"))
    if not csv_files:
        print(f"{cleaned_dir} 下暂无 CSV 文件")
        sys.exit(0)

    print(f"共 {len(csv_files)} 个清洗文件:")
    for f in csv_files:
        print(f"  - {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
