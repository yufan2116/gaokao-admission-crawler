"""Phase 20.9 OCR 预计算 / 自然排序单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.image_sort import list_image_files, natural_sort_key  # noqa: E402
from validators.ocr_precompute import precompute_report_path  # noqa: E402


def test_natural_sort_key() -> None:
    names = ["10.png", "2.png", "1.png", "20.png", "3.png"]
    ordered = sorted(names, key=lambda n: natural_sort_key(Path(n)))
    assert ordered == ["1.png", "2.png", "3.png", "10.png", "20.png"]


def test_list_image_files_natural(tmp: Path) -> None:
    for name in ("10.png", "2.png", "1.png"):
        (tmp / name).write_bytes(b"x")
    assert [p.name for p in list_image_files(tmp)] == ["1.png", "2.png", "10.png"]


def test_report_path() -> None:
    p = precompute_report_path("hubei", 2024, "school")
    assert p.name == "ocr_precompute_hubei_2024_school.json"


def main() -> int:
    import tempfile

    failed = 0
    for fn in (test_natural_sort_key, test_report_path):
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            failed += 1

    with tempfile.TemporaryDirectory() as td:
        try:
            test_list_image_files_natural(Path(td))
            print("OK  test_list_image_files_natural")
        except Exception as exc:
            print(f"FAIL test_list_image_files_natural: {exc}")
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
