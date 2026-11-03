"""
CactusLib Compatibility Layer for oxDesktop
Compatible with exteraGram and AyuGram CactusLib plugins.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union

import client_utils
from base_plugin import BasePlugin, HookResult, HookStrategy
import tgnet_bridge
import tl_runtime

# Re-export HookResult and HookStrategy
__all__ = [
    "BasePlugin",
    "HookResult",
    "HookStrategy",
    "command",
    "uri",
    "message_uri",
    "CactusUtils",
]

_COMMANDS_REGISTRY: Dict[str, Dict[str, Callable]] = {}


def command(name: Optional[str] = None, doc: Optional[str] = None, prefixes: Union[str, tuple, list] = ("/", ".")):
    """
    Decorator to register a command in a CactusUtils.Plugin.
    Usage:
        @command("ping", doc="Check ping")
        def ping_cmd(self, cmd: CactusUtils.Command):
            cmd.answer("Pong!")
            return HookResult(HookStrategy.CANCEL)
    """
    def decorator(fn: Callable):
        cmd_name = (name or fn.__name__).lstrip("/.").lower()
        fn._cactus_command = {
            "name": cmd_name,
            "doc": doc or fn.__doc__ or "",
            "prefixes": tuple(prefixes) if isinstance(prefixes, (tuple, list)) else (prefixes,),
        }
        return fn
    return decorator


def uri(plugin: Union[str, BasePlugin], command_name: str, **kwargs) -> str:
    """Generate an internal plugin URI: extera://plugin/<plugin_id>/<command>?k=v"""
    plugin_id = getattr(plugin, "id", None) or getattr(plugin, "_extera_plugin_id", None) or str(plugin)
    query_parts = [f"{k}={v}" for k, v in kwargs.items()]
    qs = f"?{'&'.join(query_parts)}" if query_parts else ""
    return f"extera://plugin/{plugin_id}/{command_name}{qs}"


def message_uri(peer_id: int, message_id: int) -> str:
    """Generate internal message URI."""
    return f"tg://openmessage?chat_id={peer_id}&message_id={message_id}"


