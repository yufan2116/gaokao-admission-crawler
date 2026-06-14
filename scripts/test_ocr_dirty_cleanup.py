"""Phase 20.6 OCR 脏数据清理单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validators.ocr_dirty_cleanup import is_ocr_dirty_school_record  # noqa: E402


def _row(**kwargs):
    defaults = {
        "id": 1,
        "source_url": "ocr_experimental:/tmp/1.png",
        "school_code": "A00104",
        "school_name": "北京大学",
        "major_group": "第04组",
        "min_score": 679.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_valid_ocr_row_not_dirty() -> None:
    assert is_ocr_dirty_school_record(_row()) is False


def test_digit_school_name_is_dirty() -> None:
    assert is_ocr_dirty_school_record(_row(school_name="4", school_code="A0010")) is True


def test_non_ocr_source_not_dirty() -> None:
    assert (
        is_ocr_dirty_school_record(
            _row(source_url="/data/raw/hubei/file.xlsx", school_name="4")
        )
        is False
    )


def main() -> int:
    tests = [test_valid_ocr_row_not_dirty, test_digit_school_name_is_dirty, test_non_ocr_source_not_dirty]
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
