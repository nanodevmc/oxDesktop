from __future__ import annotations

from datetime import datetime, timezone
import getpass
import http.client
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile


GERMANY_HINTS = (
    "germany",
    "frankfurt",
    "falkenstein",
    "nuremberg",
    "hetzner",
    "герм",
    "de-",
    "-de",
    "de1",
    "de2",
)


class DeployError(RuntimeError):
    pass


class PteroClient:
    def __init__(self, base_url: str, app_key: str, client_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_key = app_key.strip()
        self.client_key = client_key.strip()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        use_client: bool = False,
        body: dict | None = None,
        timeout: int = 20,
    ) -> dict | list | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        key = self.client_key if use_client else self.app_key
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/vnd.pterodactyl.v1+json",
            "User-Agent": "oxDesktop-Deploy/1.0",
            "Connection": "close",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        raw = self._execute(
            urllib.request.Request(url, data=data, headers=headers, method=method),
            timeout=timeout,
            label=f"{method} {path}",
        )
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def write_raw_file(
        self,
        server_id: str,
        remote_path: str,
        content: bytes,
        *,
        timeout: int = 30,
    ) -> None:
        encoded = urllib.parse.quote(remote_path, safe="/")
        url = f"{self.base_url}/api/client/servers/{server_id}/files/write?file={encoded}"
        headers = {
            "Authorization": f"Bearer {self.client_key}",
            "Accept": "application/json",
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "oxDesktop-Deploy/1.0",
            "Connection": "close",
        }
        self._execute(
            urllib.request.Request(url, data=content, headers=headers, method="POST"),
            timeout=timeout,
            label=f"POST files/write {remote_path}",
        )

    def upload_multipart(
        self,
        signed_url: str,
        filename: str,
        payload: bytes,
        *,
        timeout: int = 15,
    ) -> None:
        boundary = f"----oxDeploy{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            f"Content-Type: application/zip\r\n\r\n"
        ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": "oxDesktop-Deploy/1.0",
        }
        self._execute(
            urllib.request.Request(signed_url, data=body, headers=headers, method="POST"),
            timeout=timeout,
            label="POST signed upload",
        )

    def _execute(
        self,
        req: urllib.request.Request,
        *,
        timeout: int,
        label: str,
    ) -> bytes:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="ignore")[:500]
                if exc.code in (401, 403):
                    raise DeployError(
                        f"Отказ доступа HTTP {exc.code} на {label}. Проверьте ключ и права доступа."
                    ) from exc
                if exc.code == 429 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise DeployError(f"HTTP {exc.code} на {label}: {err_body}") from exc
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionResetError,
                http.client.HTTPException,
                OSError,
            ) as exc:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise DeployError(f"Таймаут/сеть на {label}: {exc}") from exc
        raise DeployError(f"Не удалось выполнить {label}")


def _pick_germany_node(client: PteroClient) -> tuple[dict, str]:
    loc_resp = client.request_json("GET", "/api/application/locations?per_page=100")
    locations = {
        int(item["attributes"]["id"]): item["attributes"]
        for item in (loc_resp or {}).get("data", [])
    }

    node_resp = client.request_json("GET", "/api/application/nodes?per_page=100")
    nodes = [item["attributes"] for item in (node_resp or {}).get("data", [])]
    if not nodes:
        raise DeployError("В панели не найдено ни одной ноды.")

    matched: list[tuple[int, dict, str]] = []
    available_names: list[str] = []
    for node in nodes:
        loc = locations.get(int(node.get("location_id") or 0), {})
        loc_text = f"{loc.get('short', '')} {loc.get('long', '')}".strip()
        haystack = f"{node.get('name', '')} {node.get('fqdn', '')} {node.get('description', '')} {loc_text}".lower()
        available_names.append(f"{node.get('id')}: {node.get('name')} ({loc_text})")
        if node.get("maintenance_mode"):
            continue
        score = sum(1 for hint in GERMANY_HINTS if hint in haystack)
        if loc.get("short", "").strip().lower() == "de":
            score += 5
        if score > 0:
            matched.append((score, node, loc_text))

    if not matched:
        raise DeployError(
            "Нода Германии не найдена. Доступные ноды:\n- " + "\n- ".join(available_names)
        )
    matched.sort(key=lambda item: item[0], reverse=True)
    _, best_node, loc_label = matched[0]
    return best_node, loc_label


