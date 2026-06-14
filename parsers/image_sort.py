"""图片文件名自然排序（1.png < 2.png < 10.png < 20.png）。"""

from __future__ import annotations

import re
from pathlib import Path

from parsers.parse_image_table import IMAGE_EXTENSIONS

_NATURAL_CHUNK_RE = re.compile(r"(\d+|\D+)")


def _stem_natural_parts(stem: str) -> tuple:
    """将 stem 拆为自然序 tuple（数字段按 int 比较）。"""
    parts: list[tuple[int, int | str]] = []
    for chunk in _NATURAL_CHUNK_RE.findall(stem):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            parts.append((1, chunk.lower()))
    return tuple(parts)


def natural_sort_key(path: Path | str) -> tuple:
    """
    按文件名自然序排序键。

    支持：
    - 1.png, 2.png, 10.png → 1, 2, 10
    - page1.png, page2.png, page10.png → page1, page2, page10
    - 扩展名大小写 .PNG / .JPG 不影响顺序
    """
    p = Path(path) if not isinstance(path, Path) else path
    stem = p.stem
    suffix = p.suffix.lower()

    # 纯数字 stem（1.png, 10.png）优先按整数比较
    if stem.isdigit():
        return (0, int(stem), suffix, p.name.lower())

    return (1, _stem_natural_parts(stem), suffix, p.name.lower())


def sort_image_paths(paths: list[Path]) -> list[Path]:
    """自然序排序图片路径列表（返回新列表）。"""
    return sorted(paths, key=natural_sort_key)


def sort_image_filenames(names: list[str]) -> list[str]:
    """自然序排序文件名字符串列表（返回新列表）。"""
    return [p.name for p in sort_image_paths([Path(n) for n in names])]


def list_image_files(directory: Path) -> list[Path]:
    """列出目录内 png/jpg/jpeg（扩展名大小写不敏感），自然序排序。"""
    if not directory.is_dir():
        raise ValueError(f"目录不存在: {directory}")
    files = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sort_image_paths(files)
