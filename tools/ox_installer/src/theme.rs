#![allow(dead_code)]

pub const COLOR_BG: u32 = 0xFF0E1217;
pub const COLOR_SURFACE: u32 = 0xFF161C24;
pub const COLOR_SURFACE_HOVER: u32 = 0xFF1E2530;
pub const COLOR_BORDER: u32 = 0xFF27313F;

// Aero Delta Flame Orange (matches delta_avatar.png)
pub const COLOR_ACCENT: u32 = 0xFFF55C25;
pub const COLOR_ACCENT_HOVER: u32 = 0xFFFF6F3D;
pub const COLOR_ACCENT_PRESSED: u32 = 0xFFDE371A;

pub const COLOR_TEXT_PRIMARY: u32 = 0xFFFFFFFF;
pub const COLOR_TEXT_SECONDARY: u32 = 0xFF7E8B9B;
pub const COLOR_TEXT_MUTED: u32 = 0xFF505A69;

pub const COLOR_BTN_SECONDARY: u32 = 0xFF1E2530;
pub const COLOR_BTN_SECONDARY_HOVER: u32 = 0xFF283241;

pub const WIN_WIDTH: i32 = 600;
pub const WIN_HEIGHT: i32 = 440;

#[inline]
pub fn argb_to_colorref(argb: u32) -> u32 {
    let r = (argb >> 16) & 0xFF;
    let g = (argb >> 8) & 0xFF;
    let b = argb & 0xFF;
    r | (g << 8) | (b << 16)
}
