import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

MIN_SPEED = 300 * 1024
SPEED_WINDOW = 8
ATTEMPTS = 40


def token():
    value = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if value:
        return value
    try:
        return subprocess.run(
            ['gh', 'auth', 'token'],
            capture_output=True,
            text=True,
            timeout=10).stdout.strip()
    except Exception:
        return ''


TOKEN = token()


def request(url, api=False):
    headers = {'User-Agent': 'tdesktop-prepare'}
    if api and TOKEN:
        headers['Authorization'] = 'Bearer ' + TOKEN
    if api:
        headers['Accept'] = 'application/vnd.github+json'
    return urllib.request.Request(url, headers=headers)


def download(url):
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request(url), timeout=30) as response:
                data = io.BytesIO()
                window_start = time.time()
                window_bytes = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    data.write(chunk)
                    window_bytes += len(chunk)
                    elapsed = time.time() - window_start
                    if elapsed >= SPEED_WINDOW:
                        if window_bytes / elapsed < MIN_SPEED:
                            raise TimeoutError('slow')
                        window_start = time.time()
                        window_bytes = 0
                print('Downloaded ' + url + ' (' + str(data.tell() // 1024) + ' KB)', flush=True)
                return data.getvalue()
        except Exception as e:
            print('Retry ' + str(attempt + 1) + ' for ' + url + ': ' + str(e), flush=True)
            time.sleep(1)
    raise RuntimeError('Failed to download ' + url)


def api_json(url):
    for attempt in range(10):
        try:
            with urllib.request.urlopen(request(url, True), timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print('API retry ' + str(attempt + 1) + ': ' + str(e), flush=True)
            time.sleep(2)
    raise RuntimeError('API failed ' + url)


def extract(data, target, strip=True):
    os.makedirs(target, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for member in archive.getmembers():
            parts = member.name.split('/')
            if strip:
                parts = parts[1:]
            if not parts or parts == ['']:
                continue
            name = '/'.join(parts)
            if member.issym() or member.islnk():
                continue
            member.name = name
            archive.extract(member, target)


def archive_url(remote, ref):
    github = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(\.git)?/?$', remote)
    if github:
        return 'https://codeload.github.com/' + github.group(1) + '/' + github.group(2) + '/tar.gz/' + ref, True
    gitlab = re.match(r'https?://gitlab\.com/(.+?)(\.git)?/?$', remote)
    if gitlab:
        name = gitlab.group(1).split('/')[-1]
        return 'https://gitlab.com/' + gitlab.group(1) + '/-/archive/' + ref + '/' + name + '-' + ref + '.tar.gz', True
    gitiles = re.match(r'(https?://[^/]+\.googlesource\.com/.+?)(\.git)?/?$', remote)
    if gitiles:
        return gitiles.group(1) + '/+archive/' + ref + '.tar.gz', False
    raise RuntimeError('Unsupported remote ' + remote)


def parse_gitmodules(path):
    result = []
    if not os.path.exists(path):
        return result
    current = {}
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line.startswith('[submodule'):
            if current:
                result.append(current)
            current = {}
        elif '=' in line:
            key, value = [x.strip() for x in line.split('=', 1)]
            current[key] = value
    if current:
        result.append(current)
    return result


def submodule_sha(owner_repo, ref, path):
    data = api_json('https://api.github.com/repos/' + owner_repo + '/contents/' + path + '?ref=' + ref)
    if data.get('type') != 'submodule':
        raise RuntimeError('Not a submodule: ' + path)
    return data['sha']


def fetch(remote, ref, target, only=None, recursive=False):
    if os.path.exists(target):
        shutil.rmtree(target)
    url, strip = archive_url(remote, ref)
    extract(download(url), target, strip)
    github = re.match(r'https?://github\.com/([^/]+/[^/]+?)(\.git)?/?$', remote)
    modules = parse_gitmodules(os.path.join(target, '.gitmodules'))
    if only is not None:
        modules = [m for m in modules if m.get('path') in only]
    elif not recursive:
        modules = []
    for module in modules:
        if not github:
            raise RuntimeError('Submodules need a GitHub parent: ' + remote)
        path = module['path']
        sub_remote = module['url']
        if sub_remote.startswith('../'):
            base = remote.rstrip('/')
            if base.endswith('.git'):
                base = base[:-4]
            sub_remote = base.rsplit('/', 1)[0] + '/' + sub_remote[3:]
        sha = submodule_sha(github.group(1), ref, path)
        print('Submodule ' + path + ' ' + sha, flush=True)
        fetch(sub_remote, sha, os.path.join(target, path), None, recursive and only is None)


def main():
    remote = sys.argv[1]
    if not remote.startswith('http'):
        remote = 'https://github.com/' + remote
    ref = sys.argv[2]
    target = sys.argv[3]
    only = None
    recursive = False
    for arg in sys.argv[4:]:
        if arg == '--recursive':
            recursive = True
        elif arg.startswith('--only='):
            only = arg[len('--only='):].split(',')
    fetch(remote, ref, target, only, recursive)


if __name__ == '__main__':
    main()
