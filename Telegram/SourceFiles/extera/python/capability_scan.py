import ast
import base64
import json
import re
import struct
import zipfile
import zlib
from typing import Dict, List, Optional, Set, Tuple

PERM_MESSAGES_READ = "messages.read"
PERM_MESSAGES_SEND = "messages.send"
PERM_NETWORK = "network"
PERM_FILES = "files"
PERM_INTENTS = "intents"
PERM_SETTINGS = "settings"
PERM_HOOKS = "hooks"
PERM_NATIVE = "native"

KEY_OBFUSCATION = "obfuscation"
KEY_DEX = "dex"

_SECURITY_PATTERNS: Tuple[Tuple[str, str, str], ...] = (
    ("import requests", PERM_NETWORK, "requests"),
    ("urllib.request", PERM_NETWORK, "urllib"),
    ("http.client", PERM_NETWORK, "http.client"),
    ("import socket", PERM_NETWORK, "socket"),
    ("websocket", PERM_NETWORK, "websocket"),
    ("java.net", PERM_NETWORK, "java.net"),
    ("HttpURLConnection", PERM_NETWORK, "HttpURLConnection"),
    ("OkHttpClient", PERM_NETWORK, "okhttp"),
    ("WebView", PERM_NETWORK, "WebView"),
    ("DownloadManager", PERM_NETWORK, "DownloadManager"),
    ("loadHttpFile", PERM_NETWORK, "loadHttpFile"),
    ("setDataSource", PERM_NETWORK, "setDataSource"),
    ("MessagesStorage", PERM_MESSAGES_READ, "MessagesStorage"),
    ("SQLiteDatabase", PERM_MESSAGES_READ, "MessagesStorage"),
    ("queryFinalized", PERM_MESSAGES_READ, "SQLite"),
    ("on_update", PERM_MESSAGES_READ, "on_update"),
    ("add_request_hook", PERM_MESSAGES_READ, "request hooks"),
    ("send_request(", PERM_NETWORK, "send_request"),
    ("send_request(", PERM_MESSAGES_READ, "send_request"),
    ("sendRequest(", PERM_MESSAGES_READ, "sendRequest"),
    ("get_messages", PERM_MESSAGES_READ, "getMessages"),
    ("getMessages", PERM_MESSAGES_READ, "getMessages"),
    ("SendMessagesHelper", PERM_MESSAGES_SEND, "SendMessagesHelper"),
    ("send_message(", PERM_MESSAGES_SEND, "send_message"),
    ("send_text(", PERM_MESSAGES_SEND, "send_text"),
    ("send_photo(", PERM_MESSAGES_SEND, "send_photo"),
    ("send_video(", PERM_MESSAGES_SEND, "send_video"),
    ("send_document(", PERM_MESSAGES_SEND, "send_document"),
    ("send_audio(", PERM_MESSAGES_SEND, "send_audio"),
    ("edit_message(", PERM_MESSAGES_SEND, "edit_message"),
    ("get_send_messages_helper", PERM_MESSAGES_SEND, "SendMessagesHelper"),
    ("prepareSending", PERM_MESSAGES_SEND, "prepareSending"),
    ("sendSticker", PERM_MESSAGES_SEND, "sendSticker"),
    ("sendGame", PERM_MESSAGES_SEND, "sendGame"),
    ("sendCurrentLocation", PERM_MESSAGES_SEND, "sendCurrentLocation"),
    ("retrySendMessage", PERM_MESSAGES_SEND, "retrySendMessage"),
    ("editMessage(", PERM_MESSAGES_SEND, "editMessage"),
    ("on_send_message", PERM_MESSAGES_SEND, "on_send_message"),
    ("TL_messages_send", PERM_MESSAGES_SEND, "TL_messages_send"),
    ("TL_messages_edit", PERM_MESSAGES_SEND, "TL_messages_edit"),
    ("TL_messages_delete", PERM_MESSAGES_SEND, "TL_messages_delete"),
    ("ConnectionsManager", PERM_MESSAGES_SEND, "ConnectionsManager"),
    ("java.io.File", PERM_FILES, "java.io.File"),
    ("FileOutputStream", PERM_FILES, "FileOutputStream"),
    ("ContentResolver", PERM_FILES, "ContentResolver"),
    ("MediaStore", PERM_FILES, "MediaStore"),
    ("import shutil", PERM_FILES, "shutil"),
    ("os.remove", PERM_FILES, "os.remove"),
    ("os.listdir", PERM_FILES, "os.listdir"),
    ("sqlite3", PERM_FILES, "sqlite3"),
    ("get_files_dir", PERM_FILES, "get_files_dir"),
    ("get_cache_dir", PERM_FILES, "get_cache_dir"),
    ("get_images_dir", PERM_FILES, "get_images_dir"),
    ("get_videos_dir", PERM_FILES, "get_videos_dir"),
    ("get_audios_dir", PERM_FILES, "get_audios_dir"),
    ("get_documents_dir", PERM_FILES, "get_documents_dir"),
    ("getFilesDir", PERM_FILES, "getFilesDir"),
    ("getCacheDir", PERM_FILES, "getCacheDir"),
    ("getExternalFilesDir", PERM_FILES, "getExternalFilesDir"),
    ("getExternalStorage", PERM_FILES, "getExternalStorage"),
    ("startActivity", PERM_INTENTS, "startActivity"),
    ("android.content.Intent", PERM_INTENTS, "Intent"),
    ("register_intent_handler", PERM_INTENTS, "intent hooks"),
    ("NekoConfig", PERM_SETTINGS, "app config"),
    ("NaConfig", PERM_SETTINGS, "app config"),
    ("ExteraConfig", PERM_SETTINGS, "app config"),
    ("MethodHook", PERM_HOOKS, "Xposed"),
    ("hook_method", PERM_HOOKS, "Xposed"),
    ("hook_all_methods", PERM_HOOKS, "Xposed"),
    ("hook_all_constructors", PERM_HOOKS, "Xposed"),
    ("XposedBridge", PERM_HOOKS, "Xposed"),
    ("InMemoryDexClassLoader", PERM_HOOKS, "DexClassLoader"),
    ("DexClassLoader", PERM_HOOKS, "DexClassLoader"),
    ("generate_proxy_class", PERM_HOOKS, "class proxy"),
    ("java_subclass", PERM_HOOKS, "class proxy"),
    ("joverride", PERM_HOOKS, "class proxy"),
    ("allocate_instance", PERM_HOOKS, "class proxy"),
    ("deoptimize", PERM_HOOKS, "deoptimize"),
    ("TYPE_APPLICATION_OVERLAY", PERM_HOOKS, "overlay window"),
    ("TYPE_SYSTEM_ALERT", PERM_HOOKS, "overlay window"),
    ("TYPE_SYSTEM_OVERLAY", PERM_HOOKS, "overlay window"),
    ("LayoutParams.TYPE_PHONE", PERM_HOOKS, "overlay window"),
    ("import ctypes", PERM_NATIVE, "ctypes"),
    ("ctypes.CDLL", PERM_NATIVE, "ctypes"),
    ("CDLL(", PERM_NATIVE, "ctypes"),
    ("loadLibrary", PERM_NATIVE, "loadLibrary"),
    (".so\"", PERM_NATIVE, "native library"),
    (".so'", PERM_NATIVE, "native library"),
    ("CryptUnprotectData", PERM_NATIVE, "DPAPI credential decrypt"),
    ("GetClipboardData", PERM_NATIVE, "native clipboard read"),
    ("GetAsyncKeyState", PERM_NATIVE, "keylogger API"),
    ("CreateRemoteThread", PERM_NATIVE, "process injection"),
    ("VirtualAllocEx", PERM_NATIVE, "process memory allocation"),
    ("WriteProcessMemory", PERM_NATIVE, "process memory write"),
    ("appdata\\local\\google\\chrome", PERM_FILES, "Chrome browser credentials"),
    ("appdata\\roaming\\discord", PERM_FILES, "Discord tokens"),
    ("key_datas", PERM_FILES, "Telegram session keys"),
)

