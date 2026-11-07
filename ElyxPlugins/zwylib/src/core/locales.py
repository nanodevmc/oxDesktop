from typing import Callable, Optional, Union, Dict

from org.telegram.messenger import LocaleController

from ..utils.logs import _logger
from .meta import LIB_NAME, __id__, _get_plugin_id_from_stack


class _SmartString(str):
    def __call__(self, **kwargs):
        try:
            return self.format(**kwargs)
        except KeyError:
            return self


class _Locales:
    def __init__(self, locales: Dict[str, Dict[str, str]]):
        for language_code, locales_dict in locales.items():
            setattr(self, language_code, locales_dict)

        if "en" in locales:
            self.default = locales["en"]
        elif locales:
            self.default = locales[next(iter(locales))]
        else:
            self.default = {}

    def __getattr__(self, key: str) -> Union[str, Callable]:
        return self.get(key)

    @staticmethod
    def _get_plural_form(number: int, forms: list, lang: str) -> str:
        number = abs(number)
        f_len = len(forms)

        if lang in ("ru", "uk") and f_len >= 3:
            if number % 10 == 1 and number % 100 != 11: return forms[0]
            if 2 <= number % 10 <= 4 and (number % 100 < 10 or number % 100 >= 20): return forms[1]
            return forms[2]

        # fallback
        if f_len == 0: return ""
        if f_len == 1: return forms[0]
        return forms[0] if number == 1 else forms[1]

    def _get_from_default(self, key: str) -> str:
        return self.default.get(key, key)

    def get(self, key: str, dictionary: Optional[Dict[str, str]] = None) -> Union[str, _SmartString]:
        if dictionary is None:
            lang = locales_controller.get_current_locale()
            dictionary = self.__dict__.get(lang, self.default)

        if not isinstance(dictionary, dict):
            dictionary = self.default

        val = dictionary.get(key)
        if val is None:
            val = self._get_from_default(key)

        if isinstance(val, str) and "{" in val and "}" in val:
            return _SmartString(val)
        return val

    def plural(self, key: str, number: int) -> str:
        lang = locales_controller.get_current_locale()
        dictionary = self.__dict__.get(lang, self.default)

        if not isinstance(dictionary, dict):
            dictionary = self.default

        forms = dictionary.get(key, self._get_from_default(key))
        if not isinstance(forms, list):
            return str(forms)
        return self._get_plural_form(number, forms, lang)


class _LocalesController:
    def __init__(self):
        self._locale: Optional[str] = None
        self.subs: Dict[str, Callable[[], None]] = {}

    def refresh_locale(self):
        self._locale = LocaleController.getInstance().getCurrentLocaleInfo().pluralLangCode
        for sub in self.subs.values():
            try:
                sub()
            except Exception:
                _logger.error("An error occurred:", exc_info=True)

    def subscribe_to_refresh(self, sub: Callable[[], None]):
        plugin_id = _get_plugin_id_from_stack(__id__)
        self.subs[plugin_id] = sub
        _logger.debug(f"'{plugin_id}' was subscribed to locale refresh.")

    def unsubscribe_from_refresh(self, plugin_id: Optional[str] = None):
        plugin_id = plugin_id or _get_plugin_id_from_stack(__id__)
        self.subs.pop(plugin_id, None)

    def get_current_locale(self) -> str:
        if not self._locale:
            self.refresh_locale()
        return self._locale

    @staticmethod
    def generate_locale_class(dictionaries: Dict[str, Dict[str, str]]) -> _Locales:
        return _Locales(dictionaries)


