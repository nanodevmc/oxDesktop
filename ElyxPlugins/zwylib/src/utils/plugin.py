import asyncio
import os.path
from typing import Optional, Dict, Set

from packaging.version import Version

from client_utils import get_file_loader
from base_plugin import BasePlugin

from java import cast
from java.io import File
from java.util.concurrent import ConcurrentHashMap
from android.os import Process, SystemClock
from org.telegram.messenger import MessageObject
from com.exteragram.messenger.plugins import PluginsController, Plugin, PluginsConstants, PythonPluginsEngine

from ..core.locales import L
from ..core.meta import __id__, __version__, _plugins_dir, _AU_CHANNEL_USERNAME, _AU_CHANNEL_ID, _AU_MSG_ID
from ..ui.bulletin import _bulletin
from .async_tools import _safe_set_future_result
from .java_utils import Callback1
from .logs import _logger
from .media import ensure_media_downloaded


def is_zwylib_version_sufficient(plugin_name: str, version: str, notify=True) -> bool:
    is_sufficient = Version(__version__) >= Version(version)
    if notify and not is_sufficient:
        _bulletin.show_error_with_post_redirect(
            L.not_sufficient_zwylib_ver(plugin_name=plugin_name, version=version, cur_ver=__version__),
            L.update_bulletin_button,
            _AU_CHANNEL_ID, _AU_MSG_ID, peer_username=_AU_CHANNEL_USERNAME
        )
    return is_sufficient


def _does_plugin_require_zwylib(plugin_id: str, allow_self=False) -> bool:
    try:
        with open(PluginUtils.get_plugin_path(plugin_id), encoding="utf-8", errors="ignore") as f:
            source = f.read().lower()

        if not allow_self and plugin_id == __id__:
            return False

        return "import zwylib" in source or "from zwylib import" in source
    except Exception:
        _logger.error("An error occurred:", exc_info=True)
        return False


def _does_plugin_uses_zwylib_autoupdater(plugin_id: str) -> bool:
    if plugin_id == __id__:
        return True

    if not _does_plugin_require_zwylib(plugin_id, allow_self=True):
        return False

    try:
        with open(PluginUtils.get_plugin_path(plugin_id), encoding="utf-8", errors="ignore") as f:
            source = f.read().lower()

        return "add_autoupdater_task" in source
    except Exception:
        _logger.error("An error occurred:", exc_info=True)
        return False


