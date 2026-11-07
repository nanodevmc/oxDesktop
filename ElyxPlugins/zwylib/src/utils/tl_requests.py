import asyncio
from typing import List, Callable, Optional, Any

from android_utils import run_on_ui_thread
from client_utils import get_messages_controller, send_request

from java import cast
from org.telegram.tgnet import TLRPC, TLObject
from org.telegram.messenger import ChatObject

from .java_utils import iterable_to_arraylist
from .logs import _logger, _req_logger


def process_updates(updates: TLRPC.TL_updates):
    if not isinstance(updates, TLRPC.TL_updates):
        _req_logger.debug(f"Response is not TLRPC.TL_updates ({type(updates)}).")
        return

    try:
        get_messages_controller().processUpdates(cast(TLRPC.Updates, updates), False)
    except Exception:
        _logger.error("An error occurred:", exc_info=True)


def _request_callback_factory(callback: Optional[Callable]):
    def inner_callback(response, error):
        process_updates(response)
        callback(response, error) if callback else None
    return inner_callback


class Requests:
    @staticmethod
    def send(req, callback: Optional[Callable], delay: Optional[int] = None, **kwargs):
        for k, v in kwargs.items():
            setattr(req, k, v)

        _req_logger.debug(f"Sending request {req} with {delay} delay.")
        run_on_ui_thread(
            lambda: send_request(req, _request_callback_factory(callback)),
            delay=delay or 0
        )

    @classmethod
    async def async_send(cls, req: TLObject, delay: Optional[int] = None, **kwargs) -> TLObject:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def callback(response: TLObject, error: TLRPC.TL_error):
            def bridge():
                if future.done():
                    return

                if error:
                    future.set_exception(Exception(f"Error {error.code}: {error.text}"))
                else:
                    future.set_result(response)

            # noinspection PyTypeChecker
            loop.call_soon_threadsafe(bridge)

        cls.send(req, callback, delay, **kwargs)
        return await future

    @staticmethod
    def reload_admins(chat_id: int):
        get_messages_controller().loadChannelAdmins(chat_id, False)
        _req_logger.debug(f"Reloaded admin list in '{chat_id}'.")

    @staticmethod
    def delete_messages(messages: List[int], peer_id: int, topic_id: Optional[int] = None):
        run_on_ui_thread(
            lambda: get_messages_controller().deleteMessages(
                iterable_to_arraylist(messages), None, None,
                peer_id, topic_id or 0, True, 0
            )
        )
        _req_logger.debug(f"Deleted {messages} in '{peer_id}' (thread id {topic_id or 0}).")

    @staticmethod
    async def change_slowmode(chat_id: int, seconds=0, delay=0):
         process_updates(
             await Requests.async_send(
                 TLRPC.TL_channels_toggleSlowMode(),
                 delay,
                 channel=get_messages_controller().getInputChannel(chat_id),
                 seconds=seconds
             )
         )

    @staticmethod
    async def ban(chat_id: int, peer_id: int, until_date: int | None = None, delay=0):
        banned_rights = TLRPC.TL_chatBannedRights()
        banned_rights.until_date = until_date or 0

        for attr in dir(banned_rights):
            if isinstance(getattr(banned_rights, attr), bool):
                setattr(banned_rights, attr, True)

        msg_controller = get_messages_controller()
        process_updates(
            await Requests.async_send(
                TLRPC.TL_channels_editBanned(),
                delay,
                participant=msg_controller.getInputPeer(peer_id),
                channel=msg_controller.getInputChannel(msg_controller.getChat(chat_id)),
                banned_rights=banned_rights
            )
        )

    @staticmethod
    async def unban(chat_id: int, target_peer_id: int, delay=0):
        msg_controller = get_messages_controller()
        await Requests.async_send(
            TLRPC.TL_channels_editBanned(),
            delay,
            participant=msg_controller.getInputPeer(target_peer_id),
            channel=msg_controller.getInputChannel(chat_id),
            banned_rights=TLRPC.TL_chatBannedRights()
        )

    @classmethod
    async def get_message(cls, peer_id: int, message_id: int) -> Optional[TLRPC.messages_Messages]:
        return await cls.get_messages(peer_id, [message_id])

    @staticmethod
    async def get_messages(peer_id: int, messages: List[int]) -> Optional[TLRPC.messages_Messages]:
        if ChatObject.isChannel(get_messages_controller().getChat(-peer_id)):
            req = TLRPC.TL_channels_getMessages()
            req.channel = get_messages_controller().getInputChannel(-peer_id)
        else:
            req = TLRPC.TL_messages_getMessages()
        return await Requests.async_send(req, id=iterable_to_arraylist(messages))

    @staticmethod
    async def search_messages(peer_id: int, delay=0, **kwargs) -> TLRPC.messages_Messages:
        msg_controller = get_messages_controller()

        req = TLRPC.TL_messages_search()
        req.peer = msg_controller.getInputPeer(peer_id)
        req.filter = kwargs.pop("filter", TLRPC.TL_inputMessagesFilterEmpty())
        req.q = kwargs.pop("q", "")

        from_id: Any = kwargs.pop("from_id", None)
        if from_id:
            req.from_id = msg_controller.getInputPeer(from_id)
            req.flags |= 1

        top_msg_id: Any = kwargs.pop("top_msg_id", None)
        if top_msg_id:
            req.top_msg_id = top_msg_id
            req.flags |= 2

        saved_peer_id: Any = kwargs.pop("saved_peer_id", None)
        if saved_peer_id:
            req.saved_peer_id = msg_controller.getInputPeer(saved_peer_id)
            req.flags |= 4

        saved_reaction: Any = kwargs.pop("saved_reaction", None)
        if saved_reaction:
            req.saved_reaction.add(saved_reaction.toTLReaction())
            req.flags |= 8

        response = await Requests.async_send(req, delay, **kwargs)
        return cast(TLRPC.messages_Messages, response)

    @staticmethod
    async def get_chat_participant(chat_id: int, target_peer_id: int) -> TLRPC.TL_channels_channelParticipant:
        msg_controller = get_messages_controller()
        return cast(
            TLRPC.TL_channels_channelParticipant,
            await Requests.async_send(
                TLRPC.TL_channels_getParticipant(),
                channel=msg_controller.getInputChannel(chat_id),
                participant=msg_controller.getInputPeer(target_peer_id)
            )
        )
