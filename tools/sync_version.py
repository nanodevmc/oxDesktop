#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import sys

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, ".."))
    version_txt_path = os.path.join(root_dir, "version.txt")

    if not os.path.exists(version_txt_path):
        print(f"[sync_version] ERROR: {version_txt_path} not found")
        sys.exit(1)

    with open(version_txt_path, "r", encoding="utf-8") as f:
        raw_version = f.read().strip()

    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?", raw_version)
    if not m:
        print(f"[sync_version] ERROR: invalid version format in version.txt: '{raw_version}'")
        sys.exit(1)

    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    build = int(m.group(4) or 0) if m.group(4) else None

    version_full = major * 1000000 + minor * 1000 + patch
    version_str_major = f"{major}.{minor}"
    version_str = raw_version.strip()

    # 1. Update Telegram/build/version
    build_version_path = os.path.join(root_dir, "Telegram", "build", "version")
    build_version_content = (
        f"AppVersion         {version_full}\n"
        f"AppVersionStrMajor {version_str_major}\n"
        f"AppVersionStrSmall {version_str}\n"
        f"AppVersionStr      {version_str}\n"
        f"BetaChannel        0\n"
        f"AlphaVersion       0\n"
        f"AppVersionOriginal {version_str}\n"
    )
    os.makedirs(os.path.dirname(build_version_path), exist_ok=True)
    with open(build_version_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_version_content)
    print(f"[sync_version] Updated {build_version_path}")

    # 2. Update Telegram/SourceFiles/core/version.h
    core_version_path = os.path.join(root_dir, "Telegram", "SourceFiles", "core", "version.h")
    if os.path.exists(core_version_path):
        with open(core_version_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Update if raw literals are present
        if "APP_VERSION_FULL" not in content:
            content = re.sub(
                r"(constexpr\s+auto\s+AppVersion\s*=\s*)\d+;",
                rf"\g<1>{version_full};",
                content
            )
            content = re.sub(
                r'(constexpr\s+auto\s+AppVersionStr\s*=\s*)"[^"]*";',
                rf'\g<1>"{version_str}";',
                content
            )
            with open(core_version_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"[sync_version] Updated {core_version_path}")
        else:
            print(f"[sync_version] {core_version_path} dynamically uses version_generated.h macros")

    # 3. Generate Telegram/SourceFiles/version_generated.h
    gen_header_path = os.path.join(root_dir, "Telegram", "SourceFiles", "version_generated.h")
    gen_content = (
        "#pragma once\n"
        f'#define APP_VERSION "{version_str}"\n'
        f'#define APP_VERSION_FULL {version_full}\n'
    )
    with open(gen_header_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(gen_content)
    print(f"[sync_version] Generated {gen_header_path}")

    print(f"[sync_version] Version successfully synchronized to {version_str} (full={version_full})")

if __name__ == "__main__":
    main()
