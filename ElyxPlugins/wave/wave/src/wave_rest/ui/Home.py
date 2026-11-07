import os

try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

from android.view import Gravity, View
from android.widget import FrameLayout, ImageView, LinearLayout, TextView
from android.graphics.drawable import GradientDrawable
from android.util import TypedValue
from org.telegram.ui.ActionBar import BottomSheet, Theme
from org.telegram.messenger import AndroidUtilities
from android_utils import log, run_on_ui_thread, OnClickListener
try:
    from wave_addons.Diag import log
except Exception:
    pass
from client_utils import get_last_fragment

try:
    from wave_addons import Brand
except Exception:
    from ...wave_addons import Brand

ACCENT = 0xFFFFB8A6


class HomeHeroUI:
    def _chip(self, ctx, dark, size_w=38, size_h=34):
        chip = LinearLayout(ctx)
        chip.setGravity(Gravity.CENTER)
        self._set_bg(chip, 0xFFFFFFFF if not dark else 0xCC1D2733, 14)
        chip.setPadding(self._dp(8), self._dp(6), self._dp(8), self._dp(6))
        chip.setClickable(True)
        chip.setFocusable(True)
        return chip

    def _chip_icon(self, chip, drawable_names, tint, bitmap=None):
        iv = ImageView(chip.getContext())
        try:
            if bitmap is not None:
                iv.setImageBitmap(bitmap)
                iv.setColorFilter(self._color(tint))
            else:
                iv.setImageResource(self._telegram_drawable_id(*drawable_names))
                iv.setColorFilter(self._color(tint))
        except Exception:
            pass
        chip.addView(iv, LinearLayout.LayoutParams(self._dp(18), self._dp(18)))

    def _settings_profile_header(self, ctx):
        try:
            dark = self._is_dark_theme()
            root = FrameLayout(ctx)

            bg_container = FrameLayout(ctx)
            cbg = GradientDrawable()
            r = float(self._dp(16))
            cbg.setCornerRadii([r, r, r, r, 0.0, 0.0, 0.0, 0.0])
            cbg.setColor(self._color(0xFF000000))
            bg_container.setBackground(cbg)
            bg_container.setClipToOutline(True)

            metrics = ctx.getResources().getDisplayMetrics()
            wpx = int(metrics.widthPixels - self._dp(32))
            hpx = int(self._dp(110))
            bg_view = ImageView(ctx)
            bg_view.setScaleType(ImageView.ScaleType.CENTER_CROP)
            try:
                bg_view.setImageBitmap(Brand.hero_bitmap(wpx, hpx, dark))
            except Exception as e:
                log("[Wave] hero art: {0}".format(e))
            bg_container.addView(bg_view, FrameLayout.LayoutParams(-1, -1))

            buttons = LinearLayout(ctx)
            buttons.setGravity(Gravity.CENTER_VERTICAL)
            tint = 0xFFFFFFFF if dark else 0xFF000000

            info = self._chip(ctx, dark)
            self._chip_icon(info, ("msg_info",), tint)
            info.setOnClickListener(OnClickListener(lambda v: run_on_ui_thread(lambda: self._show_info_dialog(ctx))))
            buttons.addView(info, LinearLayout.LayoutParams(self._dp(38), self._dp(34)))

            lang = self._chip(ctx, dark)
            self._chip_icon(lang, ("msg_translate",), tint)
            lang.setOnClickListener(OnClickListener(lambda v: self._show_language_menu(v)))
            lp = LinearLayout.LayoutParams(self._dp(38), self._dp(34))
            lp.leftMargin = self._dp(8)
            buttons.addView(lang, lp)

            about = self._chip(ctx, dark)
            try:
                self._chip_icon(about, (), tint, Brand.glyph_bitmap("wave", self._dp(18), self._color(tint)))
            except Exception:
                pass
            about.setOnClickListener(OnClickListener(lambda v: run_on_ui_thread(lambda: self.open_about_sheet(ctx))))
            lp = LinearLayout.LayoutParams(self._dp(38), self._dp(34))
            lp.leftMargin = self._dp(8)
            buttons.addView(about, lp)

            blp = FrameLayout.LayoutParams(-2, -2, Gravity.RIGHT | Gravity.TOP)
            blp.setMargins(0, self._dp(10), self._dp(10), 0)
            bg_container.addView(buttons, blp)

            bg_lp = FrameLayout.LayoutParams(-1, self._dp(110))
            bg_lp.setMargins(self._dp(16), self._dp(16), self._dp(16), 0)
            root.addView(bg_container, bg_lp)

            content = LinearLayout(ctx)
            content.setOrientation(LinearLayout.VERTICAL)
            content.setPadding(self._dp(32), self._dp(16) + self._dp(110) - self._dp(45), self._dp(32), self._dp(16))

            icon = ImageView(ctx)
            try:
                icon.setImageBitmap(Brand.logo_bitmap(self._dp(98)))
            except Exception as e:
                log("[Wave] logo: {0}".format(e))
            icon.setScaleType(ImageView.ScaleType.FIT_CENTER)

            top = LinearLayout(ctx)
            top.setGravity(Gravity.BOTTOM)
            top.addView(icon, LinearLayout.LayoutParams(self._dp(98), self._dp(98)))
            top.addView(View(ctx), LinearLayout.LayoutParams(0, 0, 1.0))

            chips = LinearLayout(ctx)
            chips.setGravity(Gravity.CENTER_VERTICAL)
            chip_fg = 0xFF9AA4B2 if dark else 0xFFFFFFFF
            chip_bg = 0x1AFFFFFF if dark else 0xFF000000

            support = LinearLayout(ctx)
            support.setGravity(Gravity.CENTER_VERTICAL)
            self._set_bg(support, chip_bg, 16)
            support.setPadding(self._dp(10), self._dp(6), self._dp(12), self._dp(6))
            si = ImageView(ctx)
            try:
                si.setImageResource(self._telegram_drawable_id("tabs_chats_remix", "msg_info"))
                si.setColorFilter(self._color(chip_fg))
            except Exception:
                pass
            support.addView(si, LinearLayout.LayoutParams(self._dp(18), self._dp(18)))
            st = self._text_view(ctx, self._s("wave_support"), 13, chip_fg)
            st.setPadding(self._dp(6), 0, 0, 0)
            support.addView(st)
            support.setClickable(True)
            support.setOnClickListener(OnClickListener(lambda v: self._open_username(SUPPORT)))
            chips.addView(support)

            sett = LinearLayout(ctx)
            sett.setGravity(Gravity.CENTER)
            self._set_bg(sett, chip_bg, 16)
            sett.setPadding(self._dp(10), self._dp(6), self._dp(10), self._dp(6))
            sti = ImageView(ctx)
            try:
                sti.setImageResource(self._telegram_drawable_id("msg_settings"))
                sti.setColorFilter(self._color(chip_fg))
            except Exception:
                pass
            sett.addView(sti, LinearLayout.LayoutParams(self._dp(18), self._dp(18)))
            sett.setClickable(True)
            sett.setOnClickListener(OnClickListener(lambda v: self.openShortcutsSettingsSheet(ctx)))
            slp = LinearLayout.LayoutParams(-2, -2)
            slp.leftMargin = self._dp(8)
            chips.addView(sett, slp)

            clp = LinearLayout.LayoutParams(-2, -2)
            clp.leftMargin = self._dp(16)
            clp.bottomMargin = self._dp(14)
            top.addView(chips, clp)
            content.addView(top, LinearLayout.LayoutParams(-1, -2))

            title = self._text_view(ctx, "Wave", 24, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF151A21), True)
            self._steady_custom_text(title, 1, 24)
            tlp = LinearLayout.LayoutParams(-1, -2)
            tlp.setMargins(0, self._dp(16), 0, 0)
            content.addView(title, tlp)
            sub = self._text_view(ctx, self._s("wave_profile_subtitle"), 14, self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2))
            self._steady_custom_text(sub, 1, 14)
            slp2 = LinearLayout.LayoutParams(-1, -2)
            slp2.setMargins(0, self._dp(4), 0, 0)
            content.addView(sub, slp2)
            root.addView(content, FrameLayout.LayoutParams(-1, -2))
            return root
        except Exception as e:
            log("[Wave] Profile header error: {0}".format(e))
            return None

    def _settings_status_card(self, ctx):
        try:
            dark = self._is_dark_theme()
            outer = FrameLayout(ctx)
            olp = FrameLayout.LayoutParams(-1, -2)
            olp.setMargins(self._dp(16), self._dp(4), self._dp(16), self._dp(8))
            card = FrameLayout(ctx)
            self._set_bg(card, 0x12FFFFFF if dark else 0x0A000000, 18)
            try:
                card.setClipToOutline(True)
            except Exception:
                pass
            outer.addView(card, olp)

            rows = LinearLayout(ctx)
            rows.setOrientation(LinearLayout.VERTICAL)
            rows.setPadding(self._dp(14), self._dp(12), self._dp(54), self._dp(12))
            fill = 0x1FFFFFFF if dark else 0x14000000
            for w in (0.62, 0.84, 0.5, 0.74):
                r = LinearLayout(ctx)
                r.setGravity(Gravity.CENTER_VERTICAL)
                av = View(ctx)
                self._set_bg(av, fill, 18)
                r.addView(av, LinearLayout.LayoutParams(self._dp(36), self._dp(36)))
                col = LinearLayout(ctx)
                col.setOrientation(LinearLayout.VERTICAL)
                col.setPadding(self._dp(12), 0, 0, 0)
                l1 = View(ctx)
                self._set_bg(l1, fill, 4)
                l2 = View(ctx)
                self._set_bg(l2, fill, 4)
                p1 = LinearLayout.LayoutParams(int(self._dp(190) * w), self._dp(9))
                p2 = LinearLayout.LayoutParams(int(self._dp(190) * w * 0.7), self._dp(7))
                p2.topMargin = self._dp(6)
                col.addView(l1, p1)
                col.addView(l2, p2)
                r.addView(col)
                lp = LinearLayout.LayoutParams(-1, -2)
                lp.bottomMargin = self._dp(8)
                rows.addView(r, lp)
            card.addView(rows, FrameLayout.LayoutParams(-1, self._dp(176)))

            hint = self._text_view(ctx, self._s("wave_playground_hint"), 12, self._gray_color())
            hint.setPadding(self._dp(14), 0, self._dp(14), self._dp(8))
            card.addView(hint, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
            card.setMinimumHeight(self._dp(176))

            try:
                try:
                    from wave_addons.Overlay import WaveOverlay
                except Exception:
                    from ...wave_addons.Overlay import WaveOverlay
                demo = WaveOverlay(self, None, card)
                demo.attach()
                self._demos.append(demo)
            except Exception as e:
                log("[Wave] playground overlay: {0}".format(e))
            return outer
        except Exception as e:
            log("[Wave] playground: {0}".format(e))
            return None

    def _settings_footer(self, ctx):
        try:
            dark = self._is_dark_theme()
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setGravity(Gravity.CENTER_HORIZONTAL)
            root.setPadding(0, self._dp(12), 0, self._dp(12))
            try:
                root.addView(self._authors_block(ctx), LinearLayout.LayoutParams(-1, -2))
            except Exception as e:
                log("[Wave] authors: {0}".format(e))
            row = LinearLayout(ctx)
            row.setGravity(Gravity.CENTER)
            gray = self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2)
            row.addView(self._text_view(ctx, "Designed by ", 13, gray))
            row.addView(self._text_view(ctx, "@lyzos", 13, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24), True))
            row.addView(self._text_view(ctx, " · ", 13, gray))
            row.addView(self._text_view(ctx, "@LuPlugins", 13, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24), True))
            root.addView(row)
            v = self._text_view(ctx, "Wave v1.0.0", 11, gray)
            vlp = LinearLayout.LayoutParams(-2, -2)
            vlp.topMargin = self._dp(4)
            root.addView(v, vlp)
            chip = TextView(ctx)
            chip.setText("Powered by ElyxCore")
            chip.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10)
            chip.setPadding(self._dp(8), self._dp(2), self._dp(8), self._dp(2))
            chip.setTextColor(gray)
            self._set_bg(chip, 0x0FFFFFFF if dark else 0x0F000000, 12)
            clp = LinearLayout.LayoutParams(-2, -2)
            clp.topMargin = self._dp(12)
            root.addView(chip, clp)
            return root
        except Exception as e:
            log("[Wave] footer: {0}".format(e))
            return None

    def _hero_lab_header(self, ctx, tab=0):
        try:
            dark = self._is_dark_theme()
            root = FrameLayout(ctx)
            rlp = LinearLayout.LayoutParams(-1, self._dp(172))
            rlp.setMargins(self._dp(16), self._dp(8), self._dp(16), self._dp(12))
            root.setLayoutParams(rlp)
            bg = GradientDrawable()
            bg.setCornerRadius(float(self._dp(16)))
            bg.setOrientation(GradientDrawable.Orientation.LEFT_RIGHT)
            if dark:
                bg.setColors([self._c(0xFF3A1E1B), self._c(0xFF8A4A3C)])
            else:
                bg.setColor(self._c(0xFFFFD9CF))
            root.setBackground(bg)
            try:
                art = ImageView(ctx)
                art.setImageBitmap(Brand.logo_bitmap(self._dp(150)))
                art.setAlpha(0.9)
                root.addView(art, FrameLayout.LayoutParams(self._dp(150), self._dp(150), Gravity.RIGHT | Gravity.CENTER_VERTICAL))
            except Exception:
                pass
            left = LinearLayout(ctx)
            left.setOrientation(LinearLayout.VERTICAL)
            left.setPadding(self._dp(20), self._dp(16), self._dp(20), self._dp(16))
            left.setGravity(Gravity.CENTER_VERTICAL)
            root.addView(left, FrameLayout.LayoutParams(self._dp(220), -1, Gravity.LEFT))
            fg = 0xFFFFFFFF if dark else 0xFF2A100B
            title = self._text_view(ctx, self._s("wave_hero_title"), 22, fg)
            title.setTypeface(AndroidUtilities.getTypeface("fonts/rmedium.ttf"))
            self._steady_custom_text(title, 2, 22)
            left.addView(title)
            sub = self._text_view(ctx, self._s("wave_hero_subtitle"), 13, 0xDDFFEDE8 if dark else 0xDD3A1A12)
            sub.setPadding(0, self._dp(4), 0, 0)
            self._steady_custom_text(sub, 2, 13)
            left.addView(sub)
            btn = LinearLayout(ctx)
            btn.setGravity(Gravity.CENTER)
            btn.setPadding(self._dp(18), self._dp(11), self._dp(18), self._dp(11))
            self._set_bg(btn, 0xFF0B0D14 if not dark else 0xFFFFFFFF, 22)
            label = self._text_view(ctx, self._s("wave_hero_customize"), 12, 0xFFFFFFFF if not dark else 0xFF0B0D14)
            label.setTypeface(AndroidUtilities.getTypeface("fonts/rmedium.ttf"))
            btn.addView(label)
            blp = LinearLayout.LayoutParams(-2, -2)
            blp.topMargin = self._dp(18)
            left.addView(btn, blp)
            btn.setOnClickListener(OnClickListener(lambda v: self._show_lab_sheet(ctx, tab)))
            return root
        except Exception as e:
            log("[Wave] lab hero: {0}".format(e))
            return None

    def _show_info_dialog(self, ctx=None):
        try:
            if ctx is None:
                ctx = self._resolve_ctx()
            if ctx is None:
                return
            dark = self._is_dark_theme()
            sheet = BottomSheet(ctx, True)
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setPadding(self._dp(24), self._dp(24), self._dp(24), self._dp(24))

            bar = LinearLayout(ctx)
            bar.setPadding(self._dp(4), self._dp(4), self._dp(4), self._dp(4))
            self._set_bg(bar, 0x0CFFFFFF if dark else 0x08000000, 12)
            sel_bg = 0xFF2F3C4C if dark else 0xFFFFFFFF
            tabs = []
            for label in ("Wave", self._s("wave_info_tab_motion"), self._s("wave_info_tab_tips")):
                t = TextView(ctx)
                t.setText(label)
                t.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14)
                t.setGravity(Gravity.CENTER)
                t.setPadding(0, self._dp(8), 0, self._dp(8))
                t.setClickable(True)
                bar.addView(t, LinearLayout.LayoutParams(0, -2, 1.0))
                tabs.append(t)
            blp = LinearLayout.LayoutParams(-1, -2)
            blp.bottomMargin = self._dp(16)
            root.addView(bar, blp)
            body_title = self._text_view(ctx, "", 18, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24), True)
            body = self._text_view(ctx, "", 14, self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2))
            body.setPadding(0, self._dp(8), 0, 0)
            root.addView(body_title)
            root.addView(body)
            texts = [("Wave", "wave_info_body"), (self._s("wave_info_tab_motion"), "wave_info_motion_body"), (self._s("wave_info_tab_tips"), "wave_info_tips_body")]
            sel_c = self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24)
            un_c = self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2)

            def show(i):
                for j, t in enumerate(tabs):
                    if j == i:
                        self._set_bg(t, sel_bg, 10)
                        t.setTextColor(sel_c)
                        t.getPaint().setFakeBoldText(True)
                    else:
                        t.setBackground(None)
                        t.setTextColor(un_c)
                        t.getPaint().setFakeBoldText(False)
                body_title.setText(texts[i][0])
                body.setText(self._s(texts[i][1]))
            for i, t in enumerate(tabs):
                t.setOnClickListener(OnClickListener(lambda v, k=i: show(k)))
            show(0)

            action = TextView(ctx)
            action.setText(self._s("wave_info_action"))
            action.setTextSize(15)
            action.setTypeface(None, 1)
            action.setGravity(Gravity.CENTER)
            action.setTextColor(self._color(0xFFFFFFFF))
            p = self._theme_color(Theme.key_featuredStickers_addButton, 0xFF3F8FE5)
            try:
                action.setBackground(Theme.createSimpleSelectorRoundRectDrawable(self._dp(12), p, self._mix_rgb(p, 0x000000, 0.15)))
            except Exception:
                self._set_bg(action, p, 12)
            action.setOnClickListener(OnClickListener(lambda v: sheet.dismiss()))
            alp = LinearLayout.LayoutParams(-1, self._dp(48))
            alp.topMargin = self._dp(28)
            root.addView(action, alp)
            sheet.setCustomView(root)
            sheet.show()
        except Exception as e:
            log("[Wave] info dialog: {0}".format(e))

    def open_about_sheet(self, ctx):
        try:
            dark = self._is_dark_theme()
            sheet = BottomSheet(ctx, True)
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setPadding(self._dp(28), self._dp(22), self._dp(28), self._dp(28))
            top = LinearLayout(ctx)
            top.setGravity(Gravity.CENTER_VERTICAL)
            logo = ImageView(ctx)
            try:
                logo.setImageBitmap(Brand.logo_bitmap(self._dp(96)))
            except Exception:
                pass
            top.addView(logo, LinearLayout.LayoutParams(self._dp(96), self._dp(96)))
            col = LinearLayout(ctx)
            col.setOrientation(LinearLayout.VERTICAL)
            col.setPadding(self._dp(20), 0, 0, 0)
            col.addView(self._text_view(ctx, "Wave", 26, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF), True))
            col.addView(self._text_view(ctx, "v1.0.0", 14, self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2)))
            top.addView(col, LinearLayout.LayoutParams(0, -2, 1.0))
            root.addView(top)

            def button(text, fn):
                b = TextView(ctx)
                b.setText(text)
                b.setTextSize(15)
                b.setGravity(Gravity.CENTER_VERTICAL)
                b.setPadding(self._dp(18), self._dp(14), self._dp(18), self._dp(14))
                self._set_text_button(b)
                b.setOnClickListener(OnClickListener(fn))
                lp = LinearLayout.LayoutParams(-1, -2)
                lp.topMargin = self._dp(10)
                root.addView(b, lp)
            button("@LuPlugins", lambda v: (self._open_username("LuPlugins"), sheet.dismiss()))
            button("@lyzos", lambda v: (self._open_username("lyzos"), sheet.dismiss()))
            sheet.setCustomView(root)
            sheet.show()
        except Exception as e:
            log("[Wave] about: {0}".format(e))

    def _send_banner(self):
        def work():
            try:
                from org.telegram.messenger import ApplicationLoader, UserConfig
                path = os.path.join(str(ApplicationLoader.getCacheDir().getAbsolutePath()), "wave_banner.png")
                Brand.save_png(Brand.banner_bitmap(), path)
                from client_utils import get_send_messages_helper
                helper = get_send_messages_helper()
                me = int(UserConfig.getInstance(UserConfig.selectedAccount).getClientUserId())
                from org.telegram.messenger import SendMessagesHelper
                params = SendMessagesHelper.SendMessageParams.of("", me)
                params.photo = helper.generatePhotoSizes(path, None)
                params.path = path
                run_on_ui_thread(lambda: helper.sendMessage(params))
            except Exception as e:
                log("[Wave] banner send: {0}".format(e))
        self._run_bg(work)

    def _run_bg(self, fn):
        import threading
        threading.Thread(target=fn, daemon=True).start()

    def openShortcutsSettingsSheet(self, ctx):
        try:
            dark = self._is_dark_theme()
            sheet = BottomSheet(ctx, True)
            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            root.setPadding(self._dp(20), self._dp(20), self._dp(20), self._dp(24))
            root.addView(self._text_view(ctx, self._s("wave_shortcut_title"), 18, self._theme_color(Theme.key_windowBackgroundWhiteBlackText, 0xFFFFFFFF if dark else 0xFF1D1F24), True))
            d = self._text_view(ctx, self._s("wave_shortcut_desc"), 13, self._theme_color(Theme.key_windowBackgroundWhiteGrayText, 0xFF9AA4B2))
            d.setPadding(0, self._dp(4), 0, self._dp(12))
            root.addView(d)
            for it in (self._sw("wave_enabled", True, ("msg_noise_on_solar", "msg_settings")),
                       self._sw("wave_badge", True, ("msg_stories_views", "msg_settings"))):
                v = self._build_setting_view(ctx, it, lambda: None)
                if v:
                    root.addView(v, LinearLayout.LayoutParams(-1, -2))
            sheet.setCustomView(root)
            sheet.show()
        except Exception as e:
            log("[Wave] shortcuts: {0}".format(e))


SUPPORT = "LuPlugins"
