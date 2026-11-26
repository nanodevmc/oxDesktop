#![cfg_attr(windows, windows_subsystem = "windows")]

pub mod version;

#[cfg(windows)]
mod app;
#[cfg(windows)]
mod gdi;
#[cfg(windows)]
mod registry;
#[cfg(windows)]
mod shortcuts;
#[cfg(windows)]
mod theme;
#[cfg(windows)]
mod unpacker;

#[cfg(target_os = "linux")]
mod linux;

#[cfg(target_os = "linux")]
fn main() {
    linux::run_linux_installer();
}

#[cfg(windows)]
use std::sync::atomic::Ordering;
#[cfg(windows)]
use windows_sys::Win32::Foundation::*;
#[cfg(windows)]
use windows_sys::Win32::Graphics::Dwm::*;
#[cfg(windows)]
use windows_sys::Win32::Graphics::Gdi::*;
#[cfg(windows)]
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
#[cfg(windows)]
use windows_sys::Win32::UI::WindowsAndMessaging::*;

#[cfg(windows)]
use app::{to_wide_null, InstallerApp, Screen};
#[cfg(windows)]
use gdi::GdiContext;
#[cfg(windows)]
use theme::{WIN_HEIGHT, WIN_WIDTH};
#[cfg(windows)]
use unpacker::{WM_APP_ERROR, WM_APP_FINISHED, WM_APP_PROGRESS};

#[cfg(windows)]
const GWLP_USERDATA: i32 = -21;
#[cfg(windows)]
const TME_LEAVE: u32 = 0x00000002;
#[cfg(windows)]
const WM_MOUSELEAVE: u32 = 0x02A3;

#[cfg(windows)]
#[repr(C)]
struct TRACKMOUSEEVENT {
    cb_size: u32,
    dw_flags: u32,
    hwnd_track: HWND,
    dw_hover_time: u32,
}

#[cfg(windows)]
#[link(name = "user32")]
extern "system" {
    fn TrackMouseEvent(lp_event_track: *mut TRACKMOUSEEVENT) -> BOOL;
    fn SetWindowLongPtrW(h_wnd: HWND, n_index: i32, dw_new_long: isize) -> isize;
    fn GetWindowLongPtrW(h_wnd: HWND, n_index: i32) -> isize;
    fn CreateIconFromResourceEx(
        pb_icon_bits: *const u8,
        cb_icon_bits: u32,
        f_icon: BOOL,
        dw_version: u32,
        cx_desired: i32,
        cy_desired: i32,
        u_flags: u32,
    ) -> HICON;
}