CRITICAL_THREAT_MARKERS: Tuple[str, ...] = (
    "DPAPI credential decrypt",
    "keylogger API",
    "keylogger",
    "cookie_extractor",
    "process injection",
    "process memory allocation",
    "process memory write",
    "Chrome browser credentials",
    "Discord tokens",
    "Telegram session keys",
)


def has_critical_threats(caps: Dict[str, List[str]]) -> Optional[str]:
    if not isinstance(caps, dict):
        return None
    for evidences in caps.values():
        if isinstance(evidences, (list, tuple)):
            for item in evidences:
                if item in CRITICAL_THREAT_MARKERS:
                    return str(item)
    return None


_DEX_BLOCK_REGEX = re.compile(
    r"^[ \t]*#[ \t]*__DEX_BEGIN__[ \t\r]*$(.*?)^[ \t]*#[ \t]*__DEX_END__[ \t\r]*$",
    re.M | re.S,
)
_DEX_LITERAL_REGEX = re.compile(r"(\"\"\"|'''|\"|')([A-Za-z0-9+/=\s]{512,})\1")
_DEX_PREFIXES = ("ZGV4C", "eJ", "eN", "eA", "eF")
_DEX_LOADER_IDENTIFIERS = ("InMemoryDexClassLoader", "DexClassLoader", "PathClassLoader")
_MAX_DEX_SIZE = 8 * 1024 * 1024
_DEX_CLASS_DISPLAY_MAX = 6


