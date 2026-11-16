use std::ffi::c_void;
use std::ptr::null_mut;
use windows_sys::Win32::Foundation::*;
use windows_sys::Win32::Graphics::Gdi::*;
use windows_sys::Win32::System::Memory::*;

#[repr(C)]
pub struct GdiplusStartupInput {
    pub gdiplus_version: u32,
    pub debug_event_callback: *mut c_void,
    pub suppress_background_thread: BOOL,
    pub suppress_external_codecs: BOOL,
}

#[link(name = "ole32")]
extern "system" {
    fn CreateStreamOnHGlobal(
        hglobal: *mut c_void,
        delete_on_release: BOOL,
        stream: *mut *mut c_void,
    ) -> i32;
}

#[link(name = "gdiplus")]
extern "system" {
    fn GdiplusStartup(
        token: *mut usize,
        input: *const GdiplusStartupInput,
        output: *mut c_void,
    ) -> i32;
    fn GdiplusShutdown(token: usize);
    fn GdipCreateFromHDC(hdc: HDC, graphics: *mut *mut c_void) -> i32;
    fn GdipDeleteGraphics(graphics: *mut c_void) -> i32;
    fn GdipSetSmoothingMode(graphics: *mut c_void, mode: i32) -> i32;
    fn GdipSetInterpolationMode(graphics: *mut c_void, mode: i32) -> i32;
    fn GdipCreateSolidFill(color: u32, brush: *mut *mut c_void) -> i32;
    fn GdipDeleteBrush(brush: *mut c_void) -> i32;
    fn GdipCreatePen1(color: u32, width: f32, unit: i32, pen: *mut *mut c_void) -> i32;
    fn GdipDeletePen(pen: *mut c_void) -> i32;
    fn GdipCreatePath(fill_mode: i32, path: *mut *mut c_void) -> i32;
    fn GdipDeletePath(path: *mut c_void) -> i32;
    fn GdipAddPathArcI(
        path: *mut c_void,
        x: i32,
        y: i32,
        w: i32,
        h: i32,
        start_angle: f32,
        sweep_angle: f32,
    ) -> i32;
    fn GdipClosePathFigure(path: *mut c_void) -> i32;
    fn GdipFillPath(graphics: *mut c_void, brush: *mut c_void, path: *mut c_void) -> i32;
    fn GdipDrawPath(graphics: *mut c_void, pen: *mut c_void, path: *mut c_void) -> i32;
    fn GdipFillRectangleI(graphics: *mut c_void, brush: *mut c_void, x: i32, y: i32, w: i32, h: i32) -> i32;
    fn GdipCreateBitmapFromStream(stream: *mut c_void, bitmap: *mut *mut c_void) -> i32;
    fn GdipDisposeImage(image: *mut c_void) -> i32;
    fn GdipDrawImageRectI(graphics: *mut c_void, image: *mut c_void, x: i32, y: i32, w: i32, h: i32) -> i32;
    fn GdipGetImageWidth(image: *mut c_void, width: *mut u32) -> i32;
    fn GdipGetImageHeight(image: *mut c_void, height: *mut u32) -> i32;
}

pub struct GdiContext {
    token: usize,
}

impl GdiContext {
    pub fn new() -> Option<Self> {
        let mut token: usize = 0;
        let input = GdiplusStartupInput {
            gdiplus_version: 1,
            debug_event_callback: null_mut(),
            suppress_background_thread: 0,
            suppress_external_codecs: 0,
        };
        let status = unsafe { GdiplusStartup(&mut token, &input, null_mut()) };
        if status == 0 {
            Some(Self { token })
        } else {
            None
        }
    }
}

impl Drop for GdiContext {
    fn drop(&mut self) {
        if self.token != 0 {
            unsafe { GdiplusShutdown(self.token) };
            self.token = 0;
        }
    }
}

#[allow(dead_code)]
pub struct GdiImage {
    ptr: *mut c_void,
    pub width: u32,
    pub height: u32,
}

