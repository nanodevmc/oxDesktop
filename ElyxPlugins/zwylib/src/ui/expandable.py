from dataclasses import dataclass, field
from typing import List, Callable, Optional, Dict

from android_utils import OnClickListener
from ui.settings import Custom

from java import cast
from org.telegram.ui.Cells import TextCheckCell2
from org.telegram.ui.Components import UItem

from ..core.meta import __id__, _get_plugin_id_from_stack
from ..prefs.entries import SettingEntry, SettingsManager
from ..utils.async_tools import safe_func_call
from ..utils.logs import _logger


@dataclass
class ExpandableOption:
    text: str
    settings_entry: SettingEntry
    on_toggle: Optional[Callable[[bool], None]] = None

    def set_value(self, value: bool):
        self.settings_entry.set(value)
        safe_func_call(self.on_toggle, [value])

    def toggle(self):
        self.set_value(not self.settings_entry.get())

    def as_settings_option(self) -> Custom:
        return Custom(
            item=UItem.asRoundCheckbox(-1, self.text).setChecked(self.settings_entry.get()).pad(),
            on_click=lambda _, opt=self: opt.toggle(),
        )


@dataclass
class ExpandableSwitchDispatcher:
    main_switch_text: str
    connected_options: List[ExpandableOption]
    plugin_id: str
    collapsed: bool = field(default=True, init=False)

    def generate_option_list(self) -> List[Custom]:
        try:
            entries = [
                Custom(
                    item=UItem.asExteraExpandableSwitch(
                        -1, self.main_switch_text,
                        f"{self.get_selected_count()}/{self.get_selected_count(force=True)}",
                        OnClickListener(lambda _: self.toggle_all())
                    ).setCollapsed(self.collapsed).setChecked(self.is_selected_all()),
                    on_click=self.toggle_collapsed,
                )
            ]

            if self.collapsed:
                return entries

            entries += [i.as_settings_option() for i in self.connected_options]
            return entries
        except Exception:
            _logger.error("An error occurred:", exc_info=True)
            return []

    def toggle_collapsed(self, view):
        self.collapsed = not self.collapsed
        cast(TextCheckCell2, view).setCollapsed(self.collapsed)
        SettingsManager.reload(self.plugin_id)

    def get_selected_count(self, force=False) -> int:
        return len([opt for opt in self.connected_options if opt.settings_entry.get() or force])

    def is_selected_all(self) -> bool:
        return self.get_selected_count() == self.get_selected_count(force=True)

    def toggle_all(self):
        checked = not self.is_selected_all()
        for option in self.connected_options:
            option.set_value(checked)


class ExpandableSwitchManager:
    hub: Dict[str, ExpandableSwitchDispatcher] = {}

    @classmethod
    def generate(cls, main_switch_text: str, connected_options: List[ExpandableOption]) -> List[Custom]:
        if main_switch_text not in cls.hub:
            cls.hub[main_switch_text] = ExpandableSwitchDispatcher(
                main_switch_text,
                connected_options,
                _get_plugin_id_from_stack(__id__)
            )
        return cls.hub[main_switch_text].generate_option_list()
