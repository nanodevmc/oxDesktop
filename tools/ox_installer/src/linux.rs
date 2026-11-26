use std::fs::{self, File};
use std::io::{Cursor, Write};
use std::path::{Path, PathBuf};
use zip::ZipArchive;

use crate::version::is_downgrade_or_prerelease;

static PAYLOAD_ZIP: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/payload.zip"));
static ICON_PNG: &[u8] = include_bytes!("../assets/delta_avatar.png");

pub const INSTALLER_VERSION: &str = env!("OX_VERSION");

pub fn run_linux_installer() {
    let args: Vec<String> = std::env::args().collect();
    let silent = args.iter().any(|a| a == "-y" || a == "--silent" || a == "-s");

    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let default_dir = PathBuf::from(&home).join(".local/share/oxDesktop");

    let is_gui = std::env::var("DISPLAY").is_ok() || std::env::var("WAYLAND_DISPLAY").is_ok();
    let has_zenity = which("zenity");

    if is_gui && has_zenity && !silent {
        run_zenity_flow(&default_dir, &home);
    } else {
        run_terminal_flow(&default_dir, &home, silent);
    }
}

fn which(cmd: &str) -> bool {
    if let Ok(path) = std::env::var("PATH") {
        for p in path.split(':') {
            if Path::new(p).join(cmd).is_file() {
                return true;
            }
        }
    }
    false
}

fn detect_installed_version(target_dir: &Path) -> Option<String> {
    if let Ok(output) = std::process::Command::new("oxdesktop").arg("--version").output() {
        if output.status.success() {
            let s = String::from_utf8_lossy(&output.stdout);
            if let Some(line) = s.lines().next() {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
        }
    }

    let changelog = target_dir.join("changelog.txt");
    if let Ok(content) = fs::read_to_string(&changelog) {
        if let Some(line) = content.lines().next() {
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
    }

    let version_file = target_dir.join("version.txt");
    if let Ok(content) = fs::read_to_string(&version_file) {
        let trimmed = content.trim();
        if !trimmed.is_empty() {
            return Some(trimmed.to_string());
        }
    }

    None
}

fn run_terminal_flow(target_dir: &Path, home: &str, silent: bool) {
    let header = format!("oxDesktop v{}", INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION));
    println!("\x1b[38;2;245;92;37m");
    println!("╭────────────────────────────────────────────────────────╮");
    println!("│{:^56}│", header);
    println!("│     Быстрый и безопасный клиент Telegram Desktop       │");
    println!("╰────────────────────────────────────────────────────────╯\x1b[0m");
    println!("  • Канал: https://t.me/oxDesktop");
    println!("  • GitHub: https://github.com/nanodevmc/oxDesktop\n");

    println!("Каталог установки: \x1b[1m{}\x1b[0m", target_dir.display());

    let installed_ver = detect_installed_version(target_dir);
    if let Some(ref cur) = installed_ver {
        if is_downgrade_or_prerelease(cur, INSTALLER_VERSION) && !silent {
            let cur_clean = cur.strip_prefix('v').unwrap_or(cur);
            let target_clean = INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION);
            println!("\x1b[33mВнимание:\x1b[0m Обнаружена более новая или предварительная (бета/dev) версия oxDesktop ({}).", cur_clean);
            print!("Вы действительно хотите установить более раннюю версию ({})? [Y/N Д/Н]: ", target_clean);
            let _ = std::io::stdout().flush();
            let mut input = String::new();
            let _ = std::io::stdin().read_line(&mut input);
            let trimmed = input.trim().to_lowercase();
            if trimmed != "y" && trimmed != "yes" && trimmed != "д" && trimmed != "да" {
                println!("Установка отменена пользователем.");
                return;
            }
        }
    }

    if !silent {
        print!("Начать установку? [Y/n]: ");
        let _ = std::io::stdout().flush();
        let mut input = String::new();
        let _ = std::io::stdin().read_line(&mut input);
        let trimmed = input.trim().to_lowercase();
        if !trimmed.is_empty() && trimmed != "y" && trimmed != "yes" && trimmed != "д" {
            println!("Установка отменена.");
            return;
        }
    }

    println!("\n\x1b[38;2;245;92;37m[1/3]\x1b[0m Распаковка файлов...");
    if let Err(e) = extract_payload(target_dir) {
        eprintln!("\x1b[31mОшибка распаковки: {}\x1b[0m", e);
        return;
    }

    println!("\x1b[38;2;245;92;37m[2/3]\x1b[0m Интеграция с системой (XDG .desktop и иконки)...");
    install_desktop_integration(target_dir, home);

    println!("\x1b[38;2;245;92;37m[3/3]\x1b[0m Завершение...");
    println!("\n\x1b[38;2;245;92;37m✔ oxDesktop успешно установлен в {}\x1b[0m", target_dir.display());
    println!("Вы можете запустить клиент из меню приложений или командой:");
    println!("  {}/oxDesktop\n", target_dir.display());
}

