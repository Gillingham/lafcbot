"""Disk-based LRU cache for transcoded and clipped video files."""

import asyncio
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_CACHE_BYTES = 500 * 1024 * 1024  # 500 MB


class VideoCache:
    """Manages an on-disk LRU cache of transcoded videos keyed by post shortcode,
    slide index, and target file size limit.
    """

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    ):
        if cache_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            cache_dir = project_root / ".cache" / "vxt_videos"
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max_bytes
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize(key: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]", "_", key)

    def _file_prefix(self, shortcode: str, slide_index: int) -> str:
        safe_code = self._sanitize(shortcode)
        return f"{safe_code}_{slide_index}"

    def _exact_paths(
        self, shortcode: str, slide_index: int, max_size: int
    ) -> tuple[Path, Path]:
        prefix = self._file_prefix(shortcode, slide_index)
        video_path = self.cache_dir / f"{prefix}_{max_size}.mp4"
        meta_path = self.cache_dir / f"{prefix}_{max_size}.json"
        return video_path, meta_path

    def _sync_get(
        self, shortcode: str, slide_index: int, max_size: int
    ) -> tuple[bytes, bool] | None:
        # 1. Check exact match
        video_path, meta_path = self._exact_paths(shortcode, slide_index, max_size)
        if video_path.is_file() and meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                video_data = video_path.read_bytes()
                # Update mtime for LRU tracking
                os.utime(video_path, None)
                os.utime(meta_path, None)
                return video_data, meta.get("is_clipped", False)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to read cache file {video_path}: {e}")

        # 2. Check if an unclipped full video exists for this shortcode/slide that fits max_size
        prefix = self._file_prefix(shortcode, slide_index)
        try:
            for v_path in self.cache_dir.glob(f"{prefix}_*.mp4"):
                m_path = v_path.with_suffix(".json")
                if not m_path.is_file():
                    continue
                try:
                    meta = json.loads(m_path.read_text(encoding="utf-8"))
                    if not meta.get("is_clipped", False):
                        size = v_path.stat().st_size
                        if 0 < size <= max_size:
                            video_data = v_path.read_bytes()
                            os.utime(v_path, None)
                            os.utime(m_path, None)
                            return video_data, False
                except (OSError, json.JSONDecodeError):
                    continue
        except OSError:
            pass

        return None

    async def get(
        self, shortcode: str, slide_index: int, max_size: int
    ) -> tuple[bytes, bool] | None:
        """Retrieve a cached video if available and valid for max_size."""
        return await asyncio.to_thread(self._sync_get, shortcode, slide_index, max_size)

    def _sync_set(
        self,
        shortcode: str,
        slide_index: int,
        max_size: int,
        data: bytes,
        is_clipped: bool,
    ) -> None:
        video_path, meta_path = self._exact_paths(shortcode, slide_index, max_size)
        tmp_video = self.cache_dir / f"{video_path.name}.tmp.{os.getpid()}"
        tmp_meta = self.cache_dir / f"{meta_path.name}.tmp.{os.getpid()}"

        try:
            tmp_video.write_bytes(data)
            tmp_meta.write_text(
                json.dumps({"is_clipped": is_clipped, "size": len(data)}),
                encoding="utf-8",
            )
            tmp_video.replace(video_path)
            tmp_meta.replace(meta_path)
        except OSError as e:
            logger.warning(f"Failed to write cache file {video_path}: {e}")
            tmp_video.unlink(missing_ok=True)
            tmp_meta.unlink(missing_ok=True)
            return

        self._sync_prune()

    async def set(
        self,
        shortcode: str,
        slide_index: int,
        max_size: int,
        data: bytes,
        is_clipped: bool,
    ) -> None:
        """Store a video and its metadata in cache, pruning old entries if needed."""
        await asyncio.to_thread(
            self._sync_set, shortcode, slide_index, max_size, data, is_clipped
        )

    def _sync_prune(self) -> None:
        try:
            files: list[tuple[float, Path, int]] = []
            total_size = 0
            for p in self.cache_dir.glob("*.mp4"):
                try:
                    stat = p.stat()
                    files.append((stat.st_mtime, p, stat.st_size))
                    total_size += stat.st_size
                except OSError:
                    continue

            if total_size <= self.max_bytes:
                return

            # Sort by mtime ascending (oldest first)
            files.sort(key=lambda x: x[0])
            for _, p, size in files:
                if total_size <= self.max_bytes:
                    break
                p.unlink(missing_ok=True)
                p.with_suffix(".json").unlink(missing_ok=True)
                total_size -= size
        except OSError as e:
            logger.warning(f"Error pruning video cache: {e}")

    async def clear(self) -> None:
        """Remove all files in the cache directory."""

        def _sync_clear():
            for p in self.cache_dir.glob("*"):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass

        await asyncio.to_thread(_sync_clear)
