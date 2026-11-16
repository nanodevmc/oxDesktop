use std::fs::{self, File};
use std::io::Cursor;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use windows_sys::Win32::Foundation::HWND;
use windows_sys::Win32::UI::WindowsAndMessaging::PostMessageW;
use zip::ZipArchive;

pub const WM_APP_PROGRESS: u32 = 0x8001;
pub const WM_APP_FINISHED: u32 = 0x8002;
pub const WM_APP_ERROR: u32 = 0x8003;

static PAYLOAD_ZIP: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/payload.zip"));

#[derive(Clone, Copy)]
pub struct SendHwnd(pub HWND);
unsafe impl Send for SendHwnd {}
unsafe impl Sync for SendHwnd {}

pub struct InstallOptions {
    pub target_dir: PathBuf,
    pub create_desktop_shortcut: bool,
    pub create_start_menu_shortcut: bool,
    pub hwnd: SendHwnd,
}

pub fn start_installation(options: InstallOptions, cancel_flag: Arc<AtomicBool>) {
    thread::spawn(move || {
        let res = run_install(&options, &cancel_flag);
        match res {
            Ok(_) => unsafe {
                PostMessageW(options.hwnd.0, WM_APP_FINISHED, 1, 0);
            },
            Err(_) => unsafe {
                PostMessageW(options.hwnd.0, WM_APP_ERROR, 0, 0);
            },
        }
    });
}

fn run_install(options: &InstallOptions, cancel_flag: &AtomicBool) -> Result<(), ()> {
    if PAYLOAD_ZIP.is_empty() {
        return Err(());
    }

    if let Err(_) = fs::create_dir_all(&options.target_dir) {
        return Err(());
    }

    let cursor = Cursor::new(PAYLOAD_ZIP);
    let mut archive = ZipArchive::new(cursor).map_err(|_| ())?;
    let total_files = archive.len();

    let mut main_exe_path: Option<PathBuf> = None;

    for i in 0..total_files {
        if cancel_flag.load(Ordering::Relaxed) {
            return Err(());
        }

        let mut file = archive.by_index(i).map_err(|_| ())?;
        let enclosed_name = file.enclosed_name().ok_or(())?.to_owned();
        let out_path = options.target_dir.join(&enclosed_name);

        if file.is_dir() {
            let _ = fs::create_dir_all(&out_path);
        } else {
            if let Some(parent) = out_path.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let mut outfile = File::create(&out_path).map_err(|_| ())?;
            std::io::copy(&mut file, &mut outfile).map_err(|_| ())?;

            if out_path
                .file_name()
                .map(|n| n.to_string_lossy().to_lowercase())
                == Some("oxdesktop.exe".to_string())
            {
                main_exe_path = Some(out_path.clone());
            }
        }

        let pct = if total_files > 0 {
            ((i + 1) * 90 / total_files) as usize
        } else {
            90
        };

        unsafe {
            PostMessageW(options.hwnd.0, WM_APP_PROGRESS, pct, 0);
        }
    }

    let target_exe = main_exe_path.unwrap_or_else(|| options.target_dir.join("oxDesktop.exe"));

    if options.create_desktop_shortcut {
        if let Ok(user_profile) = std::env::var("USERPROFILE") {
            let desktop_dir = Path::new(&user_profile).join("Desktop");
            if desktop_dir.exists() {
                let shortcut_file = desktop_dir.join("oxDesktop.lnk");
                crate::shortcuts::create_shortcut(
                    &shortcut_file,
                    &target_exe,
                    "oxDesktop - Secure Telegram Client",
                    &options.target_dir,
                );
            }
        }
    }

    if options.create_start_menu_shortcut {
        if let Ok(app_data) = std::env::var("APPDATA") {
            let start_menu_programs = Path::new(&app_data)
                .join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs")
                .join("oxDesktop");
            let _ = fs::create_dir_all(&start_menu_programs);
            let shortcut_file = start_menu_programs.join("oxDesktop.lnk");
            crate::shortcuts::create_shortcut(
                &shortcut_file,
                &target_exe,
                "oxDesktop - Secure Telegram Client",
                &options.target_dir,
            );
        }
    }

    crate::registry::register_uninstall(&options.target_dir, &target_exe, "7.4.3.3.1");

    unsafe {
        PostMessageW(options.hwnd.0, WM_APP_PROGRESS, 100, 0);
    }

    thread::sleep(std::time::Duration::from_millis(300));

    Ok(())
}
