from client_utils import run_on_queue

from com.exteragram.messenger.plugins import PluginsConstants

from ..autoupdate.updater import remove_autoupdater_task
from ..commands.manager import command_manager
from ..prefs.entries import SettingsManager
from ..ui.plugin_cells import _CELL_CACHE
from ..utils.async_tools import async_manager
from ..utils.logs import _logger
from ..utils.plugin import _does_plugin_require_zwylib, PluginUtils, _get_app_running_ms, _loaded_or_loading_plugins
from .locales import locales_controller
from .meta import LIB_NAME


def _perform_cleanup(plugin_id: str):
    async_manager.cancel_all_for(plugin_id)
    remove_autoupdater_task(plugin_id)
    command_manager.remove_dispatcher(plugin_id)
    locales_controller.unsubscribe_from_refresh(plugin_id)

    if plugin_id in _loaded_or_loading_plugins:
        _loaded_or_loading_plugins.remove(plugin_id)

    _logger.debug(f"Performed cleanup for '{plugin_id}'.")


def _on_plugin_unload_hook(param):
    _perform_cleanup(param.args[0])


def _refresh_language_hook(_):
    _logger.debug("Refreshing locale...")
    locales_controller.refresh_locale()
    SettingsManager.reload()


def _reload_plugins_require_zwylib():
    if not (plugins := PluginUtils.get_plugins()):
        return

    if _get_app_running_ms() < 15 * 1000:
        _logger.debug(f"Reload task of plugins require {LIB_NAME} was skipped.")
        return

    _logger.debug(f"Reloading plugins require {LIB_NAME}...")

    try:
        for plugin_id, plugin in plugins.items():
            if plugin.getEngine() != PluginsConstants.PYTHON:
                continue

            is_plugin_loaded = PluginUtils.is_plugin_loaded_or_loading(plugin_id)
            plugin_has_error_cuz_of_zwylib = (err := plugin.getError()) and err and "zwylib" in err.getMessage().lower()
            if not is_plugin_loaded and not plugin_has_error_cuz_of_zwylib:
                continue

            if _does_plugin_require_zwylib(plugin_id):
                run_on_queue(lambda pid=plugin_id: PluginUtils.reload_plugin(pid), delay=2000)
                _logger.debug(f"Planned reload of '{plugin_id}' plugin.")
    except Exception:
        _logger.error("An error occurred:", exc_info=True)


def _on_plugin_toggle(param):
    plugin_id: str = param.args[0]
    enabled: bool = param.args[1]

    _CELL_CACHE.pop(plugin_id, None)

    if enabled:
        _loaded_or_loading_plugins.add(plugin_id)
    else:
        _perform_cleanup(plugin_id)
