import copy
import json
import zlib
import os.path
from typing import Any

from ..core.meta import __id__, _CACHE_DIRECTORY
from .logs import build_log


class CacheFile:
    def __init__(self, filename: str, read_on_init=True, compress=False):
        self.filename = filename
        self.path = os.path.join(_CACHE_DIRECTORY, filename)
        self._content = b""
        self.compress = compress
        self.logger = build_log(f"{__id__}.cache")

        os.makedirs(_CACHE_DIRECTORY, exist_ok=True)

        if read_on_init:
            self.read()

    def read(self):
        if not os.path.exists(self.path):
            self.logger.debug(f"File '{self.path}' does not exist.")
            return

        try:
            with open(self.path, "rb") as file:
                file_content = file.read()

            if not file_content:
                return

            is_zlib = (
                len(file_content) >= 2 and
                (file_content[0] & 0x0F) == 8 and
                (file_content[0] * 256 + file_content[1]) % 31 == 0
            )

            if is_zlib:
                try:
                    file_content = zlib.decompress(file_content)
                except zlib.error:
                    self.logger.error(f"Header matched in '{self.path}' but decompress failed:", exc_info=True)

            self._content = file_content
        except Exception:
            self.logger.error(f"Failed to load data from '{self.path}':", exc_info=True)

    def write(self):
        data = self._content if self._content is not None else b""
        if self.compress and data:
            data = zlib.compress(data, level=6)

        try:
            with open(self.path, "wb") as file:
                file.write(data)
        except PermissionError:
            self.logger.error(f"Have no permissions to edit '{self.path}':", exc_info=True)

    def wipe(self):
        self._content = b""
        self.write()

    def delete(self):
        if not os.path.exists(self.path):
            self.logger.error(f"File '{self.path}' does not exist.")
            return

        try:
            os.remove(self.path)
        except Exception:
            self.logger.error(f"Failed to delete '{self.path}':", exc_info=True)

    @property
    def content(self) -> bytes:
        return self._content

    @content.setter
    def content(self, value: bytes):
        self._content = value


class JsonCacheFile(CacheFile):
    def __init__(self, filename: str, default: Any, read_on_init=True, compress=False):
        self._default = default  # Храним оригинал для копирования
        self.json_content = self._get_copy_of_default()
        super().__init__(filename, read_on_init, compress)

    def _get_copy_of_default(self) -> Any:
        return copy.deepcopy(self._default)

    def read(self):
        super().read()

        if not self._content:
            self.json_content = self._get_copy_of_default()
            return

        try:
            self.json_content = json.loads(self._content.decode("utf-8", errors="replace"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.logger.error(f"Failed to load JSON from '{self.path}':", exc_info=True)
            self.json_content = self._get_copy_of_default()

    def write(self):
        self._content = json.dumps(self.json_content, ensure_ascii=False).encode("utf-8", errors="replace")
        super().write()

    def wipe(self):
        self.json_content = self._get_copy_of_default()
        self.write()

    @property
    def content(self) -> Any:
        return self.json_content

    @content.setter
    def content(self, value: Any):
        self.json_content = value
