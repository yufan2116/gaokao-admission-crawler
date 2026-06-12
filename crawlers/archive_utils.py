"""压缩包解压工具（Phase 11/12：RAR / ZIP 附件）。"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_zip_archive(archive_path: Path, dest_dir: Path | None = None) -> list[Path]:
    """解压 ZIP 到目标目录。"""
    archive_path = Path(archive_path)
    if not archive_path.exists():
        return []

    out_dir = dest_dir or archive_path.parent / archive_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(out_dir)
            for name in zf.namelist():
                candidate = out_dir / name
                if candidate.is_file():
                    extracted.append(candidate)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        logger.warning("ZIP 解压失败 [%s]: %s", archive_path, exc)
        return []

    logger.info("ZIP 已解压 %s → %d 个文件", archive_path.name, len(extracted))
    return extracted


def extract_rar_archive(archive_path: Path, dest_dir: Path | None = None) -> list[Path]:
    """
    解压 RAR 到目标目录。

    Windows 10+ 优先调用系统 ``tar -xf``（支持部分 RAR）；否则尝试 tarfile。
    """
    archive_path = Path(archive_path)
    if not archive_path.exists():
        return []

    out_dir = dest_dir or archive_path.parent / archive_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("tar"):
        try:
            subprocess.run(
                ["tar", "-xf", str(archive_path), "-C", str(out_dir)],
                check=True,
                capture_output=True,
            )
            extracted = [p for p in out_dir.rglob("*") if p.is_file()]
            if extracted:
                logger.info("RAR 已解压 %s → %d 个文件 (tar)", archive_path.name, len(extracted))
                return extracted
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            logger.warning("tar 解压失败 [%s]: %s", archive_path, stderr[:200])

    try:
        with tarfile.open(archive_path, "r:*") as tar:
            tar.extractall(path=out_dir)
            extracted = [out_dir / name for name in tar.getnames() if (out_dir / name).is_file()]
        if extracted:
            logger.info("RAR 已解压 %s → %d 个文件 (tarfile)", archive_path.name, len(extracted))
            return extracted
    except (tarfile.TarError, OSError, ValueError) as exc:
        logger.warning("RAR 解压失败 [%s]: %s", archive_path, exc)

    return []


def extract_archive(archive_path: Path, dest_dir: Path | None = None) -> list[Path]:
    """按扩展名解压 ZIP / RAR。"""
    suffix = Path(archive_path).suffix.lower()
    if suffix == ".zip":
        return extract_zip_archive(archive_path, dest_dir)
    if suffix == ".rar":
        return extract_rar_archive(archive_path, dest_dir)
    return []
