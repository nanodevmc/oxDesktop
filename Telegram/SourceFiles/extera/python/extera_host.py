"""
oxDesktop Python Plugin Host & Runtime Dispatcher.
Provides sandbox lifecycle management, secure inter-process dispatch,
and event wrapping for embedded plugins.
"""

import contextlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import threading
import traceback
import uuid

import _extera
import _compat

PLUGINS_DIR = ""
SETTINGS_DIR = ""
_lock = threading.RLock()
_records = {}
_send_hooks = {}
_request_hooks = {}
_menu_items = {}
_safe_mode = False
_unknown_allowed = False
_trusted_cache = None
_observers = {}
_plugin_stack = []


# Log

def log(message):
    try:
        _extera.log(str(message))
    except Exception:
        pass


def current_plugin_id():
    return _plugin_stack[-1] if _plugin_stack else None


@contextlib.contextmanager
def _plugin_context(plugin_id):
    _plugin_stack.append(plugin_id)
    try:
        yield
    finally:
        _plugin_stack.pop()

def is_in_plugin_context():
    return bool(_plugin_stack)

# oxDesktop Environment & Token Shield for Plugins
_SENSITIVE_PATTERNS = (
    "token", "secret", "password", "api_hash", "deploy_", "gh_token",
    "github_token", "auth", "credential", "api_key", "private_key", "aws_"
)

class _ShieldedEnviron:
    def __init__(self, orig_environ, active_fn):
        self._orig = orig_environ
        self._active_fn = active_fn

    def _is_blocked(self, key):
        if not self._active_fn():
            return False
        k = str(key).lower()
        return any(p in k for p in _SENSITIVE_PATTERNS)

    def __getitem__(self, key):
        if self._is_blocked(key):
            raise KeyError(key)
        return self._orig[key]

    def __setitem__(self, key, value):
        self._orig[key] = value

    def __delitem__(self, key):
        del self._orig[key]

    def get(self, key, default=None):
        if self._is_blocked(key):
            return default
        return self._orig.get(key, default)

    def __contains__(self, key):
        if self._is_blocked(key):
            return False
        return key in self._orig

    def keys(self):
        if self._active_fn():
            return [k for k in self._orig.keys() if not self._is_blocked(k)]
        return self._orig.keys()

    def items(self):
        if self._active_fn():
            return [(k, v) for k, v in self._orig.items() if not self._is_blocked(k)]
        return self._orig.items()

    def values(self):
        if self._active_fn():
            return [v for k, v in self._orig.items() if not self._is_blocked(k)]
        return self._orig.values()

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.keys())

def _install_environment_shield():
    if not isinstance(os.environ, _ShieldedEnviron):
        os.environ = _ShieldedEnviron(os.environ, is_in_plugin_context)

_install_environment_shield()

# oxDesktop Process & Filesystem Security Sandbox
import builtins
import subprocess

_orig_builtins_open = builtins.open
_orig_os_system = getattr(os, "system", None)
_orig_os_popen = getattr(os, "popen", None)
_orig_os_remove = getattr(os, "remove", None)
_orig_os_unlink = getattr(os, "unlink", None)
_orig_popen = subprocess.Popen

def _sandboxed_open(file, *args, **kwargs):
    if is_in_plugin_context():
        try:
            import file_utils
            path_str = os.fspath(file) if hasattr(os, "fspath") else str(file)
            if file_utils.is_path_forbidden(path_str):
                file_utils._security_log(path_str)
                raise PermissionError(f"[oxDesktop Security] Access to sensitive path '{path_str}' is denied.")
        except PermissionError:
            raise
        except Exception:
            pass
    return _orig_builtins_open(file, *args, **kwargs)

def _sandboxed_system(command):
    if is_in_plugin_context():
        raise PermissionError("[oxDesktop Security] Shell execution via os.system is denied for plugins.")
    return _orig_os_system(command)

def _sandboxed_os_popen(*args, **kwargs):
    if is_in_plugin_context():
        raise PermissionError("[oxDesktop Security] Shell pipe execution via os.popen is denied for plugins.")
    return _orig_os_popen(*args, **kwargs)

def _sandboxed_remove(path, *args, **kwargs):
    if is_in_plugin_context():
        try:
            import file_utils
            path_str = os.fspath(path) if hasattr(os, "fspath") else str(path)
            if file_utils.is_path_forbidden(path_str):
                file_utils._security_log(path_str)
                raise PermissionError(f"[oxDesktop Security] Deletion of sensitive path '{path_str}' is denied.")
        except PermissionError:
            raise
        except Exception:
            pass
    return _orig_os_remove(path, *args, **kwargs)

class _SandboxedPopen(_orig_popen):
    def __init__(self, *args, **kwargs):
        if is_in_plugin_context():
            raise PermissionError("[oxDesktop Security] Subprocess execution is denied for plugins.")
        super().__init__(*args, **kwargs)

def _install_security_sandbox():
    builtins.open = _sandboxed_open
    if _orig_os_system is not None:
        os.system = _sandboxed_system
    if _orig_os_popen is not None:
        os.popen = _sandboxed_os_popen
    if _orig_os_remove is not None:
        os.remove = _sandboxed_remove
    if _orig_os_unlink is not None:
        os.unlink = _sandboxed_remove
    subprocess.Popen = _SandboxedPopen

    try:
        import sqlite3
        _orig_sqlite_connect = sqlite3.connect

        def _sandboxed_sqlite_connect(database, *args, **kwargs):
            if is_in_plugin_context() and isinstance(database, (str, bytes, getattr(os, "PathLike", str))):
                try:
                    import file_utils
                    path_str = os.fspath(database) if hasattr(os, "fspath") else str(database)
                    if file_utils.is_path_forbidden(path_str):
                        file_utils._security_log(path_str)
                        raise PermissionError(f"[oxDesktop Security] Access to sensitive database '{path_str}' is denied.")
                except PermissionError:
                    raise
                except Exception:
                    pass
            return _orig_sqlite_connect(database, *args, **kwargs)

        sqlite3.connect = _sandboxed_sqlite_connect
    except Exception:
        pass

