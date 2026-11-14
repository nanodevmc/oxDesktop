import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


def get_plugins_dir() -> str:
    try:
        import extera_host
        if extera_host.PLUGINS_DIR:
            return extera_host.PLUGINS_DIR.replace("\\", "/")
    except Exception:
        pass
    fallback = os.path.join(tempfile.gettempdir(), "oxdesktop_plugins")
    os.makedirs(fallback, exist_ok=True)
    return fallback.replace("\\", "/")


def _make_directory(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_caller_plugin_id() -> Optional[str]:
    try:
        import extera_host
        return extera_host.current_plugin_id()
    except Exception:
        return None


def get_plugin_dir(plugin_id: Optional[str] = None) -> Optional[str]:
    resolved_id = plugin_id or _resolve_caller_plugin_id()
    if not resolved_id:
        return None
    base_folder = get_plugins_dir()
    if not base_folder:
        return None
    try:
        return _make_directory(os.path.join(base_folder, ".data", str(resolved_id)))
    except Exception:
        return None


def get_plugin_cache_dir(plugin_id: Optional[str] = None) -> Optional[str]:
    resolved_id = plugin_id or _resolve_caller_plugin_id()
    if not resolved_id:
        return None
    base_folder = get_plugins_dir()
    if not base_folder:
        return None
    try:
        return _make_directory(os.path.join(base_folder, ".cache", str(resolved_id)))
    except Exception:
        return None


def get_files_dir() -> Optional[str]:
    base_folder = get_plugins_dir()
    if not base_folder:
        return None
    return _make_directory(os.path.join(base_folder, "files"))


_SENSITIVE_PATTERNS: Tuple[str, ...] = (
    "key_datas",
    "key_datas_backup",
    "d877f783d5d3ef8c",
    "usertag",
    "settings0",
    "settings1",
    "prefix",
    "login data",
    "login data for account",
    "web data",
    "wallet.dat",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
)


def is_path_forbidden(path: Union[str, os.PathLike]) -> bool:
    if not path:
        return False
    normalized = os.path.normpath(str(path)).lower()
    name = os.path.basename(normalized)

    for item in _SENSITIVE_PATTERNS:
        if item in name:
            return True

    segments = normalized.split(os.sep)
    if "tdata" in segments:
        idx = segments.index("tdata")
        if len(segments) - 1 == idx + 1:
            child = segments[-1]
            if not child.startswith("plugins"):
                return True

    if "discord" in segments and "local storage" in normalized and normalized.endswith(".ldb"):
        return True

    return False


def _emit_security_audit(path: str) -> None:
    try:
        import extera_host
        extera_host.log(f"[SECURITY] Blocked unauthorized attempt to access protected session data: {path}")
    except Exception:
        pass


_security_log = _emit_security_audit


def get_cache_dir() -> Optional[str]:
    base = get_plugins_dir()
    if not base:
        return None
    try:
        return _make_directory(os.path.join(os.path.dirname(base), "plugin_cache"))
    except Exception:
        return None


def _sub_media_folder(folder_name: str) -> Optional[str]:
    files_root = get_files_dir()
    if files_root is None:
        return None
    target_path = os.path.join(files_root, folder_name)
    try:
        return _make_directory(target_path)
    except Exception:
        return None


def get_images_dir() -> Optional[str]:
    return _sub_media_folder("plugin_images")


def get_videos_dir() -> Optional[str]:
    return _sub_media_folder("plugin_videos")


def get_audios_dir() -> Optional[str]:
    return _sub_media_folder("plugin_audios")


def get_documents_dir() -> Optional[str]:
    return _sub_media_folder("plugin_documents")


def ensure_dir_exists(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def list_dir(
    path: str,
    recursive: bool = False,
    include_files: bool = True,
    include_dirs: bool = False,
    extensions: Optional[List[str]] = None,
) -> List[str]:
    if not path or not os.path.isdir(path) or is_path_forbidden(path):
        if is_path_forbidden(path):
            _emit_security_audit(path)
        return []

    ext_filter = None
    if extensions:
        ext_filter = {
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in extensions
        }

    def _matches_filter(filename: str) -> bool:
        if ext_filter is None:
            return True
        return os.path.splitext(filename)[1].lower() in ext_filter

    output_paths: List[str] = []

    if recursive:
        for root_dir, dir_names, file_names in os.walk(path):
            if include_dirs:
                output_paths.extend(os.path.join(root_dir, d) for d in dir_names)
            if include_files:
                output_paths.extend(
                    os.path.join(root_dir, f) for f in file_names if _matches_filter(f)
                )
    else:
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                if include_dirs:
                    output_paths.append(full_path)
            elif include_files and _matches_filter(entry):
                output_paths.append(full_path)

    return sorted(output_paths)


def write_file(path: str, content: Any) -> bool:
    if is_path_forbidden(path):
        _emit_security_audit(path)
        return False
    try:
        if isinstance(content, (bytes, bytearray)):
            with open(path, "wb") as handle:
                handle.write(bytes(content))
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(content))
        return True
    except Exception:
        return False


def read_file(path: str) -> Optional[str]:
    if is_path_forbidden(path):
        _emit_security_audit(path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return None


def delete_file(path: str) -> bool:
    if is_path_forbidden(path):
        _emit_security_audit(path)
        return False
    try:
        os.remove(path)
        return True
    except Exception:
        return False


def write_file_bytes(path: str, content: bytes) -> bool:
    if is_path_forbidden(path):
        _emit_security_audit(path)
        return False
    try:
        with open(path, "wb") as handle:
            handle.write(bytes(content))
        return True
    except Exception:
        return False


def read_file_bytes(path: str) -> Optional[bytes]:
    if is_path_forbidden(path):
        _emit_security_audit(path)
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except Exception:
        return None


class FilesController:
    class ExtensionAlreadyRegistered(Exception):
        pass

    class ExtensionNotRegistered(Exception):
        pass

    class SecretInvalid(Exception):
        pass

    class Place:
        UNKNOWN = "UNKNOWN"
        ChatActivity = "ChatActivity"
        FilteredSearchView = "FilteredSearchView"
        SharedMediaLayout = "SharedMediaLayout"
        SearchDownloadsContainer = "SearchDownloadsContainer"
        ChannelAdminLogActivity = "ChannelAdminLogActivity"

    @dataclass
    class FileInfo:
        ext: str
        on_click: Optional[Callable] = None
        whitelist_places: Optional[List[str]] = None
        blacklist_places: Optional[List[str]] = None
        get_icon: Optional[Callable] = None

    _registry_lock = threading.RLock()
    _active_registrations: Dict[Tuple[str, str], dict] = {}
    _counter = [0]

    @classmethod
    def register(
        cls,
        info: Any = None,
        on_click: Optional[Callable] = None,
        whitelist_places: Optional[List] = None,
        blacklist_places: Optional[List] = None,
        get_icon: Optional[Callable] = None,
        whitelist: Optional[List] = None,
        blacklist: Optional[List] = None,
        icon: bool = False,
    ) -> str:
        if isinstance(info, cls.FileInfo):
            ext_val = info.ext
            cb = info.on_click if on_click is None else on_click
            wl = info.whitelist_places if whitelist_places is None else whitelist_places
            bl = info.blacklist_places if blacklist_places is None else blacklist_places
            icon_getter = info.get_icon if get_icon is None else get_icon
        else:
            ext_val = info
            cb = on_click
            wl = whitelist_places
            bl = blacklist_places
            icon_getter = get_icon

        wl = whitelist if whitelist is not None else wl
        bl = blacklist if blacklist is not None else bl

        if not ext_val:
            raise ValueError("register() requires a file extension")
        normalized_ext = str(ext_val).lstrip(".").lower()

        if not callable(cb):
            raise ValueError("register() requires an on_click callback")
        if wl and bl:
            raise ValueError("whitelist_places and blacklist_places are mutually exclusive")

        caller_id = _resolve_caller_plugin_id()
        if not caller_id:
            raise RuntimeError(
                "FilesController.register must be called from a plugin context "
                "(on_plugin_load / a hook callback)"
            )

        registry_key = (caller_id, normalized_ext)
        with cls._registry_lock:
            if registry_key in cls._active_registrations:
                raise cls.ExtensionAlreadyRegistered(
                    f"extension {normalized_ext!r} is already registered by {caller_id!r}"
                )
            cls._counter[0] += 1
            generated_secret = f"{caller_id}:{normalized_ext}:{cls._counter[0]}"
            cls._active_registrations[registry_key] = {
                "secret": generated_secret,
                "on_click": cb,
                "get_icon": icon_getter,
            }

        try:
            import extera_host
            extera_host.notify_file_handler_registered(caller_id, normalized_ext)
        except Exception:
            pass

        return generated_secret

    @classmethod
    def unregister(cls, ext: str, secret: str) -> None:
        normalized_ext = str(ext).lstrip(".").lower()
        caller_id = _resolve_caller_plugin_id()

        with cls._registry_lock:
            registry_key = (caller_id, normalized_ext)
            entry = cls._active_registrations.get(registry_key)
            if entry is None and caller_id is None:
                matches = [k for k in cls._active_registrations if k[1] == normalized_ext]
                if len(matches) == 1:
                    registry_key = matches[0]
                    entry = cls._active_registrations.get(registry_key)

            if entry is None:
                raise cls.ExtensionNotRegistered(f"extension {normalized_ext!r} is not registered")
            if entry["secret"] != str(secret):
                raise cls.SecretInvalid(f"invalid secret for extension {normalized_ext!r}")

            del cls._active_registrations[registry_key]

    @staticmethod
    def icons_supported() -> bool:
        return False


def _unregister_all_for_plugin(plugin_id: str) -> None:
    if not plugin_id:
        return
    with FilesController._registry_lock:
        to_remove = [k for k in FilesController._active_registrations if k[0] == plugin_id]
        for key in to_remove:
            del FilesController._active_registrations[key]
