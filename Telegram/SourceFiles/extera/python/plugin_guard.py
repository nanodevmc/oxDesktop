import ast
import math
import re
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

import capability_scan


class _ASTCanonicalizer(ast.NodeTransformer):
    TARGET_KEYWORDS = ('DEX', 'SO', 'LIB', 'PAYLOAD', 'BASE64', 'ELF', 'BINARY', 'ZIP', 'APK', 'JAR')
    ALLOWED_IDENTIFIERS = {
        'os', 'sys', 'socket', 'subprocess', 'urllib', 'requests', 'aiohttp', 'httpx',
        'sqlite3', 'zlib', 'base64', 'struct', 'hashlib', 'hmac', 'uuid', 'threading',
        'time', 're', 'json', 'math', 'glob', 'traceback',
        'UserConfig', 'MessagesStorage', 'MessagesController', 'SendMessagesHelper',
        'AccountInstance', 'ExteraConfig', 'TLRPC', 'ApplicationLoader', 'NotificationCenter',
        'BasePlugin', 'MethodHook', 'HookResult', 'HookStrategy', 'AppEvent',
        'BulletinHelper', 'AlertDialogBuilder', 'Header', 'Input', 'Switch', 'Text',
        'find_class', 'dynamic_proxy', 'run_on_queue', 'run_on_ui_thread', 'log', 'PLUGINS_QUEUE',
        'eval', 'exec', '__import__', 'compile', 'getattr', 'setattr', 'hasattr', 'open',
        'globals', 'locals', 'int', 'str', 'float', 'bytes', 'bytearray', 'len', 'range',
        'print', 'sum', 'min', 'max', 'super', 'self', 'cls', 'Exception', 'BaseException',
        'RuntimeError', 'TypeError', 'ValueError', 'KeyError', 'AttributeError', 'True', 'False', 'None',
        'phone', 'current_user', 'currentUser', 'get_user_config', 'getCurrentUser',
        'send_message', 'send_text', 'send_request',
        'InstallPluginBottomSheet', 'trusted', 'b85decode', 'rc4', 'marshal', 'loads',
    }
    _BASE64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-.")

    def _remap(self, name: str) -> str:
        return name if name in self.ALLOWED_IDENTIFIERS else "_v_"

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        for target in getattr(node, 'targets', []):
            if isinstance(target, ast.Name):
                t_upper = target.id.upper()
                if any(kw in t_upper for kw in self.TARGET_KEYWORDS):
                    node.value = ast.Constant(value="")
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self._remap(node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._remap(node.arg)
        return node

    def visit_Expr(self, node: ast.Expr) -> Optional[ast.AST]:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            val = node.value
            if (
                len(val) > 60
                or val.startswith("ZGV4")
                or val.startswith("f0VMRg")
                or ".so" in val[:20]
                or "ELF" in val[:20]
            ):
                return ast.Constant(value="")
            if val.startswith(("TL_", "payments.", "messages.", "org.telegram.")) or any(
                k in val
                for k in ("StarGift", "PaidReaction", "StarsBalance", "StarsStatus", "StarsAmount")
            ):
                return node
            if len(val) >= 16 and " " not in val and all(c in self._BASE64_CHARS for c in val):
                return ast.Constant(value="")
        elif isinstance(node.value, bytes):
            b_val = node.value
            if (
                len(b_val) > 40
                or b_val.startswith(b"dex\n")
                or b_val.startswith(b"\x7fELF")
                or len(b_val) >= 16
            ):
                return ast.Constant(value=b"")
        return node


_CFG_CONTAINERS = frozenset({'Try', 'ExceptHandler', 'If', 'While', 'For', 'With', 'Call'})
_CFG_ELEMENTS = frozenset({'Call', 'Try', 'If', 'While', 'For', 'Raise', 'Return', 'Yield', 'Import', 'ImportFrom', 'Attribute'})
_CFG_STATEMENTS = ("Assign", "Expr", "If", "Try", "For", "While", "Return", "Raise")


def _generate_cfg_tokens(root_node: ast.AST) -> str:
    tokens = set()
    for parent in ast.walk(root_node):
        p_name = type(parent).__name__
        if p_name in _CFG_CONTAINERS:
            for child in ast.iter_child_nodes(parent):
                c_name = type(child).__name__
                if c_name in _CFG_ELEMENTS:
                    tokens.add(f"cfg_{p_name}_{c_name}")
        for attr in ("body", "orelse", "finalbody"):
            seq = getattr(parent, attr, None)
            if isinstance(seq, list) and len(seq) > 1:
                for s1, s2 in zip(seq[:-1], seq[1:]):
                    t1, t2 = type(s1).__name__, type(s2).__name__
                    if t1 in _CFG_STATEMENTS and t2 in _CFG_STATEMENTS:
                        tokens.add(f"cfg_seq_{t1}_{t2}")
    return " ".join(sorted(tokens))


def _resolve_call_target(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _inspect_behavioral_tags(node: ast.AST) -> List[str]:
    tags: List[str] = []
    if isinstance(node, (ast.While, ast.For)):
        has_send = False
        has_fast_sleep = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = _resolve_call_target(sub)
                if "send_message" in name.lower():
                    has_send = True
                if name == "sleep" and sub.args:
                    arg = sub.args[0]
                    if isinstance(arg, ast.Constant):
                        try:
                            if float(arg.value) <= 0.25:
                                has_fast_sleep = True
                        except Exception:
                            pass
                    elif isinstance(arg, ast.BinOp):
                        has_fast_sleep = True
        if has_send and has_fast_sleep:
            tags.extend(["token_flood_loop", "token_rapid_send", "token_unsolicited_spammer"])

    has_db = False
    has_dyn = False
    has_stars = False
    star_ops = ("sendpaidreaction", "paidreactionprivacy", "updatestargiftprice", "transferstargift", "inputsavedstargift")

    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            low = sub.value.lower()
            if any(k in low for k in ("cache4.db", "tgnet.dat", "userconfig.xml", "getauthkey", "getsecretpkeys", "auth_key", "key_datas", "tdata")):
                has_db = True
            if any(k in low for k in star_ops):
                has_stars = True
        elif isinstance(sub, ast.Attribute):
            if any(k in sub.attr.lower() for k in star_ops):
                has_stars = True
        elif isinstance(sub, ast.Call):
            if _resolve_call_target(sub) in ("b85decode", "rc4", "compile"):
                has_dyn = True

    if has_db:
        tags.extend(["token_session_extract", "token_db_theft"])
    if has_dyn:
        tags.extend(["token_dynamic_stager", "token_payload_exec"])
    if has_stars:
        tags.extend(["token_stars_drainer", "token_gift_hijack"])

    return tags


def _build_chunk_representation(node: ast.AST, tags: List[str], normalize: bool) -> Optional[str]:
    raw_unparsed = ast.unparse(node)
    canonical_tree = _ASTCanonicalizer().visit(ast.parse(raw_unparsed)) if normalize else node
    code_text = ast.unparse(canonical_tree) if normalize else raw_unparsed
    normalized_lines = " ".join(line.strip() for line in code_text.splitlines() if line.strip())
    if len(normalized_lines) <= 20:
        return None

    components = [normalized_lines]
    cfg = _generate_cfg_tokens(canonical_tree)
    if cfg:
        components.append(cfg)
    if tags:
        components.append(" ".join(tags * 3))
    return " ".join(components)


def extract_chunks(source: str, limit: int = 64) -> List[List[Any]]:
    tagged_chunks: List[List[Any]] = []
    plain_chunks: List[List[Any]] = []
    try:
        tree = ast.parse(source)
    except Exception:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Try, ast.For, ast.While)):
            continue
        if isinstance(node, (ast.Try, ast.For, ast.While)) and len(getattr(node, "body", [])) < 2:
            continue
        if len(tagged_chunks) + len(plain_chunks) >= limit * 3:
            break

        if isinstance(node, ast.Try):
            name = "block_try"
        elif isinstance(node, ast.For):
            name = "block_for"
        elif isinstance(node, ast.While):
            name = "block_while"
        else:
            name = getattr(node, "name", type(node).__name__)

        lineno = getattr(node, "lineno", 0)
        tags = _inspect_behavioral_tags(node)
        target_node = node

        if isinstance(node, ast.ClassDef):
            try:
                sanitized_body = [
                    m if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else ast.FunctionDef(
                        name=m.name,
                        args=m.args,
                        body=[ast.Pass()],
                        decorator_list=m.decorator_list,
                        returns=getattr(m, "returns", None),
                    )
                    for m in node.body
                ]
                target_node = ast.ClassDef(
                    name=node.name,
                    bases=node.bases,
                    keywords=node.keywords,
                    body=sanitized_body,
                    decorator_list=node.decorator_list,
                )
            except Exception:
                target_node = node

        chunk_text = None
        try:
            chunk_text = _build_chunk_representation(target_node, tags, True)
        except Exception:
            try:
                chunk_text = _build_chunk_representation(target_node, tags, False)
            except Exception:
                chunk_text = None

        if chunk_text:
            dest = tagged_chunks if tags else plain_chunks
            dest.append([name, lineno, chunk_text])

    output: List[List[Any]] = []
    seen_texts: Set[str] = set()
    for entry in tagged_chunks + plain_chunks:
        if entry[2] not in seen_texts:
            seen_texts.add(entry[2])
            output.append(entry)
        if len(output) >= limit:
            break
    return output