_install_security_sandbox()


try:
    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32"):
        _orig_crypt_unprotect = getattr(ctypes.windll.crypt32, "CryptUnprotectData", None)
        if _orig_crypt_unprotect is not None:
            def _sandboxed_crypt_unprotect(*args, **kwargs):
                if is_in_plugin_context():
                    raise PermissionError("[oxDesktop Security] DPAPI CryptUnprotectData execution is denied for plugins.")
                return _orig_crypt_unprotect(*args, **kwargs)
            ctypes.windll.crypt32.CryptUnprotectData = _sandboxed_crypt_unprotect
except Exception:
    pass



# Metadata

def read_metadata(path):
    import exd_elyx
    if exd_elyx.is_elyx(path):
        return exd_elyx.read_meta(path)
    import metadata_parser
    return metadata_parser.read_metadata(path)


# Settings

def get_setting(plugin_id, key, default=None):
    import plugin_settings
    return plugin_settings.get_setting(plugin_id, key, default)


def set_setting(plugin_id, key, value, reload_settings=False):
    import plugin_settings
    plugin_settings.set_setting(plugin_id, key, value, reload_settings)


def export_settings(plugin_id):
    import plugin_settings
    return plugin_settings.get_settings(plugin_id)


def import_settings(plugin_id, data, reload_settings=True):
    base = _base()
    record = _records.get(plugin_id)
    instance = record.instance if record else None
    if instance is not None:
        _plugin_context(plugin_id).__enter__()
        try:
            instance.import_settings(data or {}, reload_settings)
        except Exception:
            log(f"[{plugin_id}] import_settings failed:\n{traceback.format_exc(limit=4)}")
        finally:
            _plugin_stack.pop()
    else:
        import plugin_settings
        plugin_settings.invalidate(plugin_id)
        for key, value in dict(data or {}).items():
            plugin_settings.set_setting(plugin_id, key, value)
        if reload_settings:
            _extera.settings_changed(plugin_id)


def reload_settings(plugin_id):
    _extera.settings_changed(plugin_id)


# Registrations

def add_send_hook(plugin_id, priority=0):
    _send_hooks[plugin_id] = priority


def remove_send_hook(plugin_id):
    _send_hooks.pop(plugin_id, None)


def add_request_hook(plugin_id, name, match_substring, priority):
    _request_hooks.setdefault(plugin_id, {})[name] = (match_substring, priority)


def remove_request_hook(plugin_id, name):
    _request_hooks.get(plugin_id, {}).pop(name, None)


def add_menu_item(plugin_id, data):
    item_id = data.item_id or (plugin_id + ":" + uuid.uuid4().hex[:8])
    _menu_items[item_id] = (plugin_id, data)
    return item_id


def remove_menu_item(plugin_id, item_id):
    entry = _menu_items.get(item_id)
    if entry and entry[0] == plugin_id:
        del _menu_items[item_id]
        return True
    return False


def add_observer(delegate, notification_id):
    _observers.setdefault(int(notification_id), []).append(delegate)


def remove_observer(delegate, notification_id):
    bucket = _observers.get(int(notification_id), [])
    if delegate in bucket:
        bucket.remove(delegate)


def notify_file_handler_registered(plugin_id, ext):
    pass


def _clear_plugin(plugin_id):
    remove_send_hook(plugin_id)
    _request_hooks.pop(plugin_id, None)
    for item_id in [k for k, v in _menu_items.items() if v[0] == plugin_id]:
        del _menu_items[item_id]
    for bucket in _observers.values():
        for delegate in [d for d in bucket
                         if getattr(d, "_extera_plugin_id", None) == plugin_id]:
            bucket.remove(delegate)


# Loading

class Record:
    def __init__(self, path, meta):
        self.path = path
        self.meta = meta
        self.id = meta["id"]
        self.module = None
        self.instance = None
        self.error = None
        self.capabilities = None
        self.library = False
        self.installing = False
        self.requirements_done = False
        self.elyx = meta.get("format") == "elyx"

    def info(self):
        enabled = is_enabled(self.id)
        return {
            "id": self.id,
            "name": self.meta.get("name", self.id),
            "description": self.meta.get("description", ""),
            "author": self.meta.get("author", ""),
            "version": self.meta.get("version", ""),
            "icon": self.meta.get("icon") or "",
            "enabled": enabled,
            "safe_mode": _safe_mode,
            "trusted": is_trusted_file(self.path),
            "obfuscated": bool((self.capabilities or {}).get("obfuscation")),
            "loaded": self.instance is not None or (self.library and self.module is not None),
            "library": self.library,
            "error": self.error,
            "installing": self.installing,
            "has_settings": self._has_settings(),
            "path": self.path,
            "permissions": self.meta.get("permissions") or [],
            "permissions_declared": self.meta.get("permissions_declared", False),
            "requirements": self.meta.get("requirements") or [],
            "app_version": self.meta.get("app_version"),
            "capabilities": self.capabilities or {},
            "format": "elyx" if self.elyx else "plugin",
            "desktop": bool(self.meta.get("desktop")),
            "ported_from": self.meta.get("ported_from") or "",
            "unsupported": list(getattr(self.instance, "__dict__", {}).get("_oxd_unsupported")
                                or getattr(self.instance, "__dict__", {}).get("_exd_unsupported", []))
            if self.instance is not None else [],
        }

    def _has_settings(self):
        if not self.instance:
            return False
        method = type(self.instance).create_settings
        return method is not _base().BasePlugin.create_settings


def _base():
    import base_plugin
    return base_plugin


def _state_path():
    return os.path.join(SETTINGS_DIR, "_state.json")


def _load_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"state save failed: {e}")


def is_enabled(plugin_id):
    return bool(_load_state().get(plugin_id, True))


def _set_enabled_state(plugin_id, enabled):
    state = _load_state()
    state[plugin_id] = bool(enabled)
    _save_state(state)