#[cfg(windows)]
unsafe extern "system" fn wnd_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    let app_ptr = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut InstallerApp;
    let app = if !app_ptr.is_null() {
        app_ptr.as_mut()
    } else {
        None
    };

    match msg {
        WM_ERASEBKGND => 1,
        WM_PAINT => {
            let mut ps: PAINTSTRUCT = std::mem::zeroed();
            let hdc = BeginPaint(hwnd, &mut ps);
            if !hdc.is_null() {
                let mem_dc = CreateCompatibleDC(hdc);
                let mem_bm = CreateCompatibleBitmap(hdc, WIN_WIDTH, WIN_HEIGHT);
                let old_bm = SelectObject(mem_dc, mem_bm);

                if let Some(app) = app {
                    app.render(mem_dc, WIN_WIDTH, WIN_HEIGHT);
                }

                BitBlt(hdc, 0, 0, WIN_WIDTH, WIN_HEIGHT, mem_dc, 0, 0, SRCCOPY);

                SelectObject(mem_dc, old_bm);
                DeleteObject(mem_bm);
                DeleteDC(mem_dc);
                EndPaint(hwnd, &ps);
            }
            0
        }
        WM_MOUSEMOVE => {
            let x = (lparam & 0xFFFF) as i16 as i32;
            let y = ((lparam >> 16) & 0xFFFF) as i16 as i32;

            let mut tme = TRACKMOUSEEVENT {
                cb_size: std::mem::size_of::<TRACKMOUSEEVENT>() as u32,
                dw_flags: TME_LEAVE,
                hwnd_track: hwnd,
                dw_hover_time: 0,
            };
            TrackMouseEvent(&mut tme);

            if let Some(app) = app {
                if app.on_mouse_move(x, y) {
                    InvalidateRect(hwnd, std::ptr::null(), 0);
                }
                if app.hovered_btn.is_some() {
                    SetCursor(LoadCursorW(std::ptr::null_mut(), IDC_HAND));
                } else {
                    SetCursor(LoadCursorW(std::ptr::null_mut(), IDC_ARROW));
                }
            }
            0
        }
        WM_MOUSELEAVE => {
            if let Some(app) = app {
                if app.hovered_btn.is_some() {
                    app.hovered_btn = None;
                    InvalidateRect(hwnd, std::ptr::null(), 0);
                }
            }
            0
        }
        WM_LBUTTONUP => {
            let x = (lparam & 0xFFFF) as i16 as i32;
            let y = ((lparam >> 16) & 0xFFFF) as i16 as i32;
            if let Some(app) = app {
                if app.on_lbutton_up(x, y, hwnd) {
                    InvalidateRect(hwnd, std::ptr::null(), 0);
                }
            }
            0
        }
        WM_APP_PROGRESS => {
            if let Some(app) = app {
                app.progress_percent = wparam as usize;
                InvalidateRect(hwnd, std::ptr::null(), 0);
            }
            0
        }
        WM_APP_FINISHED => {
            if let Some(app) = app {
                app.progress_percent = 100;
                app.screen = Screen::Finished;
                InvalidateRect(hwnd, std::ptr::null(), 0);
            }
            0
        }
        WM_APP_ERROR => {
            let err_title = to_wide_null("Ошибка установки");
            let err_msg = to_wide_null("Не удалось извлечь файлы клиента или каталог недоступен.");
            MessageBoxW(hwnd, err_msg.as_ptr(), err_title.as_ptr(), MB_ICONERROR);
            PostQuitMessage(1);
            0
        }
        WM_NCDESTROY => {
            if let Some(app) = app {
                app.cancel_flag.store(true, Ordering::Relaxed);
            }
            if !app_ptr.is_null() {
                drop(Box::from_raw(app_ptr));
                SetWindowLongPtrW(hwnd, GWLP_USERDATA, 0);
            }
            PostQuitMessage(0);
            0
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

#[cfg(windows)]
fn load_embedded_icon() -> HICON {
    static ICON_BYTES: &[u8] = include_bytes!("../assets/icon.ico");
    if ICON_BYTES.len() > 22 {
        let count = u16::from_le_bytes([ICON_BYTES[4], ICON_BYTES[5]]) as usize;
        if count > 0 {
            let bytes_in_res = u32::from_le_bytes([
                ICON_BYTES[14],
                ICON_BYTES[15],
                ICON_BYTES[16],
                ICON_BYTES[17],
            ]) as usize;
            let offset = u32::from_le_bytes([
                ICON_BYTES[18],
                ICON_BYTES[19],
                ICON_BYTES[20],
                ICON_BYTES[21],
            ]) as usize;

            if offset + bytes_in_res <= ICON_BYTES.len() {
                let bits = &ICON_BYTES[offset..(offset + bytes_in_res)];
                unsafe {
                    return CreateIconFromResourceEx(
                        bits.as_ptr(),
                        bits.len() as u32,
                        1,
                        0x00030000,
                        32,
                        32,
                        0,
                    );
                }
            }
        }
    }
    std::ptr::null_mut()
}

#[cfg(windows)]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    let is_silent = args.iter().any(|a| {
        let l = a.to_lowercase();
        l == "/silent" || l == "/verysilent" || l == "--silent" || l == "-s" || l == "/s"
    });
    if is_silent {
        let app_data = std::env::var("APPDATA").unwrap_or_else(|_| "C:\\".to_string());
        let default_target = std::path::PathBuf::from(app_data).join("oxDesktop");
        let options = unpacker::InstallOptions {
            target_dir: default_target,
            create_desktop_shortcut: true,
            create_start_menu_shortcut: true,
            hwnd: unpacker::SendHwnd(std::ptr::null_mut()),
        };
        let cancel = std::sync::atomic::AtomicBool::new(false);
        if unpacker::run_install(&options, &cancel).is_ok() {
            std::process::exit(0);
        } else {
            std::process::exit(1);
        }
    }

    let _gdi = match GdiContext::new() {
        Some(g) => g,
        None => return,
    };

    unsafe {
        let instance = GetModuleHandleW(std::ptr::null());
        let class_name = to_wide_null("OxDesktopInstallerWindowClass");
        let hicon = load_embedded_icon();

        let wc = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(wnd_proc),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: instance,
            hIcon: hicon,
            hCursor: LoadCursorW(std::ptr::null_mut(), IDC_ARROW),
            hbrBackground: std::ptr::null_mut(),
            lpszMenuName: std::ptr::null(),
            lpszClassName: class_name.as_ptr(),
            hIconSm: hicon,
        };

        RegisterClassExW(&wc);

        let screen_w = GetSystemMetrics(SM_CXSCREEN);
        let screen_h = GetSystemMetrics(SM_CYSCREEN);

        let mut win_rect = RECT {
            left: 0,
            top: 0,
            right: WIN_WIDTH,
            bottom: WIN_HEIGHT,
        };
        let style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
        AdjustWindowRectEx(&mut win_rect, style, 0, 0);

        let real_w = win_rect.right - win_rect.left;
        let real_h = win_rect.bottom - win_rect.top;
        let pos_x = (screen_w - real_w) / 2;
        let pos_y = (screen_h - real_h) / 2;

        let window_title = to_wide_null("Установка oxDesktop");

        let hwnd = CreateWindowExW(
            0,
            class_name.as_ptr(),
            window_title.as_ptr(),
            style,
            pos_x,
            pos_y,
            real_w,
            real_h,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            instance,
            std::ptr::null(),
        );

        if hwnd.is_null() {
            return;
        }

        let app_box = Box::new(InstallerApp::new());
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, Box::into_raw(app_box) as isize);

        if !hicon.is_null() {
            SendMessageW(hwnd, WM_SETICON, 1, hicon as LPARAM);
            SendMessageW(hwnd, WM_SETICON, 0, hicon as LPARAM);
        }

        let dark_mode: u32 = 1;
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE as u32,
            &dark_mode as *const u32 as _,
            4,
        );

        ShowWindow(hwnd, SW_SHOW);
        UpdateWindow(hwnd);

        let mut msg: MSG = std::mem::zeroed();
        while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
}
