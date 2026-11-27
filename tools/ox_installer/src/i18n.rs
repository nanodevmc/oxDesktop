include!(concat!(env!("OUT_DIR"), "/locales_gen.rs"));

pub static FALLBACK_LOCALE: LocaleStrings = LocaleStrings {
    code: "en",
    name: "English",
    tag: "EN",
    slogan: "Fast and secure Telegram desktop client with anti-censorship",
    folder: "Folder:",
    browse: "Browse...",
    current: "Current: ",
    new_version: "New version: ",
    installed: "✓ Already installed",
    downgrade: "! Beta / newer version",
    cancel: "Cancel",
    install: "Install",
    title_installing: "Installing oxDesktop",
    unpacking: "Extracting client files...",
    title_finished: "oxDesktop Installed",
    installed_sub: "The client has been successfully installed",
    launch_now: "Launch oxDesktop now",
    finish: "Finish",
    downgrade_title: "Downgrade Warning",
    downgrade_msg: "A newer or pre-release (beta/dev) version of oxDesktop is already installed.\n\nDo you really want to install an older version?",
};

impl LocaleStrings {
    pub fn by_code(code: &str) -> &'static LocaleStrings {
        for loc in AVAILABLE_LOCALES {
            if loc.code.eq_ignore_ascii_case(code) {
                return loc;
            }
        }
        if !AVAILABLE_LOCALES.is_empty() {
            &AVAILABLE_LOCALES[0]
        } else {
            &FALLBACK_LOCALE
        }
    }

    pub fn default_system() -> usize {
        #[cfg(windows)]
        {
            let lang_id = unsafe { crate::app::GetUserDefaultUILanguage() };
            let primary = lang_id & 0x3FF;
            let code = match primary {
                0x19 => "ru",
                0x22 => "uk",
                0x23 => "be",
                0x0A => "es",
                _ => "en",
            };
            for (i, loc) in AVAILABLE_LOCALES.iter().enumerate() {
                if loc.code.eq_ignore_ascii_case(code) {
                    return i;
                }
            }
        }
        #[cfg(not(windows))]
        {
            if let Ok(lang) = std::env::var("LANG") {
                let l = lang.to_lowercase();
                for (i, loc) in AVAILABLE_LOCALES.iter().enumerate() {
                    if l.contains(loc.code) {
                        return i;
                    }
                }
            }
        }
        0
    }
}