_BOT_TOKEN_PATTERN = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
_WEB_URL_PATTERN = re.compile(r"""https?://[^\s'"<>)]+""")
_IP_ENDPOINT_PATTERN = re.compile(r"https?://((?:\d{1,3}\.){3}\d{1,3})")
_CRYPTO_RE = re.compile(r"\b(?:T[1-9A-HJ-NP-Za-km-z]{33}|0x[a-fA-F0-9]{40}|(?:EQ|UQ)[A-Za-z0-9_-]{46})\b")
_EXFIL_HOSTS = (
    "discord.com/api/webhooks",
    "discordapp.com/api/webhooks",
    "webhook.site",
    "pipedream",
    "requestbin",
    "ngrok",
    "iplogger",
    "grabify",
    "2no.co",
)
_LOOKUP_HOSTS = ("api.ipify.org", "ipinfo.io", "ip-api.com", "ifconfig.me", "icanhazip.com")
_SESSION_NAMES = ("key_datas", "tdata", "cache4.db", "tgnet.dat", "userconfig.xml", "auth_key", "getauthkey")
_KNOWN_DNS_IPS = ("1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112")


def _is_private_or_loopback_ip(ip: str) -> bool:
    try:
        octets = [int(x) for x in ip.split(".")]
    except ValueError:
        return False
    if len(octets) != 4:
        return False
    o1, o2 = octets[0], octets[1]
    return (
        o1 in (10, 127, 0)
        or (o1 == 192 and o2 == 168)
        or (o1 == 172 and 16 <= o2 <= 31)
        or (o1 == 169 and o2 == 254)
        or (o1 == 100 and 64 <= o2 <= 127)
    )


