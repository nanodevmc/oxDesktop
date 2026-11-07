import asyncio
import os.path
from asyncio import Future
from dataclasses import dataclass
from typing import List, Optional, Union

from typing_extensions import overload

from client_utils import run_on_queue

from org.telegram.messenger import MessageObject, UserConfig
from com.exteragram.messenger.plugins import PluginsController

from ..core.companion import _companion
from ..core.meta import __id__, _get_plugin_id_from_stack
from ..core import state as _state
from ..prefs.entries import S, SettingsManager
from ..utils.async_tools import async_manager
from ..utils.cache import JsonCacheFile
from ..utils.java_utils import arraylist_to_list
from ..utils.logs import _logger, _au_logger
from ..utils.media import ensure_media_downloaded
from ..utils.plugin import PluginUtils
from ..utils.tl_requests import Requests


@dataclass
class _UpdaterTask:
    plugin_id: str
    channel_id: int
    message_id: int


class _AutoUpdater:
    def __init__(self):
        self.tasks: List[_UpdaterTask] = []
        self.force_check_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self._current_task: Optional[Future[None]] = None

    def run(self):
        def _run_internal():
            self._current_task = async_manager.run_task(self._loop())

        if self._current_task and not self._current_task.done():
            _au_logger.debug("AutoUpdater task already started.")
            return

        # wait until the client finished loading
        run_on_queue(_run_internal, delay=2000)
        _au_logger.debug("Planned AutoUpdater run in 2 seconds.")

    # noinspection PyTypeChecker
    def stop(self):
        async_manager.loop.call_soon_threadsafe(self.stop_event.set)
        async_manager.loop.call_soon_threadsafe(self.force_check_event.set)  # awake coro immediately

    async def _loop(self):
        _au_logger.debug("AutoUpdater loop started.")

        while not self.stop_event.is_set():
            try:
                try:
                    await asyncio.wait_for(
                        self.force_check_event.wait(),
                        timeout=S.autoupdate_timeout.safe_get(int)
                    )
                    _au_logger.debug("Forced update check...")
                except asyncio.TimeoutError:
                    pass
                finally:
                    self.force_check_event.clear()

                await self.check_for_updates()
            except Exception:
                _au_logger.error("Exception in async cycle:", exc_info=True)
                await asyncio.sleep(30)

    async def check_for_updates(self):
        _au_logger.debug("Checking for updates...")

        for task in list(self.tasks):
            plugin_id = task.plugin_id
            _au_logger.debug(f"Checking for '{plugin_id}'...")

            plugin = PluginUtils.get_plugin(plugin_id)
            if plugin and "b" in (plugin.getVersion() or ""):
                _au_logger.debug(f"Version of plugin '{plugin_id}' was identified as beta. Task was skipped.")
                continue

            if plugin is None:
                _au_logger.debug(f"Plugin '{plugin_id}' was not found. Task was removed.")
                self.remove_task(task)
                continue

            if not PluginUtils.is_plugin_loaded_or_loading(plugin_id):
                _au_logger.debug(f"Plugin '{plugin_id}' is disabled. Task was skipped.")
                continue

            if not autoupdate_config.is_autoupdate_on(plugin_id):
                _au_logger.debug(f"Autoupdates disabled for plugin '{plugin_id}'. Task was skipped.")
                continue

            _au_logger.debug(f"Executing for task '{plugin_id}' ({task}).")

            try:
                response = await Requests.get_message(-task.channel_id, task.message_id)
                messages = arraylist_to_list(response.messages)
                if not messages:
                    _au_logger.warning(f"Message {task.message_id} not found in '{task.channel_id}'.")
                    continue

                message = messages[0]
                msg_obj = MessageObject(UserConfig.selectedAccount, message, False, False)
            except Exception:
                _au_logger.error("An error occurred:", exc_info=True)
                continue

            _au_logger.debug("Checking if the file is a plugin...")
            await ensure_media_downloaded(msg_obj)

            if not PluginsController.isPlugin(msg_obj):
                _au_logger.debug(f"The document attached to task '{plugin_id}' message is not plugin. Task was skipped.")
                continue

            if not S.disable_ts_check.get() and message.edit_date == autoupdate_config.get_last_updated(plugin_id):
                _au_logger.debug(f"Attachment for task '{plugin_id}' has not been updated. Task was skipped.")
                continue

            _au_logger.debug("File verified. Installing plugin...")

            autoupdate_config.set_last_updated(plugin_id, message.edit_date)
            await PluginUtils.async_download_and_install_plugin(msg_obj, plugin_id, skip_media_download=True)

    def add_task(self, task: _UpdaterTask):
        if task in self.tasks:
            _au_logger.warning(f"Task {task.plugin_id} is already present.")
            return
        self.tasks.append(task)
        _au_logger.debug(f"Added task '{task.plugin_id}'.")

    def remove_task(self, task: _UpdaterTask):
        if task not in self.tasks:
            _au_logger.warning(f"Task '{task.plugin_id}' is not present.")
            return
        self.tasks.remove(task)
        _au_logger.debug(f"Removed task '{task.plugin_id}'")

    def remove_task_by_id(self, plugin_id: str):
        filtered_tasks = list(filter(lambda task: task.plugin_id != plugin_id, self.tasks))
        if len(filtered_tasks) < len(self.tasks):
            self.tasks = filtered_tasks
            _au_logger.debug(f"Removed task '{plugin_id}'.")
        else:
            _au_logger.warning(f"Task '{plugin_id}' is not present.")

    # noinspection PyTypeChecker
    def force_update_check(self):
        async_manager.loop.call_soon_threadsafe(self.force_check_event.set)
        _au_logger.debug("force_update_check")


