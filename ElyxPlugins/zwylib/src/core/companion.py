import importlib
import sys
import os.path

from .meta import _plugins_dir, _COMPANION_PATH


class _Companion:
    defaults = {
        "autoupdates_tasks": [],
        "pending_commands": {},
    }

    def __init__(self):
        self.module = None

    @staticmethod
    def create():
        lines = ["# Auto-generated zwylib companion file\n"]
        for key, default in _Companion.defaults.items():
            lines.append(f"\n{key} = {repr(default)}")

        os.makedirs(os.path.dirname(_COMPANION_PATH), exist_ok=True)
        with open(_COMPANION_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def import_it(self):
        if _plugins_dir not in sys.path:
            sys.path.append(_plugins_dir)
        importlib.invalidate_caches()

        import zwylib_companion
        self.module = zwylib_companion


_companion = _Companion()

_companion.create()
_companion.import_it()
