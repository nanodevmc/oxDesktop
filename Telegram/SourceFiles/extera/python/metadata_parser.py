import ast
import copy
import json
import os
import re
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple


class PluginMetadataError(Exception):
    pass


_METADATA_KEYS: Tuple[str, ...] = (
    "__id__",
    "__name__",
    "__description__",
    "__author__",
    "__version__",
    "__icon__",
    "__app_version__",
    "__sdk_version__",
    "__min_version__",
    "__beta__",
    "__requirements__",
    "__permissions__",
)

PERMISSION_UI = "ui"
KNOWN_PERMISSIONS: Tuple[str, ...] = (
    PERMISSION_UI,
    "messages.read",
    "messages.send",
    "network",
    "files",
    "intents",
    "settings",
    "hooks",
    "native",
)

_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,31}$")
_CORE_COLLISION_NAMES: Set[str] = {
    "sys", "os", "builtins", "_compat", "extera_host", "exd_java", "base_plugin",
}

_metadata_cache: Dict[str, Tuple[Tuple[int, int], Dict[str, Any]]] = {}


def _file_stat_key(path: str) -> Optional[Tuple[int, int]]:
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None


def read_source(path: str) -> str:
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            for candidate in ("plugin.py", "main.py", "__init__.py"):
                if candidate in names:
                    return zf.read(candidate).decode("utf-8", errors="replace")
            for entry in names:
                if entry.endswith("/plugin.py") or entry.endswith("/main.py"):
                    return zf.read(entry).decode("utf-8", errors="replace")
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _extract_ast_constants(path: str) -> Dict[str, Any]:
    content = read_source(path)
    try:
        parsed_tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        raise PluginMetadataError(f"plugin file {path!r} has a syntax error: {exc}") from exc
    except OSError as exc:
        raise PluginMetadataError(f"cannot read plugin file {path!r}: {exc}") from exc

    extracted: Dict[str, Any] = {}
    for stmt in parsed_tree.body:
        target_name: Optional[str] = None
        val_node: Optional[ast.AST] = None

        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target_name = stmt.targets[0].id
            val_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
            target_name = stmt.target.id
            val_node = stmt.value

        if not target_name or target_name not in _METADATA_KEYS or target_name in extracted:
            continue

        try:
            extracted[target_name] = ast.literal_eval(val_node)
        except (ValueError, SyntaxError, TypeError, MemoryError):
            pass

    return extracted


def _validate_plugin_id(plugin_id: Any) -> str:
    if plugin_id is None:
        raise PluginMetadataError("plugin metadata is missing the required __id__ constant")
    if not isinstance(plugin_id, str):
        raise PluginMetadataError(f"__id__ must be a string, got {type(plugin_id).__name__}")
    if not _ID_PATTERN.match(plugin_id):
        raise PluginMetadataError(
            f"invalid __id__ {plugin_id!r}: must be 2-32 characters, start with a letter "
            "and contain only Latin letters, digits, '_' or '-'"
        )
    if plugin_id in _CORE_COLLISION_NAMES:
        raise PluginMetadataError(f"__id__ {plugin_id!r} collides with a critical core module name")
    return plugin_id


def _tokenize_list_string(text: str) -> List[str]:
    results: List[str] = []
    for item in text.replace("\n", ",").split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        if results and cleaned[0] in "<>=!~":
            results[-1] = f"{results[-1]},{cleaned}"
        else:
            results.append(cleaned)
    return results


def _validate_permissions(declared: Any) -> List[str]:
    items = _tokenize_list_string(declared) if isinstance(declared, str) else declared
    if not isinstance(items, (list, tuple, set, frozenset)):
        raise PluginMetadataError("__permissions__ must be a list of permission keys")

    verified: List[str] = []
    for perm in items:
        if not isinstance(perm, str):
            raise PluginMetadataError(f"__permissions__ entries must be strings, got {type(perm).__name__}")
        perm_key = perm.strip()
        if perm_key not in KNOWN_PERMISSIONS:
            raise PluginMetadataError(
                f"unknown permission {perm!r} in __permissions__; known keys: {', '.join(KNOWN_PERMISSIONS)}"
            )
        if perm_key not in verified:
            verified.append(perm_key)
    return verified


def _read_metadata_direct(path: str) -> Dict[str, Any]:
    if str(path).endswith(".elyx"):
        try:
            import exd_elyx
            return exd_elyx.read_meta(path)
        except Exception:
            pass

    is_archive_file = os.path.isfile(path) and zipfile.is_zipfile(path)
    if is_archive_file:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                if "metadata.json" in zf.namelist():
                    raw_json = zf.read("metadata.json").decode("utf-8", errors="replace")
                    json_data = json.loads(raw_json)
                    valid_id = _validate_plugin_id(json_data.get("id"))
                    has_perms = json_data.get("permissions") is not None
                    return {
                        "id": valid_id,
                        "name": json_data.get("name") or valid_id,
                        "description": json_data.get("description", ""),
                        "author": json_data.get("author", ""),
                        "version": str(json_data.get("version", "1.0")),
                        "icon": json_data.get("icon"),
                        "app_version": json_data.get("app_version"),
                        "sdk_version": json_data.get("sdk_version"),
                        "beta": bool(json_data.get("beta", False)),
                        "requirements": [str(x) for x in json_data.get("requirements", [])],
                        "permissions": _validate_permissions(json_data.get("permissions", [])),
                        "permissions_declared": has_perms,
                        "is_archive": True,
                    }
        except Exception:
            pass

    constants = _extract_ast_constants(path)
    plugin_id = _validate_plugin_id(constants.get("__id__"))
    name = constants.get("__name__")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        name = plugin_id

    version = constants.get("__version__", "1.0")
    if not isinstance(version, str):
        version = str(version)

    app_ver: Optional[str] = constants.get("__app_version__")
    min_ver = constants.get("__min_version__")
    if app_ver is None and min_ver is not None:
        app_ver = f">={min_ver}"

    reqs = constants.get("__requirements__") or []
    if isinstance(reqs, str):
        reqs = _tokenize_list_string(reqs)
    if not isinstance(reqs, (list, tuple)) or not all(isinstance(x, str) for x in reqs):
        reqs = []

    declared_perms = "__permissions__" in constants
    perms: List[str] = []
    if declared_perms:
        try:
            perms = _validate_permissions(constants.get("__permissions__") or [])
        except PluginMetadataError:
            perms = []

    return {
        "id": plugin_id,
        "name": name if name else plugin_id,
        "description": constants.get("__description__") or "",
        "author": constants.get("__author__") or "",
        "version": version,
        "icon": constants.get("__icon__"),
        "app_version": app_ver,
        "sdk_version": constants.get("__sdk_version__"),
        "beta": bool(constants.get("__beta__", False)),
        "requirements": list(reqs),
        "permissions": perms,
        "permissions_declared": declared_perms,
        "is_archive": is_archive_file,
    }


def read_metadata(path: str) -> Dict[str, Any]:
    key = _file_stat_key(path)
    cached_entry = _metadata_cache.get(path)
    if key is not None and cached_entry is not None and cached_entry[0] == key:
        return copy.deepcopy(cached_entry[1])

    meta = _read_metadata_direct(path)
    if key is not None:
        _metadata_cache[path] = (key, copy.deepcopy(meta))
    return meta