def _pick_free_allocation(client: PteroClient, node_id: int) -> int:
    page = 1
    while True:
        resp = client.request_json(
            "GET",
            f"/api/application/nodes/{node_id}/allocations?per_page=100&page={page}",
        )
        data = (resp or {}).get("data", [])
        for item in data:
            attrs = item["attributes"]
            if not attrs.get("assigned"):
                return int(attrs["id"])
        pagination = ((resp or {}).get("meta") or {}).get("pagination") or {}
        if page >= int(pagination.get("total_pages") or 1):
            break
        page += 1
    raise DeployError(f"На ноде {node_id} нет свободных allocation (портов).")


def _score_python_image(image: str) -> tuple[int, str]:
    match = re.search(r"3\.(\d+)", image)
    minor = int(match.group(1)) if match else 0
    return minor, image


def _pick_python_egg(client: PteroClient) -> tuple[int, str, str, dict[str, str]]:
    nests_resp = client.request_json("GET", "/api/application/nests?include=eggs&per_page=100")
    candidates: list[tuple[int, int, int, str]] = []
    for nest_item in (nests_resp or {}).get("data", []):
        nest = nest_item["attributes"]
        nest_id = int(nest["id"])
        eggs = ((nest.get("relationships") or {}).get("eggs") or {}).get("data") or []
        for egg_item in eggs:
            egg = egg_item["attributes"]
            egg_id = int(egg["id"])
            name = str(egg.get("name") or "")
            desc = str(egg.get("description") or "")
            text = f"{name} {desc}".lower()
            if "python" not in text:
                continue
            score = 10
            if name.strip().lower().startswith("python"):
                score += 10
            if "generic" in text or "bot" in text:
                score += 5
            if "django" in text or "redbot" in text:
                score -= 4
            candidates.append((score, nest_id, egg_id, name))

    if not candidates:
        raise DeployError("В панели не найден Egg для Python.")

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, nest_id, egg_id, egg_name = candidates[0]
    detail_resp = client.request_json(
        "GET",
        f"/api/application/nests/{nest_id}/eggs/{egg_id}?include=variables",
    )
    egg_attrs = (detail_resp or {}).get("attributes") or {}

    docker_images = egg_attrs.get("docker_images") or {}
    if isinstance(docker_images, dict) and docker_images:
        chosen_image = max(docker_images.values(), key=_score_python_image)
    else:
        chosen_image = str(egg_attrs.get("docker_image") or "ghcr.io/parkervcp/yolks:python_3.12")

    startup = str(egg_attrs.get("startup") or "python main.py")

    env_map: dict[str, str] = {}
    variables = ((egg_attrs.get("relationships") or {}).get("variables") or {}).get("data") or []
    for var_item in variables:
        var = var_item["attributes"]
        key = str(var["env_variable"])
        default_val = "" if var.get("default_value") is None else str(var.get("default_value"))
        rules = str(var.get("rules") or "").lower()
        upper_key = key.upper()

        if any(tok in upper_key for tok in ("PY_FILE", "MAIN_FILE", "BOT_PY", "APP_PY", "ENTRYPOINT", "STARTUP_FILE")):
            env_map[key] = "main.py"
        elif "REQUIREMENTS" in upper_key:
            env_map[key] = "requirements.txt"
        elif upper_key in {"AUTO_UPDATE", "USER_UPLOAD"}:
            env_map[key] = "0"
        elif default_val:
            env_map[key] = default_val
        elif "required" in rules:
            env_map[key] = "0" if ("boolean" in rules or "numeric" in rules) else ""
        else:
            env_map[key] = default_val

    print(f"Выбран Egg: {egg_name} (ID {egg_id}), Docker: {chosen_image}")
    return egg_id, chosen_image, startup, env_map


