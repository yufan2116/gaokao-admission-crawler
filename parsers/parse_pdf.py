"""
PDF 解析占位模块。

pdfplumber 为可选依赖，未安装时给出友好提示。
MVP 阶段不强依赖 PDF 解析。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_pdf_file(file_path: str | Path) -> list[dict[str, Any]]:
    """
    解析 PDF 表格（占位实现）。

    Returns:
        解析出的记录列表；当前返回空列表并记录日志。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        logger.warning(
            "pdfplumber 未安装，跳过 PDF 解析。可执行: pip install pdfplumber"
        )
        return []

    logger.info("PDF 解析尚未实现，文件: %s", path)
    # TODO: 下一阶段用 pdfplumber 提取表格
    return []
