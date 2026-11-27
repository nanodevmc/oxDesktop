use std::ffi::{OsStr};
use std::fs;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use windows_sys::Win32::UI::WindowsAndMessaging::*;

fn to_wide_null(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

pub fn run_uninstaller(args: &[String]) {
    let is_silent = args.iter().any(|a| {
        let l = a.to_lowercase();
        l == "/silent" || l == "/verysilent" || l == "--silent" || l == "-s" || l == "/s"
    });

    // 1. Determine installation directory
    let current_exe = std::env::current_exe().ok();
    let current_dir = current_exe
        .as_ref()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()));

    let install_dir = if let Some(dir) = current_dir
        .as_ref()
        .filter(|d| d.join("oxDesktop.exe").exists() || d.join("changelog.txt").exists() || d.join("install_manifest.txt").exists())
    {
        dir.clone()
    } else if let Some(reg_dir) = crate::registry::get_install_location() {
        PathBuf::from(reg_dir)
    } else if let Ok(app_data) = std::env::var("APPDATA") {
        PathBuf::from(app_data).join("oxDesktop")
    } else {
        PathBuf::from("C:\\oxDesktop")
    };

    // 2. User confirmation
    if !is_silent {
        let title = to_wide_null("Удаление oxDesktop");
        let msg = to_wide_null(&format!(
            "Вы действительно хотите удалить oxDesktop и все его компоненты?\n\nПапка установки:\n{}",
            install_dir.display()
        ));
        unsafe {
            let res = MessageBoxW(
                std::ptr::null_mut(),
                msg.as_ptr(),
                title.as_ptr(),
                MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2,
            );
            if res != IDYES {
                return;
            }
        }
    }

    // 3. User data (tdata) confirmation
    let tdata_dir = install_dir.join("tdata");
    let delete_user_data = if !is_silent && tdata_dir.exists() {
        let title = to_wide_null("Удаление oxDesktop");
        let msg = to_wide_null(
            "Удалить также данные сессий и историю сообщений (папку tdata)?\n\nНажмите «Да» для полной очистки,\nили «Нет», чтобы сохранить авторизацию в Telegram."
        );
        unsafe {
            let res = MessageBoxW(
                std::ptr::null_mut(),
                msg.as_ptr(),
                title.as_ptr(),
                MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2,
            );
            res == IDYES
        }
    } else {
        false
    };

    // 4. Terminate running oxDesktop processes
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    let _ = Command::new("taskkill")
        .args(&["/F", "/IM", "oxDesktop.exe", "/IM", "oxWsProxy.exe", "/IM", "RapidOcrOnnx.exe"])
        .creation_flags(CREATE_NO_WINDOW)
        .output();

    std::thread::sleep(std::time::Duration::from_millis(400));

    // 5. Remove shortcuts
    if let Ok(user_profile) = std::env::var("USERPROFILE") {
        let desktop_lnk = Path::new(&user_profile).join("Desktop").join("oxDesktop.lnk");
        let _ = fs::remove_file(desktop_lnk);
    }
    if let Ok(app_data) = std::env::var("APPDATA") {
        let start_menu_ox = Path::new(&app_data)
            .join("Microsoft")
            .join("Windows")
            .join("Start Menu")
            .join("Programs")
            .join("oxDesktop");
        let _ = fs::remove_dir_all(&start_menu_ox);
    }

    // 6. Clean registry
    crate::registry::unregister_uninstall();

    // 7. Delete installed files from manifest
    let manifest_path = install_dir.join("install_manifest.txt");
    if let Ok(content) = fs::read_to_string(&manifest_path) {
        for line in content.lines() {
            let rel = line.trim();
            if !rel.is_empty() {
                let target = install_dir.join(rel);
                if target != current_exe.as_deref().unwrap_or(Path::new("")) {
                    let _ = fs::remove_file(&target);
                }
            }
        }
        let _ = fs::remove_file(&manifest_path);
    }

    // Known files
    let known_files = [
        "oxDesktop.exe",
        "oxWsProxy.exe",
        "RapidOcrOnnx.exe",
        "onnxruntime.dll",
        "changelog.txt",
        "install_manifest.json",
        "install_manifest.txt",
        "d3dcompiler_47.dll",
        "dxil.dll",
        "dxcompiler.dll",
        "opengl32sw.dll",
        "modules.json",
        "updater.exe",
    ];
    for f in &known_files {
        let p = install_dir.join(f);
        if p != current_exe.as_deref().unwrap_or(Path::new("")) {
            let _ = fs::remove_file(&p);
        }
    }

    // Known directories
    let known_dirs = ["models", "log", "dump"];
    for d in &known_dirs {
        let p = install_dir.join(d);
        let _ = fs::remove_dir_all(&p);
    }

    if delete_user_data {
        let _ = fs::remove_dir_all(&tdata_dir);
    }

    // 8. Deferred self-deletion of uninstall.exe and containing directory
    let dir_str = install_dir.to_string_lossy();
    let current_exe_str = current_exe
        .as_ref()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();

    let cmd_str = if delete_user_data || (!tdata_dir.exists()) {
        format!(
            "ping 127.0.0.1 -n 3 > nul & del /f /q \"{}\" & rmdir /s /q \"{}\"",
            current_exe_str, dir_str
        )
    } else {
        format!(
            "ping 127.0.0.1 -n 3 > nul & del /f /q \"{}\"",
            current_exe_str
        )
    };

    let _ = Command::new("cmd.exe")
        .args(&["/c", &cmd_str])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn();

    // 9. Completion notice
    if !is_silent {
        let title = to_wide_null("Удаление oxDesktop");
        let msg = to_wide_null("oxDesktop успешно удален с вашего компьютера.");
        unsafe {
            MessageBoxW(
                std::ptr::null_mut(),
                msg.as_ptr(),
                title.as_ptr(),
                MB_OK | MB_ICONINFORMATION,
            );
        }
    }
}