def _resolve_owner_id(client: PteroClient) -> tuple[int, str]:
    acct = client.request_json("GET", "/api/client/account", use_client=True)
    attrs = (acct or {}).get("attributes") or {}
    username = str(attrs.get("username") or attrs.get("email") or "owner")
    if attrs.get("id"):
        return int(attrs["id"]), username

    email = str(attrs.get("email") or "")
    users_resp = client.request_json(
        "GET",
        f"/api/application/users?filter[email]={urllib.parse.quote(email)}&per_page=10",
    )
    users = (users_resp or {}).get("data", [])
    if users:
        return int(users[0]["attributes"]["id"]), username
    raise DeployError("Не удалось определить user_id владельца Client API ключа.")


def _find_existing_server(
    client: PteroClient,
    user_id: int,
    server_name: str,
) -> dict | None:
    resp = client.request_json("GET", "/api/application/servers?per_page=100")
    for item in (resp or {}).get("data", []):
        attrs = item["attributes"]
        if int(attrs.get("user") or 0) == user_id and attrs.get("name") == server_name:
            return attrs
    return None


def _compute_disk_mb(node: dict, requested_disk_mb: int) -> int:
    total_disk = int(node.get("disk") or requested_disk_mb)
    over = int(node.get("disk_overallocate") or 0)
    used_disk = int((node.get("allocated_resources") or {}).get("disk") or 0)
    if over < 0:
        return requested_disk_mb
    max_allowed = int(total_disk * (1 + over / 100.0)) - used_disk
    if max_allowed < 1024:
        raise DeployError(f"На ноде {node.get('name')} недостаточно свободного диска ({max_allowed} MB).")
    return min(requested_disk_mb, max_allowed)


def _create_or_get_server(
    client: PteroClient,
    *,
    server_name: str,
    memory_mb: int,
    cpu_pct: int,
    disk_mb: int,
) -> tuple[str, str]:
    user_id, owner_login = _resolve_owner_id(client)
    existing = _find_existing_server(client, user_id, server_name)
    if existing:
        identifier = str(existing["identifier"])
        print(f"Сервер '{server_name}' уже существует ({identifier}), обновляем файлы.")
        return identifier, owner_login

    node, loc_label = _pick_germany_node(client)
    node_id = int(node["id"])
    alloc_id = _pick_free_allocation(client, node_id)
    final_disk = _compute_disk_mb(node, disk_mb)
    egg_id, docker_image, startup, env_map = _pick_python_egg(client)

    payload = {
        "name": server_name,
        "user": user_id,
        "egg": egg_id,
        "docker_image": docker_image,
        "startup": startup,
        "environment": env_map,
        "limits": {
            "memory": memory_mb,
            "swap": 0,
            "disk": final_disk,
            "io": 500,
            "cpu": cpu_pct,
        },
        "feature_limits": {
            "databases": 0,
            "allocations": 1,
            "backups": 1,
        },
        "allocation": {"default": alloc_id},
        "start_on_completion": False,
    }
    created = client.request_json("POST", "/api/application/servers", body=payload)
    attrs = (created or {}).get("attributes") or {}
    identifier = str(attrs["identifier"])
    print(
        f"Создан сервер '{server_name}' ({identifier}) на ноде '{node.get('name')}' ({loc_label}), "
        f"CPU={cpu_pct}%, RAM={memory_mb} MB, Disk={final_disk} MB."
    )
    return identifier, owner_login


def _wait_installed(client: PteroClient, identifier: str) -> None:
    print("Ожидание завершения установки контейнера...")
    for _ in range(45):
        resp = client.request_json(
            "GET",
            f"/api/client/servers/{identifier}",
            use_client=True,
        )
        attrs = (resp or {}).get("attributes") or {}
        if not attrs.get("is_installing") and not attrs.get("is_transferring"):
            return
        time.sleep(3)
    raise DeployError("Превышено время ожидания установки сервера в панели.")