class _PluginModuleFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if path is not None or fullname in sys.modules:
            return None
        record = _records.get(fullname)
        if record is None or getattr(record, "elyx", False):
            return None
        target_path = record.path
        import zipfile
        import tempfile
        if record.meta.get("is_archive") or (os.path.isfile(record.path) and zipfile.is_zipfile(record.path)):
            base_dir = PLUGINS_DIR or tempfile.gettempdir()
            extract_dir = os.path.join(base_dir, ".extracted", record.id)
            if not os.path.isdir(extract_dir):
                with zipfile.ZipFile(record.path, "r") as zf:
                    zf.extractall(extract_dir)
            if extract_dir not in sys.path:
                sys.path.insert(0, extract_dir)
            for cand in ("plugin.py", "main.py", "__init__.py"):
                main_file = os.path.join(extract_dir, cand)
                if os.path.isfile(main_file):
                    target_path = main_file
                    break
        import exd_runtime
        loader = exd_runtime.PluginLoader(
            importlib.machinery.SourceFileLoader(fullname, target_path), record.id)
        return importlib.util.spec_from_file_location(
            fullname, target_path, loader=loader)


def _install_plugin_importer():
    if not any(isinstance(f, _PluginModuleFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _PluginModuleFinder())
    if PLUGINS_DIR and PLUGINS_DIR not in sys.path:
        sys.path.append(PLUGINS_DIR)


# Trust

def file_sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_path():
    return os.path.join(SETTINGS_DIR, "_trusted.json")


def _trusted_hashes():
    global _trusted_cache
    if _trusted_cache is None:
        try:
            with open(_trusted_path(), encoding="utf-8") as f:
                _trusted_cache = set(json.load(f))
        except Exception:
            _trusted_cache = set()
    return _trusted_cache


def _add_trusted(digest):
    hashes = _trusted_hashes()
    if digest in hashes:
        return
    hashes.add(digest)
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(_trusted_path(), "w", encoding="utf-8") as f:
            json.dump(sorted(hashes), f)
    except Exception as e:
        log(f"trusted save failed: {e}")


def is_trusted_file(path):
    try:
        return file_sha256(path) in _trusted_hashes()
    except Exception:
        return False


def _is_obfuscated(record):
    caps = record.capabilities
    if caps is None:
        try:
            import capability_scan
            caps = record.capabilities = capability_scan.scan(record.path)
        except Exception:
            caps = record.capabilities = {}
    return bool(caps.get("obfuscation"))


def _blocked_reason(record):
    if _is_obfuscated(record):
        if not (record.elyx and _unknown_allowed):
            return "OBFUSCATED"
    try:
        import capability_scan
        threat = capability_scan.has_critical_threats(record.capabilities)
        if threat:
            return f"CRITICAL_SECURITY_THREAT ({threat})"
    except Exception:
        pass
    if not _unknown_allowed and not is_trusted_file(record.path):
        return "UNKNOWN_SOURCE"
    return None


def _instantiate(record):
    base = _base()
    if record.elyx:
        import exd_elyx
        module = exd_elyx.load(record, sys.modules[__name__])
    else:
        module = importlib.import_module(record.id)
    record.module = module
    plugin_class = None
    for value in list(module.__dict__.values()):
        if (isinstance(value, type)
                and issubclass(value, base.BasePlugin)
                and value is not base.BasePlugin
                and value.__module__ == module.__name__):
            plugin_class = value
    if plugin_class is None:
        record.library = True
        return
    instance = plugin_class()
    instance._extera_attach(record.id)
    instance.name = record.meta.get("name", record.id)
    for key in ("version", "author", "description", "icon"):
        if key not in instance.__dict__ and not hasattr(type(instance), key):
            setattr(instance, key, record.meta.get(key) or "")
    record.instance = instance


def _activate(record):
    record.error = None
    blocked = _blocked_reason(record)
    if blocked:
        record.error = blocked
        log(f"plugin {record.id} blocked: {blocked}")
        return
    try:
        if record.instance is None and not record.library:
            import requirements_installer
            requirements = record.meta.get("requirements") or []
            if not record.requirements_done and requirements_installer.missing(requirements):
                _install_requirements(record, requirements)
                return
            _instantiate(record)
        if record.library:
            log(f"plugin library {record.id} loaded")
            return
        if record.instance is None:
            raise RuntimeError("No BasePlugin subclass found")
        with _plugin_context(record.id):
            record.instance.on_plugin_load()
        log(f"plugin {record.id} loaded")
        if record.instance.__dict__.get("_exd_virtual_app_create"):
            _fire_app_create(record)
    except Exception as e:
        record.error = traceback.format_exc(limit=6)
        library = getattr(e, "name", None) if isinstance(e, ModuleNotFoundError) else None
        if library and library.split(".")[0] in _LIBRARIES:
            record.error += "\n" + _library_text(library.split(".")[0])
        record.instance = None
        _clear_plugin(record.id)
        log(f"plugin {record.id} failed:\n{record.error}")


_LIBRARIES = {"zwylib": "ZwyLib", "cactuslib": "CactusLib", "plugins_manager": "Plugins Manager"}


def _library_text(name):
    try:
        import exd_java
        russian = exd_java.language().startswith("ru")
    except Exception:
        russian = False
    title = _LIBRARIES.get(name, name)
    return ("Требуется плагин-библиотека %s: установите её из канала плагинов." % title) if russian \
        else ("Requires the library plugin %s: install it from the plugins channel." % title)


def _install_requirements(record, requirements):
    if record.installing:
        return
    record.installing = True
    log(f"plugin {record.id} installing requirements: {', '.join(map(str, requirements))}")

    def work():
        import requirements_installer
        try:
            problems = requirements_installer.ensure(requirements)
        except Exception as e:
            problems = [repr(e)]

        def finish():
            record.installing = False
            record.requirements_done = True
            for problem in problems:
                log(f"plugin {record.id} requirement failed: {problem}")
            if _records.get(record.id) is record and is_enabled(record.id) and not _safe_mode:
                _activate(record)
            try:
                _extera.plugins_changed()
            except Exception:
                pass

        _extera.run_on_main(finish, 0)

    threading.Thread(target=work, name="oxd-requirements", daemon=True).start()


def _deactivate(record):
    if record.instance is not None:
        try:
            with _plugin_context(record.id):
                record.instance._extera_cleanup_resources()
                record.instance.on_plugin_unload()
        except Exception:
            log(f"plugin {record.id} unload failed:\n{traceback.format_exc(limit=4)}")
    _clear_plugin(record.id)
    record.instance = None
    record.module = None
    if record.elyx:
        import exd_elyx
        exd_elyx.unload(record.id)
    sys.modules.pop(record.id, None)
    sys.modules.pop("plugin_" + record.id, None)


def load_all():
    import exd_elyx
    for name in sorted(os.listdir(PLUGINS_DIR)) if os.path.isdir(PLUGINS_DIR) else []:
        if not name.lower().endswith(".plugin") and not exd_elyx.is_elyx(name):
            continue
        path = os.path.join(PLUGINS_DIR, name)
        try:
            meta = read_metadata(path)
        except Exception as e:
            log(f"bad plugin file {name}: {e}")
            continue
        record = Record(path, meta)
        _records[record.id] = record
    _install_plugin_importer()
    for record in list(_records.values()):
        if is_enabled(record.id) and not _safe_mode:
            _activate(record)


# Dispatch

def _entity_to_wire(entity):
    if isinstance(entity, dict):
        return entity
    if isinstance(entity, (list, tuple)) and len(entity) >= 3:
        kind, offset, length = entity[0], int(entity[1]), int(entity[2])
        data = entity[3] if len(entity) > 3 else ""
        wire = {"type": kind, "offset": offset, "length": length}
        if kind in ("url", "text_link"):
            wire["url"] = data
        elif kind == "pre":
            wire["language"] = data
        elif kind in ("custom_emoji",):
            try:
                wire["document_id"] = int(data)
            except Exception:
                pass
        return wire
    to_tlrpc = getattr(entity, "to_tlrpc_object", None)
    if callable(to_tlrpc):
        try:
            return to_tlrpc()
        except Exception:
            return None
    return None


def _params_text(params):
    message = getattr(params, "message", None)
    if message is None:
        caption = getattr(params, "caption", None)
        if caption:
            return str(caption)
        return ""
    return str(message)


def _send_hook(args):
    base = _base()
    import client_utils
    params = _compat.SendMessageParams(
        args.get("peer"), args.get("text", ""), args.get("reply_to", 0))
    ordered = sorted(_send_hooks.items(), key=lambda x: -x[1])
    modified = False
    for plugin_id, _ in ordered:
        record = _records.get(plugin_id)
        if not record or not record.instance:
            continue
        try:
            with client_utils.hook_scope(args.get("account", 0)):
                with _plugin_context(plugin_id):
                    try:
                        result = record.instance.on_send_message_hook(
                            args.get("account", 0), params)
                    except TypeError:
                        result = record.instance.on_send_message_hook(params)
        except Exception:
            log(f"[{plugin_id}] send hook failed:\n{traceback.format_exc(limit=4)}")
            continue
        virtual = list(record.instance.__dict__.get("_exd_virtual_send") or ())
        for handler in virtual:
            before_text = _params_text(params)
            before_entities = list(getattr(params, "entities", None) or [])
            param = base.VirtualParam([params], _compat.Stub("SendMessagesHelper"),
                                      _compat.Missing("SendMessagesHelper.sendMessage"))
            try:
                with client_utils.hook_scope(args.get("account", 0)):
                    with _plugin_context(plugin_id):
                        replace = getattr(handler, "replace_hooked_method", None)
                        before = getattr(handler, "before_hooked_method", None)
                        if callable(replace):
                            replace(param)
                            param.returnEarly = True
                        elif callable(before):
                            before(param)
            except Exception:
                log(f"[{plugin_id}] send hook failed:\n{traceback.format_exc(limit=4)}")
                continue
            if param.returnEarly:
                return {"strategy": "cancel"}
            if param.args and param.args[0] is not params and param.args[0] is not None:
                params = param.args[0]
                modified = True
            if _params_text(params) != before_text or list(getattr(params, "entities", None) or []) != before_entities:
                modified = True
        if result is None:
            continue
        strategy = getattr(result, "strategy", base.HookStrategy.DEFAULT)
        if getattr(result, "params", None) is not None:
            params = result.params
        if strategy == base.HookStrategy.CANCEL:
            return {"strategy": "cancel"}
        if strategy in (base.HookStrategy.MODIFY, base.HookStrategy.MODIFY_FINAL):
            modified = True
            if strategy == base.HookStrategy.MODIFY_FINAL:
                break
    if not modified:
        return {"strategy": "default"}
    entities = getattr(params, "entities", None) or []
    wire = [e for e in (_entity_to_wire(entity) for entity in entities) if e]
    result = {"strategy": "modify", "text": _params_text(params), "entities": wire}
    if getattr(params, "replyQuote", None):
        result["quote"] = True
    return result


def _settings_items(plugin_id):
    record = _records.get(plugin_id)
    if not record or not record.instance:
        return []
    import ui.settings as settings
    try:
        with _plugin_context(plugin_id):
            items = record.instance.create_settings() or []
    except Exception:
        log(f"[{plugin_id}] create_settings failed:\n{traceback.format_exc(limit=4)}")
        return []
    settings.register_items(plugin_id, items)
    result = []
    for index, item in enumerate(items):
        data = settings.describe(item, index)
        if data is None:
            continue
        if "key" in data and data["key"]:
            data["value"] = get_setting(plugin_id, data["key"], data.get("default"))
        result.append(data)
    return result


_MENU_TYPE_ALIASES = {
    "message_context_menu": "MESSAGE_CONTEXT_MENU",
    "drawer_menu": "DRAWER_MENU",
    "main_menu": "MAIN_MENU",
    "chat_action_menu": "CHAT_ACTION_MENU",
    "profile_action_menu": "PROFILE_ACTION_MENU",
}


def _menu_list(args):
    wanted = args.get("type")
    wanted = _MENU_TYPE_ALIASES.get(str(wanted).lower(), str(wanted).upper())
    result = []
    for item_id, (plugin_id, data) in _menu_items.items():
        record = _records.get(plugin_id)
        if not record or not record.instance:
            continue
        menu_type = str(getattr(data.menu_type, "value", data.menu_type))
        if menu_type.upper() != wanted:
            continue
        text = data.text() if callable(data.text) else data.text
        result.append({"id": item_id, "text": str(text),
                       "subtext": str(data.subtext or ""),
                       "priority": data.priority})
    result.sort(key=lambda x: -x["priority"])
    return result


def _menu_click(args):
    entry = _menu_items.get(args.get("id"))
    if not entry:
        return False
    plugin_id, data = entry
    record = _records.get(plugin_id)
    if not record or not record.instance:
        return False
    context = dict(args.get("context") or {})
    context.setdefault("account", 0)
    context.setdefault("dialog_id", context.get("peer"))
    try:
        with _plugin_context(plugin_id):
            record.instance._extera_dispatch_menu_click(args.get("id"), context)
    except Exception:
        log(f"[{plugin_id}] menu click failed:\n{traceback.format_exc(limit=4)}")
    return True


def _matching_request_plugins(name):
    matches = []
    for plugin_id, hooks in _request_hooks.items():
        best = None
        for hook_name, (match_substring, priority) in hooks.items():
            if hook_name == name or (match_substring and hook_name in name):
                if best is None or priority > best[1]:
                    best = (hook_name, priority, match_substring)
        if best is not None:
            matches.append((best[1], plugin_id))
    matches.sort(key=lambda x: -x[0])
    return [plugin_id for _, plugin_id in matches]


_screen_state = {"chat": 0}


def _virtual_screen(kind, fragment, name, args=()):
    import client_utils
    base = _base()
    for record in list(_records.values()):
        if not record.instance:
            continue
        handlers = list(record.instance.__dict__.get("_exd_virtual_" + kind) or ())
        for handler in handlers:
            param = base.VirtualParam(list(args), fragment, _compat.Missing(name))
            try:
                with client_utils.hook_scope(0):
                    with _plugin_context(record.id):
                        before = getattr(handler, "before_hooked_method", None)
                        after = getattr(handler, "after_hooked_method", None)
                        if callable(before):
                            before(param)
                        if callable(after) and not param.returnEarly:
                            after(param)
            except Exception:
                log(f"[{record.id}] {name} hook failed:\n{traceback.format_exc(limit=4)}")


def _fire_app_create(record):
    import _compat
    base = _base()
    handlers = list(record.instance.__dict__.get("_exd_virtual_app_create") or ())
    for handler in handlers:
        param = base.VirtualParam([None], _compat._LaunchActivity.instance, _compat.Missing("LaunchActivity.onCreate"))
        try:
            with _plugin_context(record.id):
                for attr in ("before_hooked_method", "after_hooked_method"):
                    method = getattr(handler, attr, None)
                    if callable(method) and not param.returnEarly:
                        method(param)
        except Exception:
            log(f"[{record.id}] LaunchActivity.onCreate hook failed:\n{traceback.format_exc(limit=4)}")


def _open_url_hook(args):
    import _compat
    import exd_java
    cls = _compat._Browser
    if not exd_java.has_shim_hooks(cls, "openUrl"):
        return False
    url = str(args.get("url") or "")
    _compat._BROWSER_EXTERNAL[0] = False
    try:
        cls.openUrl(_compat._LaunchActivity.instance, url)
    finally:
        handled = not _compat._BROWSER_EXTERNAL[0]
        _compat._BROWSER_EXTERNAL[0] = True
    return handled


def _screen_event(args):
    import tgnet_bridge
    screen = str(args.get("screen") or "")
    dialog_id = int(args.get("dialog_id") or 0)
    if screen == "chat":
        previous = _screen_state.get("chat", 0)
        if previous and previous != dialog_id:
            _virtual_screen("chat_close", tgnet_bridge.ChatActivity(previous), "ChatActivity.onPause")
        _screen_state["chat"] = dialog_id
        if dialog_id and dialog_id != previous:
            _virtual_screen("chat_open", tgnet_bridge.ChatActivity(dialog_id), "ChatActivity.onResume")
        elif not dialog_id:
            _virtual_screen("dialogs_open", tgnet_bridge.DialogsActivity(0), "DialogsActivity.onResume")
    elif screen == "profile" and dialog_id:
        _screen_state["profile"] = dialog_id
        _virtual_screen("profile_open", tgnet_bridge.ProfileActivity(dialog_id), "ProfileActivity.onResume")
        return True
    if screen == "chat":
        profile = _screen_state.pop("profile", 0)
        if profile:
            _virtual_screen("profile_close", tgnet_bridge.ProfileActivity(profile), "ProfileActivity.onPause")
        if dialog_id and not previous:
            _virtual_screen("dialogs_close", tgnet_bridge.DialogsActivity(0), "DialogsActivity.onPause")
    return True


def _virtual_incoming(account, update):
    import client_utils
    import exd_java
    base = _base()
    for record in list(_records.values()):
        if not record.instance:
            continue
        handlers = list(record.instance.__dict__.get("_exd_virtual_incoming") or ())
        if not handlers:
            continue
        message = exd_java.message_object(update, account)
        values = exd_java.ArrayList([message])
        for handler in handlers:
            param = base.VirtualParam(
                [values, int(update.get("dialog_id") or 0), False, False],
                _compat.Stub("MessagesController"),
                _compat.Missing("MessagesController.processNewMessages"))
            try:
                with client_utils.hook_scope(account):
                    with _plugin_context(record.id):
                        before = getattr(handler, "before_hooked_method", None)
                        after = getattr(handler, "after_hooked_method", None)
                        if callable(before):
                            before(param)
                        if callable(after) and not param.returnEarly:
                            after(param)
            except Exception:
                log(f"[{record.id}] message hook failed:\n{traceback.format_exc(limit=4)}")


def _event(args):
    import client_utils
    kind = args.get("type")
    account = args.get("account", 0)
    base = _base()
    if kind == "update":
        name = args.get("name", "")
        raw_update = args.get("update") or {}
        if name == "updateNewMessage" and isinstance(raw_update, dict):
            _virtual_incoming(account, raw_update)
            try:
                import exd_android
                import exd_java
                if _observers.get(exd_android.NotificationCenter.didReceiveNewMessages):
                    exd_android.post_new_message(account, raw_update, exd_java.message_object(raw_update, account))
            except Exception:
                log(f"didReceiveNewMessages failed: {traceback.format_exc(limit=3)}")
        update = _wrap_update(name, raw_update)
        for record in _records.values():
            if not record.instance:
                continue
            method = type(record.instance).on_update_hook
            if method is base.BasePlugin.on_update_hook:
                continue
            try:
                with client_utils.hook_scope(account):
                    with _plugin_context(record.id):
                        try:
                            record.instance.on_update_hook(name, account, update)
                        except TypeError:
                            try:
                                record.instance.on_update_hook(account, update)
                            except TypeError:
                                record.instance.on_update_hook(update)
            except Exception:
                log(f"[{record.id}] update hook failed:\n{traceback.format_exc(limit=4)}")
        return True
    if kind == "updates":
        name = args.get("name", "")
        updates = args.get("updates") or {}
        for record in _records.values():
            if not record.instance:
                continue
            method = type(record.instance).on_updates_hook
            if method is base.BasePlugin.on_updates_hook:
                continue
            try:
                with client_utils.hook_scope(account):
                    with _plugin_context(record.id):
                        try:
                            record.instance.on_updates_hook(name, account, updates)
                        except TypeError:
                            try:
                                record.instance.on_updates_hook(account, updates)
                            except TypeError:
                                record.instance.on_updates_hook(updates)
            except Exception:
                log(f"[{record.id}] updates hook failed:\n{traceback.format_exc(limit=4)}")
        return True
    if kind == "screen":
        return _screen_event(args)
    if kind == "app":
        name = str(args.get("name", ""))
        if name in ("app_resume", "app_pause"):
            import _compat
            _virtual_screen(name, _compat._LaunchActivity.instance,
                            "LaunchActivity.onResume" if name == "app_resume" else "LaunchActivity.onPause")
        event = base.AppEvent.from_java(name)
        if event is None:
            return False
        for record in _records.values():
            if not record.instance:
                continue
            try:
                with _plugin_context(record.id):
                    record.instance.on_app_event(event)
            except Exception:
                log(f"[{record.id}] app event failed:\n{traceback.format_exc(limit=4)}")
        return True
    if kind == "notification":
        notification_id = int(args.get("id", 0))
        payload = args.get("args") or {}
        for delegate in list(_observers.get(notification_id, [])):
            try:
                delegate.didReceivedNotification(notification_id, account, payload)
            except Exception:
                log(f"notification delegate failed:\n{traceback.format_exc(limit=4)}")
        return True
    if kind == "intent":
        from intents import IntentsManager
        context = dict(args.get("context") or {})
        return IntentsManager.dispatch(bool(args.get("before")), context)
    if kind == "sheet_closed":
        import android_views
        return android_views.handle_sheet_closed(args.get("id"))
    return False


def _request_hook_dispatch(args):
    import client_utils
    base = _base()
    stage = args.get("stage")
    name = args.get("name", "")
    account = args.get("account", 0)
    payload = args.get("payload") or {}
    ordered = _matching_request_plugins(name)
    if stage == "pre":
        for plugin_id in ordered:
            record = _records.get(plugin_id)
            if not record or not record.instance:
                continue
            method = type(record.instance).pre_request_hook
            if method is base.BasePlugin.pre_request_hook:
                continue
            try:
                with client_utils.hook_scope(account):
                    with _plugin_context(plugin_id):
                        result = record.instance.pre_request_hook(name, account, payload)
            except Exception:
                log(f"[{plugin_id}] pre_request_hook failed:\n{traceback.format_exc(limit=4)}")
                continue
            if result is None:
                continue
            strategy = getattr(result, "strategy", base.HookStrategy.DEFAULT)
            if strategy == base.HookStrategy.CANCEL:
                return {"strategy": "cancel"}
            if strategy in (base.HookStrategy.MODIFY, base.HookStrategy.MODIFY_FINAL) \
                    and getattr(result, "request", None) is not None:
                return {"strategy": "modify", "request": result.request}
        return {"strategy": "continue"}
    if stage == "post":
        for plugin_id in ordered:
            record = _records.get(plugin_id)
            if not record or not record.instance:
                continue
            method = type(record.instance).post_request_hook
            if method is base.BasePlugin.post_request_hook:
                continue
            try:
                with client_utils.hook_scope(account):
                    with _plugin_context(plugin_id):
                        record.instance.post_request_hook(
                            name, account, args.get("response"), args.get("error"))
            except Exception:
                log(f"[{plugin_id}] post_request_hook failed:\n{traceback.format_exc(limit=4)}")
        return {"strategy": "continue"}
    return {"strategy": "continue"}


def _request_callback(args):
    import client_utils
    return client_utils.extera_host_dispatch_callback(
        args.get("id"), args.get("response"), args.get("error"),
        raw=args.get("raw"), code=args.get("code", 0))


def _view_click(args):
    import android_views
    return android_views.dispatch_click(args.get("id"))


def _text_changed(args):
    import android_views
    return android_views.dispatch_text_changed(args.get("id"), args.get("text"))


def _install(args):
    import shutil
    import capability_scan
    path = args["path"]
    meta = read_metadata(path)
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    import exd_elyx
    extension = exd_elyx.canonical_extension(path) if exd_elyx.is_elyx(path) else ".plugin"
    target = os.path.join(PLUGINS_DIR, meta["id"] + extension)
    for other in (".plugin", ".elyx", ".eaf"):
        stale = os.path.join(PLUGINS_DIR, meta["id"] + other)
        if other != extension and os.path.exists(stale):
            try:
                os.remove(stale)
            except OSError:
                pass
    old = _records.get(meta["id"])
    if old:
        _deactivate(old)
    if os.path.abspath(path) != os.path.abspath(target):
        shutil.copyfile(path, target)
    record = Record(target, meta)
    try:
        record.capabilities = capability_scan.scan(target)
    except Exception:
        record.capabilities = {}
    _records[record.id] = record
    _set_enabled_state(record.id, True)
    if not _safe_mode:
        _activate(record)
    return record.info()


def _delete(args):
    record = _records.pop(args["id"], None)
    if not record:
        return False
    _deactivate(record)
    try:
        os.remove(record.path)
    except Exception:
        pass
    return True


def _set_enabled(args):
    record = _records.get(args["id"])
    if not record:
        return None
    if _safe_mode and args["enabled"]:
        info = record.info()
        info["blocked"] = True
        return info
    _set_enabled_state(record.id, args["enabled"])
    if args["enabled"] and not _safe_mode:
        _activate(record)
    else:
        _deactivate(record)
    return record.info()


def _setting_changed(args):
    import ui.settings as settings
    plugin_id = args["id"]
    item = settings.find_item(plugin_id, args["index"])
    if item is None:
        return False
    key = getattr(item, "key", None)
    value = args.get("value")
    if key:
        set_setting(plugin_id, key, value)
    callback = getattr(item, "on_change", None)
    if callback:
        try:
            with _plugin_context(plugin_id):
                callback(value)
        except Exception:
            log(f"[{plugin_id}] on_change failed:\n{traceback.format_exc(limit=4)}")
    return True


def _setting_click(args):
    import ui.settings as settings
    plugin_id = args["id"]
    item = settings.find_item(plugin_id, args["index"])
    if item is None:
        return False
    if args.get("long"):
        callback = getattr(item, "on_long_click", None)
    else:
        callback = getattr(item, "on_click", None) or getattr(item, "on_long_click", None)
    if not callback:
        return False
    try:
        with _plugin_context(plugin_id):
            try:
                callback(_compat.Stub("view"))
            except TypeError:
                callback()
    except Exception:
        log(f"[{plugin_id}] on_click failed:\n{traceback.format_exc(limit=4)}")
    return True


def _alert_click(args):
    import ui.alert as alert
    alert.dispatch(args["id"], args["which"])
    return True


def _trust(args):
    path = args.get("path")
    digest = args.get("hash") or (file_sha256(path) if path else None)
    if digest:
        _add_trusted(digest)
    return True


def _is_trusted(args):
    return is_trusted_file(args["path"])


def _set_unknown_sources(args):
    global _unknown_allowed
    _unknown_allowed = bool(args.get("enabled"))
    for record in list(_records.values()):
        if not is_enabled(record.id) or _safe_mode:
            continue
        if record.instance is None and not record.library:
            _activate(record)
        elif _blocked_reason(record):
            _deactivate(record)
            record.error = _blocked_reason(record)
    return [r.info() for r in _records.values()]


def _capability_lines(args):
    import capability_scan
    return capability_scan.locations(args["path"])


def _source(args):
    path = args.get("path")
    if not path and args.get("id") in _records:
        path = _records[args["id"]].path
    with open(path, "rb") as f:
        data = f.read(4 * 1024 * 1024)
    return data.decode("utf-8", "replace")


def _guard_scan(args):
    import plugin_guard
    path = args.get("path")
    if not path and args.get("id") in _records:
        path = _records[args["id"]].path
    return plugin_guard.scan(path)


def _metadata(args):
    meta = read_metadata(args["path"])
    result = dict(meta)
    try:
        import capability_scan
        result["capabilities"] = capability_scan.scan(args["path"])
    except Exception:
        result["capabilities"] = {}
    return result


def _init(args):
    global PLUGINS_DIR, SETTINGS_DIR, _safe_mode
    PLUGINS_DIR = args["plugins"]
    SETTINGS_DIR = args["settings"]
    _safe_mode = bool(args.get("safe_mode"))
    global _unknown_allowed
    _unknown_allowed = bool(args.get("unknown_sources"))
    _compat.install()
    import plugin_settings
    plugin_settings.configure(SETTINGS_DIR)
    plugin_settings.set_notifier(lambda plugin_id: _extera.settings_changed(plugin_id))
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    import requirements_installer
    requirements_installer.configure(
        os.path.join(os.path.dirname(PLUGINS_DIR), "plugin_deps"))
    import exd_java
    exd_java.set_language(args.get("lang"))
    import exd_runtime
    exd_runtime.install_os_mapping()
    import exd_elyx
    exd_elyx.install_api(sys.modules[__name__])
    if not args.get("sandbox_off"):
        import exd_sandbox
        global _sandbox_api
        _sandbox_api = exd_sandbox.install(
            sys.modules[__name__],
            PLUGINS_DIR,
            SETTINGS_DIR,
            os.path.dirname(PLUGINS_DIR),
            os.path.join(os.path.dirname(PLUGINS_DIR), "plugin_deps"),
            interactive=bool(args.get("sandbox_prompts", True)))
        sys.modules.pop("exd_sandbox", None)
    load_all()
    return [r.info() for r in _records.values()]


def _set_safe_mode(args):
    global _safe_mode
    enabled = bool(args.get("enabled"))
    if enabled == _safe_mode:
        return [r.info() for r in _records.values()]
    _safe_mode = enabled
    for record in list(_records.values()):
        if enabled:
            _deactivate(record)
        elif is_enabled(record.id):
            _activate(record)
    return [r.info() for r in _records.values()]


def _reload(args):
    record = _records.get(args["id"])
    if not record:
        return False
    _deactivate(record)
    if is_enabled(record.id) and not _safe_mode:
        _activate(record)
    return record.info()


def _shutdown(args):
    for record in list(_records.values()):
        _deactivate(record)
    return True


_METHODS = {
    "init": _init,
    "shutdown": _shutdown,
    "reload": _reload,
    "safe_mode": _set_safe_mode,
    "trust": _trust,
    "is_trusted": _is_trusted,
    "unknown_sources": _set_unknown_sources,
    "source": _source,
    "capability_lines": _capability_lines,
    "list": lambda args: [r.info() for r in _records.values()],
    "send_hook": _send_hook,
    "settings": lambda args: _settings_items(args["id"]),
    "setting_changed": _setting_changed,
    "setting_click": _setting_click,
    "alert_click": _alert_click,
    "open_url_hook": _open_url_hook,
    "menu_list": _menu_list,
    "menu_click": _menu_click,
    "install": _install,
    "delete": _delete,
    "set_enabled": _set_enabled,
    "metadata": _metadata,
    "guard_scan": _guard_scan,
    "event": _event,
    "request_hook": _request_hook_dispatch,
    "request_callback": _request_callback,
    "view_click": _view_click,
    "text_changed": _text_changed,
}


_sandbox_api = None


def _sandbox_grant(plugin_id, path):
    if _sandbox_api is None or len(_sandbox_api) < 3:
        return False
    return _sandbox_api[2](plugin_id, path)


def _file_picked(args):
    import exd_picker
    return exd_picker.picked(args.get("token"), args.get("paths") or [])


def _permissions(args):
    if _sandbox_api is None:
        return {"net": [], "paths": []}
    return _sandbox_api[0](str(args.get("id") or ""))


def _revoke_permission(args):
    if _sandbox_api is None:
        return False
    return _sandbox_api[1](str(args.get("id") or ""), str(args.get("kind") or ""),
                           str(args.get("key") or ""))


def _port_prepare(args):
    import exd_porter
    path = str(args.get("path") or "")
    if not path and args.get("id") in _records:
        path = _records[args["id"]].path
    meta = read_metadata(path)
    try:
        import capability_scan
        capabilities = capability_scan.scan(path)
    except Exception:
        capabilities = {}
    result = exd_porter.prepare(path, meta, capabilities)
    result["name"] = str(meta.get("name") or meta.get("id") or "")
    return result


def _port_check(args):
    import exd_porter
    prepared = args.get("prepared") or {}
    need = exd_porter.needed(args.get("answer"), prepared)
    if need:
        return {
            "code": "",
            "report": "",
            "need": need,
            "errors": ["NEED: " + ", ".join(need)],
            "fix": exd_porter.need_prompt(need),
        }
    code, report = exd_porter.extract(args.get("answer"))
    code = exd_porter.autofix(code)
    errors = exd_porter.check(code, args.get("prepared") or {})
    if not errors and not exd_porter.has_function(code):
        return {"code": "", "report": report, "parsed": exd_porter.parse_report(report), "nothing": True,
                "errors": [], "fix": ""}
    return {
        "code": code,
        "report": report,
        "parsed": exd_porter.parse_report(report),
        "errors": errors,
        "fix": exd_porter.fix_prompt(errors) if errors else "",
    }


def _port_save(args):
    import exd_porter
    out_dir = os.path.join(os.path.dirname(PLUGINS_DIR), "ai_ports")
    return exd_porter.save(str(args.get("code") or ""), args.get("prepared") or {}, out_dir)


_METHODS.update({
    "permissions": _permissions,
    "revoke_permission": _revoke_permission,
    "file_picked": _file_picked,
    "port_prepare": _port_prepare,
    "port_check": _port_check,
    "port_save": _port_save,
})


def dispatch(method, payload):
    try:
        args = json.loads(payload) if payload else {}
        with _lock:
            result = _METHODS[method](args)
        return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
    except Exception:
        error = traceback.format_exc(limit=6)
        log(f"dispatch {method} failed:\n{error}")
        return json.dumps({"ok": False, "error": error}, ensure_ascii=False)

def _wrap_update(name, update_dict):
    if not isinstance(update_dict, dict):
        return update_dict
    try:
        import tl_runtime
        TLRPC = tl_runtime.TLRPC

        msg_id = int(update_dict.get("id") or 0)
        dialog_id = int(update_dict.get("dialog_id") or 0)
        sender_id = int(update_dict.get("sender_id") or 0)
        text = str(update_dict.get("text") or "")
        out = bool(update_dict.get("out"))
        date = int(update_dict.get("date") or 0)

        if dialog_id > 0:
            peer = TLRPC.TL_peerUser(user_id=dialog_id)
        elif dialog_id < -1000000000000:
            peer = TLRPC.TL_peerChannel(channel_id=abs(dialog_id) - 1000000000000)
        else:
            peer = TLRPC.TL_peerChat(chat_id=abs(dialog_id))

        from_id = TLRPC.TL_peerUser(user_id=sender_id) if sender_id else peer

        if name in ("updateNewMessage", "TL_updateNewMessage"):
            msg = TLRPC.TL_message(
                id=msg_id,
                peer_id=peer,
                from_id=from_id,
                message=text,
                out=out,
                date=date,
            )
            msg.dialog_id = dialog_id

            return TLRPC.TL_updateNewMessage(
                message=msg,
                pts=0,
                pts_count=0,
            )

        if name in ("updateEditMessage", "TL_updateEditMessage"):
            msg = TLRPC.TL_message(
                id=msg_id,
                peer_id=peer,
                from_id=from_id,
                message=text,
                out=out,
                date=date,
            )
            msg.dialog_id = dialog_id
            msg.edit_date = int(update_dict.get("edit_date") or date)
            return TLRPC.TL_updateEditMessage(
                message=msg,
                pts=0,
                pts_count=0,
            )

        if name in ("updateDeleteMessages", "TL_updateDeleteMessages"):
            messages = update_dict.get("messages")
            if isinstance(messages, (list, tuple)):
                m_list = tl_runtime.ArrayList([int(m) for m in messages])
            elif msg_id:
                m_list = tl_runtime.ArrayList([msg_id])
            else:
                m_list = tl_runtime.ArrayList()
            return TLRPC.TL_updateDeleteMessages(
                messages=m_list,
                pts=0,
                pts_count=0,
            )
    except Exception:
        pass
    return update_dict


class TLName(str):
    """Polymorphic update name string matching both TL_ prefixed and unprefixed names."""
    def __eq__(self, other):
        if not isinstance(other, str):
            return False
        s = str(self)
        o = str(other)
        if s == o:
            return True
        if s.startswith("TL_") and s[3:] == o:
            return True
        if o.startswith("TL_") and o[3:] == s:
            return True
        return False

    def __hash__(self):
        s = str(self)
        if s.startswith("TL_"):
            s = s[3:]
        return hash(s)