@overload
def add_autoupdater_task(channel_id: int, message_id: int):
    ...


@overload
def add_autoupdater_task(plugin_id: str, channel_id: int, message_id: int):
    ...


def add_autoupdater_task(plugin_id: Union[str, int], channel_id: int, message_id: Optional[int] = None):
    if isinstance(plugin_id, int):  # using (channel_id: int, message_id: int) args signature
        channel_id, message_id = plugin_id, channel_id
        plugin_id = _get_plugin_id_from_stack(__id__)

    task = _UpdaterTask(plugin_id, channel_id, message_id)

    if _state.autoupdater is None:
        _companion.module.autoupdates_tasks.append(task)
        _logger.debug(f"Saved AutoUpdater task '{plugin_id}' to cache.")
        return

    _state.autoupdater.add_task(task)
    _logger.debug(f"Added '{plugin_id}' AutoUpdater task.")


def remove_autoupdater_task(plugin_id: Optional[str] = None):
    if plugin_id is None:
        plugin_id = _get_plugin_id_from_stack(__id__)

    if _state.autoupdater is None:
        _companion.module.autoupdates_tasks = list(
            filter(lambda task: task.plugin_id != plugin_id, _companion.module.autoupdates_tasks)
        )
        _logger.debug(f"Removed '{plugin_id}' AutoUpdater task from cache.")
        return

    _state.autoupdater.remove_task_by_id(plugin_id)
    _logger.debug(f"Removed '{plugin_id}' AutoUpdater task.")


def _cache_all_autoupdater_tasks():
    _companion.module.autoupdates_tasks.clear()
    _companion.module.autoupdates_tasks = _state.autoupdater.tasks.copy()
    _logger.debug("All AutoUpdater tasks have been cached.")


def _load_cached_autoupdater_tasks():
    _state.autoupdater.tasks = _companion.module.autoupdates_tasks.copy()
    _companion.module.autoupdates_tasks.clear()
    _logger.debug("All AutoUpdater tasks have been loaded from cache.")


def toggle_plugin_autoupdates(pid: str):
    autoupdate_config.toggle_autoupdate(pid)
    SettingsManager.reload()


class _AutoUpdateConfig:
    def __init__(self):
        self._storage = JsonCacheFile("zwylib_au__config", {})
        self._timestamps_storage = JsonCacheFile("zwylib_au__msg_edited_ts", {})  # plugin_id: edit_timestamp_of_message_with_file
        self._merge_configs_if_needed()

    def _update_key(self, plugin_id: str, key: str, value):
        self._storage.content.setdefault(plugin_id, {})[key] = value
        self._storage.write()

    def _merge_configs_if_needed(self):
        if os.path.exists(self._timestamps_storage.path):
            _logger.debug(f"Merging timestamps info to common config: {self._timestamps_storage.content}")

            for plugin_id, timestamp in self._timestamps_storage.content.items():
                self._update_key(plugin_id, "last_updated", timestamp)
            self._timestamps_storage.delete()

    def is_autoupdate_on(self, plugin_id: str) -> bool:
        return self._storage.content.get(plugin_id, {}).get("autoupdates", True)

    def enable_autoupdate(self, plugin_id: str, enabled: bool):
        self._update_key(plugin_id, "autoupdates", enabled)
        _logger.debug(f"{'Enabled' if enabled else 'Disabled'} autoupdates for '{plugin_id}'.")

    def toggle_autoupdate(self, plugin_id: str):
        self.enable_autoupdate(plugin_id, not self.is_autoupdate_on(plugin_id))

    def get_last_updated(self, plugin_id: str) -> int:
        return self._storage.content.get(plugin_id, {}).get("last_updated", 0)

    def set_last_updated(self, plugin_id: str, timestamp: int):
        return self._update_key(plugin_id, "last_updated", timestamp)

    def wipe_timestamp_storage(self):
        for plugin_id in self._storage.content.keys():
            self._update_key(plugin_id, "last_updated", 0)
        _logger.debug("Timestamp storage was wiped.")


autoupdate_config = _AutoUpdateConfig()
