import asyncio
from asyncio import Future
from dataclasses import dataclass
from typing import List, Optional

from hook_utils import get_private_field, set_private_field
from android_utils import run_on_ui_thread
from client_utils import get_messages_controller, get_last_fragment
from base_plugin import MethodHook

from java import cast, dynamic_proxy
from android.os import Bundle
from org.telegram.tgnet import TLRPC
from org.telegram.ui import LaunchActivity, GroupCreateActivity, DialogsActivity
from com.exteragram.messenger.utils.chats import ChatUtils
from de.robv.android.xposed import XC_MethodHook

from ..core.meta import __id__, _get_plugin_id_from_stack
from ..utils.async_tools import _safe_set_future_result, _safe_set_future_exception, async_manager
from ..utils.hooks import HookUtils
from ..utils.java_utils import Callback1, iterable_to_arraylist, create_bundle
from ..utils.logs import _logger


def open_message(peer_id: int, msg_id: int, topic_id: Optional[int] = None):
    launch_activity = cast(LaunchActivity, get_last_fragment().getParentActivity())
    launch_activity.openMessage(
        peer_id,  # dialogId
        msg_id,  # messageId
        None,  # quote
        None,  # progress
        topic_id or 0,  # fromMessageId
        -1,  # quoteOffset
        None,  # task_id
        None,  # pollOption
    )


async def safe_open_message(peer_id: int, msg_id: int, topic_id=0, chat_username: Optional[str] = None):
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    access_hash = get_messages_controller().getInputPeer(-peer_id)
    if access_hash != 0:
        open_message(peer_id, msg_id, topic_id)
        return

    if not chat_username:
        _logger.warning(f"No access_hash and no username for peer '{peer_id}'.")
        return

    ChatUtils.getInstance().resolveChannel(
        chat_username,
        Callback1(lambda chat: _safe_set_future_result(future, chat))
    )

    if await future:
        open_message(peer_id, msg_id, topic_id)
    else:
        _logger.error(f"Resolution failed for '{chat_username}'.")


@dataclass
class PickedDialogs:
    users: List[int]
    chats: List[int]


@dataclass
class _TopicKey:
    dialog_id: int
    topic_id: int


class DialogPicker:
    class _PickerDelegate(dynamic_proxy(GroupCreateActivity.GroupCreateActivityDelegate)):
        def __init__(self, future: Future):
            super().__init__()
            self.future = future

        def didSelectUsers(self, _, __, ids):
            if self.future.done():
                return

            loop = async_manager.loop

            try:
                picked = PickedDialogs([], [])
                for i in ids.toArray():
                    if i < 0:
                        picked.chats.append(-i)
                    else:
                        picked.users.append(i)

                _safe_set_future_result(self.future, picked)
            except Exception as e:
                _safe_set_future_exception(self.future, e)

    class _GroupCreateAdapterHook(MethodHook):
        def after_hooked_method(self, param: XC_MethodHook.MethodHookParam):
            try:
                adapter = param.thisObject
                contacts = get_private_field(adapter, "contacts")
                new_contacts = iterable_to_arraylist(filter(lambda i: isinstance(i, TLRPC.Chat), contacts.toArray()))
                set_private_field(adapter, "contacts", new_contacts)
                _logger.debug("Filtered contacts out.")
            except Exception:
                _logger.error("An error occurred:", exc_info=True)

    class _ChatsPickerDelegate(dynamic_proxy(DialogsActivity.DialogsActivityDelegate)):
        def __init__(self, future: Future):
            super().__init__()
            self.future = future

        # noinspection PyPep8Naming, PyUnusedLocal
        def didSelectDialogs(self, fragment, dids, message, param, notify, scheduleDate, scheduleRepeatPeriod, topicsFragment) -> bool:
            if self.future.done():
                return True

            try:
                j_topic_key = dids.get(0)
                dialog_id = j_topic_key.dialogId
                topic_id = j_topic_key.topicId

                _safe_set_future_result(self.future, _TopicKey(-dialog_id, topic_id))

                run_on_ui_thread(lambda: get_last_fragment().finishFragment(not bool(topic_id)))
                if topic_id:
                    run_on_ui_thread(lambda: get_last_fragment().finishFragment(True))
            except Exception as e:
                _safe_set_future_exception(self.future, e)
            return True

    class _OnFragmentDestroyHook(MethodHook):
        def __init__(self, future: Future, hooks: List):
            self.future = future
            self.hooks = hooks

        def after_hooked_method(self, param: XC_MethodHook.MethodHookParam):
            try:
                for i in self.hooks:
                    HookUtils.unhook(i)

                _safe_set_future_exception(self.future, Exception("Cancelled."))
            except Exception:
                _logger.error("An error occurred:", exc_info=True)

    @classmethod
    async def pick_dialogs(cls, pre_picked: Optional[List[int]] = None, chats_only=False) -> PickedDialogs:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        plugin_id = _get_plugin_id_from_stack(__id__)

        try:
            hooks = []
            args = Bundle()
            args.putBoolean("isAlwaysShare", True)
            args.putInt("chatAddType", 2)

            activity = GroupCreateActivity(args)
            activity.setDelegate(cls._PickerDelegate(future))
            if pre_picked:
                pre_picked = [-i for i in pre_picked]
                activity.select(iterable_to_arraylist(pre_picked, int_auto_convert=False), False, False)

            if chats_only:
                clazz = GroupCreateActivity.GroupCreateAdapter.getClass()
                for constructor in clazz.getConstructors():
                    hooks.append(HookUtils.hook(plugin_id, constructor, cls._GroupCreateAdapterHook()))

            method = activity.getClass().getDeclaredMethod("onFragmentDestroy")
            hooks.append(HookUtils.hook(plugin_id, method, cls._OnFragmentDestroyHook(future, hooks)))

            run_on_ui_thread(lambda: get_last_fragment().presentFragment(activity))
        except Exception as e:
            future.set_exception(e)

        return await future

    @classmethod
    async def pick_chat(cls, groups=True, channels=True, topics=False) -> _TopicKey:
        future = asyncio.get_running_loop().create_future()
        plugin_id = _get_plugin_id_from_stack(__id__)

        try:
            hooks = []
            args = create_bundle({
                "dialogsType": getattr(DialogsActivity, "DIALOGS_TYPE_ADD_USERS_TO", 2),
                "onlySelect": True,
                "canSelectTopics": topics,
                "allowSwitchAccount": False,
                "allowGlobalSearch": True,
                "allowUsers": False,
                "allowBots": False,
                "allowChannels": channels,
                "allowLegacyGroups": groups,
                "allowMegagroups": groups,
                "allowGroups": groups,
            })

            activity = DialogsActivity(args)
            activity.setDelegate(cls._ChatsPickerDelegate(future))

            method = activity.getClass().getDeclaredMethod("onFragmentDestroy")
            hooks.append(HookUtils.hook(plugin_id, method, cls._OnFragmentDestroyHook(future, hooks)))

            run_on_ui_thread(lambda: get_last_fragment().presentFragment(activity))
        except Exception as e:
            future.set_exception(e)

        return await future
