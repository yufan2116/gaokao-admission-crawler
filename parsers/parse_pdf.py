"""
PDF 解析入口（Phase 13 委托至 parse_pdf_tables）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from parsers.parse_pdf_tables import parse_pdf_tables

logger = logging.getLogger(__name__)


def parse_pdf_file(
    file_path: str | Path,
    data_type: str = "school",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    解析 PDF 表格，返回记录列表（兼容旧接口）。

    内部调用 parse_pdf_tables；失败时返回空列表。
    """
    result = parse_pdf_tables(file_path, data_type=data_type, **kwargs)
    if not result.ok:
        logger.info(
            "PDF 解析未成功 [%s]: status=%s",
            Path(file_path).name,
            result.status,
        )
        return []
    return result.df.to_dict(orient="records")
