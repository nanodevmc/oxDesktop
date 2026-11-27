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

    println!("cargo:rerun-if-changed=locales");
    generate_locales(&out_dir);

    let zip_path = out_dir.join("payload.zip");

    let file = File::create(&zip_path).expect("Failed to create payload.zip");
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Zstd)
        .compression_level(Some(19))
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

fn extract_json_val(content: &str, key: &str) -> String {
    let pattern = format!("\"{}\":", key);
    if let Some(pos) = content.find(&pattern) {
        let rest = &content[pos + pattern.len()..];
        if let Some(start_quote) = rest.find('"') {
            let val_rest = &rest[start_quote + 1..];
            let mut result = String::new();
            let mut chars = val_rest.chars();
            while let Some(c) = chars.next() {
                if c == '\\' {
                    if let Some(next) = chars.next() {
                        if next == 'n' {
                            result.push('\n');
                        } else if next == '"' {
                            result.push('"');
                        } else if next == '\\' {
                            result.push('\\');
                        } else {
                            result.push(next);
                        }
                    }
                } else if c == '"' {
                    break;
                } else {
                    result.push(c);
                }
            }
            return result;
        }
    }
    String::new()
}

fn generate_locales(out_dir: &Path) {
    let locales_dir = Path::new("locales");
    let mut locales = Vec::new();

    if locales_dir.exists() {
        if let Ok(entries) = fs::read_dir(locales_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Ok(content) = fs::read_to_string(&path) {
                        locales.push((
                            extract_json_val(&content, "code"),
                            extract_json_val(&content, "name"),
                            extract_json_val(&content, "tag"),
                            extract_json_val(&content, "slogan"),
                            extract_json_val(&content, "folder"),
                            extract_json_val(&content, "browse"),
                            extract_json_val(&content, "current"),
                            extract_json_val(&content, "new_version"),
                            extract_json_val(&content, "installed"),
                            extract_json_val(&content, "downgrade"),
                            extract_json_val(&content, "cancel"),
                            extract_json_val(&content, "install"),
                            extract_json_val(&content, "title_installing"),
                            extract_json_val(&content, "unpacking"),
                            extract_json_val(&content, "title_finished"),
                            extract_json_val(&content, "installed_sub"),
                            extract_json_val(&content, "launch_now"),
                            extract_json_val(&content, "finish"),
                            extract_json_val(&content, "downgrade_title"),
                            extract_json_val(&content, "downgrade_msg"),
                        ));
                    }
                }
            }
        }
    }

    locales.sort_by(|a, b| {
        let order = |code: &str| match code {
            "ru" => 0,
            "en" => 1,
            "es" => 2,
            "uk" => 3,
            "be" => 4,
            _ => 10,
        };
        order(&a.0).cmp(&order(&b.0))
    });

    let mut code = String::new();
    code.push_str("#[derive(Clone, Copy, Debug)]\n");
    code.push_str("pub struct LocaleStrings {\n");
    code.push_str("    pub code: &'static str,\n");
    code.push_str("    pub name: &'static str,\n");
    code.push_str("    pub tag: &'static str,\n");
    code.push_str("    pub slogan: &'static str,\n");
    code.push_str("    pub folder: &'static str,\n");
    code.push_str("    pub browse: &'static str,\n");
    code.push_str("    pub current: &'static str,\n");
    code.push_str("    pub new_version: &'static str,\n");
    code.push_str("    pub installed: &'static str,\n");
    code.push_str("    pub downgrade: &'static str,\n");
    code.push_str("    pub cancel: &'static str,\n");
    code.push_str("    pub install: &'static str,\n");
    code.push_str("    pub title_installing: &'static str,\n");
    code.push_str("    pub unpacking: &'static str,\n");
    code.push_str("    pub title_finished: &'static str,\n");
    code.push_str("    pub installed_sub: &'static str,\n");
    code.push_str("    pub launch_now: &'static str,\n");
    code.push_str("    pub finish: &'static str,\n");
    code.push_str("    pub downgrade_title: &'static str,\n");
    code.push_str("    pub downgrade_msg: &'static str,\n");
    code.push_str("}\n\n");

    code.push_str("pub static AVAILABLE_LOCALES: &[LocaleStrings] = &[\n");
    for loc in &locales {
        code.push_str("    LocaleStrings {\n");
        code.push_str(&format!("        code: {:?},\n", loc.0));
        code.push_str(&format!("        name: {:?},\n", loc.1));
        code.push_str(&format!("        tag: {:?},\n", loc.2));
        code.push_str(&format!("        slogan: {:?},\n", loc.3));
        code.push_str(&format!("        folder: {:?},\n", loc.4));
        code.push_str(&format!("        browse: {:?},\n", loc.5));
        code.push_str(&format!("        current: {:?},\n", loc.6));
        code.push_str(&format!("        new_version: {:?},\n", loc.7));
        code.push_str(&format!("        installed: {:?},\n", loc.8));
        code.push_str(&format!("        downgrade: {:?},\n", loc.9));
        code.push_str(&format!("        cancel: {:?},\n", loc.10));
        code.push_str(&format!("        install: {:?},\n", loc.11));
        code.push_str(&format!("        title_installing: {:?},\n", loc.12));
        code.push_str(&format!("        unpacking: {:?},\n", loc.13));
        code.push_str(&format!("        title_finished: {:?},\n", loc.14));
        code.push_str(&format!("        installed_sub: {:?},\n", loc.15));
        code.push_str(&format!("        launch_now: {:?},\n", loc.16));
        code.push_str(&format!("        finish: {:?},\n", loc.17));
        code.push_str(&format!("        downgrade_title: {:?},\n", loc.18));
        code.push_str(&format!("        downgrade_msg: {:?},\n", loc.19));
        code.push_str("    },\n");
    }
    code.push_str("];\n");

    fs::write(out_dir.join("locales_gen.rs"), code).expect("Failed to write locales_gen.rs");
}
