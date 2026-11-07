import logging
from typing import List

from android_utils import copy_to_clipboard
from ui.settings import Header, Text, Divider, Custom

from ..autoupdate.updater import autoupdate_config
from ..core.locales import L
from ..core import state as _state
from ..ui.bulletin import _bulletin
from ..ui.plugin_cells import plugin_cell_setting_factory_instance, _CELL_CACHE
from ..utils.logs import format_exc_from, _logger
from ..utils.plugin import _does_plugin_uses_zwylib_autoupdater, PluginUtils
from .entries import S


class _PrefsGenerator:
    @classmethod
    def generate_entries(cls) -> list:
        try:
            stuff = [
                cls._gen_autoupdate(),
                cls._gen_dev()
            ]
            return [item for sublist in stuff for item in sublist]
        except Exception as e:
            _logger.error("An error occurred while generating settings:", exc_info=True)
            return [
                Divider(f"An error occurred while generating settings:\n{e}"),
                Text(
                    text="Copy full traceback",
                    icon="msg_copy",
                    on_click=lambda _: copy_to_clipboard(format_exc_from(e))
                )
            ]

    @classmethod
    def _gen_autoupdate(cls) -> list:
        def force_update_check_onclick():
            if not _state.autoupdater:
                _bulletin.show_error(L.au_not_initialised)
                return
            _state.autoupdater.force_update_check()
            _bulletin.show_info(L.force_update_check_started)

        entries: List = [
            Header(L.autoupdater_header),
            S.enable_autoupdates.as_switch(
                text=L.enable_autoupdates_title,
                subtext=L.enable_autoupdates_hint,
                on_change=lambda enabled: _state.autoupdater.stop() if enabled else _state.autoupdater.run()
            ),
        ]

        if not S.enable_autoupdates.get():
            entries.append(Divider())
            return entries

        return [
            *entries,
            S.autoupdate_timeout.as_input(
                text=L.autoupdate_timeout_title,
                subtext=L.autoupdate_timeout_hint,
            ),
            Text(
                text=L.force_update_check,
                icon="msg_photo_switch2",
                accent=True,
                on_click=lambda _: force_update_check_onclick()
            ),
            Divider(),
            Text(
                text=L.prefs_manage_au_tasks,
                subtext=L.prefs_manage_au_tasks_hint,
                icon="msg_list",
                create_sub_fragment=lambda: cls._gen_autoupdate_sub()
            ),
            Divider(),
        ]

    @classmethod
    def _gen_autoupdate_sub(cls):
        plugins = PluginUtils.get_plugins()
        if not plugins:
            return [Text(L.no_plugins_used_zwylib_autoupdater_found)]

        active_plugins = {
            p_id: p for p_id, p in plugins.items()
            if _does_plugin_uses_zwylib_autoupdater(p_id) and PluginUtils.is_plugin_loaded_or_loading(p_id)
        }

        if not active_plugins:
            return [Text(L.no_plugins_used_zwylib_autoupdater_found)]

        for cached_id in list(_CELL_CACHE.keys()):
            if cached_id not in active_plugins:
                del _CELL_CACHE[cached_id]

        enabled_cells = []
        disabled_cells = []

        for plugin_id, plugin in active_plugins.items():
            if plugin_id not in _CELL_CACHE:
                _CELL_CACHE[plugin_id] = Custom(
                    factory=plugin_cell_setting_factory_instance,
                    factory_args=plugin,
                )

            cell = _CELL_CACHE[plugin_id]
            if autoupdate_config.is_autoupdate_on(plugin_id):
                enabled_cells.append(cell)
            else:
                disabled_cells.append(cell)

        entries = []

        if enabled_cells:
            entries += [Header(L.prefs_au_enabled_header), *enabled_cells, Divider()]

        if disabled_cells:
            entries += [Header(L.prefs_au_disabled_header), *disabled_cells, Divider()]

        if isinstance(entries[-1], Divider):
            entries.pop(-1)
        entries.append(Divider(L.prefs_au_tasks_hint))

        return entries

    @classmethod
    def _gen_dev(cls) -> list:
        def switch_debug_mode(enabled: bool):
            _logger.setLevel(logging.DEBUG if enabled else logging.INFO)
            _logger.info(f"Set '{logging.getLevelName(_logger.level)}' level.")

        def wipe_ts_db(_):
            autoupdate_config.wipe_timestamp_storage()
            _bulletin.show_success("Timestamp storage has been wiped!")

        entries: List = [
            Header(L.dev_header),
            S.debug_mode.as_switch(
                text=L.debug_mode_title,
                subtext=L.debug_mode_hint,
                on_change=switch_debug_mode,
            )
        ]

        if not S.debug_mode.get():
            return entries + [Divider()]

        entries.extend([
            S.disable_ts_check.as_switch(
                text="Disable timestamp check",
            ),
            Text(
                text="Wipe timestamp storage",
                on_click=wipe_ts_db,
            ),
            Divider(),
        ])

        return entries