class PluginUtils:
    @classmethod
    def get_engines(cls) -> ConcurrentHashMap:
        return PluginsController.getEngines()

    @classmethod
    def get_python_engine(cls) -> PythonPluginsEngine:
        return cast(PythonPluginsEngine, cls.get_engines().get(PluginsConstants.PYTHON))

    @classmethod
    def get_engine_key_for_file(cls, file_path: str) -> Optional[str]:
        engines_map = cls.get_engines()
        file = File(file_path)
        for engine_key in engines_map.keySet().toArray():
            if engines_map.get(engine_key).isPlugin(file, None):
                return str(engine_key)
        return None

    @classmethod
    def get_plugin_engine_key(cls, plugin_id: str) -> Optional[str]:
        plugin = cls.get_plugin(plugin_id)
        if plugin is None:
            return None
        return str(plugin.getEngine() or PluginsConstants.PYTHON)

    @classmethod
    def get_plugin(cls, plugin_id: str) -> Optional[Plugin]:
        try:
            return cls.get_plugins_hashmap().get(plugin_id)
        except Exception:
            _logger.error("An error occurred:", exc_info=True)
        return None

    @classmethod
    def get_plugin_instance(cls, plugin_id: str) -> Optional[BasePlugin]:
        return cls.get_python_engine().pluginInstances.get(plugin_id)

    @classmethod
    def get_plugins_hashmap(cls) -> Optional[ConcurrentHashMap]:
        try:
            return PluginsController.getInstance().plugins
        except Exception:
            _logger.error("An error occurred:", exc_info=True)
        return None

    @classmethod
    def get_plugins(cls) -> Optional[Dict[str, Plugin]]:
        try:
            plugins_hashmap = cls.get_plugins_hashmap()
            return {k: plugins_hashmap.get(k) for k in plugins_hashmap.keySet().toArray()}
        except Exception:
            _logger.error("An error occurred:", exc_info=True)
        return None

    @classmethod
    def get_plugin_path(cls, plugin_id: str) -> str:
        return os.path.join(_plugins_dir, f"{plugin_id}.py")

    @classmethod
    async def install_plugin(cls, file_path: str, timeout: Optional[float] = 300) -> bool:
        def install_callback(error: Optional[str]):
            if error:
                _logger.error(f"Error installing '{file_path}':", exc_info=Exception(error))
                _safe_set_future_result(future, False)
            else:
                _safe_set_future_result(future, True)

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        _logger.debug(f"Installing '{os.path.split(file_path)[1]}' plugin...")

        try:
            engine_key = cls.get_engine_key_for_file(file_path)
            if engine_key is None:
                raise Exception("No plugin engine accepts this file.")

            cls.get_engines().get(engine_key).loadPluginFromFile(file_path, None, Callback1(install_callback), None)
        except Exception:
            _safe_set_future_result(future, False)
            _logger.error(f"Error installing '{file_path}':", exc_info=True)

        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            _logger.error(f"Installation of '{file_path}' did not finish in {timeout} seconds.")
            return False

    @classmethod
    def reload_plugin(cls, plugin_id: str):
        try:
            engine = cls.get_python_engine()
            controller = PluginsController.getInstance()
            was_enabled = engine.pluginInstances.containsKey(plugin_id)

            if was_enabled:
                engine.setPluginEnabled(plugin_id, False, None)

            old_instance = engine.pluginInstances.remove(plugin_id)
            if old_instance is not None:
                try:
                    old_instance.close()
                except Exception:
                    _logger.error("An error:", exc_info=True)

            if controller.plugins.containsKey(plugin_id):
                controller.plugins.remove(plugin_id)

            engine.loadPlugin(plugin_id, cls.get_plugin_path(plugin_id))
            if was_enabled:
                engine.setPluginEnabled(plugin_id, True, None)

            controller.notifyPluginsChanged()

            _logger.debug(f"Plugin '{plugin_id}' was reloaded.")
        except Exception:
            _logger.error("An error occurred:", exc_info=True)

    @classmethod
    def is_plugin_loaded_or_loading(cls, plugin_id: str) -> bool:
        plugin = cls.get_plugin(plugin_id)
        return plugin_id in _loaded_or_loading_plugins or (plugin and plugin.isEnabled())

    @classmethod
    async def async_download_and_install_plugin(cls, msg_obj: MessageObject, plugin_id: str, skip_media_download=False, max_tries=3):
        if not skip_media_download:
            media_loaded = False
            for try_num in range(1, max_tries + 1):
                _logger.debug(f"Trying to load '{plugin_id}.plugin' file... (try {try_num}/{max_tries})")
                if media_loaded := await ensure_media_downloaded(msg_obj):
                    break

            if not media_loaded:
                _logger.warning("File was not loaded. Plugin installation aborted.")
                return

            _logger.debug("File was loaded successfully.")

        media = MessageObject.getMedia(msg_obj)
        attachment = media.photo or media.document
        file_path = str(get_file_loader().getPathToAttach(attachment, True))

        installed_engine = cls.get_plugin_engine_key(plugin_id)
        file_engine = cls.get_engine_key_for_file(file_path)
        if installed_engine not in (None, PluginsConstants.PYTHON, file_engine):
            _logger.warning(
                f"Plugin '{plugin_id}' is installed by the '{installed_engine}' engine, "
                f"but the file is for '{file_engine}'. Plugin installation aborted."
            )
            return

        if await PluginUtils.install_plugin(file_path):
            _logger.info(f"Plugin '{plugin_id}' was successfully downloaded and installed.")


def _get_app_running_ms() -> int:
    return SystemClock.elapsedRealtime() - Process.getStartElapsedRealtime()


_loaded_or_loading_plugins: Set[str] = {__id__}
