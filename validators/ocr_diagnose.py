"""
OCR 运行时诊断（Phase 20.10）。

只收集环境与性能信息，不修改主流程 OCR 配置。
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CLEANED_DIR
from parsers.ocr_engine import (
    PRODUCTION_PADDLE_INIT_KWARGS,
    _configure_paddle_runtime,
    _run_engine_predict,
    get_engine_version,
    get_ocr_engine,
    onnxruntime_available,
    rapidocr_available,
)
from parsers.parse_image_table import OCR_MAX_SIDE_PX, _prepare_image_for_ocr

logger = logging.getLogger(__name__)

DIAGNOSE_OUTPUT = CLEANED_DIR / "ocr_diagnose.json"

PRODUCTION_INIT_KWARGS = PRODUCTION_PADDLE_INIT_KWARGS

DEFAULT_SAMPLE_IMAGE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "raw"
    / "hubei"
    / "2024"
    / "school"
    / "attachments"
    / "1.png"
)

PRODUCTION_INIT_KWARGS: dict[str, Any] = {
    "lang": "ch",
    "enable_mkldnn": False,
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_textline_orientation": False,
}

LIGHTWEIGHT_REFERENCE_KWARGS: dict[str, Any] = {
    "use_angle_cls": False,
    "lang": "ch",
    "show_log": False,
}


def _pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _installed_packages() -> dict[str, str | None]:
    return {
        "paddlepaddle": _pkg_version("paddlepaddle"),
        "paddlepaddle-gpu": _pkg_version("paddlepaddle-gpu"),
        "paddleocr": _pkg_version("paddleocr"),
        "paddlex": _pkg_version("paddlex"),
    }


def _cpu_count() -> int:
    return os.cpu_count() or 0


def _memory_info() -> dict[str, Any]:
    try:
        import psutil

        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "used_percent": vm.percent,
            "source": "psutil",
        }
    except ImportError:
        if sys.platform == "win32":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                total = stat.ullTotalPhys / (1024**3)
                avail = stat.ullAvailPhys / (1024**3)
                return {
                    "total_gb": round(total, 2),
                    "available_gb": round(avail, 2),
                    "used_percent": stat.dwMemoryLoad,
                    "source": "win32 GlobalMemoryStatusEx",
                }
            except OSError:
                pass
        return {"source": "unavailable", "note": "install psutil for detailed memory stats"}


def _paddle_cuda_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "cuda_compiled": False,
        "cuda_available": False,
        "device_count": 0,
        "current_device": None,
    }
    try:
        import paddle

        info["paddle_version"] = paddle.__version__
        info["cuda_compiled"] = bool(
            paddle.device.is_compiled_with_cuda()
            if hasattr(paddle.device, "is_compiled_with_cuda")
            else False
        )
        if info["cuda_compiled"] and hasattr(paddle.device, "cuda"):
            try:
                info["device_count"] = int(paddle.device.cuda.device_count())
                info["cuda_available"] = info["device_count"] > 0
                if info["cuda_available"]:
                    info["current_device"] = paddle.device.get_device()
            except Exception as exc:
                info["cuda_error"] = str(exc)
    except ImportError:
        info["paddle_import_error"] = "paddle not installed"
    return info


def _image_size_info(image_path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(image_path.resolve()) if image_path.exists() else str(image_path),
        "exists": image_path.exists(),
    }
    if not image_path.exists():
        return info
    try:
        from PIL import Image

        with Image.open(image_path) as im:
            width, height = im.size
            longest = max(width, height)
            info.update(
                {
                    "width": width,
                    "height": height,
                    "longest_side_px": longest,
                    "megapixels": round((width * height) / 1_000_000, 3),
                    "oversized_before_resize": longest > OCR_MAX_SIDE_PX,
                    "ocr_max_side_px": OCR_MAX_SIDE_PX,
                }
            )
        prepared = _prepare_image_for_ocr(image_path)
        if prepared != image_path and prepared.exists():
            with Image.open(prepared) as im2:
                pw, ph = im2.size
                plong = max(pw, ph)
                info["prepared_path"] = str(prepared)
                info["prepared_width"] = pw
                info["prepared_height"] = ph
                info["prepared_longest_side_px"] = plong
                info["was_resized_for_ocr"] = True
                info["oversized_after_resize"] = plong > OCR_MAX_SIDE_PX
        else:
            info["prepared_path"] = str(image_path)
            info["prepared_width"] = width
            info["prepared_height"] = height
            info["prepared_longest_side_px"] = longest
            info["was_resized_for_ocr"] = False
            info["oversized_after_resize"] = longest > OCR_MAX_SIDE_PX
    except OSError as exc:
        info["error"] = str(exc)
    return info


def _create_tiny_benchmark_image() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    out = CLEANED_DIR / "ocr_diagnose_tiny.png"
    im = Image.new("RGB", (480, 120), color="white")
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 40), "OCR benchmark 测试 12345", fill="black", font=font)
    im.save(out)
    return out


def _run_predict_seconds(engine_key: str, ocr_engine: Any, image_path: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    text_count = 0
    error: str | None = None
    try:
        items = _run_engine_predict(engine_key, ocr_engine, image_path)
        text_count = len(items)
    except Exception as exc:
        error = str(exc)
    elapsed = round(time.perf_counter() - t0, 3)
    return {
        "engine": engine_key,
        "ocr_seconds": elapsed,
        "text_boxes_detected": text_count,
        "error": error,
        "image": image_path.name,
        "image_path": str(image_path),
    }


def _benchmark_engine(engine_key: str, tiny_path: Path, sample_prepared: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {"engine": engine_key}
    try:
        eng = get_ocr_engine(engine_key)
        out["engine_hints"] = _engine_model_hints(eng)
        out["benchmark_on_tiny"] = _run_predict_seconds(engine_key, eng, tiny_path)
        if sample_prepared is not None:
            out["benchmark_on_sample_prepared"] = _run_predict_seconds(
                engine_key, eng, sample_prepared
            )
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _engine_model_hints(engine: Any) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    for attr in ("det_model_name", "rec_model_name", "cls_model_name", "model_name"):
        if hasattr(engine, attr):
            hints[attr] = getattr(engine, attr)
    for attr in ("use_angle_cls", "use_textline_orientation", "enable_mkldnn"):
        if hasattr(engine, attr):
            hints[attr] = getattr(engine, attr)
    text = repr(engine)
    if "PP-OCRv5_server" in text or "server_det" in text.lower():
        hints["detected_model_tier"] = "server/heavy"
    elif "mobile" in text.lower():
        hints["detected_model_tier"] = "mobile/light"
    return hints


def _create_lightweight_engine() -> Any:
    _configure_paddle_runtime()
    from paddleocr import PaddleOCR

    kwargs = dict(LIGHTWEIGHT_REFERENCE_KWARGS)
    kwargs["enable_mkldnn"] = False
    try:
        return PaddleOCR(**kwargs)
    except TypeError:
        legacy = {"lang": "ch", "use_angle_cls": False, "show_log": False}
        try:
            return PaddleOCR(**legacy)
        except TypeError:
            return PaddleOCR(lang="ch")


def _compare_lightweight_reference(current: dict[str, Any]) -> dict[str, Any]:
    return {
        "reference": LIGHTWEIGHT_REFERENCE_KWARGS,
        "production_init_kwargs": current,
        "matches_lightweight_use_angle_cls_false": current.get("use_textline_orientation") is False
        or current.get("use_angle_cls") is False
        or "use_angle_cls" not in current,
        "note": "主流程使用 PaddleOCR 3.x 新参数名；轻量参考仍记录 use_angle_cls=False",
    }


def _paddleocr_import_status(*, engine_loaded: bool, load_error: str | None) -> dict[str, Any]:
    return {
        "package_version": _pkg_version("paddleocr"),
        "engine_loaded": engine_loaded,
        "import_error": load_error,
    }
    return {
        "reference": LIGHTWEIGHT_REFERENCE_KWARGS,
        "production_init_kwargs": current,
        "matches_lightweight_use_angle_cls_false": current.get("use_textline_orientation") is False
        or current.get("use_angle_cls") is False
        or "use_angle_cls" not in current,
        "note": "主流程使用 PaddleOCR 3.x 新参数名；轻量参考仍记录 use_angle_cls=False",
    }


def _runtime_checks(
    packages: dict[str, str | None],
    cuda: dict[str, Any],
    sample_image: dict[str, Any],
    production_hints: dict[str, Any],
    paddle_status: dict[str, Any] | None = None,
    largest_in_dir: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paddle_ver = cuda.get("paddle_version") or packages.get("paddlepaddle") or ""
    major_minor = paddle_ver.split(".")[:2]
    paddle_33_plus = False
    try:
        if len(major_minor) >= 2:
            paddle_33_plus = int(major_minor[0]) >= 3 and int(major_minor[1].split("+")[0]) >= 3
    except ValueError:
        pass

    using_gpu_pkg = packages.get("paddlepaddle-gpu") is not None
    using_cpu_pkg = packages.get("paddlepaddle") is not None and not using_gpu_pkg
    mkldnn_env = os.environ.get("FLAGS_use_mkldnn", "(unset)")
    heavy_models = production_hints.get("detected_model_tier") == "server/heavy" or any(
        "server" in str(v).lower() for v in production_hints.values()
    )
    if not heavy_models and packages.get("paddleocr", "").startswith("3."):
        heavy_models = True
        heavy_models_note = "PaddleOCR 3.x 默认倾向 PP-OCRv5_server 大模型（见运行时 Creating model 日志）"
    else:
        heavy_models_note = None

    torch_import_issue = None
    import_err = (paddle_status or {}).get("import_error") if isinstance(paddle_status, dict) else None
    if import_err and "torch" in import_err.lower():
        torch_import_issue = import_err

    likely = [
        reason
        for reason, ok in [
            ("CPU paddlepaddle（无 CUDA）", using_cpu_pkg and not cuda.get("cuda_available")),
            ("Paddle 3.3+ on Windows CPU", paddle_33_plus and sys.platform == "win32"),
            ("PP-OCRv5 server 大模型（det/rec）", heavy_models),
            ("原图较大需缩放至 1400px", sample_image.get("oversized_before_resize") or (largest_in_dir or {}).get("oversized_before_resize")),
            ("paddleocr 导入链依赖 torch/modelscope 异常", bool(torch_import_issue)),
        ]
        if ok
    ]

    return {
        "using_cpu_paddlepaddle": using_cpu_pkg and not cuda.get("cuda_available"),
        "paddlepaddle_gpu_installed": using_gpu_pkg,
        "gpu_enabled_at_runtime": bool(cuda.get("cuda_available")),
        "paddle_3_3_plus_windows_cpu": paddle_33_plus and sys.platform == "win32",
        "image_oversized_before_resize": sample_image.get("oversized_before_resize"),
        "image_resized_for_ocr": sample_image.get("was_resized_for_ocr"),
        "image_oversized_after_resize": sample_image.get("oversized_after_resize"),
        "angle_cls_or_textline_orientation_disabled": production_hints.get("use_textline_orientation")
        is False
        or production_hints.get("use_angle_cls") is False
        or PRODUCTION_INIT_KWARGS.get("use_textline_orientation") is False,
        "mkldnn_enabled_in_production_kwargs": PRODUCTION_INIT_KWARGS.get("enable_mkldnn"),
        "mkldnn_env_FLAGS_use_mkldnn": mkldnn_env,
        "heavy_server_det_rec_models": heavy_models,
        "heavy_models_note": heavy_models_note,
        "torch_import_issue": torch_import_issue,
        "likely_slow_reasons": likely,
    }


def _historical_ocr_hints() -> dict[str, Any]:
    hints: dict[str, Any] = {}
    profile_path = CLEANED_DIR / "ocr_profile.json"
    if profile_path.is_file():
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            rows = data.get("profiles") or []
            hints["ocr_profile"] = [
                {
                    "image": r.get("image"),
                    "ocr_seconds": r.get("ocr_seconds"),
                    "parser_used": r.get("parser_used"),
                    "cache_hit": r.get("cache_hit"),
                }
                for r in rows
            ]
        except (OSError, json.JSONDecodeError):
            pass
    return hints


def _largest_image_in_dir(directory: Path) -> dict[str, Any] | None:
    if not directory.is_dir():
        return None
    largest: dict[str, Any] | None = None
    try:
        from PIL import Image

        from parsers.image_sort import list_image_files

        for path in list_image_files(directory):
            with Image.open(path) as im:
                w, h = im.size
                longest = max(w, h)
                if largest is None or longest > largest["longest_side_px"]:
                    largest = {
                        "filename": path.name,
                        "width": w,
                        "height": h,
                        "longest_side_px": longest,
                        "oversized_before_resize": longest > OCR_MAX_SIDE_PX,
                    }
    except OSError:
        return None
    return largest


def run_ocr_diagnose(
    *,
    sample_image: str | Path | None = None,
    run_sample_benchmark: bool = False,
    ocr_engine: str = "paddle",
) -> dict[str, Any]:
    """收集 OCR 运行时诊断并写入 ocr_diagnose.json。"""
    sample_path = Path(sample_image) if sample_image else DEFAULT_SAMPLE_IMAGE
    packages = _installed_packages()
    cuda = _paddle_cuda_info()
    sample_info = _image_size_info(sample_path)
    sample_dir = sample_path.parent if sample_path.parent.is_dir() else None
    largest_in_dir = _largest_image_in_dir(sample_dir) if sample_dir else None
    historical = _historical_ocr_hints()
    tiny_path = _create_tiny_benchmark_image()

    sample_prepared = (
        Path(sample_info.get("prepared_path") or sample_path)
        if run_sample_benchmark and sample_path.exists()
        else None
    )

    benchmarks: dict[str, Any] = {
        "tiny_image_path": str(tiny_path),
        "primary_engine": ocr_engine,
        "paddle": _benchmark_engine("paddle", tiny_path, sample_prepared),
    }
    rapidocr_diag: dict[str, Any] = {
        "installed": rapidocr_available(),
        "onnxruntime_installed": onnxruntime_available(),
        "package_version": get_engine_version("rapidocr"),
    }
    if rapidocr_available():
        rapidocr_diag["benchmark"] = _benchmark_engine("rapidocr", tiny_path, sample_prepared)
    benchmarks["rapidocr"] = rapidocr_diag

    production_hints = benchmarks["paddle"].get("engine_hints") or {}
    engine_load_error = benchmarks["paddle"].get("error")
    paddle_status = _paddleocr_import_status(
        engine_loaded=engine_load_error is None,
        load_error=engine_load_error,
    )

    lightweight_result: dict[str, Any] | None = None
    try:
        lightweight_engine = _create_lightweight_engine()
        lightweight_hints = _engine_model_hints(lightweight_engine)
        lightweight_result = {
            "init_kwargs_attempted": {**LIGHTWEIGHT_REFERENCE_KWARGS, "enable_mkldnn": False},
            "engine_hints": lightweight_hints,
            "benchmark_on_tiny": _run_predict_seconds("paddle", lightweight_engine, tiny_path),
        }
    except Exception as exc:
        lightweight_result = {"error": str(exc), "note": "轻量 Paddle 参考配置，仅诊断用"}
        logger.warning("lightweight OCR benchmark 跳过: %s", exc)

    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "report_path": str(DIAGNOSE_OUTPUT),
        "python_version": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "paddleocr_import": paddle_status,
        "paddle_cuda": cuda,
        "cpu_count": _cpu_count(),
        "memory": _memory_info(),
        "production_init_kwargs": PRODUCTION_INIT_KWARGS,
        "lightweight_reference_kwargs": LIGHTWEIGHT_REFERENCE_KWARGS,
        "lightweight_comparison": _compare_lightweight_reference(PRODUCTION_INIT_KWARGS),
        "production_engine_hints": production_hints,
        "sample_image": sample_info,
        "largest_image_in_sample_dir": largest_in_dir,
        "historical_ocr_hints": historical,
        "benchmarks": benchmarks,
        "lightweight_diagnostic": lightweight_result,
        "checks": _runtime_checks(
            packages, cuda, sample_info, production_hints, paddle_status, largest_in_dir
        ),
    }

    DIAGNOSE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSE_OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def format_diagnose_lines(report: dict[str, Any]) -> list[str]:
    checks = report.get("checks") or {}
    pkgs = report.get("packages") or {}
    cuda = report.get("paddle_cuda") or {}
    sample = report.get("sample_image") or {}
    bench = (report.get("benchmarks") or {}).get("paddle") or {}
    bench_tiny = bench.get("benchmark_on_tiny") or {}
    rapid = (report.get("benchmarks") or {}).get("rapidocr") or {}
    rapid_bench = (rapid.get("benchmark") or {}).get("benchmark_on_tiny") or {}
    bench_line = (
        f"paddle tiny benchmark: {bench_tiny.get('ocr_seconds')}s boxes={bench_tiny.get('text_boxes_detected')}"
        if bench_tiny.get("ocr_seconds") is not None
        else f"paddle tiny benchmark: error={bench_tiny.get('error') or bench.get('error')}"
    )
    rapid_line = (
        f"rapidocr installed={rapid.get('installed')} onnx={rapid.get('onnxruntime_installed')}"
    )
    if rapid_bench.get("ocr_seconds") is not None:
        rapid_line += f" tiny={rapid_bench.get('ocr_seconds')}s"
    elif rapid.get("error"):
        rapid_line += f" error={rapid.get('error')}"
    lines = [
        "OCR 运行时诊断",
        f"python: {report.get('python_version', '').split()[0]}",
        f"paddlepaddle: {pkgs.get('paddlepaddle')}  paddlepaddle-gpu: {pkgs.get('paddlepaddle-gpu')}",
        f"paddleocr: {pkgs.get('paddleocr')}  paddle: {cuda.get('paddle_version')}",
        f"CUDA compiled: {cuda.get('cuda_compiled')}  available: {cuda.get('cuda_available')}",
        f"CPU cores: {report.get('cpu_count')}  memory: {report.get('memory')}",
        f"production kwargs: {report.get('production_init_kwargs')}",
        f"mkldnn(production): {PRODUCTION_INIT_KWARGS.get('enable_mkldnn')}",
        "",
        f"sample: {sample.get('path')}",
        f"  size: {sample.get('width')}x{sample.get('height')} prepared: {sample.get('prepared_width')}x{sample.get('prepared_height')}",
        f"  oversized_before_resize: {sample.get('oversized_before_resize')}  resized: {sample.get('was_resized_for_ocr')}",
        "",
        bench_line,
        rapid_line,
        "",
        "likely_slow_reasons:",
    ]
    for reason in checks.get("likely_slow_reasons") or []:
        lines.append(f"  - {reason}")
    lines.append("")
    lines.append(f"report: {report.get('report_path')}")
    return lines