def _collect_deploy_files(repo_root: Path) -> dict[str, bytes]:
    bot_dir = repo_root / "bot"
    if not bot_dir.is_dir():
        raise DeployError(f"Папка bot/ не найдена в {repo_root}")
    if not (bot_dir / ".env").is_file():
        raise DeployError("Файл bot/.env отсутствует — нечего загружать для конфигурации.")

    files: dict[str, bytes] = {}
    root_wrapper = (
        "import asyncio\n"
        "from bot.main import main\n\n"
        'if __name__ == "__main__":\n'
        "    asyncio.run(main())\n"
    ).encode("utf-8")
    files["main.py"] = root_wrapper
    files["requirements.txt"] = (bot_dir / "requirements.txt").read_bytes()

    for extra_name in ("badges.json", "changelog.txt", "version.txt"):
        extra_path = repo_root / extra_name
        if extra_path.is_file():
            files[extra_name] = extra_path.read_bytes()

    allowed_suffixes = {".py", ".txt", ".md", ".example", ""}
    for path in sorted(bot_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(repo_root).as_posix()
        parts = set(path.relative_to(bot_dir).parts)
        if "__pycache__" in parts or "data" in parts:
            continue
        if path.name.endswith((".pyc", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".bak")):
            continue
        if path.name != ".env" and path.suffix.lower() not in allowed_suffixes:
            continue
        files[rel] = path.read_bytes()

    return files


def _upload_via_zip(client: PteroClient, identifier: str, files: dict[str, bytes]) -> None:
    archive_name = "oxdesktop_bot_deploy.zip"
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path, content in files.items():
                zf.writestr(rel_path, content)
        archive_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    signed = client.request_json(
        "GET",
        f"/api/client/servers/{identifier}/files/upload",
        use_client=True,
    )
    upload_url = str(((signed or {}).get("attributes") or {}).get("url") or "")
    if not upload_url:
        raise DeployError("Панель не вернула signed upload URL.")

    client.upload_multipart(upload_url, archive_name, archive_bytes)
    client.request_json(
        "POST",
        f"/api/client/servers/{identifier}/files/decompress",
        use_client=True,
        body={"root": "/", "file": archive_name},
        timeout=45,
    )
    client.request_json(
        "POST",
        f"/api/client/servers/{identifier}/files/delete",
        use_client=True,
        body={"root": "/", "files": [archive_name]},
    )


def _upload_one_by_one(client: PteroClient, identifier: str, files: dict[str, bytes]) -> None:
    created_dirs: set[str] = {""}
    for rel_path in sorted(files):
        parent = Path(rel_path).parent.as_posix()
        if parent == ".":
            parent = ""
        if parent not in created_dirs:
            cur = ""
            for part in parent.split("/"):
                next_dir = f"{cur}/{part}" if cur else part
                if next_dir not in created_dirs:
                    root_arg = f"/{cur}" if cur else "/"
                    try:
                        client.request_json(
                            "POST",
                            f"/api/client/servers/{identifier}/files/create-folder",
                            use_client=True,
                            body={"root": root_arg, "name": part},
                        )
                    except DeployError:
                        pass
                    created_dirs.add(next_dir)
                cur = next_dir
        client.write_raw_file(identifier, f"/{rel_path}", files[rel_path])
        time.sleep(0.3)


def _verify_listing(client: PteroClient, identifier: str, files: dict[str, bytes]) -> None:
    root_resp = client.request_json(
        "GET",
        f"/api/client/servers/{identifier}/files/list?directory=/",
        use_client=True,
    )
    bot_resp = client.request_json(
        "GET",
        f"/api/client/servers/{identifier}/files/list?directory=/bot",
        use_client=True,
    )
    remote_sizes: dict[str, int] = {}
    for item in (root_resp or {}).get("data", []):
        attrs = item["attributes"]
        if attrs.get("is_file"):
            remote_sizes[attrs["name"]] = int(attrs["size"])
    for item in (bot_resp or {}).get("data", []):
        attrs = item["attributes"]
        if attrs.get("is_file"):
            remote_sizes[f"bot/{attrs['name']}"] = int(attrs["size"])

    for key in ("main.py", "requirements.txt", "bot/main.py", "bot/.env"):
        expected = len(files[key])
        actual = remote_sizes.get(key)
        if actual != expected:
            raise DeployError(
                f"Проверка размера провалена для {key}: локально {expected} Б, на сервере {actual}."
            )
    print(f"Листинг проверен: ключевые файлы на месте ({len(files)} файлов залито).")


def _append_build_log(repo_root: Path, host: str, identifier: str, files: dict[str, bytes]) -> None:
    ver_file = repo_root / "version.txt"
    version = ver_file.read_text(encoding="utf-8", errors="ignore").strip() if ver_file.exists() else "bot"
    total_bytes = sum(len(v) for v in files.values())
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log_path = repo_root / "BUILD_LOG.md"
    entry = (
        f"- {date_str} | v{version} | oxDesktop bot ({len(files)} файлов, {total_bytes} Б) "
        f"| {host} (server {identifier}) | ОК\n"
    )
    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    else:
        log_path.write_text("# Журнал сборок и деплоев\n\n" + entry, encoding="utf-8")


    def start_server(self, identifier: str) -> None:
        self.request_json(
            "POST",
            f"/api/client/servers/{identifier}/power",
            use_client=True,
            body={"signal": "start"},
        )

    def get_resources(self, identifier: str) -> dict:
        resp = self.request_json(
            "GET",
            f"/api/client/servers/{identifier}/resources",
            use_client=True,
        )
        return (resp or {}).get("attributes") or {}


def main() -> int:
    host = (os.getenv("DEPLOY_HOST") or "").strip() or input("Host URL (e.g. http://85.190.241.150): ").strip()
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    target_server_id = (os.getenv("DEPLOY_SERVER_ID") or "").strip()
    app_key = (os.getenv("DEPLOY_APP_KEY") or "").strip()
    if not target_server_id and not app_key:
        app_key = getpass.getpass("Application API key (ptla_...): ")
    client_key = (os.getenv("DEPLOY_CLIENT_KEY") or "").strip() or getpass.getpass("Client API key (ptlc_...): ")

    repo_root = Path(os.getenv("DEPLOY_SOURCE_DIR") or Path.cwd()).resolve()
    server_name = (os.getenv("DEPLOY_SERVER_NAME") or "oxdesktop-bot").strip()
    memory_mb = int(os.getenv("DEPLOY_MEMORY_MB", "3072"))
    cpu_pct = int(os.getenv("DEPLOY_CPU_PCT", "100"))
    disk_mb = int(os.getenv("DEPLOY_DISK_MB", "5120"))

    client = PteroClient(host, app_key, client_key)
    files = _collect_deploy_files(repo_root)

    if target_server_id:
        identifier = target_server_id
        print(f"Целевой существующий сервер: {identifier}")
    else:
        identifier, _ = _create_or_get_server(
            client,
            server_name=server_name,
            memory_mb=memory_mb,
            cpu_pct=cpu_pct,
            disk_mb=disk_mb,
        )
    _wait_installed(client, identifier)

    try:
        _upload_via_zip(client, identifier, files)
    except DeployError as exc:
        print(f"ZIP upload недоступен ({exc}), заливаем по одному файлу через Panel API...")
        _upload_one_by_one(client, identifier, files)

    _verify_listing(client, identifier, files)
    client.start_server(identifier)
    _append_build_log(repo_root, host, identifier, files)
    print("Ожидание запуска и установки зависимостей (15 сек)...")
    time.sleep(15)
    res = client.get_resources(identifier)
    print(
        f"Готово! Сервер: {host.rstrip('/')}/server/{identifier} | "
        f"Состояние: {res.get('current_state')} | "
        f"RAM: {round((res.get('resources') or {}).get('memory_bytes', 0) / 1048576, 1)} MB"
    )
    try:
        encoded = urllib.parse.quote("/bot/data/bot.log", safe="/")
        url = f"{client.base_url}/api/client/servers/{identifier}/files/contents?file={encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {client.client_key}",
                "Accept": "text/plain",
                "User-Agent": "oxDesktop-Deploy/1.0",
            },
        )
        raw_log = client._execute(req, timeout=15, label="GET bot.log").decode("utf-8", errors="replace")
        print("--- bot/data/bot.log (tail) ---")
        print("\n".join(raw_log.splitlines()[-25:]))
    except Exception as log_exc:
        print(f"Лог bot/data/bot.log пока недоступен ({log_exc}) — контейнер ещё может ставить pip-пакеты.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeployError as exc:
        print(f"DEPLOY ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
