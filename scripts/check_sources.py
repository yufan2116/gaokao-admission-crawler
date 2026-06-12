"""
检查 JIANGSU_SOURCES 中 URL 配置情况。

用法:
    python scripts/check_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawlers.sources_registry import JIANGSU_SOURCES, check_sources_status  # noqa: E402


def main() -> None:
    if not JIANGSU_SOURCES:
        print("JIANGSU_SOURCES 为空，请在 crawlers/sources_registry.py 中添加配置")
        sys.exit(1)

    summary = check_sources_status()
    total_configured = 0
    total_missing = 0

    for row in summary:
        print(
            f"[{row['year']}][{row['data_type']}] "
            f"{row['configured']} configured, {row['missing']} missing"
        )
        if row.get("attachments_missing", 0) or row.get("attachments_configured", 0):
            print(
                f"  attachments: {row.get('attachments_configured', 0)} configured, "
                f"{row.get('attachments_missing', 0)} missing"
            )
        total_configured += row["configured"]
        total_missing += row["missing"]

    print(f"\nTotal: {total_configured} configured, {total_missing} missing URL(s)")

    if total_missing > 0:
        print("\n请在 crawlers/sources_registry.py 中为缺失项补全 url 字段。")


if __name__ == "__main__":
    main()
