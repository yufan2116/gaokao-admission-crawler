"""
OCR 引擎抽象（Phase 20.8 / 20.11）。

支持 paddle（默认）与 rapidocr；所有推理经 get_ocr_engine() 单例复用。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import OCR_CACHE_DIR

logger = logging.getLogger(__name__)

DEFAULT_OCR_ENGINE = "paddle"
VALID_OCR_ENGINES = frozenset({"paddle", "rapidocr"})
VALID_OCR_ENGINE_MODES = frozenset({"paddle", "rapidocr", "hybrid"})

_ENGINE_INSTANCES: dict[str, Any] = {}
_LAST_ENGINE_KEY: str | None = None
_LAST_GET_RECREATED: bool = False


def normalize_ocr_engine_mode(engine: str | None) -> str:
    """CLI / 流程 engine 模式（含 hybrid）。"""
    if not engine:
        return DEFAULT_OCR_ENGINE
    key = str(engine).lower().strip()
    if key not in VALID_OCR_ENGINE_MODES:
        raise ValueError(f"不支持的 OCR engine: {engine!r}，可选: paddle, rapidocr, hybrid")
    return key


def is_hybrid_engine_mode(engine: str | None) -> bool:
    return normalize_ocr_engine_mode(engine) == "hybrid"


def normalize_ocr_engine(engine: str | None) -> str:
    """实际推理 engine（paddle | rapidocr）。"""
    key = normalize_ocr_engine_mode(engine)
    if key == "hybrid":
        raise ValueError("hybrid 不是推理 engine，请使用 run_hybrid_image_parse")
    return key


def paddleocr_available() -> bool:
    try:
        import paddleocr  # noqa: F401

        return True
    except ImportError:
        return False
    except OSError:
        return False


def rapidocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False
    except OSError:
        return False


def onnxruntime_available() -> bool:
    try:
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False
    except OSError:
        return False


def ocr_engine_available(engine: str | None = None) -> bool:
    key = normalize_ocr_engine(engine)
    if key == "paddle":
        return paddleocr_available()
    return rapidocr_available()


def get_engine_version(engine: str | None = None) -> str:
    key = normalize_ocr_engine(engine)
    if key == "paddle":
        return importlib.metadata.version("paddleocr") if _pkg_installed("paddleocr") else "unknown"
    if key == "rapidocr":
        if _pkg_installed("rapidocr-onnxruntime"):
            return importlib.metadata.version("rapidocr-onnxruntime")
        return "unknown"
    return "unknown"


def _pkg_installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _configure_paddle_runtime() -> None:
    """Windows/CPU 上禁用 oneDNN+PIR 组合，避免 Paddle 3.3+ 崩溃。"""
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")


PRODUCTION_PADDLE_INIT_KWARGS: dict[str, Any] = {
    "lang": "ch",
    "enable_mkldnn": False,
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_textline_orientation": False,
}


def get_ocr_engine(engine: str | None = None) -> Any:
    """返回指定 engine 的全局单例；首次调用时加载模型。"""
    global _LAST_GET_RECREATED, _LAST_ENGINE_KEY
    key = normalize_ocr_engine(engine)
    if key in _ENGINE_INSTANCES:
        _LAST_GET_RECREATED = False
        _LAST_ENGINE_KEY = key
        return _ENGINE_INSTANCES[key]

    if key == "paddle":
        if not paddleocr_available():
            raise RuntimeError("ocr_not_installed")
        _configure_paddle_runtime()
        from paddleocr import PaddleOCR

        init_kwargs: dict[str, Any] = {
            "lang": "ch",
            "enable_mkldnn": False,
        }
        try:
            inst = PaddleOCR(
                **init_kwargs,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            inst = PaddleOCR(**init_kwargs)
    else:
        if not rapidocr_available():
            raise RuntimeError("rapidocr_not_installed")
        from rapidocr_onnxruntime import RapidOCR

        inst = RapidOCR()

    _ENGINE_INSTANCES[key] = inst
    _LAST_GET_RECREATED = True
    _LAST_ENGINE_KEY = key
    logger.debug("OCR 引擎已初始化 [%s]", key)
    return inst


def ocr_engine_was_recreated(engine: str | None = None) -> bool:
    """最近一次 get_ocr_engine() 是否新建了实例。"""
    if engine is not None and normalize_ocr_engine(engine) != _LAST_ENGINE_KEY:
        return False
    return _LAST_GET_RECREATED


def uses_ocr_engine_singleton() -> bool:
    return True


def image_cache_key(image_path: Path) -> str:
    digest = hashlib.sha256()
    with image_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ocr_cache_path(image_path: Path, engine: str | None = None) -> Path:
    key = normalize_ocr_engine(engine)
    return OCR_CACHE_DIR / key / f"{image_cache_key(image_path)}.json"


def _legacy_paddle_cache_path(image_path: Path) -> Path:
    return OCR_CACHE_DIR / f"{image_cache_key(image_path)}.json"


def _read_cache_file(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("OCR 缓存读取失败 [%s]: %s", path.name, exc)
        return None
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    return items


def load_ocr_cache(image_path: Path, engine: str | None = None) -> list[dict[str, Any]] | None:
    key = normalize_ocr_engine(engine)
    cached = _read_cache_file(ocr_cache_path(image_path, key))
    if cached is not None:
        return cached
    if key == "paddle":
        return _read_cache_file(_legacy_paddle_cache_path(image_path))
    return None


def _json_safe(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def save_ocr_cache(
    image_path: Path,
    items: list[dict[str, Any]],
    *,
    engine: str | None = None,
) -> Path:
    key = normalize_ocr_engine(engine)
    out_dir = OCR_CACHE_DIR / key
    out_dir.mkdir(parents=True, exist_ok=True)
    path = ocr_cache_path(image_path, key)
    payload = {
        "image": image_path.name,
        "image_sha256": image_cache_key(image_path),
        "engine": key,
        "engine_version": get_engine_version(key),
        "items": _json_safe(items),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _box_centers(box: Any) -> tuple[float, float]:
    if box is None:
        return 0.0, 0.0
    if hasattr(box, "tolist"):
        box = box.tolist()
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(
        isinstance(v, (int, float)) for v in box
    ):
        x_center = (float(box[0]) + float(box[2])) / 2
        y_center = (float(box[1]) + float(box[3])) / 2
        return x_center, y_center
    xs: list[float] = []
    ys: list[float] = []
    for point in box:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _ocr_item(text: str, box: Any, score: float | None) -> dict[str, Any]:
    x_center, y_center = _box_centers(box)
    return {
        "text": text,
        "score": score,
        "box": box,
        "x_center": x_center,
        "y_center": y_center,
    }


def _items_from_legacy_result(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not raw:
        return items
    for block in raw:
        if not block:
            continue
        for line in block:
            if not line or len(line) < 2:
                continue
            box, text_info = line[0], line[1]
            text = (text_info[0] or "").strip()
            score = float(text_info[1]) if len(text_info) > 1 else None
            if text:
                items.append(_ocr_item(text, box, score))
    return items


def _items_from_modern_page(page: Any) -> list[dict[str, Any]]:
    if hasattr(page, "get"):
        data = page
    elif isinstance(page, dict):
        data = page
    else:
        return []
    texts = data.get("rec_texts") or data.get("rec_text") or []
    scores = data.get("rec_scores") or data.get("rec_score") or []
    polys = data.get("rec_polys") or data.get("dt_polys") or data.get("rec_boxes") or []
    items: list[dict[str, Any]] = []
    for idx, text in enumerate(texts):
        text = (text or "").strip()
        if not text:
            continue
        box = polys[idx] if idx < len(polys) else None
        score = float(scores[idx]) if idx < len(scores) else None
        items.append(_ocr_item(text, box, score))
    return items


def _normalize_paddle_output(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        if not raw:
            return []
        first = raw[0]
        if isinstance(first, list):
            return _items_from_legacy_result(raw)
        return _items_from_modern_page(first)
    return _items_from_modern_page(raw)


def _run_paddle_predict(ocr_engine: Any, prepared_path: Path) -> list[dict[str, Any]]:
    img = str(prepared_path)
    if hasattr(ocr_engine, "predict"):
        raw = list(ocr_engine.predict(img))
        if raw:
            return _items_from_modern_page(raw[0])
        return []
    raw = ocr_engine.ocr(img, cls=False)
    return _normalize_paddle_output(raw)


def _items_from_rapidocr_result(result: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not result:
        return items
    for row in result:
        if not row or len(row) < 2:
            continue
        box, text = row[0], row[1]
        text = (text or "").strip()
        if not text:
            continue
        score: float | None = None
        if len(row) > 2 and row[2] is not None:
            try:
                score = float(row[2])
            except (TypeError, ValueError):
                score = None
        items.append(_ocr_item(text, box, score))
    return items


def _run_rapidocr_predict(ocr_engine: Any, prepared_path: Path) -> list[dict[str, Any]]:
    output = ocr_engine(str(prepared_path))
    result = output[0] if isinstance(output, tuple) else output
    return _items_from_rapidocr_result(result)


def _run_engine_predict(engine_key: str, ocr_engine: Any, prepared_path: Path) -> list[dict[str, Any]]:
    if engine_key == "rapidocr":
        return _run_rapidocr_predict(ocr_engine, prepared_path)
    return _run_paddle_predict(ocr_engine, prepared_path)


def _parser_used_name(engine_key: str) -> str:
    return "rapidocr" if engine_key == "rapidocr" else "paddleocr"


@dataclass
class OcrInferenceResult:
    items: list[dict[str, Any]]
    cache_hit: bool
    cache_miss: bool
    parser_used: str
    ocr_engine_recreated: bool
    engine: str = DEFAULT_OCR_ENGINE
    cache_path: str | None = None


def run_ocr_inference(
    original_path: Path,
    prepared_path: Path,
    *,
    use_cache: bool = True,
    engine: str | None = None,
) -> OcrInferenceResult:
    """
    带缓存的 OCR 推理。

    original_path: 原始图片（cache key）
    prepared_path: 送入模型的路径（可能为缩放 tmp）
    engine: paddle | rapidocr
    """
    engine_key = normalize_ocr_engine(engine)

    if use_cache:
        cached = load_ocr_cache(original_path, engine_key)
        if cached is not None:
            return OcrInferenceResult(
                items=cached,
                cache_hit=True,
                cache_miss=False,
                parser_used="ocr_cache",
                ocr_engine_recreated=False,
                engine=engine_key,
                cache_path=str(ocr_cache_path(original_path, engine_key)),
            )

    if not ocr_engine_available(engine_key):
        missing = "rapidocr_not_installed" if engine_key == "rapidocr" else "ocr_not_installed"
        raise RuntimeError(missing)

    ocr_engine = get_ocr_engine(engine_key)
    recreated = ocr_engine_was_recreated(engine_key)
    items = _run_engine_predict(engine_key, ocr_engine, prepared_path)
    cache_file: Path | None = None
    if use_cache and items:
        cache_file = save_ocr_cache(original_path, items, engine=engine_key)

    return OcrInferenceResult(
        items=items,
        cache_hit=False,
        cache_miss=True,
        parser_used=_parser_used_name(engine_key),
        ocr_engine_recreated=recreated,
        engine=engine_key,
        cache_path=str(cache_file) if cache_file else None,
    )