def _compute_shannon_entropy(data: str) -> float:
    if not data:
        return 0.0
    freq: Dict[str, int] = {}
    for char in data:
        freq[char] = freq.get(char, 0) + 1
    total = len(data)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def _iter_string_constants(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


_SESSION_KEYWORD_RE = re.compile(
    r"(?<![a-z0-9_])(key_datas|tdata|cache4\.db|tgnet\.dat|userconfig\.xml|auth_key|getauthkey)(?![a-z0-9_])"
)
_NETWORK_LIBS_RE = re.compile(
    r"\b(requests|urllib|urllib3|http\.client|aiohttp|httpx|socket|okhttpclient|httpurlconnection|websocket)\b"
)
_SEND_OR_UPLOAD_RE = re.compile(
    r"(\.post\(|\.put\(|senddocument|send_file|sendfile|\bfiles\s*=|upload|sendall\(|\.send\(|urlopen\()"
)
_FS_READ_RE = re.compile(
    r"(\bopen\(|read_bytes|shutil\.copy|copyfile|copytree|make_archive|zipfile|glob\.glob|os\.walk|listdir|sqlite3|fileinputstream)"
)
_EXTERNAL_IN_RE = re.compile(
    r"(requests\.|urlopen|urllib|httpx|aiohttp|\.recv\(|b64decode|b85decode|a85decode|decompress\(|marshal\.loads|fromhex|okhttp|httpurlconnection)"
)
_CLIP_READ_RE = re.compile(
    r"(getprimaryclip|getclipboardtext|clipboard\.paste|clipboard\(\)\.text|getclipboard\(\)|\.gettext\(\)\s*.*clip|pyperclip\.paste)"
)
_CLIP_WRITE_RE = re.compile(r"(setprimaryclip|addtoclipboard|clipboard\.copy|pyperclip\.copy|settext\()")
_WALLET_MATCH_RE = re.compile(r"(T\[1-9A-HJ|0x\[a-fA-F0-9\]\{40\}|\[A-Za-z0-9_-\]\{4[68]\}|\(\?:EQ\|UQ\)|bc1\[)")


def _extract_source_span(lines: List[str], node: ast.AST) -> str:
    try:
        start_line = node.lineno - 1
        end_line = node.end_lineno - 1
        if start_line == end_line:
            return lines[start_line][node.col_offset:node.end_col_offset]
        if end_line - start_line > 40:
            end_line = start_line + 40
        return "\n".join(lines[start_line:end_line + 1])
    except Exception:
        return ""


def _collect_descendant_nodes(parent: ast.AST):
    stack = list(ast.iter_child_nodes(parent))
    while stack:
        item = stack.pop()
        yield item
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(item))


