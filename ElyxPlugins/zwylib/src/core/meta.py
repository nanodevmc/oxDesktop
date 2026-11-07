import sys
import os.path
from typing import Optional, Any, Union, TypeVar

import file_utils

LIB_NAME = "ZwyLib"
__description__ = (
    "Zwylair's library with highly used things, used for other plugins.\n"
    "Documentation: https://zwylib-docs.vercel.app/"
)
__icon__ = "zwyPluginsIcons/11"
__id__ = "zwylib"
__version__ = "3.0.0"
__author__ = "@zwylair"
__min_version__ = "12.10.6"

_T = TypeVar("_T")
_ASYNC_SHARED_KEY = "_zwylib_async_shared"
MATCH_PARENT = -1
WRAP_CONTENT = -2

_plugins_dir = file_utils.get_plugins_dir()


def _get_plugin_id_from_stack(fallback: Optional[str] = None) -> Optional[str]:
    index = 0
    while True:
        index += 1

        try:
            frame = sys._getframe(index)
            file_path = frame.f_code.co_filename

            if _plugins_dir not in file_path:
                continue

            if "ElyxPlugins" in file_path:
                plugin_id = file_path.split("ElyxPlugins/")[1].split("/")[0]
            else:
                plugin_id = os.path.splitext(file_path)[0].split("/")[-1]

            # ignore zwylib cuz idk what amount of frames it might take,
            # better use zwylib id as fallback in these cases ig
            if plugin_id == __id__:
                continue

            return plugin_id
        except ValueError:
            return None or fallback


_AU_CHANNEL_USERNAME = "zwyPlugins"
_AU_CHANNEL_ID = 2521243181
_AU_MSG_ID = 141

DEFAULT_COMMAND_PREFIX = "."
_ALLOWED_ARG_TYPES = (str, int, float, bool, Any)
_ALLOWED_ORIGIN = (Union, Optional)

_CACHE_DIRECTORY = os.path.join(_plugins_dir, "cache")
_COMPANION_PATH = os.path.join(_plugins_dir, "zwylib_companion", "__init__.py")
