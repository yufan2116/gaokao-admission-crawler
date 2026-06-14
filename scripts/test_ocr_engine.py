"""Phase 20.8 OCR 引擎单例与缓存单元测试（不依赖 PaddleOCR）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.ocr_engine import (  # noqa: E402
    image_cache_key,
    load_ocr_cache,
    ocr_cache_path,
    save_ocr_cache,
    uses_ocr_engine_singleton,
)


def test_singleton_flag() -> None:
    assert uses_ocr_engine_singleton() is True


def test_cache_roundtrip(tmp_path: Path) -> None:
    from config import OCR_CACHE_DIR

    img = tmp_path / "sample.png"
    img.write_bytes(b"fake-png-bytes")
    items = [{"text": "北京大学", "score": 0.99, "x_center": 1.0, "y_center": 2.0}]
    path = save_ocr_cache(img, items, engine="paddle")
    assert path == ocr_cache_path(img, "paddle")
    loaded = load_ocr_cache(img, "paddle")
    assert loaded is not None
    assert loaded[0]["text"] == "北京大学"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert image_cache_key(img) == payload["image_sha256"]
    assert payload["engine"] == "paddle"

    path_r = save_ocr_cache(img, items, engine="rapidocr")
    assert path_r == ocr_cache_path(img, "rapidocr")
    assert path_r != path
    loaded_r = load_ocr_cache(img, "rapidocr")
    assert loaded_r is not None
    assert load_ocr_cache(img, "paddle") is not None


def main() -> int:
    import tempfile

    failed = 0
    tests = [test_singleton_flag]
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            failed += 1

    with tempfile.TemporaryDirectory() as td:
        import config
        import parsers.ocr_engine as oe

        old = config.OCR_CACHE_DIR
        config.OCR_CACHE_DIR = Path(td) / "ocr"
        oe.OCR_CACHE_DIR = config.OCR_CACHE_DIR
        try:
            test_cache_roundtrip(Path(td))
            print("OK  test_cache_roundtrip")
        except Exception as exc:
            print(f"FAIL test_cache_roundtrip: {exc}")
            failed += 1
        finally:
            config.OCR_CACHE_DIR = old
            oe.OCR_CACHE_DIR = old

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
