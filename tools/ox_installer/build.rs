use std::env;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use zip::write::SimpleFileOptions;
use zip::ZipWriter;

fn main() {
    println!("cargo:rerun-if-changed=payload");
    println!("cargo:rerun-if-changed=assets");
    println!("cargo:rerun-if-changed=../../version.txt");

    let version = fs::read_to_string("../../version.txt")
        .unwrap_or_else(|_| "7.4.4".to_string())
        .trim()
        .to_string();
    println!("cargo:rustc-env=OX_VERSION={}", version);

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let zip_path = out_dir.join("payload.zip");

    let file = File::create(&zip_path).expect("Failed to create payload.zip");
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Zstd)
        .compression_level(Some(22))
        .unix_permissions(0o755);

    let payload_dir = Path::new("payload");
    if payload_dir.exists() {
        add_dir_to_zip(&mut zip, payload_dir, payload_dir, options);
    }
    zip.finish().expect("Failed to finalize payload.zip");

    #[cfg(windows)]
    {
        let mut res = winres::WindowsResource::new();
        res.set_icon("assets/icon.ico");
        res.set("ProductName", "oxDesktop");
        res.set("FileDescription", "oxDesktop Installer");
        res.set("ProductVersion", &version);
        res.set("FileVersion", &version);
        res.set("LegalCopyright", "Copyright (C) 2026 oxDesktop");
        let _ = res.compile();
    }
}

fn add_dir_to_zip<W: Write + std::io::Seek>(
    zip: &mut ZipWriter<W>,
    base_dir: &Path,
    current_dir: &Path,
    options: SimpleFileOptions,
) {
    if let Ok(entries) = fs::read_dir(current_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            let relative = path
                .strip_prefix(base_dir)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");

            if path.is_dir() {
                let _ = zip.add_directory(format!("{}/", relative), options);
                add_dir_to_zip(zip, base_dir, &path, options);
            } else if path.is_file() {
                if let Ok(mut f) = File::open(&path) {
                    let mut buffer = Vec::new();
                    if f.read_to_end(&mut buffer).is_ok() {
                        let _ = zip.start_file(relative, options);
                        let _ = zip.write_all(&buffer);
                    }
                }
            }
        }
    }
}
