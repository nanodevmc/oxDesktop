from __future__ import annotations

import functools
import json
import os
import re
import shlex
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import client_utils
from base_plugin import BasePlugin, HookResult, HookStrategy
import tgnet_bridge
import tl_runtime

__all__ = [
    "BasePlugin",
    "HookResult",
    "HookStrategy",
    "command",
    "uri",
    "message_uri",
    "CactusUtils",
]

_REGISTERED_COMMANDS: Dict[str, Dict[str, Dict[str, Any]]] = {}


def command(
    name: Optional[str] = None,
    doc: Optional[str] = None,
    prefixes: Union[str, tuple, list] = ("/", "."),
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        cmd_name = (name or fn.__name__).lstrip("/.").lower()
        prefix_tuple = tuple(prefixes) if isinstance(prefixes, (tuple, list)) else (prefixes,)
        fn._cactus_command = {
            "name": cmd_name,
            "doc": doc or fn.__doc__ or "",
            "prefixes": prefix_tuple,
        }
        return fn
    return decorator


def uri(plugin: Union[str, BasePlugin], command_name: str, **kwargs: Any) -> str:
    plugin_identifier = getattr(plugin, "id", None) or getattr(plugin, "_extera_plugin_id", None) or str(plugin)
    params = [f"{k}={v}" for k, v in kwargs.items()]
    query_string = f"?{'&'.join(params)}" if params else ""
    return f"extera://plugin/{plugin_identifier}/{command_name}{query_string}"


def message_uri(peer_id: int, message_id: int) -> str:
    return f"tg://openmessage?chat_id={peer_id}&message_id={message_id}"


class CactusUtils:
    class Uri:
        @staticmethod
        def create(plugin: Union[str, BasePlugin], command_name: str, **kwargs: Any) -> str:
            return uri(plugin, command_name, **kwargs)

    class Command:
        def __init__(self, name: str, args: List[str], text: str, params: Any, account: int, plugin: Any):
            self.name = name
            self.args = args
            self.text = text
            self.raw_args = text
            self.params = params
            self.account = account
            self.plugin = plugin

            p_id = int(getattr(params, "peer", 0) or getattr(params, "peer_id", 0) or client_utils.get_current_dialog_id())
            self.peer_id = p_id
            self.peer = p_id
            self.dialog_id = p_id

            r_id = int(getattr(params, "reply_to_id", 0) or getattr(params, "replyToMsg", 0) or 0)
            self.reply_to_id = r_id
            self.reply_to = r_id

            msg_text = getattr(params, "message", "") or ""
            self.raw_message = msg_text
            self.message = msg_text

        def answer(self, text: str, parse_mode: Optional[str] = "markdown", reply_to_sender: bool = False) -> None:
            reply_target = self.reply_to_id if reply_to_sender else 0
            client_utils.send_text(
                peer_id=self.peer_id,
                text=str(text),
                replyToMsg=reply_target,
                parse_mode=parse_mode,
                account=self.account,
            )

        def reply(self, text: str, parse_mode: Optional[str] = "markdown") -> None:
            self.answer(text, parse_mode=parse_mode, reply_to_sender=True)

        def edit(self, new_text: str) -> None:
            text_str = str(new_text)
            self.params.message = text_str
            try:
                self.params.text = text_str
            except Exception:
                pass
            if hasattr(self.params, "__setitem__"):
                try:
                    self.params["message"] = text_str
                    self.params["text"] = text_str
                except Exception:
                    pass

        def cancel(self) -> HookResult:
            return HookResult(strategy=HookStrategy.CANCEL)

    class Telegram:
        class TLRPCException(Exception):
            def __init__(self, error: Any):
                self.error = error
                super().__init__(str(error))

        class Result:
            def __init__(self, response: Any = None, error: Any = None):
                self.response = response
                self.error = error

        @classmethod
        def send(cls, req: Any, *, wait_response: bool = True, timeout: int = 7, raise_errors: bool = True) -> Any:
            if not wait_response:
                return client_utils.send_request(req)

            completion_event = threading.Event()
            payload_box: List[Any] = [None, None]

            def on_finished(resp: Any, err: Any) -> None:
                payload_box[0] = resp
                payload_box[1] = err
                completion_event.set()

            request_id = client_utils.send_request(req, fn=on_finished)
            if not request_id:
                if raise_errors:
                    raise RuntimeError("Failed to send TLRPC request via client_utils")
                return cls.Result(None, "Failed to send request")

            wait_success = completion_event.wait(timeout=max(1, int(timeout)))
            if not wait_success:
                if raise_errors:
                    raise TimeoutError(f"TLRPC request {type(req).__name__} timed out after {timeout}s")
                return cls.Result(None, f"Request timed out after {timeout}s")

            response_data, error_data = payload_box
            if error_data is not None:
                if raise_errors:
                    raise cls.TLRPCException(error_data)
                return cls.Result(None, error_data)

            if not raise_errors:
                return cls.Result(response_data, None)
            return response_data

        send_request = send

        @staticmethod
        def tlrpc_object(cls_or_name: Any, **kwargs: Any) -> Any:
            if isinstance(cls_or_name, str):
                target_cls = getattr(tl_runtime.TLRPC, cls_or_name, None)
                if target_cls is None:
                    raise ValueError(f"Unknown TLRPC constructor: {cls_or_name}")
            else:
                target_cls = cls_or_name
            return target_cls(**kwargs)

        @staticmethod
        def get_user(user_id: int) -> Any:
            return tgnet_bridge.get_user(user_id)

        @staticmethod
        def get_chat(chat_id: int) -> Any:
            return tgnet_bridge.get_chat(chat_id)

        @staticmethod
        def get_peer(dialog_id: int) -> Any:
            return tgnet_bridge.get_peer(dialog_id)

    class Database:
        def __init__(self, plugin_id: str, db_name: str = "db.json"):
            self._plugin_id = plugin_id
            self._db_name = db_name
            self._lock = threading.RLock()
            self._cached_store: Dict[str, Any] = {}
            self._is_ready = False

        def _locate_file_path(self) -> str:
            from extera_host import SETTINGS_DIR
            base_dir = SETTINGS_DIR or os.path.expanduser("~")
            db_dir = os.path.join(base_dir, "databases", self._plugin_id)
            os.makedirs(db_dir, exist_ok=True)
            return os.path.join(db_dir, self._db_name)

        def _ensure_loaded(self) -> None:
            if self._is_ready:
                return
            with self._lock:
                path = self._locate_file_path()
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as handle:
                            self._cached_store = json.load(handle)
                    except Exception:
                        self._cached_store = {}
                else:
                    self._cached_store = {}
                self._is_ready = True

        def _persist(self) -> None:
            with self._lock:
                path = self._locate_file_path()
                try:
                    with open(path, "w", encoding="utf-8") as handle:
                        json.dump(self._cached_store, handle, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        def get(self, key: str, default: Any = None) -> Any:
            self._ensure_loaded()
            with self._lock:
                return self._cached_store.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self._ensure_loaded()
            with self._lock:
                self._cached_store[key] = value
                self._persist()

        def delete(self, key: str) -> None:
            self._ensure_loaded()
            with self._lock:
                if key in self._cached_store:
                    del self._cached_store[key]
                    self._persist()

        def all(self) -> Dict[str, Any]:
            self._ensure_loaded()
            with self._lock:
                return dict(self._cached_store)

    @staticmethod
    def get_all_commands() -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for pid, commands in _REGISTERED_COMMANDS.items():
            for cmd_name, info in commands.items():
                pfxs = info.get("prefixes", ("/", "."))
                entries.append({
                    "name": cmd_name,
                    "doc": info.get("doc", ""),
                    "prefix": pfxs[0] if pfxs else "/",
                    "prefixes": pfxs,
                    "plugin_id": pid,
                })
        return entries

    class Plugin(BasePlugin):
        def __init__(self):
            super().__init__()
            self._cactus_commands: Dict[str, Callable] = {}
            self._db_instance: Optional[CactusUtils.Database] = None
            self.utils = CactusUtils
            self.Telegram = CactusUtils.Telegram

        def _register_cactus_commands(self) -> None:
            pid = self.id or getattr(self, "_extera_plugin_id", "default")
            if pid not in _REGISTERED_COMMANDS:
                _REGISTERED_COMMANDS[pid] = {}

            for member_name in dir(self):
                try:
                    member = getattr(self, member_name)
                    if callable(member) and hasattr(member, "_cactus_command"):
                        cmd_spec = member._cactus_command
                        cmd_name = cmd_spec["name"]
                        self._cactus_commands[cmd_name] = member
                        _REGISTERED_COMMANDS[pid][cmd_name] = {
                            "name": cmd_name,
                            "doc": cmd_spec.get("doc", ""),
                            "prefixes": cmd_spec.get("prefixes", ("/", ".")),
                            "handler": member,
                            "plugin_id": pid,
                        }
                except Exception:
                    continue

            if self._cactus_commands:
                self.add_on_send_message_hook(priority=100)

        def get_all_commands(self) -> List[Dict[str, Any]]:
            return CactusUtils.get_all_commands()

        def _extera_attach(self, plugin_id: str) -> None:
            super()._extera_attach(plugin_id)
            self._register_cactus_commands()

        def on_plugin_load(self) -> None:
            self._register_cactus_commands()
            super().on_plugin_load()

        def on_plugin_unload(self) -> None:
            pid = self.id or getattr(self, "_extera_plugin_id", "default")
            _REGISTERED_COMMANDS.pop(pid, None)
            super().on_plugin_unload()

        @property
        def db(self) -> CactusUtils.Database:
            if self._db_instance is None:
                pid = self.id or getattr(self, "_extera_plugin_id", "default")
                self._db_instance = CactusUtils.Database(pid)
            return self._db_instance

        def on_send_message_hook(self, account: int, params: Any) -> Optional[HookResult]:
            if not self._cactus_commands:
                return HookResult(strategy=HookStrategy.DEFAULT)

            msg = getattr(params, "message", None)
            if not msg or not isinstance(msg, str) or not msg.strip():
                return HookResult(strategy=HookStrategy.DEFAULT)

            stripped_msg = msg.strip()

            for cmd_name, handler in self._cactus_commands.items():
                cmd_meta = getattr(handler, "_cactus_command", {})
                prefix_list = cmd_meta.get("prefixes", ("/", "."))

                for pfx in prefix_list:
                    pattern = f"^{re.escape(pfx)}{re.escape(cmd_name)}(\\s+.*)?$"
                    matched = re.match(pattern, stripped_msg, re.IGNORECASE)
                    if matched:
                        tail = (matched.group(1) or "").strip()
                        try:
                            split_args = shlex.split(tail)
                        except Exception:
                            split_args = tail.split()

                        cmd_context = CactusUtils.Command(
                            name=cmd_name,
                            args=split_args,
                            text=tail,
                            params=params,
                            account=account,
                            plugin=self,
                        )

                        try:
                            try:
                                outcome = handler(cmd_context)
                            except TypeError:
                                outcome = handler(self, cmd_context)

                            if isinstance(outcome, HookResult):
                                return outcome
                            return HookResult(strategy=HookStrategy.CANCEL)
                        except Exception as exc:
                            self.logger.error(f"Command '{cmd_name}' execution error: {exc}")
                            return HookResult(strategy=HookStrategy.DEFAULT)

            return HookResult(strategy=HookStrategy.DEFAULT)
