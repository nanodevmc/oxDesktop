from typing import Dict

from client_utils import get_media_data_controller
from extera_utils.classes import Base, java_subclass, joverride
from ui.settings import Custom

from android.util import TypedValue
from android.view import View, Gravity
from android.widget import LinearLayout, FrameLayout, TextView
from android.content import Context
from org.telegram.messenger import AndroidUtilities
from org.telegram.ui.ActionBar import Theme
from org.telegram.ui.Components import LayoutHelper, BackupImageView, UItem
from com.exteragram.messenger.plugins import Plugin
from com.exteragram.messenger.plugins.models import CustomSetting

from ..autoupdate.updater import toggle_plugin_autoupdates
from ..core.meta import MATCH_PARENT, WRAP_CONTENT


# noinspection PyPep8Naming,PyUnusedLocal,PyAttributeOutsideInit
@java_subclass(FrameLayout)
class PluginCell(Base):
    def on_post_init(self, context: Context):
        self.need_divider = False
        self.setWillNotDraw(False)

        self.icon_view = BackupImageView(context)
        self.icon_view.setRoundRadius(AndroidUtilities.dp(8))
        self.addView(self.icon_view,
                     LayoutHelper.createFrame(48, 48, Gravity.LEFT | Gravity.CENTER_VERTICAL, 16, 0, 0, 0))

        text_layout = LinearLayout(context)
        text_layout.setOrientation(LinearLayout.VERTICAL)

        self.name_text_view = TextView(context)
        self.name_text_view.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText))
        self.name_text_view.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 16)
        self.name_text_view.setLines(1)
        self.name_text_view.setSingleLine(True)

        self.author_text_view = TextView(context)
        self.author_text_view.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteGrayText))
        self.author_text_view.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13)
        self.author_text_view.setLines(1)
        self.author_text_view.setSingleLine(True)

        text_layout.addView(self.name_text_view, LayoutHelper.createLinear(MATCH_PARENT, WRAP_CONTENT))
        text_layout.addView(self.author_text_view,
                            LayoutHelper.createLinear(MATCH_PARENT, WRAP_CONTENT, 0, 2, 0, 0))
        self.addView(text_layout,
                     LayoutHelper.createFrame(MATCH_PARENT, WRAP_CONTENT, Gravity.LEFT | Gravity.CENTER_VERTICAL,
                                              76, 0, 16, 0))

    def set_data(self, plugin: Plugin, divider: bool):
        self.need_divider = divider
        self.name_text_view.setText(plugin.getName() or "Unknown Plugin")

        version = plugin.getVersion() or "1.0"
        author = plugin.getAuthor() or "Unknown"
        self.author_text_view.setText(f"v{version} • {author}")

        show_icon = plugin.getPack() is not None and plugin.getIndex() >= 0
        pack, index = (plugin.getPack(), plugin.getIndex()) if show_icon else ("exteraPlugins", 0)
        get_media_data_controller().setPlaceholderImageByIndex(self.icon_view, pack, index, "100_100")

        self.requestLayout()

    @joverride()
    def onMeasure(self, widthMeasureSpec: int, heightMeasureSpec: int):
        super().onMeasure(
            View.MeasureSpec.makeMeasureSpec(View.MeasureSpec.getSize(widthMeasureSpec), View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(AndroidUtilities.dp(68), View.MeasureSpec.EXACTLY),
        )


# noinspection PyPep8Naming,PyUnusedLocal,PyAttributeOutsideInit,PyMethodMayBeStatic
@java_subclass(CustomSetting.Factory)
class PluginCellSettingFactory(Base):
    @joverride()
    def create(self, plugin: Plugin, setting: CustomSetting, args):
        if not args:
            return None

        item = UItem.ofFactory(self.getClass())
        item.object = args
        return item

    @joverride()
    def createView(self, context, list_view, current_account, class_guid, resources_provider):
        return PluginCell.new_instance(context).java

    @joverride()
    def bindView(self, view, item, divider, adapter, list_view):
        if item.object:
            PluginCell.from_java(view).set_data(item.object, divider)

    @joverride()
    def onClick(self, plugin, item, view):
        toggle_plugin_autoupdates(item.object.getId())


plugin_cell_setting_factory_instance = PluginCellSettingFactory.new_instance().java
UItem.UItemFactory.setup(plugin_cell_setting_factory_instance)

_CELL_CACHE: Dict[str, Custom] = {}