def _read_uleb128(buffer: bytes, start_pos: int) -> Tuple[int, int]:
    val = 0
    shift = 0
    curr = start_pos
    while True:
        b = buffer[curr]
        curr += 1
        val |= (b & 0x7F) << shift
        if b < 0x80:
            return val, curr
        shift += 7


def _extract_dex_string_table(raw_dex: bytes) -> List[str]:
    count, table_offset = struct.unpack_from("<II", raw_dex, 0x38)
    strings = []
    for idx in range(count):
        str_offset, = struct.unpack_from("<I", raw_dex, table_offset + idx * 4)
        _, str_start = _read_uleb128(raw_dex, str_offset)
        str_end = raw_dex.index(b"\0", str_start)
        strings.append(raw_dex[str_start:str_end].decode("utf-8", errors="replace"))
    return strings


def _extract_dex_metadata(raw_dex: bytes) -> Tuple[Set[str], List[str], List[Tuple[str, str]]]:
    strings = _extract_dex_string_table(raw_dex)
    type_count, type_table = struct.unpack_from("<II", raw_dex, 0x40)
    types = [
        strings[struct.unpack_from("<I", raw_dex, type_table + i * 4)[0]]
        for i in range(type_count)
    ]

    method_count, method_table = struct.unpack_from("<II", raw_dex, 0x58)
    methods = []
    for i in range(method_count):
        cls_idx, _, name_idx = struct.unpack_from("<HHI", raw_dex, method_table + i * 8)
        methods.append((types[cls_idx], strings[name_idx]))

    class_count, class_table = struct.unpack_from("<II", raw_dex, 0x60)
    defined = {
        types[struct.unpack_from("<I", raw_dex, class_table + i * 32)[0]]
        for i in range(class_count)
    }
    return defined, types, methods


def _normalize_descriptor(descriptor: str) -> str:
    if descriptor.startswith("L") and descriptor.endswith(";"):
        return descriptor[1:-1].replace("/", ".")
    return descriptor


def _decode_dex_comment_block(raw_text: str) -> Optional[bytes]:
    cleaned = "".join(line.strip().lstrip("#").strip() for line in raw_text.splitlines())
    try:
        data = base64.b64decode(cleaned)
    except Exception:
        return None
    try:
        data = zlib.decompress(data)
    except zlib.error:
        pass
    if not data.startswith(b"dex\n") or len(data) > _MAX_DEX_SIZE:
        return None
    return data


