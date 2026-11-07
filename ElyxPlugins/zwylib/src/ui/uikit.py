import asyncio
from dataclasses import dataclass
from typing import List, Callable, Optional, Any, Generic

from android_utils import run_on_ui_thread
from client_utils import get_last_fragment, get_media_data_controller
from ui.alert import AlertDialogBuilder

from java import dynamic_proxy
from android.text import InputType
from android.util import TypedValue
from android.view import View, Gravity
from android.widget import LinearLayout, FrameLayout, TextView
from android.content import DialogInterface
from org.telegram.messenger import AndroidUtilities, LocaleController, ApplicationLoader
from org.telegram.messenger.utils import ViewOutlineProviderImpl
from org.telegram.ui.Cells import CheckBoxCell, RadioColorCell
from org.telegram.ui.ActionBar import AlertDialog, Theme, BottomSheet as JBottomSheet
from org.telegram.ui.Components import ItemOptions, EditTextBoldCursor, LayoutHelper, BackupImageView, LineProgressView

from ..core.locales import L
from ..core.meta import _T, MATCH_PARENT, WRAP_CONTENT
from ..utils.async_tools import safe_func_call, _safe_set_future_result
from ..utils.java_utils import PyRunnable
from ..utils.logs import _logger


class UI:
    @dataclass
    class PopupMenuItem:
        text: str
        on_click: Callable[[], None]
        icon: str
        is_red: bool = False

    class PopupMenuBuilder:
        def __init__(self, view: View):
            self._view = view
            self._items: List["UI.PopupMenuItem"] = []

        def add_item(self, item: "UI.PopupMenuItem"):
            self._items.append(item)

        def show(self):
            try:
                fragment = get_last_fragment()
                builder = ItemOptions.makeOptions(fragment, self._view)

                for item in self._items:
                    context = ApplicationLoader.applicationContext
                    icon_res_id = context.getResources().getIdentifier(item.icon, "drawable", context.getPackageName())
                    builder.add(icon_res_id, item.text, item.is_red, PyRunnable(item.on_click))

                builder.show()
            except Exception:
                _logger.error("An error occurred:", exc_info=True)

    @dataclass
    class AlertButton:
        text: str
        on_click: Optional[Callable[[AlertDialogBuilder, int], None]] = None
        type: int = AlertDialogBuilder.BUTTON_POSITIVE
        red: bool = False

    class AlertDialog:
        def __init__(self, title: str, text: str, buttons: List["UI.AlertButton"]):
            self.text = text
            self.title = title
            self.buttons = buttons
            self._builder: Optional[AlertDialogBuilder] = None

        def show(self):
            try:
                builder = self._builder
                if builder and (dialog := builder.get_dialog()) and dialog.isShowing():
                    _logger.warning("Alert already shown.")
                    return

                builder = AlertDialogBuilder(get_last_fragment().getParentActivity(), AlertDialogBuilder.ALERT_TYPE_MESSAGE)

                # use internal title and message setters to support SpannableStringBuilder
                builder._java_builder.setTitle(self.title)
                builder._java_builder.setMessage(self.text)
                builder.create()

                builder.set_cancelable(True)
                builder.set_canceled_on_touch_outside(True)

                for btn in self.buttons:
                    if not btn:
                        continue

                    match btn.type:
                        case AlertDialogBuilder.BUTTON_POSITIVE:
                            builder.set_positive_button(btn.text, btn.on_click)
                        case AlertDialogBuilder.BUTTON_NEGATIVE:
                            builder.set_negative_button(btn.text, btn.on_click)
                        case AlertDialogBuilder.BUTTON_NEUTRAL:
                            builder.set_neutral_button(btn.text, btn.on_click)

                    if btn.red:
                        builder.make_button_red(btn.type)

                builder.show()
                _logger.debug("Alert created and shown.")
            except Exception:
                _logger.error("An error occurred:", exc_info=True)

        def dismiss(self):
            def do_on_ui_thread():
                self._builder.dismiss()
                self._builder = None

            if self._builder and (dialog := self._builder.get_dialog()) and dialog.isShowing():
                run_on_ui_thread(do_on_ui_thread)
                _logger.debug("Alert was dismissed.")

    class BaseInputDialog(Generic[_T]):
        class _ViewClickListener(dynamic_proxy(View.OnClickListener)):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def onClick(self, view):
                self.callback(view)

        class _DialogClickListener(dynamic_proxy(AlertDialog.OnButtonClickListener)):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def onClick(self, dialog, which):
                self.callback(dialog, which)

        class _DismissListener(dynamic_proxy(DialogInterface.OnDismissListener)):
            def __init__(self, edit_text, resolve):
                super().__init__()
                self.edit_text = edit_text
                self.resolve = resolve

            def onDismiss(self, _):
                AndroidUtilities.hideKeyboard(self.edit_text)
                self.resolve(None)

        class _ShowListener(dynamic_proxy(DialogInterface.OnShowListener)):
            def __init__(self, edit_text):
                super().__init__()
                self.edit_text = edit_text

            def onShow(self, _):
                self.edit_text.requestFocus()
                self.edit_text.setSelection(self.edit_text.length())
                AndroidUtilities.showKeyboard(self.edit_text)

        def __init__(self):
            self.edit_text: Optional[EditTextBoldCursor] = None
            self.container: Optional[LinearLayout] = None

        def create_checkbox(self, context, label: str, is_checked: bool, divider: bool, on_click_extra=None):
            cell = CheckBoxCell(context, 1)
            cell.setBackgroundDrawable(Theme.getSelectorDrawable(False))
            cell.setText(label, "", is_checked, divider)

            p_left = AndroidUtilities.dp(16) if LocaleController.isRTL else AndroidUtilities.dp(8)
            p_right = AndroidUtilities.dp(8) if LocaleController.isRTL else AndroidUtilities.dp(16)
            cell.setPadding(p_left, 0, p_right, 0)

            def on_click(_):
                cell.setChecked(not cell.isChecked(), True)
                if on_click_extra:
                    on_click_extra(cell.isChecked())

            cell.setOnClickListener(self._ViewClickListener(on_click))
            return cell

        async def _show_impl(
                self,
                title: str,
                initial_text: str = "",
                hint: str = "",
                on_build_view: Callable[[LinearLayout, Any, Any], None] = None,
                get_result: Callable[[], _T] = None
        ) -> Optional[_T]:
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            def resolve(result):
                _safe_set_future_result(future, result)

            def show_dialog_on_ui():
                fragment = get_last_fragment()
                get_themed_color = fragment.getThemedColor
                context = fragment.getParentActivity()

                builder = AlertDialog.Builder(context)
                builder.setTitle(title)

                self.container = LinearLayout(context)
                self.container.setOrientation(LinearLayout.VERTICAL)

                self.edit_text = EditTextBoldCursor(context)
                self.edit_text.lineYFix = True
                self.edit_text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 18)
                self.edit_text.setText(initial_text)
                self.edit_text.setTextColor(get_themed_color(Theme.key_dialogTextBlack))
                self.edit_text.setHintColor(get_themed_color(Theme.key_groupcreate_hintText))
                self.edit_text.setHintText(hint)
                self.edit_text.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE)
                self.edit_text.setCursorColor(get_themed_color(Theme.key_windowBackgroundWhiteInputFieldActivated))
                self.edit_text.setLineColors(
                    get_themed_color(Theme.key_windowBackgroundWhiteInputField),
                    get_themed_color(Theme.key_windowBackgroundWhiteInputFieldActivated),
                    get_themed_color(Theme.key_text_RedRegular)
                )
                self.edit_text.setBackgroundDrawable(None)
                self.edit_text.setPadding(0, AndroidUtilities.dp(6), 0, AndroidUtilities.dp(6))

                self.container.addView(self.edit_text, LayoutHelper.createLinear(MATCH_PARENT, WRAP_CONTENT, 24, 0, 24, 10))

                if on_build_view:
                    on_build_view(self.container, context, get_themed_color)

                builder.setView(self.container)
                builder.setWidth(AndroidUtilities.dp(292))

                def on_done(_, __):
                    res = get_result() if get_result else self.edit_text.getText().toString()
                    dialog.dismiss()
                    resolve(res)

                builder.setPositiveButton(L.alert_done, self._DialogClickListener(on_done))
                builder.setNegativeButton(L.alert_cancel, self._DialogClickListener(lambda _, __: dialog.dismiss()))

                dialog = builder.create()
                dialog.setDismissDialogByButtons(False)
                dialog.setOnDismissListener(self._DismissListener(self.edit_text, resolve))
                dialog.setOnShowListener(self._ShowListener(self.edit_text))
                dialog.show()

            run_on_ui_thread(show_dialog_on_ui)
            return await future

    class StringInputDialog(BaseInputDialog[str]):
        @classmethod
        async def show(cls, title: str, initial_text="", hint="") -> Optional[str]:
            return await cls()._show_impl(title=title, initial_text=initial_text, hint=hint)

    class SelectorDialog:
        class _ViewClickListener(dynamic_proxy(View.OnClickListener)):
            def __init__(self, callback: Callable[[View], None]):
                super().__init__()
                self.callback = callback

            def onClick(self, view: View):
                self.callback(view)

        @classmethod
        async def show(cls, title: str, items: List[str], current_index: int = -1) -> Optional[int]:
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            def resolve(result):
                _safe_set_future_result(future, result)

            def show_on_ui():
                fragment = get_last_fragment()
                if not fragment:
                    resolve(None)
                    return

                context = fragment.getParentActivity()

                builder = AlertDialogBuilder(context)
                builder.set_title(title)

                linear_layout = LinearLayout(context)
                linear_layout.setOrientation(LinearLayout.VERTICAL)

                def on_item_click(index: int):
                    builder.dismiss()
                    resolve(index)

                for i, item_text in enumerate(items):
                    cell = RadioColorCell(context)
                    cell.setPadding(AndroidUtilities.dp(4), 0, AndroidUtilities.dp(4), 0)
                    cell.setCheckColor(
                        Theme.getColor(Theme.key_radioBackground),
                        Theme.getColor(Theme.key_dialogRadioBackgroundChecked)
                    )
                    cell.setTextAndValue(item_text, i == current_index)
                    cell.setBackground(Theme.createSelectorDrawable(Theme.getColor(Theme.key_listSelector), 2))
                    cell.setOnClickListener(cls._ViewClickListener(
                        lambda _, idx=i: on_item_click(idx)
                    ))

                    linear_layout.addView(cell, LayoutHelper.createLinear(MATCH_PARENT, WRAP_CONTENT))

                builder.set_view(linear_layout)

                builder.set_negative_button(
                    L.alert_cancel,
                    lambda dialog_builder, which: dialog_builder.dismiss()
                )

                builder.set_on_dismiss_listener(lambda _: resolve(None))

                builder.create()
                builder.show()

            run_on_ui_thread(show_on_ui)
            return await future

    class BottomSheet:
        def __init__(
                self,
                title: str,
                description: Optional[str],
                sticker: str,
                worker: Callable[["UI.BottomSheet"], None],
                on_finish: Optional[Callable[["UI.BottomSheet"], None]] = None,
                on_dismiss: Optional[Callable[["UI.BottomSheet"], None]] = None,
        ):
            self.title = title
            self.description = description
            self.worker = worker
            self.finish_listener = on_finish
            self.dismiss_listener = on_dismiss

            self.dissmissed = False
            self.sheet = None
            self.description_view = None
            self.progress_view = None

            try:
                context = get_last_fragment().getParentActivity()

                self.sheet = JBottomSheet(context, False)
                self.sheet.fixNavigationBar()

                root = LinearLayout(context)
                root.setOrientation(1)
                root.setPadding(0, AndroidUtilities.dp(18), 0, AndroidUtilities.dp(18))

                try:
                    sticker_pack_name, sticker_index = sticker.split("/")
                    image_container = FrameLayout(context)
                    image_container.clipChildren = False
                    image_container.clipToPadding = False

                    image_view = BackupImageView(context)
                    image_view.outlineProvider = ViewOutlineProviderImpl.boundsWithRoundRect(AndroidUtilities.dpf2(12.0))
                    image_view.clipToOutline = True
                    image_view.imageReceiver.setAutoRepeat(1)
                    image_container.addView(image_view, LayoutHelper.createFrame(144, 144, Gravity.CENTER))

                    root.addView(image_container, LayoutHelper.createFrame(MATCH_PARENT, float(WRAP_CONTENT)))

                    get_media_data_controller().setPlaceholderImageByIndex(image_view, sticker_pack_name, int(sticker_index), "150_150")
                except Exception:
                    _logger.error(f"Failed to set '{sticker}' sticker in BottomSheet:", exc_info=True)

                title_view = TextView(context)
                title_view.setText(self.title)
                title_view.setTextSize(1, 20.0)
                title_view.setTypeface(AndroidUtilities.bold())
                title_view.setGravity(1)
                title_view.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText))
                root.addView(title_view, LayoutHelper.createLinear(-1, -2, 1, 40, 15, 40, 0))

                self.progress_view = LineProgressView(context)
                self.progress_view.setProgressColor(Theme.getColor(Theme.key_featuredStickers_addButton))
                self.progress_view.setBackColor(Theme.getColor(Theme.key_windowBackgroundGray))
                root.addView(self.progress_view, LayoutHelper.createLinear(-1, 5, 1, 45, 25, 45, 0))

                self.description_view = TextView(context)
                self.description_view.setText(self.description)
                self.description_view.setTextSize(1, 13.0)
                self.description_view.setGravity(1)
                self.description_view.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText))
                root.addView(self.description_view, LayoutHelper.createLinear(-1, -2, 1, 35, 10, 35, 10))

                self.sheet.setCustomView(root)
                self.sheet.setCanDismissWithSwipe(False)
                self.sheet.setCanDismissWithTouchOutside(False)
                self.sheet.setCancelable(False)
                self.sheet.setOnDismissListener(PyRunnable(self.on_dismiss))
            except Exception:
                _logger.error(f"Failed to create BottomSheet:", exc_info=True)

        def show(self):
            run_on_ui_thread(self.sheet.show)

        def start_worker(self):
            safe_func_call(self.worker, [self])

        def update_status(self, progress: float, text: str):
            self.progress_view.setProgress(min(progress, 1.0), True)
            self.description_view.setText(text)

        def finish(self):
            run_on_ui_thread(self.sheet.dismiss)
            safe_func_call(self.finish_listener, [self])
            del(self.sheet)

        def on_dismiss(self):
            self.dissmissed = True
            safe_func_call(self.dismiss_listener, [self])
