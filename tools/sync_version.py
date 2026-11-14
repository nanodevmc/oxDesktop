#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/sync_version.py - oxDesktop Single Source of Truth Version Synchronizer.
Reads version.txt and synchronizes:
1. Telegram/build/version
2. Telegram/SourceFiles/version_generated.h
3. Telegram/SourceFiles/core/version.h (fallback macros & constants)
4. Telegram/Resources/winrc/Telegram.rc (FileVersion, ProductVersion, binary FILEVERSION)
5. Telegram/Resources/winrc/Updater.rc (FileVersion, ProductVersion, binary FILEVERSION)
6. Telegram/Resources/uwp/AppX/AppxManifest.xml (Identity Version)
7. flatpak/io.github.nanodevmc.oxDesktop.metainfo.xml (top release version)
"""

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
    build = int(m.group(4) or 0) if m.group(4) else 0

    version_full = major * 1000000 + minor * 1000 + patch
    version_str_major = f"{major}.{minor}"
    version_str = raw_version.strip()
    parts_4 = [str(major), str(minor), str(patch), str(build)]
    version_4_dot = ".".join(parts_4)
    version_4_comma = ",".join(parts_4)

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

        # Update fallback macros
        content = re.sub(
            r'(#define\s+APP_VERSION\s+)"[^"]*"',
            rf'\g<1>"{version_str}"',
            content
        )
        content = re.sub(
            r'(#define\s+APP_VERSION_FULL\s+)\d+',
            rf'\g<1>{version_full}',
            content
        )
        # Update raw literals if present
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
        print(f"[sync_version] Updated fallback macros in {core_version_path}")

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

    # 4. Update Windows Resource Telegram.rc
    telegram_rc_path = os.path.join(root_dir, "Telegram", "Resources", "winrc", "Telegram.rc")
    if os.path.exists(telegram_rc_path):
        with open(telegram_rc_path, "r", encoding="utf-8") as f:
            rc_content = f.read()
        rc_content = re.sub(r"(FILEVERSION\s+)\d+,\d+,\d+,\d+", rf"\g<1>{version_4_comma}", rc_content)
        rc_content = re.sub(r"(PRODUCTVERSION\s+)\d+,\d+,\d+,\d+", rf"\g<1>{version_4_comma}", rc_content)
        rc_content = re.sub(r'("FileVersion",\s*)"[^"]*"', rf'\g<1>"{version_str}"', rc_content)
        rc_content = re.sub(r'("ProductVersion",\s*)"[^"]*"', rf'\g<1>"{version_str}"', rc_content)
        with open(telegram_rc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rc_content)
        print(f"[sync_version] Updated {telegram_rc_path}")

    # 5. Update Windows Resource Updater.rc
    updater_rc_path = os.path.join(root_dir, "Telegram", "Resources", "winrc", "Updater.rc")
    if os.path.exists(updater_rc_path):
        with open(updater_rc_path, "r", encoding="utf-8") as f:
            rc_content = f.read()
        rc_content = re.sub(r"(FILEVERSION\s+)\d+,\d+,\d+,\d+", rf"\g<1>{version_4_comma}", rc_content)
        rc_content = re.sub(r"(PRODUCTVERSION\s+)\d+,\d+,\d+,\d+", rf"\g<1>{version_4_comma}", rc_content)
        rc_content = re.sub(r'("FileVersion",\s*)"[^"]*"', rf'\g<1>"{version_str}"', rc_content)
        rc_content = re.sub(r'("ProductVersion",\s*)"[^"]*"', rf'\g<1>"{version_str}"', rc_content)
        with open(updater_rc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rc_content)
        print(f"[sync_version] Updated {updater_rc_path}")

    # 6. Update UWP AppxManifest.xml
    appx_path = os.path.join(root_dir, "Telegram", "Resources", "uwp", "AppX", "AppxManifest.xml")
    if os.path.exists(appx_path):
        with open(appx_path, "r", encoding="utf-8") as f:
            appx_content = f.read()
        appx_content = re.sub(r'( Version=)"[^"]*"', rf'\g<1>"{version_4_dot}"', appx_content)
        with open(appx_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(appx_content)
        print(f"[sync_version] Updated {appx_path}")

    # 7. Update Flatpak AppStream metainfo
    flatpak_path = os.path.join(root_dir, "flatpak", "io.github.nanodevmc.oxDesktop.metainfo.xml")
    if os.path.exists(flatpak_path):
        with open(flatpak_path, "r", encoding="utf-8") as f:
            meta_content = f.read()
        meta_content = re.sub(
            r'(<release\s+version=)"[^"]*"(\s+date="[^"]*">)',
            rf'\g<1>"{version_str}"\g<2>',
            meta_content,
            count=1
        )
        meta_content = re.sub(
            r'<p>oxDesktop v\d+[\d\.]*\s+(?:major\s+)?release:</p>',
            rf'<p>oxDesktop v{version_str} release:</p>',
            meta_content,
            count=1
        )
        with open(flatpak_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(meta_content)
        print(f"[sync_version] Updated {flatpak_path}")

    print(f"[sync_version] Version successfully synchronized to {version_str} (full={version_full}, 4part={version_4_dot})")


if __name__ == "__main__":
    main()