class CactusUtils:
    """Unified CactusLib helper utilities for oxDesktop."""

    class Command:
        """Represents an intercepted command execution context."""

        def __init__(self, name: str, args: List[str], text: str, params: Any, account: int, plugin: Any):
            self.name = name
            self.args = args
            self.text = text
            self.params = params
            self.account = account
            self.plugin = plugin
            
            # Extract peer and message details
            self.peer_id = int(getattr(params, "peer", 0) or getattr(params, "peer_id", 0) or client_utils.get_current_dialog_id())
            self.reply_to_id = int(getattr(params, "reply_to_id", 0) or getattr(params, "replyToMsg", 0) or 0)
            self.raw_message = getattr(params, "message", "") or ""

        def answer(self, text: str, parse_mode: Optional[str] = "markdown", reply_to_sender: bool = False):
            """Send a reply to the current dialog."""
            reply_id = self.reply_to_id if reply_to_sender else 0
            client_utils.send_text(
                peer_id=self.peer_id,
                text=str(text),
                replyToMsg=reply_id,
                parse_mode=parse_mode,
                account=self.account,
            )

        def reply(self, text: str, parse_mode: Optional[str] = "markdown"):
            """Send a reply targeting the current message or reply-to."""
            self.answer(text, parse_mode=parse_mode, reply_to_sender=True)

        def edit(self, new_text: str):
            """Modify outgoing message text in-place before it is sent."""
            self.params.message = str(new_text)

        def cancel(self) -> HookResult:
            """Cancel sending the command message."""
            return HookResult(strategy=HookStrategy.CANCEL)

    class Telegram:
        """Synchronous and asynchronous Telegram MTProto request helpers."""

        @staticmethod
        def send(req: Any, *, wait_response: bool = True, timeout: int = 7, raise_errors: bool = True) -> Any:
            """Send TLRPC request with optional synchronous waiting."""
            if not wait_response:
                return client_utils.send_request(req)

            event = threading.Event()
            result_box = [None, None]  # [response, error]

            def callback(resp, err):
                result_box[0] = resp
                result_box[1] = err
                event.set()

            req_id = client_utils.send_request(req, fn=callback)
            if not req_id:
                if raise_errors:
                    raise RuntimeError("Failed to send TLRPC request via client_utils")
                return None

            finished = event.wait(timeout=max(1, int(timeout)))
            if not finished:
                if raise_errors:
                    raise TimeoutError(f"TLRPC request {type(req).__name__} timed out after {timeout}s")
                return None

            response, error = result_box
            if error is not None:
                if raise_errors:
                    raise RuntimeError(f"TLRPC error: {error}")
                return None
            return response

        @staticmethod
        def tlrpc_object(cls_or_name: Any, **kwargs) -> Any:
            """Construct TLRPC object dynamically with kwargs."""
            if isinstance(cls_or_name, str):
                cls = getattr(tl_runtime.TLRPC, cls_or_name, None)
                if cls is None:
                    raise ValueError(f"Unknown TLRPC constructor: {cls_or_name}")
            else:
                cls = cls_or_name
            return cls(**kwargs)

        @staticmethod
        def get_user(user_id: int):
            return tgnet_bridge.get_user(user_id)

        @staticmethod
        def get_chat(chat_id: int):
            return tgnet_bridge.get_chat(chat_id)

        @staticmethod
        def get_peer(dialog_id: int):
            return tgnet_bridge.get_peer(dialog_id)

    class Database:
        """Lightweight persistent JSON storage for CactusLib plugins."""

        def __init__(self, plugin_id: str, db_name: str = "db.json"):
            self._plugin_id = plugin_id
            self._db_name = db_name
            self._lock = threading.RLock()
            self._data: Dict[str, Any] = {}
            self._loaded = False

        def _get_path(self) -> str:
            from extera_host import SETTINGS_DIR
            base_dir = SETTINGS_DIR or os.path.expanduser("~")
            db_dir = os.path.join(base_dir, "databases", self._plugin_id)
            os.makedirs(db_dir, exist_ok=True)
            return os.path.join(db_dir, self._db_name)

        def _load(self):
            if self._loaded:
                return
            with self._lock:
                path = self._get_path()
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            self._data = json.load(f)
                    except Exception:
                        self._data = {}
                else:
                    self._data = {}
                self._loaded = True

        def _save(self):
            with self._lock:
                path = self._get_path()
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(self._data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        def get(self, key: str, default: Any = None) -> Any:
            self._load()
            with self._lock:
                return self._data.get(key, default)

        def set(self, key: str, value: Any):
            self._load()
            with self._lock:
                self._data[key] = value
                self._save()

        def delete(self, key: str):
            self._load()
            with self._lock:
                if key in self._data:
                    del self._data[key]
                    self._save()

        def all(self) -> Dict[str, Any]:
            self._load()
            with self._lock:
                return dict(self._data)

    class Plugin(BasePlugin):
        """
        Base plugin class for CactusLib plugins.
        Provides automated @command dispatch, database access, and helper utilities.
        """

        def __init__(self):
            super().__init__()
            self._cactus_commands: Dict[str, Callable] = {}
            self._db: Optional[CactusUtils.Database] = None
            self.utils = CactusUtils
            self.Telegram = CactusUtils.Telegram

        def on_plugin_load(self):
            # Discover and register all methods decorated with @command
            for attr_name in dir(self):
                try:
                    attr = getattr(self, attr_name)
                    if callable(attr) and hasattr(attr, "_cactus_command"):
                        cmd_info = attr._cactus_command
                        cmd_name = cmd_info["name"]
                        self._cactus_commands[cmd_name] = attr
                except Exception:
                    continue

            # Enable outgoing message hook if commands exist
            if self._cactus_commands:
                self.add_on_send_message_hook(priority=100)

        @property
        def db(self) -> CactusUtils.Database:
            if self._db is None:
                pid = self.id or getattr(self, "_extera_plugin_id", "default")
                self._db = CactusUtils.Database(pid)
            return self._db

        def on_send_message_hook(self, account: int, params: Any) -> Optional[HookResult]:
            """Intercept outgoing messages and route registered commands."""
            if not self._cactus_commands:
                return HookResult(strategy=HookStrategy.DEFAULT)

            msg = getattr(params, "message", None)
            if not msg or not isinstance(msg, str) or not msg.strip():
                return HookResult(strategy=HookStrategy.DEFAULT)

            stripped = msg.strip()
            # Match command prefix
            for cmd_name, handler in self._cactus_commands.items():
                cmd_info = getattr(handler, "_cactus_command", {})
                prefixes = cmd_info.get("prefixes", ("/", "."))

                for pfx in prefixes:
                    pattern = f"^{re.escape(pfx)}{re.escape(cmd_name)}(\\s+.*)?$"
                    m = re.match(pattern, stripped, re.IGNORECASE)
                    if m:
                        rest = (m.group(1) or "").strip()
                        try:
                            args = shlex.split(rest)
                        except Exception:
                            args = rest.split()

                        cmd_ctx = CactusUtils.Command(
                            name=cmd_name,
                            args=args,
                            text=rest,
                            params=params,
                            account=account,
                            plugin=self,
                        )

                        try:
                            res = handler(cmd_ctx)
                            if isinstance(res, HookResult):
                                return res
                            # If no HookResult was returned, assume cancellation if answered or modified
                            return HookResult(strategy=HookStrategy.CANCEL)
                        except Exception as e:
                            self.logger.error(f"Command '{cmd_name}' execution error: {e}")
                            return HookResult(strategy=HookStrategy.DEFAULT)

            return HookResult(strategy=HookStrategy.DEFAULT)
