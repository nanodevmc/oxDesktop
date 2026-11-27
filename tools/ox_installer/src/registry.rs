use std::ffi::{c_void, OsStr};
use std::os::windows::ffi::OsStrExt;
use std::path::Path;

type HKEY = *mut c_void;
const HKEY_CURRENT_USER: HKEY = 0x80000001usize as HKEY;
const KEY_SET_VALUE: u32 = 0x0002;
const KEY_READ: u32 = 0x20019;
const REG_SZ: u32 = 1;
const REG_DWORD: u32 = 4;

#[link(name = "advapi32")]
extern "system" {
    fn RegOpenKeyExW(
        h_key: HKEY,
        lp_sub_key: *const u16,
        ul_options: u32,
        sam_desired: u32,
        phk_result: *mut HKEY,
    ) -> i32;

    fn RegQueryValueExW(
        h_key: HKEY,
        lp_value_name: *const u16,
        lp_reserved: *const u32,
        lp_type: *mut u32,
        lp_data: *mut u8,
        lpcb_data: *mut u32,
    ) -> i32;

    fn RegCreateKeyExW(
        h_key: HKEY,
        lp_sub_key: *const u16,
        reserved: u32,
        lp_class: *mut u16,
        dw_options: u32,
        sam_desired: u32,
        lp_security_attributes: *const c_void,
        phk_result: *mut HKEY,
        lpdw_disposition: *mut u32,
    ) -> i32;

    fn RegSetValueExW(
        h_key: HKEY,
        lp_value_name: *const u16,
        reserved: u32,
        dw_type: u32,
        lp_data: *const u8,
        cb_data: u32,
    ) -> i32;

    fn RegDeleteKeyW(h_key: HKEY, lp_sub_key: *const u16) -> i32;

    fn RegCloseKey(h_key: HKEY) -> i32;
}

fn to_wide_null(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

pub fn register_uninstall(install_dir: &Path, target_exe: &Path, version: &str) {
    unsafe {
        let subkey = to_wide_null("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\oxDesktop");
        let mut hkey: HKEY = std::ptr::null_mut();
        let mut disposition: u32 = 0;

        if RegCreateKeyExW(
            HKEY_CURRENT_USER,
            subkey.as_ptr(),
            0,
            std::ptr::null_mut(),
            0,
            KEY_SET_VALUE,
            std::ptr::null(),
            &mut hkey,
            &mut disposition,
        ) == 0
        {
            let set_str = |key_name: &str, val: &str| {
                let name_wide = to_wide_null(key_name);
                let val_wide = to_wide_null(val);
                let _ = RegSetValueExW(
                    hkey,
                    name_wide.as_ptr(),
                    0,
                    REG_SZ,
                    val_wide.as_ptr() as *const u8,
                    (val_wide.len() * 2) as u32,
                );
            };

            let set_dword = |key_name: &str, val: u32| {
                let name_wide = to_wide_null(key_name);
                let _ = RegSetValueExW(
                    hkey,
                    name_wide.as_ptr(),
                    0,
                    REG_DWORD,
                    &val as *const u32 as *const u8,
                    4,
                );
            };

            set_str("DisplayName", "oxDesktop");
            set_str("DisplayVersion", version);
            set_str("Publisher", "NanoDev");
            set_str("InstallLocation", &install_dir.to_string_lossy());
            set_str("DisplayIcon", &target_exe.to_string_lossy());
            let uninstall_exe = install_dir.join("uninstall.exe");
            set_str(
                "UninstallString",
                &format!("\"{}\"", uninstall_exe.to_string_lossy()),
            );
            set_str(
                "QuietUninstallString",
                &format!("\"{}\" --silent", uninstall_exe.to_string_lossy()),
            );
            set_str("URLInfoAbout", "https://github.com/nanodevmc/oxDesktop");
            set_dword("NoModify", 1);
            set_dword("NoRepair", 1);

            RegCloseKey(hkey);
        }
    }
}

pub fn unregister_uninstall() {
    unsafe {
        let subkey = to_wide_null("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\oxDesktop");
        let _ = RegDeleteKeyW(HKEY_CURRENT_USER, subkey.as_ptr());
    }
}

pub fn get_install_location() -> Option<String> {
    unsafe {
        let subkey = to_wide_null("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\oxDesktop");
        let mut hkey: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(HKEY_CURRENT_USER, subkey.as_ptr(), 0, KEY_READ, &mut hkey) == 0 {
            let val_name = to_wide_null("InstallLocation");
            let mut buf = [0u16; 512];
            let mut cb_data = (buf.len() * 2) as u32;
            let mut val_type = 0u32;
            let res = RegQueryValueExW(
                hkey,
                val_name.as_ptr(),
                std::ptr::null(),
                &mut val_type,
                buf.as_mut_ptr() as *mut u8,
                &mut cb_data,
            );
            RegCloseKey(hkey);
            if res == 0 && (val_type == REG_SZ) {
                let len = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
                let loc = String::from_utf16_lossy(&buf[..len]).trim().to_string();
                if !loc.is_empty() {
                    return Some(loc);
                }
            }
        }
    }
    None
}

pub fn get_installed_version() -> Option<String> {
    unsafe {
        let subkey = to_wide_null("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\oxDesktop");
        let mut hkey: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(HKEY_CURRENT_USER, subkey.as_ptr(), 0, KEY_READ, &mut hkey) == 0 {
            let val_name = to_wide_null("DisplayVersion");
            let mut buf = [0u16; 256];
            let mut cb_data = (buf.len() * 2) as u32;
            let mut val_type = 0u32;
            let res = RegQueryValueExW(
                hkey,
                val_name.as_ptr(),
                std::ptr::null(),
                &mut val_type,
                buf.as_mut_ptr() as *mut u8,
                &mut cb_data,
            );
            RegCloseKey(hkey);
            if res == 0 && (val_type == REG_SZ) {
                let len = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
                let ver = String::from_utf16_lossy(&buf[..len]).trim().to_string();
                if !ver.is_empty() {
                    return Some(ver);
                }
            }
        }
    }

    if let Ok(app_data) = std::env::var("APPDATA") {
        let changelog = Path::new(&app_data).join("oxDesktop").join("changelog.txt");
        if let Ok(content) = std::fs::read_to_string(changelog) {
            for line in content.lines() {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    let v = trimmed.strip_prefix("oxDesktop").unwrap_or(trimmed).trim();
                    let v = v.strip_prefix('v').unwrap_or(v).trim();
                    if !v.is_empty() {
                        return Some(v.to_string());
                    }
                }
            }
        }
    }
    None
}
