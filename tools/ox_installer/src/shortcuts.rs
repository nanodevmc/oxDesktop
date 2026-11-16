use std::ffi::c_void;
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
use std::ptr::null_mut;
use windows_sys::core::GUID;

const CLSCTX_INPROC_SERVER: u32 = 1;
const COINIT_APARTMENTTHREADED: u32 = 2;

const CLSID_SHELL_LINK: GUID = GUID {
    data1: 0x00021401,
    data2: 0x0000,
    data3: 0x0000,
    data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
};

const IID_ISHELL_LINK_W: GUID = GUID {
    data1: 0x000214F9,
    data2: 0x0000,
    data3: 0x0000,
    data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
};

const IID_IPERSIST_FILE: GUID = GUID {
    data1: 0x0000010B,
    data2: 0x0000,
    data3: 0x0000,
    data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
};

#[link(name = "ole32")]
extern "system" {
    fn CoInitializeEx(pv_reserved: *mut c_void, dw_co_init: u32) -> i32;
    fn CoCreateInstance(
        rclsid: *const GUID,
        p_unk_outer: *mut c_void,
        dw_cls_context: u32,
        riid: *const GUID,
        ppv: *mut *mut c_void,
    ) -> i32;
}

fn to_wide_null(s: &str) -> Vec<u16> {
    std::ffi::OsStr::new(s)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

pub fn create_shortcut(
    shortcut_path: &Path,
    target_exe: &Path,
    description: &str,
    working_dir: &Path,
) -> bool {
    unsafe {
        let _ = CoInitializeEx(null_mut(), COINIT_APARTMENTTHREADED);

        let mut shell_link_ptr: *mut c_void = null_mut();
        let hr = CoCreateInstance(
            &CLSID_SHELL_LINK,
            null_mut(),
            CLSCTX_INPROC_SERVER,
            &IID_ISHELL_LINK_W,
            &mut shell_link_ptr,
        );

        if hr != 0 || shell_link_ptr.is_null() {
            return false;
        }

        let vtable = *(shell_link_ptr as *mut *mut usize);

        let set_path_fn: extern "system" fn(*mut c_void, *const u16) -> i32 =
            std::mem::transmute(*vtable.add(20));
        let set_desc_fn: extern "system" fn(*mut c_void, *const u16) -> i32 =
            std::mem::transmute(*vtable.add(7));
        let set_work_dir_fn: extern "system" fn(*mut c_void, *const u16) -> i32 =
            std::mem::transmute(*vtable.add(9));
        let set_icon_fn: extern "system" fn(*mut c_void, *const u16, i32) -> i32 =
            std::mem::transmute(*vtable.add(17));
        let query_interface_fn: extern "system" fn(
            *mut c_void,
            *const GUID,
            *mut *mut c_void,
        ) -> i32 = std::mem::transmute(*vtable.add(0));
        let release_fn: extern "system" fn(*mut c_void) -> u32 =
            std::mem::transmute(*vtable.add(2));

        let target_wide = to_wide_null(&target_exe.to_string_lossy());
        let desc_wide = to_wide_null(description);
        let work_wide = to_wide_null(&working_dir.to_string_lossy());

        set_path_fn(shell_link_ptr, target_wide.as_ptr());
        set_desc_fn(shell_link_ptr, desc_wide.as_ptr());
        set_work_dir_fn(shell_link_ptr, work_wide.as_ptr());
        set_icon_fn(shell_link_ptr, target_wide.as_ptr(), 0);

        let mut persist_file_ptr: *mut c_void = null_mut();
        let hr_qi = query_interface_fn(
            shell_link_ptr,
            &IID_IPERSIST_FILE,
            &mut persist_file_ptr,
        );

        let mut success = false;
        if hr_qi == 0 && !persist_file_ptr.is_null() {
            let pf_vtable = *(persist_file_ptr as *mut *mut usize);
            let save_fn: extern "system" fn(*mut c_void, *const u16, i32) -> i32 =
                std::mem::transmute(*pf_vtable.add(6));
            let pf_release_fn: extern "system" fn(*mut c_void) -> u32 =
                std::mem::transmute(*pf_vtable.add(2));

            let shortcut_wide = to_wide_null(&shortcut_path.to_string_lossy());
            let hr_save = save_fn(persist_file_ptr, shortcut_wide.as_ptr(), 1);
            if hr_save == 0 {
                success = true;
            }
            pf_release_fn(persist_file_ptr);
        }

        release_fn(shell_link_ptr);
        success
    }
}