def _decode_dex_string_literal(raw_text: str) -> Optional[bytes]:
    stripped = "".join(raw_text.split())
    if not stripped.startswith(_DEX_PREFIXES) or len(stripped) > _MAX_DEX_SIZE * 2:
        return None
    try:
        decoded = base64.b64decode(stripped)
    except Exception:
        return None
    if not decoded.startswith(b"dex\n"):
        try:
            decompressor = zlib.decompressobj()
            if not decompressor.decompress(decoded, 4).startswith(b"dex\n"):
                return None
            decoded = zlib.decompressobj().decompress(decoded, _MAX_DEX_SIZE + 1)
        except zlib.error:
            return None
    if len(decoded) > _MAX_DEX_SIZE:
        return None
    return decoded


def _scan_embedded_dex(source_code: str) -> Dict[str, List[str]]:
    payloads: List[Optional[bytes]] = []
    intervals: List[Tuple[int, int]] = []

    for blk in _DEX_BLOCK_REGEX.finditer(source_code):
        try:
            payloads.append(_decode_dex_comment_block(blk.group(1)))
        except Exception:
            payloads.append(None)
        intervals.append(blk.span())

    for lit in _DEX_LITERAL_REGEX.finditer(source_code):
        raw = _decode_dex_string_literal(lit.group(2))
        if raw is not None:
            payloads.append(raw)
            intervals.append(lit.span(2))

    if not payloads:
        return {}

    remaining_parts: List[str] = []
    idx = 0
    for s_start, s_end in sorted(intervals):
        if s_start >= idx:
            remaining_parts.append(source_code[idx:s_start])
            idx = s_end
    remaining_parts.append(source_code[idx:])
    code_outside = "".join(remaining_parts)
    is_actively_loaded = any(loader in code_outside for loader in _DEX_LOADER_IDENTIFIERS)

    summary_info: List[str] = []
    results: Dict[str, List[str]] = {}
    aggregated_size = 0
    collected_classes: List[str] = []

    for binary in payloads:
        if binary is None:
            _append_opaque_evidence(results, "unreadable DEX block")
            continue
        aggregated_size += len(binary)
        try:
            classes_defined, all_types, all_methods = _extract_dex_metadata(binary)
        except Exception:
            _append_opaque_evidence(results, "unreadable DEX block")
            continue

        collected_classes.extend(sorted(_normalize_descriptor(c) for c in classes_defined))
        if not is_actively_loaded:
            _append_opaque_evidence(results, "embedded DEX binary")
            continue

        external_types = [_normalize_descriptor(t) for t in all_types if t not in classes_defined]
        invocations = [
            f"{_normalize_descriptor(owner)}.{method}"
            for owner, method in all_methods
            if owner not in classes_defined
        ]
        symbol_text = "\n".join(external_types + invocations)

        for pat, perm, ev in _SECURITY_PATTERNS:
            tag = f"DEX: {ev}"
            if pat in symbol_text and tag not in results.setdefault(perm, []):
                results[perm].append(tag)

        if (
            any(".exec" in m for m in invocations if m.startswith("java.lang.Runtime"))
            or "java.lang.ProcessBuilder" in external_types
        ):
            bucket = results.setdefault(PERM_NATIVE, [])
            if "DEX: Runtime.exec" not in bucket:
                bucket.append("DEX: Runtime.exec")

    if aggregated_size == 0 and not results:
        return {}

    summary_info.append(f"size:{aggregated_size}")
    summary_info.append("loaded:" + ("yes" if is_actively_loaded else "no"))
    for cls_name in collected_classes[:_DEX_CLASS_DISPLAY_MAX]:
        summary_info.append(f"class:{cls_name}")
    if len(collected_classes) > _DEX_CLASS_DISPLAY_MAX:
        summary_info.append(f"more:{len(collected_classes) - _DEX_CLASS_DISPLAY_MAX}")

    results[KEY_DEX] = summary_info
    return {p: lst for p, lst in results.items() if lst}


_PACKER_MARKERS = (
    ("__pyarmor__", "pyarmor"),
    ("pytransform", "pyarmor"),
    ("pyarmor_runtime", "pyarmor"),
    ("PYARMOR", "pyarmor"),
    ("pyminifier", "pyminifier"),
    ("Sourcedefender", "sourcedefender"),
    ("sourcedefender", "sourcedefender"),
)

