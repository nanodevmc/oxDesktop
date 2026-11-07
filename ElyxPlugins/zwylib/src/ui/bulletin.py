from typing import Optional, Any

from android_utils import copy_to_clipboard
from ui.bulletin import BulletinHelper as _BulletinHelper

from org.telegram.messenger import R

from ..core.locales import L
from ..utils.async_tools import async_manager
from .navigation import safe_open_message


class _InnerBulletinHelper(_BulletinHelper):
    def __init__(self, prefix: Optional[str] = None):
        self.prefix = "" if not prefix or not prefix.strip() else f"{prefix}:"

    def _get_prefixed_text(self, text: str) -> str:
        return f"{self.prefix} {text}" if self.prefix else text

    def show_info(self, message: str, fragment: Optional[Any] = None):
        _BulletinHelper.show_info(self._get_prefixed_text(message), fragment)

    def show_error(self, message: str, fragment: Optional[Any] = None):
        _BulletinHelper.show_simple(self._get_prefixed_text(message), R.raw.error, fragment)

    def show_success(self, message: str, fragment: Optional[Any] = None):
        _BulletinHelper.show_success(self._get_prefixed_text(message), fragment)

    def show_with_copy(self, message: str, text_to_copy: str, icon_res_id: int):
        _BulletinHelper.show_with_button(
            self._get_prefixed_text(message),
            icon_res_id,
            L.copy_button,
            on_click=lambda: copy_to_clipboard(text_to_copy),
        )

    def show_info_with_copy(self, message: str, copy_text: str):
        self.show_with_copy(message, str(copy_text), R.raw.info)

    def show_error_with_copy(self, message: str, copy_text: str):
        self.show_with_copy(message, str(copy_text), R.raw.error)

    def show_success_with_copy(self, message: str, copy_text: str):
        self.show_with_copy(message, str(copy_text), R.raw.contact_check)

    def show_with_post_redirect(self, message: str, button_text: str, peer_id: int, message_id: int, topic_id=0, peer_username: Optional[str] = None, icon_res_id: int=0):
        def open_post():
            async_manager.run_task(safe_open_message(
                peer_id,
                message_id,
                topic_id,
                peer_username
            ))

        _BulletinHelper.show_with_button(
            self._get_prefixed_text(message),
            icon_res_id,
            button_text,
            on_click=lambda: open_post(),
        )

    def show_info_with_post_redirect(self, message: str, button_text: str, peer_id: int, message_id: int, topic_id=0, peer_username: Optional[str] = None):
        self.show_with_post_redirect(message, button_text, peer_id, message_id, topic_id, peer_username, R.raw.info)

    def show_error_with_post_redirect(self, message: str, button_text: str, peer_id: int, message_id: int, topic_id=0, peer_username: Optional[str] = None):
        self.show_with_post_redirect(message, button_text, peer_id, message_id, topic_id, peer_username, R.raw.error)

    def show_success_with_post_redirect(self, message: str, button_text: str, peer_id: int, message_id: int, topic_id=0, peer_username: Optional[str] = None):
        self.show_with_post_redirect(message, button_text, peer_id, message_id, topic_id, peer_username, R.raw.contact_check)


def build_bulletin_helper(prefix: Optional[str] = None) -> "_InnerBulletinHelper":
    return _InnerBulletinHelper(prefix)


_bulletin = build_bulletin_helper()
