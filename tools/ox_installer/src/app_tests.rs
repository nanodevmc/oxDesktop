#[cfg(test)]
mod tests {
    use crate::app::{ButtonId, InstallerApp, Layout, Rect, Screen};
    use crate::theme::{WIN_HEIGHT, WIN_WIDTH};

    #[test]
    fn test_rect_contains() {
        let r = Rect::new(10, 20, 100, 50);
        assert!(r.contains(10, 20));
        assert!(r.contains(109, 69));
        assert!(!r.contains(9, 20));
        assert!(!r.contains(10, 19));
        assert!(!r.contains(110, 50));
        assert!(!r.contains(50, 70));
    }

    #[test]
    fn test_layout_hit_test_welcome() {
        let app = InstallerApp::new();
        let w = WIN_WIDTH;
        let h = WIN_HEIGHT;

        // Browse button
        let browse_rect = Layout::browse_rect(w);
        let hit = app.hit_test(browse_rect.x + 5, browse_rect.y + 5);
        assert_eq!(hit, Some(ButtonId::Browse));

        // Telegram link
        let tg_rect = Layout::link_telegram_rect();
        let hit_tg = app.hit_test(tg_rect.x + 5, tg_rect.y + 5);
        assert_eq!(hit_tg, Some(ButtonId::LinkTelegram));

        // GitHub link
        let gh_rect = Layout::link_github_rect();
        let hit_gh = app.hit_test(gh_rect.x + 5, gh_rect.y + 5);
        assert_eq!(hit_gh, Some(ButtonId::LinkGitHub));

        // Cancel button
        let cancel_rect = Layout::cancel_rect(w, h);
        let hit_cancel = app.hit_test(cancel_rect.x + 5, cancel_rect.y + 5);
        assert_eq!(hit_cancel, Some(ButtonId::Cancel));

        // Install button
        let install_rect = Layout::install_rect(w, h);
        let hit_install = app.hit_test(install_rect.x + 5, install_rect.y + 5);
        assert_eq!(hit_install, Some(ButtonId::Install));
    }

    #[test]
    fn test_layout_hit_test_finished() {
        let mut app = InstallerApp::new();
        app.screen = Screen::Finished;
        let w = WIN_WIDTH;

        // CheckLaunch
        let chk_rect = Layout::finish_chk_rect(w);
        let hit_chk = app.hit_test(chk_rect.x + 5, chk_rect.y + 5);
        assert_eq!(hit_chk, Some(ButtonId::CheckLaunch));

        // Finish button
        let finish_rect = Layout::finish_btn_rect(w);
        let hit_finish = app.hit_test(finish_rect.x + 5, finish_rect.y + 5);
        assert_eq!(hit_finish, Some(ButtonId::Finish));
    }
}
