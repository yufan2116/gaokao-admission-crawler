"""Phase 20.2 --ocr-limit 单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawlers.discovery import _build_ocr_limit_allowed_paths  # noqa: E402


def test_ocr_limit_first_n_unique() -> None:
    items = [
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/1.png",
            "source_title": "湖北省2024年本科普通批（首选物理）",
            "attachment_title": "1.png",
        },
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/2.png",
            "source_title": "湖北省2024年本科普通批（首选物理）",
            "attachment_title": "2.png",
        },
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/3.png",
            "source_title": "湖北省2024年本科普通批（首选物理）",
            "attachment_title": "3.png",
        },
    ]
    allowed, all_paths = _build_ocr_limit_allowed_paths(items, enable_ocr=True, ocr_limit=2)
    assert allowed is not None
    assert len(allowed) == 2
    assert len(all_paths) == 3
    assert len(all_paths - allowed) == 1


def test_ocr_limit_unlimited() -> None:
    items = [
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/1.png",
            "source_title": "t",
            "attachment_title": "1.png",
        },
    ]
    allowed, all_paths = _build_ocr_limit_allowed_paths(items, enable_ocr=True, ocr_limit=None)
    assert allowed is None
    assert len(all_paths) == 1


def test_ocr_limit_dedupe_same_path() -> None:
    items = [
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/1.png",
            "source_title": "历史",
            "attachment_title": "1.png",
        },
        {
            "ocr": True,
            "local_path": "data/raw/hubei/2024/school/attachments/1.png",
            "source_title": "物理",
            "attachment_title": "1.png",
        },
    ]
    allowed, all_paths = _build_ocr_limit_allowed_paths(items, enable_ocr=True, ocr_limit=5)
    assert len(all_paths) == 1


def main() -> int:
    tests = [
        test_ocr_limit_first_n_unique,
        test_ocr_limit_unlimited,
        test_ocr_limit_dedupe_same_path,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