def _extract_name_identifiers(node: ast.AST) -> Set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _propagate_tainted_names(lines: List[str], assignments: List[ast.AST]) -> Set[str]:
    tainted = set()
    for _ in range(4):
        modified = False
        for node in assignments:
            val_text = _extract_source_span(lines, node.value).lower()
            if not (_EXTERNAL_IN_RE.search(val_text) or _extract_name_identifiers(node.value) & tainted):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                for var_id in _extract_name_identifiers(tgt):
                    if var_id not in tainted:
                        tainted.add(var_id)
                        modified = True
        if not modified:
            break
    return tainted


def _detect_dynamic_invocations(tree: ast.AST, source: str) -> Tuple[List[int], List[int], List[int]]:
    lines = source.splitlines()
    scope_roots = [tree] + [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    grouped_calls = []
    global_taints: Set[str] = set()

    for scope in scope_roots:
        assign_nodes = []
        exec_nodes = []
        for child in _collect_descendant_nodes(scope):
            if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and child.value is not None:
                assign_nodes.append(child)
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id in ("exec", "eval")
                and child.args
            ):
                exec_nodes.append(child)

        if not assign_nodes and not exec_nodes:
            continue
        local_taint = _propagate_tainted_names(lines, assign_nodes)
        global_taints |= local_taint
        grouped_calls.append((exec_nodes, local_taint))

    remote_lines: List[int] = []
    indirect_lines: List[int] = []
    local_lines: List[int] = []

    for calls, local_scope_taint in grouped_calls:
        for node in calls:
            arg = node.args[0]
            txt = _extract_source_span(lines, arg).lower()
            names = _extract_name_identifiers(arg)
            if _EXTERNAL_IN_RE.search(txt) or (names & local_scope_taint):
                remote_lines.append(node.lineno)
            elif names & global_taints:
                indirect_lines.append(node.lineno)
            else:
                local_lines.append(node.lineno)

    return remote_lines, indirect_lines, local_lines


