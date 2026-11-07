import sys
import logging
import traceback
from typing import Any

from android_utils import log as _internal_log

from com.exteragram.messenger.utils import AppUtils

from ..core.meta import __id__


def _is_java_obj(obj):
    if hasattr(obj, "getClass"):
        return any(i.startswith("_chaquopy") for i in dir(obj.getClass()))
    return False


def _safe_mapper(obj: Any):
    try:
        if _is_java_obj(obj):
            return AppUtils.getGson().toJson(obj)
        return str(obj)
    except Exception:
        try:
            if _is_java_obj(obj):
                cls_name = obj.getClass().getSimpleName()
                obj_hash = hex(id(obj))[-8:]
                return f"<{cls_name}@{obj_hash}>"
            return str(obj)
        except Exception:
            return f"<UNREPRESENTABLE_{type(obj).__name__}>"


class _CustomLogger(logging.Logger):
    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        func_name = sys._getframe(2).f_code.co_name
        level_name = logging.getLevelName(level)

        prefix = f"[{level_name}] [{self.name}] [{func_name}]"
        formatted_msg = f"{_safe_mapper(msg)} {' '.join(map(_safe_mapper, args))}".strip()
        final_output = f"{prefix} {formatted_msg}"

        if exc_info:
            tb = traceback.format_exc() if exc_info is True else "".join(
                traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
            )
            final_output += f"\n{tb.strip()}"

        _internal_log(final_output)


def build_log(plugin_name: str, level=logging.NOTSET) -> logging.Logger:
    manager = logging.Logger.manager

    if plugin_name in manager.loggerDict:
        old_logger = manager.loggerDict[plugin_name]
        if hasattr(old_logger, "handlers"):
            old_logger.handlers.clear()
        del manager.loggerDict[plugin_name]

    new_logger = logging.getLogger(plugin_name)

    if level != logging.NOTSET:
        new_logger.setLevel(level)

    if not isinstance(new_logger, _CustomLogger):
        new_logger.__class__ = _CustomLogger

    return new_logger


def format_exc() -> str:
    return traceback.format_exc().strip()


def format_exc_from(e: Exception) -> str:
    exc_info = traceback.format_exception(type(e), e, e.__traceback__)
    return "".join(exc_info).strip()


def format_exc_only(e: Exception) -> str:
    exc_info = traceback.format_exception_only(type(e), e)
    return "".join(exc_info).strip()


logging.setLoggerClass(_CustomLogger)

_logger = build_log(__id__)
_cmd_logger = build_log(f"{__id__}.commands")
_au_logger = build_log(f"{__id__}.autoupdater")
_req_logger = build_log(f"{__id__}.requests")
_async_logger = build_log(f"{__id__}.async")
_hu_logger = build_log(f"{__id__}.hookutils")