fn run_zenity_flow(target_dir: &Path, home: &str) {
    let installed_ver = detect_installed_version(target_dir);
    if let Some(ref cur) = installed_ver {
        if is_downgrade_or_prerelease(cur, INSTALLER_VERSION) {
            let warn_text = format!(
                "Обнаружена более новая или предварительная (бета/dev) версия oxDesktop ({}).\n\nВы действительно хотите установить более раннюю версию (v{})?",
                cur.strip_prefix('v').unwrap_or(cur),
                INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION)
            );
            let warn_status = std::process::Command::new("zenity")
                .arg("--question")
                .arg("--title=Предупреждение о версии oxDesktop")
                .arg(format!("--text={}", warn_text))
                .arg("--ok-label=Продолжить")
                .arg("--cancel-label=Отмена")
                .arg("--width=440")
                .status();

            if let Ok(st) = warn_status {
                if !st.success() {
                    return;
                }
            } else {
                return;
            }
        }
    }

    let question = format!(
        "Установить oxDesktop v{} в:\n{}\n\nКанал: t.me/oxDesktop",
        INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION),
        target_dir.display()
    );

    let status = std::process::Command::new("zenity")
        .arg("--question")
        .arg("--title=Установка oxDesktop")
        .arg(format!("--text={}", question))
        .arg("--ok-label=Установить")
        .arg("--cancel-label=Отмена")
        .arg("--width=420")
        .status();

    if let Ok(st) = status {
        if !st.success() {
            return;
        }
    }

    if let Err(e) = extract_payload(target_dir) {
        let _ = std::process::Command::new("zenity")
            .arg("--error")
            .arg(format!("--text=Ошибка распаковки: {}", e))
            .status();
        return;
    }

    install_desktop_integration(target_dir, home);

    let _ = std::process::Command::new("zenity")
        .arg("--info")
        .arg("--title=Готово")
        .arg("--text=oxDesktop успешно установлен и доступен в меню приложений!")
        .status();
}

fn extract_payload(dest_dir: &Path) -> Result<(), String> {
    if PAYLOAD_ZIP.is_empty() {
        return Err("Payload ZIP пуст".to_string());
    }

    fs::create_dir_all(dest_dir).map_err(|e| e.to_string())?;

    let cursor = Cursor::new(PAYLOAD_ZIP);
    let mut archive = ZipArchive::new(cursor).map_err(|e| e.to_string())?;

    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| e.to_string())?;
        let enclosed = file
            .enclosed_name()
            .ok_or_else(|| "Неверное имя файла".to_string())?
            .to_owned();
        let out_path = dest_dir.join(enclosed);

        if file.is_dir() {
            let _ = fs::create_dir_all(&out_path);
        } else {
            if let Some(parent) = out_path.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let mut outfile = File::create(&out_path).map_err(|e| e.to_string())?;
            std::io::copy(&mut file, &mut outfile).map_err(|e| e.to_string())?;

            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let is_exec = out_path
                    .file_name()
                    .map(|n| {
                        let name = n.to_string_lossy().to_lowercase();
                        name == "oxdesktop" || name == "oxdesktop-bin" || name.ends_with(".sh")
                    })
                    .unwrap_or(false);

                if is_exec {
                    let _ = fs::set_permissions(&out_path, fs::Permissions::from_mode(0o755));
                }
            }
        }
    }

    Ok(())
}

fn install_desktop_integration(install_dir: &Path, home: &str) {
    let binary_path = install_dir.join("oxDesktop");

    let icons_dir = PathBuf::from(home).join(".local/share/icons/hicolor/256x256/apps");
    let pixmaps_dir = PathBuf::from(home).join(".local/share/pixmaps");
    let apps_dir = PathBuf::from(home).join(".local/share/applications");
    let desktop_dir = PathBuf::from(home).join("Desktop");

    let _ = fs::create_dir_all(&icons_dir);
    let _ = fs::create_dir_all(&pixmaps_dir);
    let _ = fs::create_dir_all(&apps_dir);

    let icon_dest1 = icons_dir.join("oxDesktop.png");
    let icon_dest2 = pixmaps_dir.join("oxDesktop.png");
    let _ = fs::write(&icon_dest1, ICON_PNG);
    let _ = fs::write(&icon_dest2, ICON_PNG);

    let desktop_content = format!(
        "[Desktop Entry]\n\
        Version=1.0\n\
        Name=oxDesktop\n\
        Comment=Fast and Secure Telegram Client\n\
        Exec=\"{}\" -- %u\n\
        Icon=oxDesktop\n\
        Terminal=false\n\
        Type=Application\n\
        Categories=Network;InstantMessaging;Chat;\n\
        MimeType=x-scheme-handler/tg;\n\
        Keywords=tg;telegram;chat;oxdesktop;\n",
        binary_path.display()
    );

    let app_desktop = apps_dir.join("oxDesktop.desktop");
    let _ = fs::write(&app_desktop, &desktop_content);

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&app_desktop, fs::Permissions::from_mode(0o755));

        if desktop_dir.is_dir() {
            let desktop_shortcut = desktop_dir.join("oxDesktop.desktop");
            let _ = fs::write(&desktop_shortcut, &desktop_content);
            let _ = fs::set_permissions(&desktop_shortcut, fs::Permissions::from_mode(0o755));
        }
    }

    let _ = std::process::Command::new("update-desktop-database")
        .arg(&apps_dir)
        .status();
}
