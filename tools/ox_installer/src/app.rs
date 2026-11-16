use std::ffi::{c_void, OsStr};
use std::os::windows::ffi::OsStrExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use windows_sys::Win32::Foundation::*;
use windows_sys::Win32::Graphics::Gdi::*;
use windows_sys::Win32::UI::WindowsAndMessaging::*;

use crate::gdi::*;
use crate::theme::*;
use crate::unpacker::{start_installation, InstallOptions};
use google_material_symbols::GoogleMaterialSymbols;

#[link(name = "gdi32")]
extern "system" {
    fn AddFontMemResourceEx(
        pb_font: *const c_void,
        cb_font: u32,
        pdv: *const c_void,
        pc_fonts: *mut u32,
    ) -> HANDLE;
    fn RemoveFontMemResourceEx(h: HANDLE) -> BOOL;
}

const BIF_RETURNONLYFSDIRS: u32 = 0x00000001;
const BIF_NEWDIALOGSTYLE: u32 = 0x00000040;

#[repr(C)]
struct BROWSEINFOW {
    hwnd_owner: HWND,
    pidl_root: *const c_void,
    psz_display_name: *mut u16,
    lpsz_title: *const u16,
    ul_flags: u32,
    lpfn: *const c_void,
    l_param: isize,
    i_image: i32,
}

#[link(name = "shell32")]
extern "system" {
    fn SHBrowseForFolderW(lpbi: *const BROWSEINFOW) -> *mut c_void;
    fn SHGetPathFromIDListW(pidl: *const c_void, psz_path: *mut u16) -> BOOL;
    fn ShellExecuteW(
        hwnd: HWND,
        lp_operation: *const u16,
        lp_file: *const u16,
        lp_parameters: *const u16,
        lp_directory: *const u16,
        n_show_cmd: i32,
    ) -> HINSTANCE;
}

#[link(name = "ole32")]
extern "system" {
    fn CoTaskMemFree(pv: *const c_void);
}

