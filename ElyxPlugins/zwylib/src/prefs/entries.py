from typing import Callable, Optional, Any, Union

import plugin_settings
from ui.settings import Switch, Input, Selector

from com.exteragram.messenger.plugins import PluginsController

from ..core.meta import __id__, _T, _get_plugin_id_from_stack
from ..ui.bulletin import _bulletin
from ..utils.logs import _logger


class SettingEntry:
    def __init__(self, key: str, default: Any, icon: Optional[str] = None):
        self.key = key
        self.default = default
        self.icon = icon
        self.plugin_id = _get_plugin_id_from_stack(__id__)

    def get(self) -> Any:
        return SettingsManager.get(self.plugin_id, self)

    def safe_get(self, factory: Callable[[Any], _T], bulletin_text: str = None, log_text: str = None) -> _T:
        try:
            return factory(self.get())
        except Exception:
            _logger.error(log_text or f"Error getting setting '{self.key}', using default instead. Trace:", exc_info=True)
            if bulletin_text:
                _bulletin.show_error(bulletin_text)
            return factory(self.default)

    def set(self, value: Any):
        SettingsManager.set(self.plugin_id, self.key, value)

    def _bind(self, component_cls, **kwargs):
        kwargs["key"] = self.key
        kwargs["default"] = self.default
        if self.icon:
            kwargs["icon"] = self.icon
        return component_cls(**kwargs)

    def as_input(self, **kwargs) -> Input:
        return self._bind(Input, **kwargs)

    def as_selector(self, **kwargs) -> Selector:
        return self._bind(Selector, **kwargs)

    def as_switch(self, **kwargs) -> Switch:
        return self._bind(Switch, **kwargs)


class S:
    autoupdate_timeout = SettingEntry("autoupdate_timeout", "600", icon="msg2_autodelete")
    enable_autoupdates = SettingEntry("enable_autoupdates", True, icon="msg_download")
    disable_ts_check = SettingEntry("disable_ts_check", False, icon="msg_recent")
    debug_mode = SettingEntry("debug_mode", False, icon="msg_log")

    # Deprecated
    disable_autoupdate = SettingEntry("disable_autoupdate", False)


class SettingsManager:
    @classmethod
    def get(cls, plugin_id: str, item: Union[str, SettingEntry], default: Optional[_T] = None) -> Optional[_T]:
        if isinstance(item, SettingEntry):
            return plugin_settings.get_setting(plugin_id, item.key, item.default)
        return plugin_settings.get_setting(plugin_id, item, default)

    @classmethod
    def set(cls, plugin_id: str, item: Union[str, SettingEntry], value: Any, reload_settings=True):
        key = item.key if isinstance(item, SettingEntry) else item
        plugin_settings.set_setting(plugin_id, key, value)
        if reload_settings:
            cls.reload(plugin_id)

    @classmethod
    def reload(cls, plugin_id: str = None):
        plugin_id = plugin_id or _get_plugin_id_from_stack(__id__)
        PluginsController.getInstance().loadPluginSettings(plugin_id)

    # noinspection PyProtectedMember
    @classmethod
    def remove_setting(cls, key: str, plugin_id: str = None):
        plugin_id = plugin_id or _get_plugin_id_from_stack(__id__)
        with plugin_settings._lock:
            if plugin_id in plugin_settings._settings_cache:
                plugin_settings._settings_cache[plugin_id].pop(key, None)
                plugin_settings._save_settings_to_file()


class _PrefsUtils:
    @classmethod
    def execute_migrations(cls):
        previous = SettingsManager.get(__id__, S.disable_autoupdate.key, None)
        if previous is not None:
            S.enable_autoupdates.set(not previous)