def _evaluate_security_rules(source: str, capabilities: Dict[str, List[str]]) -> Tuple[List[Dict[str, Any]], str]:
    findings: List[Dict[str, Any]] = []
    lines = source.lower().splitlines()

    def record_issue(rule: str, level: str, detail: str, line_no: int = 0) -> None:
        if not line_no:
            probe = str(detail).lower().split(",")[0].strip()
            if probe:
                for idx, text in enumerate(lines, 1):
                    if probe in text:
                        line_no = idx
                        break
        findings.append({"rule": rule, "level": level, "detail": detail, "line": line_no})

    lower_source = source.lower()
    try:
        parsed_ast = ast.parse(source)
    except Exception:
        parsed_ast = None

    called_names = set()
    if parsed_ast is not None:
        for node in ast.walk(parsed_ast):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

    has_network = bool(_NETWORK_LIBS_RE.search(lower_source))
    combined_literals = "\n".join(_iter_string_constants(parsed_ast)).lower() if parsed_ast else lower_source
    session_keys = sorted({m.group(1) for m in _SESSION_KEYWORD_RE.finditer(combined_literals)})

    if "getauthkey" in lower_source.replace("_", "") and "getauthkey" not in session_keys:
        session_keys.append("getauthkey")

    if any(k in lower_source for k in ("exd_sandbox", "_exd_sandbox_installed", "_sandbox.json", "addaudithook")):
        record_issue("SANDBOX_TAMPERING", "CRITICAL", "sandbox internals")

    if _BOT_TOKEN_PATTERN.search(source):
        record_issue("EMBEDDED_TELEGRAM_BOT_TOKEN", "CRITICAL", "bot token in code")

    if "api.telegram.org/bot" in lower_source:
        record_issue("C2_TELEGRAM_BOT_API", "CRITICAL", "api.telegram.org/bot")

    for host in _EXFIL_HOSTS:
        if host in lower_source:
            record_issue("UNAUTHORIZED_DATA_EXFILTRATION", "CRITICAL", host)

    public_ips = [m for m in _IP_ENDPOINT_PATTERN.finditer(source) if not _is_private_or_loopback_ip(m.group(1))]
    unrecognized_ips = [m.group(0) for m in public_ips if m.group(1) not in _KNOWN_DNS_IPS]
    if unrecognized_ips:
        record_issue("RAW_IP_C2_ENDPOINT", "CRITICAL" if session_keys else "HIGH", unrecognized_ips[0])
    elif public_ips:
        record_issue("RAW_IP_C2_ENDPOINT", "WARNING", public_ips[0].group(0))

    for host in _LOOKUP_HOSTS:
        if host in lower_source:
            record_issue("EXTERNAL_IP_QUERY_SERVICE", "WARNING", host)

    has_file_read = bool(_FS_READ_RE.search(lower_source))
    has_upload = bool(_SEND_OR_UPLOAD_RE.search(lower_source))

    if session_keys and has_file_read and has_network and has_upload:
        record_issue("TELEGRAM_DATABASE_EXFILTRATION", "CRITICAL", ", ".join(session_keys))
    elif session_keys and has_file_read:
        record_issue("TELEGRAM_INTERNAL_STORAGE_THEFT", "HIGH", ", ".join(session_keys))
    elif session_keys:
        record_issue("TELEGRAM_STORAGE_MENTION", "WARNING", ", ".join(session_keys))

    if "777000" in source and has_network and has_upload:
        record_issue("SERVICE_2FA_CODE_INTERCEPTION", "CRITICAL", "777000")

    if (
        "resetauthorizations" in lower_source
        or "deleteaccount" in lower_source
        or "auth.resetauthorizations" in lower_source
        or "account.deleteaccount" in lower_source
    ):
        record_issue("UNAUTHORIZED_DATA_EXFILTRATION", "CRITICAL", "account destructive call")

    if parsed_ast is not None:
        rem_l, ind_l, loc_l = _detect_dynamic_invocations(parsed_ast, source)
        if rem_l and has_network:
            record_issue("REMOTE_CODE_EXECUTION_STAGER", "CRITICAL", "exec/eval of downloaded code", rem_l[0])
        elif rem_l or ind_l:
            record_issue("DYNAMIC_CODE_EXECUTION", "HIGH", "exec/eval of external data", (rem_l or ind_l)[0])
        elif loc_l:
            record_issue("DYNAMIC_CODE_EXECUTION", "WARNING", "exec/eval", loc_l[0])
    elif called_names & {"exec", "eval"}:
        record_issue("DYNAMIC_CODE_EXECUTION", "WARNING", "exec/eval")

    if "compile" in called_names:
        record_issue("DYNAMIC_CODE_COMPILATION", "WARNING", "compile")

    if _CRYPTO_RE.search(source) or _WALLET_MATCH_RE.search(source):
        reads = bool(_CLIP_READ_RE.search(lower_source))
        writes = bool(_CLIP_WRITE_RE.search(lower_source))
        if reads and writes and _WALLET_MATCH_RE.search(source):
            record_issue("CLIPBOARD_CRYPTO_CLIPPER", "CRITICAL", "clipboard address replacement")
        elif reads and writes:
            record_issue("CLIPBOARD_CRYPTO_CLIPPER", "WARNING", "clipboard with wallet address")

    if "subprocess" in lower_source or "os.system" in lower_source or "popen" in lower_source:
        is_shell = "shell=true" in lower_source.replace(" ", "") or "os.system" in lower_source
        known_binaries = any(k in lower_source for k in ("ffmpeg", "ffprobe", "yt-dlp", "yt_dlp"))
        if known_binaries and not is_shell:
            record_issue("EXTERNAL_PROGRAM_LAUNCH", "WARNING", "ffmpeg")
        elif is_shell or has_network:
            record_issue("PRIVILEGED_COMMAND_EXECUTION", "HIGH", "process execution")
        else:
            record_issue("PRIVILEGED_COMMAND_EXECUTION", "WARNING", "process execution")

    if "ctypes" in lower_source:
        record_issue("CTYPES_NATIVE_ACCESS", "WARNING", "ctypes")

    obf = capabilities.get("obfuscation") or []
    if obf:
        record_issue("OBFUSCATED_CODE_STRUCTURE", "CRITICAL", ", ".join(obf))

    entropy_rating = "NORMAL"
    if parsed_ast is not None:
        max_ent = 0.0
        for literal in _iter_string_constants(parsed_ast):
            if len(literal) >= 200 and " " not in literal[:200]:
                max_ent = max(max_ent, _compute_shannon_entropy(literal))
        if max_ent >= 5.6:
            entropy_rating = "HIGH"
            record_issue("HIGH_ENTROPY_LITERAL_DETECTED", "WARNING", f"{max_ent:.2f}")
        elif max_ent >= 5.0:
            entropy_rating = "ELEVATED"

    return findings, entropy_rating