pub fn to_wide_null(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Screen {
    Welcome,
    Installing,
    Finished,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ButtonId {
    Install,
    Cancel,
    Browse,
    Finish,
    CheckLaunch,
    LinkTelegram,
    LinkGitHub,
}

#[derive(Clone, Copy)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

impl Rect {
    pub const fn new(x: i32, y: i32, w: i32, h: i32) -> Self {
        Self { x, y, w, h }
    }

    pub fn contains(&self, px: i32, py: i32) -> bool {
        px >= self.x && px < (self.x + self.w) && py >= self.y && py < (self.y + self.h)
    }

    pub fn to_win32_rect(&self) -> RECT {
        RECT {
            left: self.x,
            top: self.y,
            right: self.x + self.w,
            bottom: self.y + self.h,
        }
    }
}

pub struct AppFonts {
    pub title: HFONT,
    pub heading: HFONT,
    pub body: HFONT,
    pub button: HFONT,
    pub small: HFONT,
    pub icon: HFONT,
    pub font_res: HANDLE,
}

impl AppFonts {
    pub fn new() -> Self {
        unsafe {
            let make_font = |size: i32, weight: i32| {
                let name = to_wide_null("Segoe UI");
                CreateFontW(
                    -size,
                    0,
                    0,
                    0,
                    weight,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    5,
                    0,
                    name.as_ptr(),
                )
            };

            let mut num_fonts = 0u32;
            let font_res = AddFontMemResourceEx(
                GoogleMaterialSymbols::FONT_BYTES.as_ptr() as *const c_void,
                GoogleMaterialSymbols::FONT_BYTES.len() as u32,
                std::ptr::null(),
                &mut num_fonts,
            );

            let icon_name = to_wide_null(GoogleMaterialSymbols::FONT_FAMILY);
            let icon = CreateFontW(
                -13,
                0,
                0,
                0,
                400,
                0,
                0,
                0,
                1,
                0,
                0,
                5,
                0,
                icon_name.as_ptr(),
            );

            Self {
                title: make_font(22, 700),
                heading: make_font(15, 600),
                body: make_font(12, 400),
                button: make_font(13, 600),
                small: make_font(11, 400),
                icon,
                font_res,
            }
        }
    }
}

impl Drop for AppFonts {
    fn drop(&mut self) {
        unsafe {
            if !self.title.is_null() {
                DeleteObject(self.title);
            }
            if !self.heading.is_null() {
                DeleteObject(self.heading);
            }
            if !self.body.is_null() {
                DeleteObject(self.body);
            }
            if !self.button.is_null() {
                DeleteObject(self.button);
            }
            if !self.small.is_null() {
                DeleteObject(self.small);
            }
            if !self.icon.is_null() {
                DeleteObject(self.icon);
            }
            if !self.font_res.is_null() {
                RemoveFontMemResourceEx(self.font_res);
            }
        }
    }
}

pub const INSTALLER_VERSION: &str = env!("OX_VERSION");

pub struct InstallerApp {
    pub screen: Screen,
    pub target_dir: PathBuf,
    pub installed_version: Option<String>,
    pub is_same_version: bool,
    pub create_desktop_shortcut: bool,
    pub create_start_menu_shortcut: bool,
    pub launch_after_install: bool,
    pub progress_percent: usize,
    pub logo_img: Option<GdiImage>,
    pub fonts: AppFonts,
    pub hovered_btn: Option<ButtonId>,
    pub cancel_flag: Arc<AtomicBool>,
}

impl InstallerApp {
    pub fn new() -> Self {
        let app_data = std::env::var("APPDATA").unwrap_or_else(|_| "C:\\".to_string());
        let default_target = PathBuf::from(app_data).join("oxDesktop");

        let delta_bytes = include_bytes!("../assets/delta_avatar.png");
        let logo_img = GdiImage::from_bytes(delta_bytes);

        let installed_version = crate::registry::get_installed_version();
        let is_same_version = if let Some(ref cur) = installed_version {
            let clean_cur = cur.strip_prefix('v').unwrap_or(cur).trim();
            let clean_inst = INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION).trim();
            clean_cur == clean_inst
        } else {
            false
        };

        Self {
            screen: Screen::Welcome,
            target_dir: default_target,
            installed_version,
            is_same_version,
            create_desktop_shortcut: true,
            create_start_menu_shortcut: true,
            launch_after_install: true,
            progress_percent: 0,
            logo_img,
            fonts: AppFonts::new(),
            hovered_btn: None,
            cancel_flag: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn render(&self, hdc: HDC, width: i32, height: i32) {
        let Some(graphics) = GdiGraphics::from_hdc(hdc) else {
            return;
        };

        graphics.fill_rect(0, 0, width, height, COLOR_BG);

        unsafe {
            SetBkMode(hdc, 1);
        }

        match self.screen {
            Screen::Welcome => self.render_welcome(hdc, &graphics, width, height),
            Screen::Installing => self.render_installing(hdc, &graphics, width, height),
            Screen::Finished => self.render_finished(hdc, &graphics, width, height),
        }
    }

    fn render_welcome(&self, hdc: HDC, graphics: &GdiGraphics, width: i32, height: i32) {
        // --- 1. Левый верхний угол: информация о версиях ---
        unsafe {
            SelectObject(hdc, self.fonts.small);

            // Текущая версия
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_MUTED));
            let mut r_cur_lbl = Rect::new(20, 14, 100, 16).to_win32_rect();
            let cur_lbl = to_wide_null("Текущая версия:");
            DrawTextW(hdc, cur_lbl.as_ptr(), -1, &mut r_cur_lbl, 0x00000000 | 0x00000004);

            let cur_val_str = match &self.installed_version {
                Some(v) => format!("v{}", v.strip_prefix('v').unwrap_or(v)),
                None => "не установлена".to_string(),
            };
            SetTextColor(hdc, argb_to_colorref(if self.installed_version.is_some() { COLOR_TEXT_PRIMARY } else { COLOR_TEXT_MUTED }));
            let mut r_cur_val = Rect::new(122, 14, 110, 16).to_win32_rect();
            let cur_val_w = to_wide_null(&cur_val_str);
            DrawTextW(hdc, cur_val_w.as_ptr(), -1, &mut r_cur_val, 0x00000000 | 0x00000004);

            // Устанавливаемая версия
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_MUTED));
            let mut r_inst_lbl = Rect::new(20, 32, 136, 16).to_win32_rect();
            let inst_lbl = to_wide_null("Устанавливаемая версия:");
            DrawTextW(hdc, inst_lbl.as_ptr(), -1, &mut r_inst_lbl, 0x00000000 | 0x00000004);

            SetTextColor(hdc, argb_to_colorref(COLOR_ACCENT));
            let inst_val_str = format!("v{}", INSTALLER_VERSION.strip_prefix('v').unwrap_or(INSTALLER_VERSION));
            let mut r_inst_val = Rect::new(158, 32, 90, 16).to_win32_rect();
            let inst_val_w = to_wide_null(&inst_val_str);
            DrawTextW(hdc, inst_val_w.as_ptr(), -1, &mut r_inst_val, 0x00000000 | 0x00000004);

            // Если версия одинакова (1в1)
            if self.is_same_version {
                SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_MUTED));
                let mut r_note = Rect::new(20, 50, 210, 32).to_win32_rect();
                let note_str = to_wide_null("Обновление не требуется\n(можно переустановить с нуля).");
                DrawTextW(hdc, note_str.as_ptr(), -1, &mut r_note, 0x00000000);
            }
        }

        // --- 2. Центр: Дельта логотип, заголовок и подзаголовок (сдвинуты вниз для лучшего баланса) ---
        let logo_size = 64;
        let logo_x = (width - logo_size) / 2;
        let logo_y = 20;

        if let Some(logo) = &self.logo_img {
            logo.draw(graphics.raw(), logo_x, logo_y, logo_size, logo_size);
        }

        unsafe {
            SelectObject(hdc, self.fonts.title);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let mut r_title = Rect::new(0, logo_y + logo_size + 6, width, 28).to_win32_rect();
            let title_str = to_wide_null("oxDesktop");
            DrawTextW(hdc, title_str.as_ptr(), -1, &mut r_title, 0x00000001 | 0x00000020);

            // Подзаголовок сдвинут заметно ниже под заголовок
            SelectObject(hdc, self.fonts.body);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_SECONDARY));
            let mut r_sub = Rect::new(0, logo_y + logo_size + 42, width, 22).to_win32_rect();
            let sub_str = to_wide_null("Быстрый и безопасный клиент Telegram с обходом блокировок");
            DrawTextW(hdc, sub_str.as_ptr(), -1, &mut r_sub, 0x00000001 | 0x00000020);
        }

        // --- 3. Поле выбора пути ---
        let form_w = 460;
        let form_x = (width - form_w) / 2;
        let path_y = 176;
        let path_h = 36;

        graphics.fill_rounded_rect(form_x, path_y, form_w, path_h, 6, COLOR_SURFACE);
        graphics.draw_rounded_rect(form_x, path_y, form_w, path_h, 6, COLOR_BORDER, 1.0);

        unsafe {
            SelectObject(hdc, self.fonts.small);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_MUTED));
            let mut r_lbl = Rect::new(form_x + 12, path_y + 9, 45, 18).to_win32_rect();
            let lbl = to_wide_null("Папка:");
            DrawTextW(hdc, lbl.as_ptr(), -1, &mut r_lbl, 0x00000000 | 0x00000004 | 0x00000020);

            SelectObject(hdc, self.fonts.body);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let path_display = self.target_dir.to_string_lossy();
            let mut r_path = Rect::new(form_x + 58, path_y + 8, form_w - 138, 20).to_win32_rect();
            let path_wide = to_wide_null(&path_display);
            DrawTextW(
                hdc,
                path_wide.as_ptr(),
                -1,
                &mut r_path,
                0x00000000 | 0x00000004 | 0x00000020 | 0x00004000,
            );
        }

        self.draw_button_ex(
            hdc,
            graphics,
            ButtonId::Browse,
            Rect::new(form_x + form_w - 74, path_y + 6, 66, 24),
            "Обзор...",
            false,
            true,
        );

        // --- 4. Ссылки в левом нижнем углу (пониже, друг под другом) ---
        let link_x = 32;
        let tg_y = 320;
        let gh_y = 344;

        unsafe {
            let tg_hover = self.hovered_btn == Some(ButtonId::LinkTelegram);
            let gh_hover = self.hovered_btn == Some(ButtonId::LinkGitHub);

            // Иконка Telegram (Google Material Symbol "Send")
            SelectObject(hdc, self.fonts.icon);
            SetTextColor(
                hdc,
                argb_to_colorref(if tg_hover { COLOR_ACCENT } else { COLOR_TEXT_MUTED }),
            );
            let tg_icon_char = char::from(GoogleMaterialSymbols::Send);
            let mut tg_icon_w = [0u16; 3];
            let tg_icon_len = tg_icon_char.encode_utf16(&mut tg_icon_w).len();
            tg_icon_w[tg_icon_len] = 0;
            let mut r_tg_icon = Rect::new(link_x, tg_y + 1, 16, 18).to_win32_rect();
            DrawTextW(hdc, tg_icon_w.as_ptr(), -1, &mut r_tg_icon, 0x00000000 | 0x00000004);

            // Текст Telegram
            SelectObject(hdc, self.fonts.small);
            let mut r_tg = Rect::new(link_x + 20, tg_y + 1, 110, 18).to_win32_rect();
            let tg = to_wide_null("t.me/oxDesktop");
            DrawTextW(hdc, tg.as_ptr(), -1, &mut r_tg, 0x00000000 | 0x00000004);

            // Иконка GitHub (Google Material Symbol "Code")
            SelectObject(hdc, self.fonts.icon);
            SetTextColor(
                hdc,
                argb_to_colorref(if gh_hover { COLOR_ACCENT } else { COLOR_TEXT_MUTED }),
            );
            let gh_icon_char = char::from(GoogleMaterialSymbols::Code);
            let mut gh_icon_w = [0u16; 3];
            let gh_icon_len = gh_icon_char.encode_utf16(&mut gh_icon_w).len();
            gh_icon_w[gh_icon_len] = 0;
            let mut r_gh_icon = Rect::new(link_x, gh_y + 1, 16, 18).to_win32_rect();
            DrawTextW(hdc, gh_icon_w.as_ptr(), -1, &mut r_gh_icon, 0x00000000 | 0x00000004);

            // Текст GitHub
            SelectObject(hdc, self.fonts.small);
            let mut r_gh = Rect::new(link_x + 20, gh_y + 1, 90, 18).to_win32_rect();
            let gh = to_wide_null("GitHub");
            DrawTextW(hdc, gh.as_ptr(), -1, &mut r_gh, 0x00000000 | 0x00000004);
        }

        // --- 6. Правый нижний угол: кнопки Отмена и Установить ---
        let footer_y = height - 54;

        self.draw_button(
            hdc,
            graphics,
            ButtonId::Cancel,
            Rect::new(width - 216, footer_y, 88, 36),
            "Отмена",
            false,
        );

        self.draw_button(
            hdc,
            graphics,
            ButtonId::Install,
            Rect::new(width - 118, footer_y, 98, 36),
            "Установить",
            true,
        );
    }

    fn render_installing(&self, hdc: HDC, graphics: &GdiGraphics, width: i32, _height: i32) {
        let logo_size = 72;
        let logo_x = (width - logo_size) / 2;
        let logo_y = 55;

        if let Some(logo) = &self.logo_img {
            logo.draw(graphics.raw(), logo_x, logo_y, logo_size, logo_size);
        }

        unsafe {
            SelectObject(hdc, self.fonts.title);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let mut r_title = Rect::new(0, logo_y + logo_size + 18, width, 28).to_win32_rect();
            let title_str = to_wide_null("Установка oxDesktop");
            DrawTextW(hdc, title_str.as_ptr(), -1, &mut r_title, 0x00000001 | 0x00000020);

            SelectObject(hdc, self.fonts.body);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_SECONDARY));
            let status_msg = format!("Распаковка файлов клиента... {}%", self.progress_percent);
            let mut r_sub = Rect::new(0, logo_y + logo_size + 50, width, 20).to_win32_rect();
            let sub_str = to_wide_null(&status_msg);
            DrawTextW(hdc, sub_str.as_ptr(), -1, &mut r_sub, 0x00000001 | 0x00000020);
        }

        let bar_w = 380;
        let bar_h = 6;
        let bar_x = (width - bar_w) / 2;
        let bar_y = 232;

        graphics.fill_rounded_rect(bar_x, bar_y, bar_w, bar_h, 3, COLOR_SURFACE);
        graphics.draw_rounded_rect(bar_x, bar_y, bar_w, bar_h, 3, COLOR_BORDER, 1.0);

        let fill_w = ((bar_w as f32) * (self.progress_percent as f32 / 100.0)) as i32;
        if fill_w > 4 {
            graphics.fill_rounded_rect(bar_x, bar_y, fill_w, bar_h, 3, COLOR_ACCENT);
        }
    }

    fn render_finished(&self, hdc: HDC, graphics: &GdiGraphics, width: i32, _height: i32) {
        let logo_size = 72;
        let logo_x = (width - logo_size) / 2;
        let logo_y = 48;

        if let Some(logo) = &self.logo_img {
            logo.draw(graphics.raw(), logo_x, logo_y, logo_size, logo_size);
        }

        graphics.fill_rounded_rect(logo_x + 50, logo_y + 50, 24, 24, 12, COLOR_ACCENT);
        unsafe {
            SelectObject(hdc, self.fonts.small);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let mut r_chk = Rect::new(logo_x + 50, logo_y + 50, 24, 24).to_win32_rect();
            let chk = to_wide_null("✓");
            DrawTextW(hdc, chk.as_ptr(), -1, &mut r_chk, 0x00000001 | 0x00000004 | 0x00000020);

            SelectObject(hdc, self.fonts.title);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let mut r_title = Rect::new(0, logo_y + logo_size + 16, width, 28).to_win32_rect();
            let title_str = to_wide_null("oxDesktop установлен");
            DrawTextW(hdc, title_str.as_ptr(), -1, &mut r_title, 0x00000001 | 0x00000020);

            SelectObject(hdc, self.fonts.body);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_SECONDARY));
            let mut r_sub = Rect::new(0, logo_y + logo_size + 46, width, 20).to_win32_rect();
            let sub_str = to_wide_null("Клиент готов к первому запуску");
            DrawTextW(hdc, sub_str.as_ptr(), -1, &mut r_sub, 0x00000001 | 0x00000020);
        }

        // Чекбокс выровнен строго по центру
        let chk_w = 220;
        let chk_x = (width - chk_w) / 2;
        self.draw_checkbox(
            hdc,
            graphics,
            ButtonId::CheckLaunch,
            Rect::new(chk_x, 226, chk_w, 24),
            "Запустить oxDesktop сейчас",
            self.launch_after_install,
        );

        // Кнопка Готово выровнена строго по центру
        let btn_w = 140;
        let btn_x = (width - btn_w) / 2;
        self.draw_button(
            hdc,
            graphics,
            ButtonId::Finish,
            Rect::new(btn_x, 280, btn_w, 38),
            "Готово",
            true,
        );
    }

    fn draw_button(
        &self,
        hdc: HDC,
        graphics: &GdiGraphics,
        id: ButtonId,
        rect: Rect,
        text: &str,
        is_primary: bool,
    ) {
        self.draw_button_ex(hdc, graphics, id, rect, text, is_primary, false);
    }

    fn draw_button_ex(
        &self,
        hdc: HDC,
        graphics: &GdiGraphics,
        id: ButtonId,
        rect: Rect,
        text: &str,
        is_primary: bool,
        small_font: bool,
    ) {
        let is_hovered = self.hovered_btn == Some(id);

        let (bg_color, text_color, border_color) = if is_primary {
            if is_hovered {
                (COLOR_ACCENT_HOVER, COLOR_TEXT_PRIMARY, COLOR_ACCENT_HOVER)
            } else {
                (COLOR_ACCENT, COLOR_TEXT_PRIMARY, COLOR_ACCENT)
            }
        } else {
            if is_hovered {
                (COLOR_BTN_SECONDARY_HOVER, COLOR_TEXT_PRIMARY, COLOR_BORDER)
            } else {
                (COLOR_BTN_SECONDARY, COLOR_TEXT_PRIMARY, COLOR_BORDER)
            }
        };

        graphics.fill_rounded_rect(rect.x, rect.y, rect.w, rect.h, 6, bg_color);
        graphics.draw_rounded_rect(rect.x, rect.y, rect.w, rect.h, 6, border_color, 1.0);

        unsafe {
            SelectObject(hdc, if small_font { self.fonts.small } else { self.fonts.button });
            SetTextColor(hdc, argb_to_colorref(text_color));
            let mut win_rect = rect.to_win32_rect();
            let text_wide = to_wide_null(text);
            DrawTextW(
                hdc,
                text_wide.as_ptr(),
                -1,
                &mut win_rect,
                0x00000001 | 0x00000004 | 0x00000020,
            );
        }
    }

    fn draw_checkbox(
        &self,
        hdc: HDC,
        graphics: &GdiGraphics,
        _id: ButtonId,
        rect: Rect,
        text: &str,
        checked: bool,
    ) {
        let box_size = 16;
        let box_rect = Rect::new(rect.x, rect.y + 4, box_size, box_size);

        if checked {
            graphics.fill_rounded_rect(box_rect.x, box_rect.y, box_rect.w, box_rect.h, 4, COLOR_ACCENT);
        } else {
            graphics.fill_rounded_rect(box_rect.x, box_rect.y, box_rect.w, box_rect.h, 4, COLOR_SURFACE_HOVER);
            graphics.draw_rounded_rect(box_rect.x, box_rect.y, box_rect.w, box_rect.h, 4, COLOR_BORDER, 1.0);
        }

        unsafe {
            if checked {
                SelectObject(hdc, self.fonts.small);
                SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
                let mut r_mark = box_rect.to_win32_rect();
                let mark = to_wide_null("✓");
                DrawTextW(hdc, mark.as_ptr(), -1, &mut r_mark, 0x00000001 | 0x00000004 | 0x00000020);
            }

            SelectObject(hdc, self.fonts.body);
            SetTextColor(hdc, argb_to_colorref(COLOR_TEXT_PRIMARY));
            let mut r_txt = Rect::new(rect.x + 22, rect.y, rect.w - 22, rect.h).to_win32_rect();
            let wide_txt = to_wide_null(text);
            DrawTextW(hdc, wide_txt.as_ptr(), -1, &mut r_txt, 0x00000000 | 0x00000004 | 0x00000020);
        }
    }

    pub fn on_mouse_move(&mut self, x: i32, y: i32) -> bool {
        let new_hover = self.hit_test(x, y);
        if new_hover != self.hovered_btn {
            self.hovered_btn = new_hover;
            true
        } else {
            false
        }
    }

    pub fn on_lbutton_up(&mut self, x: i32, y: i32, hwnd: HWND) -> bool {
        let hit = self.hit_test(x, y);
        let Some(btn) = hit else {
            return false;
        };

        match btn {
            ButtonId::Install => {
                self.screen = Screen::Installing;
                self.progress_percent = 0;
                let options = InstallOptions {
                    target_dir: self.target_dir.clone(),
                    create_desktop_shortcut: self.create_desktop_shortcut,
                    create_start_menu_shortcut: self.create_start_menu_shortcut,
                    hwnd: crate::unpacker::SendHwnd(hwnd),
                };
                start_installation(options, self.cancel_flag.clone());
                true
            }
            ButtonId::Cancel => {
                self.cancel_flag.store(true, Ordering::Relaxed);
                unsafe {
                    PostQuitMessage(0);
                }
                false
            }
            ButtonId::Browse => {
                if let Some(selected) = self.browse_folder(hwnd) {
                    self.target_dir = selected;
                    true
                } else {
                    false
                }
            }
            ButtonId::CheckLaunch => {
                self.launch_after_install = !self.launch_after_install;
                true
            }
            ButtonId::Finish => {
                if self.launch_after_install {
                    let exe_path = self.target_dir.join("oxDesktop.exe");
                    let exe_wide = to_wide_null(&exe_path.to_string_lossy());
                    let dir_wide = to_wide_null(&self.target_dir.to_string_lossy());
                    let op_wide = to_wide_null("open");
                    unsafe {
                        ShellExecuteW(
                            std::ptr::null_mut(),
                            op_wide.as_ptr(),
                            exe_wide.as_ptr(),
                            std::ptr::null(),
                            dir_wide.as_ptr(),
                            5,
                        );
                    }
                }
                unsafe {
                    PostQuitMessage(0);
                }
                false
            }
            ButtonId::LinkTelegram => {
                let op = to_wide_null("open");
                let url = to_wide_null("https://t.me/oxDesktop");
                unsafe {
                    ShellExecuteW(
                        std::ptr::null_mut(),
                        op.as_ptr(),
                        url.as_ptr(),
                        std::ptr::null(),
                        std::ptr::null(),
                        5,
                    );
                }
                false
            }
            ButtonId::LinkGitHub => {
                let op = to_wide_null("open");
                let url = to_wide_null("https://github.com/nanodevmc/oxDesktop");
                unsafe {
                    ShellExecuteW(
                        std::ptr::null_mut(),
                        op.as_ptr(),
                        url.as_ptr(),
                        std::ptr::null(),
                        std::ptr::null(),
                        5,
                    );
                }
                false
            }
        }
    }

    fn hit_test(&self, x: i32, y: i32) -> Option<ButtonId> {
        let w = WIN_WIDTH;
        let h = WIN_HEIGHT;
        let form_w = 460;
        let form_x = (w - form_w) / 2;
        let path_y = 176;
        let link_x = 32;
        let tg_y = 320;
        let gh_y = 344;
        let footer_y = h - 54;

        match self.screen {
            Screen::Welcome => {
                // Ссылки в левом нижнем углу (друг под другом)
                if Rect::new(link_x, tg_y - 2, 130, 22).contains(x, y) {
                    return Some(ButtonId::LinkTelegram);
                }
                if Rect::new(link_x, gh_y - 2, 110, 22).contains(x, y) {
                    return Some(ButtonId::LinkGitHub);
                }
                // Кнопка Обзор пути
                if Rect::new(form_x + form_w - 74, path_y + 6, 66, 24).contains(x, y) {
                    return Some(ButtonId::Browse);
                }
                // Кнопки в правом нижнем углу
                if Rect::new(w - 216, footer_y, 88, 36).contains(x, y) {
                    return Some(ButtonId::Cancel);
                }
                if Rect::new(w - 118, footer_y, 98, 36).contains(x, y) {
                    return Some(ButtonId::Install);
                }
            }
            Screen::Installing => {}
            Screen::Finished => {
                let chk_w = 220;
                let chk_x = (w - chk_w) / 2;
                if Rect::new(chk_x, 226, chk_w, 24).contains(x, y) {
                    return Some(ButtonId::CheckLaunch);
                }
                let btn_w = 140;
                let btn_x = (w - btn_w) / 2;
                if Rect::new(btn_x, 280, btn_w, 38).contains(x, y) {
                    return Some(ButtonId::Finish);
                }
            }
        }
        None
    }

    fn browse_folder(&self, owner: HWND) -> Option<PathBuf> {
        let title_wide = to_wide_null("Выберите папку для установки oxDesktop");
        let bi = BROWSEINFOW {
            hwnd_owner: owner,
            pidl_root: std::ptr::null(),
            psz_display_name: std::ptr::null_mut(),
            lpsz_title: title_wide.as_ptr(),
            ul_flags: BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE,
            lpfn: std::ptr::null(),
            l_param: 0,
            i_image: 0,
        };

        unsafe {
            let pidl = SHBrowseForFolderW(&bi);
            if !pidl.is_null() {
                let mut path_buf = [0u16; 1024];
                let success = SHGetPathFromIDListW(pidl, path_buf.as_mut_ptr());
                CoTaskMemFree(pidl);
                if success != 0 {
                    let len = path_buf.iter().position(|&c| c == 0).unwrap_or(path_buf.len());
                    let path_str = String::from_utf16_lossy(&path_buf[..len]);
                    return Some(PathBuf::from(path_str));
                }
            }
        }
        None
    }
}
