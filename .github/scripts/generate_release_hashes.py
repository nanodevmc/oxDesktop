#!/usr/bin/env python3
import sys
import os
import glob
import json
import hashlib

def main():
    if len(sys.argv) < 3:
        print("Usage: generate_release_hashes.py <assets_dir> <version>")
        sys.exit(1)

    assets_dir = sys.argv[1]
    version = sys.argv[2]
    
    files_hashes = {}
    lines = []

    for path in sorted(glob.glob(os.path.join(assets_dir, "*"))):
        if not os.path.isfile(path):
            continue
        filename = os.path.basename(path)
        if filename.startswith("release_hashes"):
            continue
        with open(path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        files_hashes[filename] = h
        lines.append(f"{h}  {filename}")

    data = {
        "version": version,
        "hashes": files_hashes
    }

    json_path = os.path.join(assets_dir, "release_hashes.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    txt_path = os.path.join(assets_dir, "release_hashes.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Generated {json_path} and {txt_path} with {len(files_hashes)} entries.")

if __name__ == "__main__":
    main()