_locales = {
    "en": {
        "autoupdater_header": "Auto Updater",
        "autoupdate_timeout_title": "Auto Update Timeout",
        "autoupdate_timeout_hint": "Time in seconds between update checks.",
        "enable_autoupdates_title": "Auto-updates",
        "enable_autoupdates_hint": f"Auto-updates are supported for all plugins using {LIB_NAME}.",
        "not_sufficient_zwylib_ver": "{plugin_name} needs " + LIB_NAME + " {version}+, got {cur_ver}.",
        "update_bulletin_button": "Update",
        "debug_mode_title": "Debug Mode",
        "debug_mode_hint": "Prints some info to logs.",
        "dev_header": "Developer Stuff",
        "stub_command_message": "This command is a stub for registration of subcommand. Dont use it.",
        "copy_button": "Copy",
        "command_execution_error": "An error occurred executing command '{cmd_name}'",
        "force_update_check": "Force Update Check",
        "au_not_initialised" : "Auto updater was not started.",
        "plugin_install_error": "An error occurred while installing plugin '{}'.",
        "likely_cmd_name_misspelling": "It seems like you have misspelled the command name.",
        "alert_done": "Done",
        "alert_cancel": "Cancel",
        "force_update_check_started": "Checking for plugin updates...",
        "prefs_manage_au_tasks": "Manage autoupdate tasks",
        "prefs_manage_au_tasks_hint": "Enable/disable autoupdates for plugins",
        "prefs_au_enabled_header": "Enabled",
        "prefs_au_disabled_header": "Disabled",
        "prefs_au_tasks_hint": "Tap to toggle plugin's autoupdate status.",
        "no_plugins_using_zwylib_autoupdater_found": f"No plugins using {LIB_NAME} autoupdater found!",
    },
    "ru": {
        "autoupdater_header": "Автообновления",
        "autoupdate_timeout_title": "Таймаут автообновления",
        "autoupdate_timeout_hint": "Время в секундах между проверками обновлений.",
        "enable_autoupdates_title": "Автообновления",
        "enable_autoupdates_hint": f"Автообновления доступны всем плагинам, использующие {LIB_NAME}.",
        "not_sufficient_zwylib_ver": "{plugin_name} нужен " + LIB_NAME + " {version}+, текущая {cur_ver}.",
        "update_bulletin_button": "Обновить",
        "debug_mode_title": "Режим отладки",
        "debug_mode_hint": "Разрешает написывать еще больше логов.",
        "dev_header": "Для разработчиков",
        "stub_command_message": "Эта команда - заглушка для регистрации подкоманд. Не используйте ее.",
        "copy_button": "Скопировать",
        "command_execution_error": "Возникла ошибка при выполнении команды '{cmd_name}'",
        "force_update_check": "Проверить наличие обновлений",
        "au_not_initialised" : "Автообновлялка не была запущена.",
        "plugin_install_error": "Произошла ошибка во время установки плагина '{}'.",
        "likely_cmd_name_misspelling": "Похоже, что вы неправильно написали название команды.",
        "alert_done": "Готово",
        "alert_cancel": "Отмена",
        "force_update_check_started": "Проверка доступных обновлений...",
        "prefs_manage_au_tasks": "Задачи автообновления",
        "prefs_manage_au_tasks_hint": "Включение/отключение автообновлений для плагинов",
        "prefs_au_enabled_header": "Активные",
        "prefs_au_disabled_header": "Выключенные",
        "prefs_au_tasks_hint": "Нажмите, чтобы изменить статус автообновления плагина.",
        "no_plugins_using_zwylib_autoupdater_found": f"Плагины, использующие автообновление {LIB_NAME}, не найдены!",
    },
    "uk": {
        "autoupdater_header": "Автооновлення",
        "autoupdate_timeout_title": "Таймаут автооновлення",
        "autoupdate_timeout_hint": "Час у секундах між перевірками оновлень.",
        "enable_autoupdates_title": "Автооновлення",
        "enable_autoupdates_hint": f"Автооновлення доступні усім плагінам, що використовують {LIB_NAME}.",
        "not_sufficient_zwylib_ver": "{plugin_name} потрібен " + LIB_NAME + " {version}+, поточна {cur_ver}.",
        "update_bulletin_button": "Оновити",
        "debug_mode_title": "Режим налагодження",
        "debug_mode_hint": "Дозволяє написувати ще більше логів.",
        "dev_header": "Для розробників",
        "stub_command_message": "Ця команда - заглушка для реєстрації підкоманд. Не використовуйте її.",
        "copy_button": "Скопіювати",
        "command_execution_error": "Виникла помилка під час виконання команди '{cmd_name}'",
        "force_update_check": "Перевірити наявність оновлень",
        "au_not_initialised" : "Автооновлення не були ввімкнені.",
        "plugin_install_error": "Виникла помилка під час встановлення плагіну '{}'.",
        "likely_cmd_name_misspelling": "Схоже, що ви неправильно написали назву команди.",
        "alert_done": "Готово",
        "alert_cancel": "Скасувати",
        "force_update_check_started": "Перевірка доступних оновлень...",
        "prefs_manage_au_tasks": "Задачі автооновлення",
        "prefs_manage_au_tasks_hint": "Увімкнення/вимкнення автооновлень для плагінів",
        "prefs_au_enabled_header": "Активні",
        "prefs_au_disabled_header": "Вимкнені",
        "prefs_au_tasks_hint": "Натисніть, щоб змінити статус автооновлення плагіна.",
        "no_plugins_using_zwylib_autoupdater_found": f"Плагіни, що використовують автооновлення {LIB_NAME}, не знайдені!",
    },
}

locales_controller = _LocalesController()

L = locales_controller.generate_locale_class(_locales)
