import urllib.request
import json
import os
import re
import sys
from datetime import datetime, timezone

REPO = "nanodevmc/oxDesktop"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(ROOT, "docs")
VERSION_TXT = os.path.join(ROOT, "version.txt")
VERSION_JSON = os.path.join(DOCS_DIR, "version.json")

def get_fallback_version():
    if os.path.exists(VERSION_TXT):
        with open(VERSION_TXT, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    return "7.4.6"

def fetch_latest_release():
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=10"
    headers = {
        "User-Agent": "oxDesktop-Docs-Version-Sync",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Check if local gh_token or env GITHUB_TOKEN is available
    token = os.environ.get("GITHUB_TOKEN", "")
    token_file = r"C:\Users\nanodev\Desktop\gh_token.txt"
    if not token and os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as tf:
                token = tf.read().strip()
        except Exception:
            pass
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
            for r in releases:
                tag = r.get("tag_name", "")
                if tag and tag != "ci-cache" and not r.get("draft", False):
                    version = re.sub(r"^[vV]", "", tag).strip()
                    return {
                        "version": version,
                        "tag_name": tag,
                        "published_at": r.get("published_at", ""),
                        "html_url": r.get("html_url", f"https://github.com/{REPO}/releases/tag/{tag}"),
                        "name": r.get("name", tag),
                    }
    except Exception as e:
        print(f"Warning: Failed to fetch from GitHub API ({e}). Falling back to version.txt.")
    
    fallback = get_fallback_version()
    return {
        "version": fallback,
        "tag_name": f"v{fallback}",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "html_url": f"https://github.com/{REPO}/releases",
        "name": f"oxDesktop v{fallback}",
    }

def update_docs_html(version_info):
    version = version_info["version"]
    tag = version_info["tag_name"]
    release_url = version_info["html_url"]
    
    # Pattern to match the version span in .footer-meta
    # e.g.: <span>oxDesktop v7.4.3.3</span> or <span id="footer-version"...>...</span>
    version_span_html = f'<span id="footer-version" class="footer-version"><a href="{release_url}" target="_blank" rel="noopener noreferrer">oxDesktop v{version}</a></span>'
    
    updated_files = 0
    for root, _, files in os.walk(DOCS_DIR):
        for fname in files:
            if fname.endswith(".html"):
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                # Regex to replace existing version in footer-meta
                new_content = re.sub(
                    r'(<div class="footer-meta">[\s\S]*?)(?:<span(?: id="footer-version")?(?: class="footer-version")?>.*?oxDesktop\s*v[0-9.]+.*?</span>)([\s\S]*?</div>)',
                    rf'\1{version_span_html}\2',
                    content
                )
                
                if new_content != content:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    updated_files += 1
                    print(f"Updated footer in {fname} -> v{version}")

    print(f"Synchronized {updated_files} HTML pages with version v{version}.")

def main():
    print("Fetching latest release info from GitHub API...")
    info = fetch_latest_release()
    info["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(f"Written {VERSION_JSON}: version={info['version']}, tag={info['tag_name']}")
    
    update_docs_html(info)
    print("Docs version sync completed successfully.")

if __name__ == "__main__":
    main()
