import logging
import os
import sys

from client_utils import run_on_queue
from base_plugin import BasePlugin, HookResult, HookStrategy

from org.telegram.messenger import LocaleController
from com.exteragram.messenger.plugins import PluginsController, PythonPluginsEngine

_package_dir = os.path.dirname(os.path.dirname(sys._getframe().f_code.co_filename))
_stale_module = sys.modules.get("zwylib")
if _stale_module is not None and not str(getattr(_stale_module, "__file__", "") or "").startswith(_package_dir):
    for _module_name in [name for name in sys.modules if name == "zwylib" or name.startswith("zwylib.")]:
        del sys.modules[_module_name]

from zwylib.src.autoupdate.updater import _AutoUpdater, add_autoupdater_task, _cache_all_autoupdater_tasks, \
    _load_cached_autoupdater_tasks
from zwylib.src.commands.manager import _register_zwylib_commands, command_manager
from zwylib.src.core.lifecycle import _on_plugin_unload_hook, _refresh_language_hook, _reload_plugins_require_zwylib, \
    _on_plugin_toggle
from zwylib.src.core.meta import __id__, _AU_CHANNEL_ID, _AU_MSG_ID
from zwylib.src.core import state as _state
from zwylib.src.prefs.entries import S, _PrefsUtils
from zwylib.src.prefs.page import _PrefsGenerator
from zwylib.src.ui.plugin_cells import _CELL_CACHE
from zwylib.src.utils.async_tools import async_manager
from zwylib.src.utils.hooks import HookUtils
from zwylib.src.utils.logs import _logger, _cmd_logger, _au_logger
from zwylib.src.utils.traces import _TraceCollapser


_own_modules = {}


class ZwyLib(BasePlugin):
    def on_plugin_load(self):
        for module_name, module in _own_modules.items():
            sys.modules[module_name] = module
        _own_modules.clear()

        _logger.setLevel(logging.DEBUG if S.debug_mode.get() else logging.INFO)

        _PrefsUtils.execute_migrations()

        if S.enable_autoupdates.get():
            _state.autoupdater = _AutoUpdater()
            _load_cached_autoupdater_tasks()
            add_autoupdater_task(__id__, _AU_CHANNEL_ID, _AU_MSG_ID)
            _au_logger.debug("Added tasks from cache.")

            _state.autoupdater.run()
            _au_logger.debug("AutoUpdater ran.")

        command_manager.mark_as_not_temporal()
        command_manager.load_pending_commands()
        _register_zwylib_commands()
        _cmd_logger.debug("Command manager registered.")

        self.add_on_send_message_hook(priority=999)

        HookUtils.hook_before(
            HookUtils.find_max_args_method(PythonPluginsEngine.getClass(), "unloadPlugin"),
            _on_plugin_unload_hook
        )
        HookUtils.hook_after(
            HookUtils.find_max_args_method(LocaleController.getClass(), "applyLanguage"),
            _refresh_language_hook
        )
        HookUtils.hook_before(
            HookUtils.find_max_args_method(PluginsController.getClass(), "setPluginEnabled"),
            _on_plugin_toggle
        )
        _logger.debug("Hooked.")

        run_on_queue(_reload_plugins_require_zwylib)

        _logger.info("Loaded.")

    def on_plugin_unload(self):
        if _state.autoupdater:
            _cache_all_autoupdater_tasks()
            _logger.debug("AutoUpdater tasks cached.")

            _state.autoupdater.stop()
            _logger.debug("AutoUpdater loop was force-stopped.")

        async_manager.stop()
        _logger.debug("Async manager stopped.")

        command_manager.save_commands_as_pending()
        command_manager.unregister_all()
        _logger.debug("Commands cached.")

        _CELL_CACHE.clear()

        _logger.info("Unloaded.")

        for module_name in [name for name in sys.modules if name == __id__ or name.startswith(__id__ + ".")]:
            _own_modules[module_name] = sys.modules.pop(module_name)

    def create_settings(self):
        return _PrefsGenerator.generate_entries()

    def on_send_message_hook(self, account, params) -> HookResult:
        handlers = [
            command_manager.handle_send_message_hook,
            _TraceCollapser.handle_send_message_hook,
        ]

        for handler in handlers:
            result = handler(params, account)
            if result.strategy != HookStrategy.DEFAULT:
                return result
        return HookResult()
