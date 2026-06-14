"""Phase 20.14 图片自然序排序单元测试。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.image_sort import (  # noqa: E402
    list_image_files,
    natural_sort_key,
    sort_image_filenames,
    sort_image_paths,
)


def test_numeric_png() -> None:
    names = ["1.png", "10.png", "2.png"]
    assert sort_image_filenames(names) == ["1.png", "2.png", "10.png"]


def test_page_prefix() -> None:
    names = ["page1.png", "page10.png", "page2.png"]
    assert sort_image_filenames(names) == ["page1.png", "page2.png", "page10.png"]


def test_hubei_page_names() -> None:
    names = [
        "hubei_2024_wuli_page10.png",
        "hubei_2024_wuli_page1.png",
        "hubei_2024_wuli_page2.png",
    ]
    ordered = sort_image_filenames(names)
    assert ordered == [
        "hubei_2024_wuli_page1.png",
        "hubei_2024_wuli_page2.png",
        "hubei_2024_wuli_page10.png",
    ]


def test_extension_case_insensitive() -> None:
    names = ["2.JPG", "1.png", "10.PNG", "3.jpg"]
    ordered = sort_image_filenames(names)
    assert ordered == ["1.png", "2.JPG", "3.jpg", "10.PNG"]


def test_list_image_files_directory() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("10.png", "2.png", "1.png", "20.png"):
            (tmp / name).write_bytes(b"x")
        assert [p.name for p in list_image_files(tmp)] == [
            "1.png",
            "2.png",
            "10.png",
            "20.png",
        ]


def test_sort_image_paths() -> None:
    paths = sort_image_paths([Path("10.png"), Path("2.png"), Path("1.png")])
    assert [p.name for p in paths] == ["1.png", "2.png", "10.png"]


def test_natural_sort_key_numeric() -> None:
    assert natural_sort_key("1.png") < natural_sort_key("2.png")
    assert natural_sort_key("2.png") < natural_sort_key("10.png")


def main() -> int:
    tests = [
        test_numeric_png,
        test_page_prefix,
        test_hubei_page_names,
        test_extension_case_insensitive,
        test_list_image_files_directory,
        test_sort_image_paths,
        test_natural_sort_key_numeric,
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
