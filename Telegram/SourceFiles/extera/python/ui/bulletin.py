from typing import Any, Callable, Optional

import _extera


class BulletinHelper:
    DURATION_SHORT = 1500
    DURATION_LONG = 2750
    DURATION_PROLONG = 5000

    @staticmethod
    def show_info(message: str, fragment: Any = None, *args, **kwargs):
        _extera.toast(str(message))

    @staticmethod
    def show_error(message: str, fragment: Any = None, *args, **kwargs):
        _extera.toast(str(message))

    @staticmethod
    def show_success(message: str, fragment: Any = None, *args, **kwargs):
        _extera.toast(str(message))

    @staticmethod
    def show_simple(message: str, icon: Any = None, fragment: Any = None,
                    *args, **kwargs):
        _extera.toast(str(message))

    @staticmethod
    def show_with_button(message: str, icon: Any = None,
                         button_text: str = "",
                         on_click: Optional[Callable] = None, *args, **kwargs):
        _extera.toast(str(message))

    @staticmethod
    def show_copied_to_clipboard(*args, **kwargs):
        _extera.toast("Copied to clipboard")

    @staticmethod
    def show_link_copied(*args, **kwargs):
        _extera.toast("Link copied")