_DECODER_TRANSFORMS = {
    "b64decode": "base64",
    "b85decode": "base85",
    "a85decode": "base85",
    "b32decode": "base32",
    "b16decode": "base16",
    "unhexlify": "unhexlify",
    "decompress": "zlib",
    "loads": "marshal",
    "fromhex": "hex",
    "decode": "codecs",
    "frombytes": "bytes",
}

_MANGLED_NAME_REGEX = re.compile(r"\b_[A-Za-z]{0,2}[0-9a-z]{16,}\b")
_HEX_ESCAPE_REGEX = re.compile(r"\\x[0-9a-fA-F]{2}")


def _inspect_node_func_name(node: ast.AST) -> str:
    func_node = getattr(node, "func", None)
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return func_node.attr
    return ""


def _evaluate_decoder_signature(node: ast.AST, known_fns: Dict[str, str], tainted_vars: Dict[str, str]) -> str:
    if isinstance(node, ast.Name) and node.id in tainted_vars:
        return tainted_vars[node.id]
    if not isinstance(node, ast.Call):
        return ""
    call_name = _inspect_node_func_name(node)
    caller_id = getattr(getattr(node.func, "value", None), "id", "")
    if isinstance(node.func, ast.Name) and call_name in known_fns:
        return known_fns[call_name]
    if call_name == "decode" and caller_id != "codecs":
        return ""
    if call_name == "loads" and caller_id != "marshal":
        return ""
    return _DECODER_TRANSFORMS.get(call_name, "")


def _locate_first_decoder_type(tree: ast.AST, known_fns: Dict[str, str], tainted_vars: Dict[str, str]) -> str:
    for child in ast.walk(tree):
        found = _evaluate_decoder_signature(child, known_fns, tainted_vars)
        if found:
            return found
    return ""


