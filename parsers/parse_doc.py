"""Word .doc 检测（Phase 11：识别图片型投档表，不做 OCR）。"""

from __future__ import annotations

from pathlib import Path


def is_image_based_doc(path: Path) -> bool:
    """
    判断 .doc 是否为嵌入图片的扫描表（河南 henanjk RAR 常见格式）。

    通过 OLE Data 流中的 PNG/JPEG 魔数判断。
    """
    path = Path(path)
    if path.suffix.lower() != ".doc":
        return False
    try:
        import olefile
    except ImportError:
        return False

    try:
        ole = olefile.OleFileIO(str(path))
    except OSError:
        return False

    try:
        if not ole.exists("Data"):
            return False
        head = ole.openstream("Data").read(4096)
        return b"PNG\r\n" in head or b"\xff\xd8\xff" in head
    finally:
        ole.close()
