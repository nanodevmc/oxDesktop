from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request


RAPID_WIN_URL = (
    "https://github.com/RapidAI/RapidOcrOnnx/releases/download/"
    "1.2.3/windows-bin-vs2022-mt.7z"
)
RAPID_LINUX_URL = (
    "https://github.com/RapidAI/RapidOcrOnnx/releases/download/"
    "1.2.2/linux-bin.7z"
)

MODELS = {
    "det.onnx": (
        "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/"
        "detection/v3/det.onnx"
    ),
    "cls.onnx": (
        "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/"
        "preprocessing/textline-orientation/PP-LCNet_x1_0_textline_ori.onnx"
    ),
    "cyr_rec.onnx": (
        "https://huggingface.co/PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec_onnx/"
        "resolve/main/inference.onnx"
    ),
    "cyr_rec.yml": (
        "https://huggingface.co/PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec_onnx/"
        "resolve/main/inference.yml"
    ),
    "latin_rec.onnx": (
        "https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec_onnx/"
        "resolve/main/inference.onnx"
    ),
    "latin_rec.yml": (
        "https://huggingface.co/PaddlePaddle/latin_PP-OCRv5_mobile_rec_onnx/"
        "resolve/main/inference.yml"
    ),
}


def download_file(url: str, dst: pathlib.Path) -> None:
    if dst.exists() and dst.stat().st_size > 0:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    print(f"[prepare_ocr] Downloading {dst.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "oxDesktop-OCR-Fetch/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
    os.replace(tmp, dst)


def extract_keys_from_yml(yml_path: pathlib.Path, out_keys: pathlib.Path) -> int:
    text = yml_path.read_text(encoding="utf-8")
    chars: list[str] = []
    in_dict = False
    for line in text.splitlines():
        if line.strip() == "character_dict:":
            in_dict = True
            continue
        if in_dict:
            if not line.startswith("  - "):
                break
            val = line[4:]
            if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
                val = val[1:-1].replace("''", "'")
            elif len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            chars.append(val)
    if not chars:
        raise RuntimeError(f"Empty character_dict in {yml_path}")
    out_keys.write_text("\n".join(chars) + "\n", encoding="utf-8", newline="\n")
    return len(chars)


def find_7z() -> str:
    for candidate in ("7z", "7za", "7zz", r"C:\Program Files\7-Zip\7z.exe"):
        found = shutil.which(candidate)
        if found:
            return found
        if pathlib.Path(candidate).exists():
            return candidate
    raise RuntimeError("7z archive extractor not found")


def install_rapid_binary(platform_name: str, out_dir: pathlib.Path) -> pathlib.Path:
    if platform_name == "win64":
        target = out_dir / "RapidOcrOnnx.exe"
        archive_url = RAPID_WIN_URL
        rel_member = "windows-bin-vs2022-mt/win-BIN-CPU-x64/RapidOcrOnnx.exe"
    elif platform_name == "linux64":
        target = out_dir / "RapidOcrOnnx"
        archive_url = RAPID_LINUX_URL
        rel_member = "linux-bin/Linux-BIN-CPU/RapidOcrOnnx"
    else:
        raise ValueError(f"Unsupported platform: {platform_name}")

    if target.exists() and target.stat().st_size > 1_000_000:
        return target

    seven_z = find_7z()
    with tempfile.TemporaryDirectory(prefix="ox_ocr_") as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        archive = tmp_path / "rapid.7z"
        download_file(archive_url, archive)
        ext = tmp_path / "ext"
        ext.mkdir()
        res = subprocess.run(
            [seven_z, "x", "-y", f"-o{ext}", str(archive)],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"7z extract failed: {res.stderr or res.stdout}")
        src = ext / rel_member
        if not src.exists():
            raise RuntimeError(f"Missing binary after extraction: {src}")
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    if platform_name == "linux64":
        os.chmod(target, 0o755)
    return target


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare bundled offline PP-OCRv5 runtime")
    parser.add_argument("--platform", choices=("win64", "linux64"), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out).resolve()
    models_dir = out_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    binary = install_rapid_binary(args.platform, out_dir)
    print(f"[prepare_ocr] Binary ready: {binary} ({binary.stat().st_size} bytes)")

    for fname, url in MODELS.items():
        download_file(url, models_dir / fname)

    cyr_count = extract_keys_from_yml(models_dir / "cyr_rec.yml", models_dir / "cyr_keys.txt")
    lat_count = extract_keys_from_yml(models_dir / "latin_rec.yml", models_dir / "latin_keys.txt")
    (models_dir / "cyr_rec.yml").unlink(missing_ok=True)
    (models_dir / "latin_rec.yml").unlink(missing_ok=True)

    required = [
        "det.onnx",
        "cls.onnx",
        "cyr_rec.onnx",
        "cyr_keys.txt",
        "latin_rec.onnx",
        "latin_keys.txt",
    ]
    manifest = {
        "schema": 1,
        "platform": args.platform,
        "binary": binary.name,
        "cyr_keys_count": cyr_count,
        "latin_keys_count": lat_count,
        "files": {},
    }
    for name in required:
        fp = models_dir / name
        if not fp.exists() or fp.stat().st_size == 0:
            raise RuntimeError(f"Missing required OCR asset: {fp}")
        manifest["files"][name] = {
            "size": fp.stat().st_size,
            "sha256": sha256_file(fp),
        }

    (out_dir / "ocr_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(f"[prepare_ocr] OCR runtime ready at {out_dir} (cyr={cyr_count}, latin={lat_count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