impl GdiImage {
    pub fn from_bytes(bytes: &[u8]) -> Option<Self> {
        unsafe {
            let hglobal = GlobalAlloc(GMEM_MOVEABLE, bytes.len());
            if hglobal.is_null() {
                return None;
            }
            let ptr = GlobalLock(hglobal);
            if ptr.is_null() {
                GlobalFree(hglobal);
                return None;
            }
            std::ptr::copy_nonoverlapping(bytes.as_ptr(), ptr as *mut u8, bytes.len());
            GlobalUnlock(hglobal);

            let mut stream: *mut c_void = null_mut();
            if CreateStreamOnHGlobal(hglobal, 1, &mut stream as *mut *mut c_void as _) != 0 {
                GlobalFree(hglobal);
                return None;
            }

            let mut bitmap: *mut c_void = null_mut();
            let status = GdipCreateBitmapFromStream(stream, &mut bitmap);

            let vtable = *(stream as *mut *mut usize);
            let release_fn: extern "system" fn(*mut c_void) -> u32 =
                std::mem::transmute(*vtable.add(2));
            release_fn(stream);

            if status != 0 || bitmap.is_null() {
                return None;
            }

            let mut width = 0;
            let mut height = 0;
            GdipGetImageWidth(bitmap, &mut width);
            GdipGetImageHeight(bitmap, &mut height);

            Some(Self {
                ptr: bitmap,
                width,
                height,
            })
        }
    }

    pub fn draw(&self, graphics: *mut c_void, x: i32, y: i32, w: i32, h: i32) {
        if !self.ptr.is_null() {
            unsafe {
                GdipDrawImageRectI(graphics, self.ptr, x, y, w, h);
            }
        }
    }
}

impl Drop for GdiImage {
    fn drop(&mut self) {
        if !self.ptr.is_null() {
            unsafe { GdipDisposeImage(self.ptr) };
            self.ptr = null_mut();
        }
    }
}

pub struct GdiGraphics {
    ptr: *mut c_void,
}

impl GdiGraphics {
    pub fn from_hdc(hdc: HDC) -> Option<Self> {
        let mut ptr = null_mut();
        let status = unsafe { GdipCreateFromHDC(hdc, &mut ptr) };
        if status == 0 && !ptr.is_null() {
            unsafe {
                GdipSetSmoothingMode(ptr, 4);
                GdipSetInterpolationMode(ptr, 7);
            }
            Some(Self { ptr })
        } else {
            None
        }
    }

    pub fn raw(&self) -> *mut c_void {
        self.ptr
    }

    pub fn fill_rect(&self, x: i32, y: i32, w: i32, h: i32, color: u32) {
        unsafe {
            let mut brush = null_mut();
            if GdipCreateSolidFill(color, &mut brush) == 0 {
                GdipFillRectangleI(self.ptr, brush, x, y, w, h);
                GdipDeleteBrush(brush);
            }
        }
    }

    pub fn fill_rounded_rect(&self, x: i32, y: i32, w: i32, h: i32, radius: i32, color: u32) {
        unsafe {
            let mut path = null_mut();
            if GdipCreatePath(0, &mut path) == 0 {
                let d = radius * 2;
                GdipAddPathArcI(path, x, y, d, d, 180.0, 90.0);
                GdipAddPathArcI(path, x + w - d, y, d, d, 270.0, 90.0);
                GdipAddPathArcI(path, x + w - d, y + h - d, d, d, 0.0, 90.0);
                GdipAddPathArcI(path, x, y + h - d, d, d, 90.0, 90.0);
                GdipClosePathFigure(path);

                let mut brush = null_mut();
                if GdipCreateSolidFill(color, &mut brush) == 0 {
                    GdipFillPath(self.ptr, brush, path);
                    GdipDeleteBrush(brush);
                }
                GdipDeletePath(path);
            }
        }
    }

    pub fn draw_rounded_rect(
        &self,
        x: i32,
        y: i32,
        w: i32,
        h: i32,
        radius: i32,
        border_color: u32,
        border_width: f32,
    ) {
        unsafe {
            let mut path = null_mut();
            if GdipCreatePath(0, &mut path) == 0 {
                let d = radius * 2;
                GdipAddPathArcI(path, x, y, d, d, 180.0, 90.0);
                GdipAddPathArcI(path, x + w - d, y, d, d, 270.0, 90.0);
                GdipAddPathArcI(path, x + w - d, y + h - d, d, d, 0.0, 90.0);
                GdipAddPathArcI(path, x, y + h - d, d, d, 90.0, 90.0);
                GdipClosePathFigure(path);

                let mut pen = null_mut();
                if GdipCreatePen1(border_color, border_width, 2, &mut pen) == 0 {
                    GdipDrawPath(self.ptr, pen, path);
                    GdipDeletePen(pen);
                }
                GdipDeletePath(path);
            }
        }
    }
}

impl Drop for GdiGraphics {
    fn drop(&mut self) {
        if !self.ptr.is_null() {
            unsafe { GdipDeleteGraphics(self.ptr) };
            self.ptr = null_mut();
        }
    }
}
