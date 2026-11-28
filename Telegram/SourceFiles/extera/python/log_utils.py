from enum import IntEnum
import _extera

__all__ = ["LogLevel", "Logger", "get_logger", "dump"]


class LogLevel(IntEnum):
    VERBOSE = 2
    DEBUG = 3
    INFO = 4
    WARNING = 5
    ERROR = 6
    OFF = 100


class Logger:
    def __init__(self, tag: str = "pysdk"):
        self.tag = str(tag)

    def _emit(self, level: str, msg: object, *args) -> None:
        text = str(msg) % args if args else str(msg)
        try:
            _extera.log(f"[{self.tag}][{level}] {text}")
        except Exception:
            pass

    def v(self, msg: object, *args) -> None:
        self._emit("V", msg, *args)

    def d(self, msg: object, *args) -> None:
        self._emit("D", msg, *args)

    def i(self, msg: object, *args) -> None:
        self._emit("I", msg, *args)

    def w(self, msg: object, *args) -> None:
        self._emit("W", msg, *args)

    def e(self, msg: object, *args) -> None:
        self._emit("E", msg, *args)


def get_logger(tag: str = "pysdk") -> Logger:
    return Logger(tag)


def dump(obj: object, label: str = "dump") -> str:
    text = f"{label}: {obj!r}"
    Logger("dump").d(text)
    return text