def _analyze_dynamic_execs(source_code: str) -> List[str]:
    try:
        parsed_tree = ast.parse(source_code)
    except Exception:
        return []

    defined_fns = [
        n for n in ast.walk(parsed_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assignments = [
        n for n in parsed_tree.body
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
    ]

    function_signatures: Dict[str, str] = {}
    tainted_variables: Dict[str, str] = {}
    is_updated = True

    while is_updated:
        is_updated = False
        for fn in defined_fns:
            if fn.name in function_signatures:
                continue
            signature = _locate_first_decoder_type(fn, function_signatures, tainted_variables)
            if signature:
                function_signatures[fn.name] = signature
                is_updated = True

        for assign_node in assignments:
            signature = _locate_first_decoder_type(assign_node.value, function_signatures, tainted_variables)
            if not signature:
                continue
            targets = (
                assign_node.targets
                if isinstance(assign_node, ast.Assign)
                else [assign_node.target]
            )
            for tgt in targets:
                if isinstance(tgt, ast.Name) and tgt.id not in tainted_variables:
                    tainted_variables[tgt.id] = signature
                    is_updated = True

    detected_indicators: List[str] = []
    for node in ast.walk(parsed_tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in ("exec", "eval", "compile"):
            continue
        for arg in node.args[:1]:
            sig = _locate_first_decoder_type(arg, function_signatures, tainted_variables)
            if sig:
                label = f"exec+{sig}"
                if label not in detected_indicators:
                    detected_indicators.append(label)

    if "marshal.loads" in source_code and "types.FunctionType" in source_code:
        detected_indicators.append("marshal code")

    return detected_indicators


def _detect_obfuscation(source: str) -> List[str]:
    strong_indicators: List[str] = []
    weak_indicators: List[str] = []

    def _record(container: List[str], item: str) -> None:
        if item not in container:
            container.append(item)

    for marker, name in _PACKER_MARKERS:
        if marker in source:
            _record(strong_indicators, name)

    for ev in _analyze_dynamic_execs(source):
        _record(strong_indicators, ev)

    names = set(_MANGLED_NAME_REGEX.findall(source))
    if len(names) >= 8:
        _record(strong_indicators, "mangled names")

    lines = source.splitlines() or [""]
    if max(len(l) for l in lines) >= 2000:
        _record(weak_indicators, "long lines")

    if len(_HEX_ESCAPE_REGEX.findall(source)) >= 50:
        _record(weak_indicators, "escaped strings")

    if strong_indicators:
        return strong_indicators + weak_indicators
    if len(weak_indicators) >= 2:
        return weak_indicators
    return []


_MAX_FILE_BYTES = 4 * 1024 * 1024
_MAX_ZIP_BYTES = 16 * 1024 * 1024

_KNOWN_IMPORT_SCOPES = {
    "requests": (PERM_NETWORK, "requests"),
    "urllib": (PERM_NETWORK, "urllib"),
    "urllib3": (PERM_NETWORK, "urllib3"),
    "http": (PERM_NETWORK, "http"),
    "socket": (PERM_NETWORK, "socket"),
    "ssl": (PERM_NETWORK, "ssl"),
    "aiohttp": (PERM_NETWORK, "aiohttp"),
    "httpx": (PERM_NETWORK, "httpx"),
    "websocket": (PERM_NETWORK, "websocket"),
    "websockets": (PERM_NETWORK, "websockets"),
    "ftplib": (PERM_NETWORK, "ftplib"),
    "smtplib": (PERM_NETWORK, "smtplib"),
    "shutil": (PERM_FILES, "shutil"),
    "pathlib": (PERM_FILES, "pathlib"),
    "glob": (PERM_FILES, "glob"),
    "sqlite3": (PERM_FILES, "sqlite3"),
    "tempfile": (PERM_FILES, "tempfile"),
    "subprocess": (PERM_NATIVE, "subprocess"),
    "ctypes": (PERM_NATIVE, "ctypes"),
    "cffi": (PERM_NATIVE, "cffi"),
    "multiprocessing": (PERM_NATIVE, "multiprocessing"),
    "winreg": (PERM_NATIVE, "winreg"),
    "win32crypt": (PERM_NATIVE, "win32crypt"),
    "win32api": (PERM_NATIVE, "win32api"),
    "pynput": (PERM_NATIVE, "keylogger"),
    "keyboard": (PERM_NATIVE, "keylogger"),
    "browser_cookie3": (PERM_NATIVE, "cookie_extractor"),
    "mss": (PERM_NATIVE, "screen_capture"),
    "pyautogui": (PERM_NATIVE, "screen_capture"),
}


def _scan_imports(source: str) -> Dict[str, List[str]]:
    detected: Dict[str, List[str]] = {}
    try:
        root_node = ast.parse(source)
    except Exception:
        return detected

    for node in ast.walk(root_node):
        collected_names: List[str] = []
        if isinstance(node, ast.Import):
            collected_names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            collected_names = [node.module]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            collected_names = [str(node.args[0].value)]

        for module_name in collected_names:
            base_module = module_name.split(".")[0]
            matched = _KNOWN_IMPORT_SCOPES.get(base_module)
            if matched:
                perm_key, label = matched
                bucket = detected.setdefault(perm_key, [])
                if label not in bucket:
                    bucket.append(label)

    return detected


def _merge_dictionaries(dest: Dict[str, List[str]], src: Dict[str, List[str]]) -> None:
    for key, values in src.items():
        bucket = dest.setdefault(key, [])
        for v in values:
            if v not in bucket:
                bucket.append(v)


def _scan_source_string(source: str) -> Dict[str, List[str]]:
    findings: Dict[str, List[str]] = {}
    for pat, perm, ev in _SECURITY_PATTERNS:
        if pat in source:
            bucket = findings.setdefault(perm, [])
            if ev not in bucket:
                bucket.append(ev)

    _merge_dictionaries(findings, _scan_imports(source))
    obf = _detect_obfuscation(source)
    if obf:
        findings[KEY_OBFUSCATION] = obf

    _merge_dictionaries(findings, _scan_embedded_dex(source))
    return {k: v for k, v in findings.items() if v}


def _append_opaque_evidence(findings: Dict[str, List[str]], item: str) -> None:
    bucket = findings.setdefault(KEY_OBFUSCATION, [])
    if item not in bucket:
        bucket.append(item)


def _is_compiled_bytecode(filename: str, content: bytes) -> bool:
    if filename.endswith(".pyc"):
        return True
    if len(content) >= 4 and content[2:4] == b"\r\n":
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _scan_zip_container(path: str) -> Dict[str, List[str]]:
    findings: Dict[str, List[str]] = {}
    remaining_budget = _MAX_ZIP_BYTES

    with zipfile.ZipFile(path) as zf:
        eligible_entries = [
            info for info in zf.infolist()
            if not info.is_dir() and info.filename.endswith((".py", ".pyc"))
        ]
        all_entry_names = set(zf.namelist())

        for idx, entry in enumerate(eligible_entries):
            if remaining_budget <= 0:
                _append_opaque_evidence(findings, f"unscanned files ({len(eligible_entries) - idx})")
                break
            chunk_limit = min(_MAX_FILE_BYTES, remaining_budget)
            try:
                with zf.open(entry) as stream:
                    raw_data = stream.read(chunk_limit + 1)
            except Exception:
                continue

            was_truncated = len(raw_data) > chunk_limit
            raw_data = raw_data[:chunk_limit]
            remaining_budget -= len(raw_data)

            if _is_compiled_bytecode(entry.filename, raw_data):
                clean_name = entry.filename.replace("\\", "/")
                parts = clean_name.split("/")
                if len(parts) >= 2 and parts[-2] == "__pycache__":
                    base_py = parts[-1].split(".")[0] + ".py"
                    parent = "/".join(parts[:-2])
                    source_py = f"{parent}/{base_py}" if parent else base_py
                    if source_py in all_entry_names:
                        continue
                _append_opaque_evidence(findings, f"compiled bytecode ({entry.filename})")
                continue

            if was_truncated:
                _append_opaque_evidence(findings, f"truncated source ({entry.filename})")

            _merge_dictionaries(findings, _scan_source_string(raw_data.decode("utf-8", errors="replace")))

    return {k: v for k, v in findings.items() if v}


def scan(path: str) -> Dict[str, List[str]]:
    try:
        if zipfile.is_zipfile(path):
            return _scan_zip_container(path)
        with open(path, "rb") as handle:
            raw_data = handle.read(_MAX_FILE_BYTES + 1)
    except Exception:
        return {}

    truncated = len(raw_data) > _MAX_FILE_BYTES
    raw_data = raw_data[:_MAX_FILE_BYTES]

    if _is_compiled_bytecode(path, raw_data):
        return {KEY_OBFUSCATION: ["compiled bytecode"]}

    results = _scan_source_string(raw_data.decode("utf-8", errors="replace"))
    if truncated:
        _append_opaque_evidence(results, "truncated source")
    return results


_IMPORT_REGEX = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")


def _read_candidate_sources(path: str) -> List[str]:
    if zipfile.is_zipfile(path):
        texts = []
        with zipfile.ZipFile(path) as zf:
            for entry in zf.infolist():
                if entry.filename.endswith(".py") and not entry.is_dir():
                    try:
                        with zf.open(entry) as stream:
                            texts.append(stream.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace"))
                    except Exception:
                        continue
        return texts
    try:
        with open(path, "rb") as handle:
            return [handle.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")]
    except Exception:
        return []


def locations(path: str) -> Dict[str, dict]:
    sources = _read_candidate_sources(path)
    located: Dict[str, dict] = {}

    def _mark(permission: str, line_no: int, content: str) -> None:
        rec = located.setdefault(permission, {"lines": [], "total": 0, "seen": set()})
        pair = (line_no, content)
        if pair in rec["seen"]:
            return
        rec["seen"].add(pair)
        rec["total"] += 1
        if len(rec["lines"]) < 4:
            rec["lines"].append([line_no, content.strip()[:160]])

    for src in sources:
        for num, line in enumerate(src.splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            for pat, perm, _ in _SECURITY_PATTERNS:
                if pat in line:
                    _mark(perm, num, line)
            match = _IMPORT_REGEX.match(line)
            if match:
                mod = (match.group(1) or match.group(2)).split(".")[0]
                matched = _KNOWN_IMPORT_SCOPES.get(mod)
                if matched:
                    _mark(matched[0], num, line)

    for entry in located.values():
        entry.pop("seen", None)

    return located


def scan_json(path: str) -> str:
    try:
        return json.dumps(scan(path), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