def _extract_unique_endpoints(source: str) -> List[str]:
    endpoints: List[str] = []
    for match in _WEB_URL_PATTERN.findall(source):
        clean_url = match.rstrip(".,;")
        if clean_url not in endpoints:
            endpoints.append(clean_url)
        if len(endpoints) >= 12:
            break
    return endpoints


_SLICE_KEYWORDS = (
    "requests", "urllib", "socket", "exec", "eval", "compile", "base64", "b64decode",
    "marshal", "subprocess", "os.system", "ctypes", "open(", "send_message", "http",
    "token", "phone", "777000", "clipboard", "tdata", "key_data", "auth",
)


def _extract_context_slice(source: str, max_chars: int = 14000) -> str:
    lines = source.splitlines()
    flagged_indices: Set[int] = set()

    for idx, line in enumerate(lines):
        low = line.lower()
        if any(marker in low for marker in _SLICE_KEYWORDS):
            for neighbor in range(max(0, idx - 4), min(len(lines), idx + 5)):
                flagged_indices.add(neighbor)

    if not flagged_indices:
        return "\n".join(lines)[:max_chars]

    output_lines: List[str] = []
    prev_idx = -2
    accumulated_size = 0

    for idx in sorted(flagged_indices):
        if idx != prev_idx + 1:
            output_lines.append(f"# line {idx + 1}")
        text_line = lines[idx][:300]
        output_lines.append(text_line)
        accumulated_size += len(text_line) + 1
        prev_idx = idx
        if accumulated_size >= max_chars:
            break

    return "\n".join(output_lines)[:max_chars]


def _read_source_content(path: str) -> str:
    if zipfile.is_zipfile(path):
        segments = []
        with zipfile.ZipFile(path) as zf:
            for item in zf.infolist():
                if item.filename.endswith(".py"):
                    with zf.open(item) as stream:
                        segments.append(stream.read(16 * 1024 * 1024).decode("utf-8", "replace"))
        return "\n".join(segments)
    with open(path, "rb") as handle:
        return handle.read(16 * 1024 * 1024).decode("utf-8", "replace")


def scan(path: str) -> Dict[str, Any]:
    source_code = _read_source_content(path)
    try:
        caps = capability_scan.scan(path)
    except Exception:
        caps = {}

    findings_list, entropy_score = _evaluate_security_rules(source_code, caps)
    return {
        "chunks": extract_chunks(source_code, 48),
        "findings": findings_list,
        "entropy": entropy_score,
        "endpoints": _extract_unique_endpoints(source_code),
        "slice": _extract_context_slice(source_code),
    }
