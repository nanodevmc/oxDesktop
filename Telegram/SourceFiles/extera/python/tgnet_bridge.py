import json
import os
import tempfile
import time

import _compat
import _extera
import tl_runtime

TLRPC = tl_runtime.TLRPC


def peer_info(dialog_id):
    try:
        return json.loads(_extera.peer_info(int(dialog_id or 0)) or "{}")
    except Exception:
        return {}


def get_input_peer(dialog_id):
    info = peer_info(dialog_id)
    kind = info.get("type")
    if info.get("self"):
        return TLRPC.TL_inputPeerSelf()
    if kind == "user":
        return TLRPC.TL_inputPeerUser(
            user_id=int(info.get("bare_id") or 0),
            access_hash=int(info.get("access_hash") or 0))
    if kind == "channel":
        return TLRPC.TL_inputPeerChannel(
            channel_id=int(info.get("bare_id") or 0),
            access_hash=int(info.get("access_hash") or 0))
    if kind == "chat":
        return TLRPC.TL_inputPeerChat(chat_id=int(info.get("bare_id") or 0))
    return TLRPC.TL_inputPeerEmpty()


def get_input_user(user_id):
    info = peer_info(user_id)
    if info.get("self"):
        return TLRPC.TL_inputUserSelf()
    if info.get("type") != "user":
        return TLRPC.TL_inputUserEmpty()
    return TLRPC.TL_inputUser(
        user_id=int(info.get("bare_id") or 0),
        access_hash=int(info.get("access_hash") or 0))


def get_input_channel(channel_id):
    cid = int(channel_id or 0)
    if not cid:
        return TLRPC.TL_inputChannelEmpty()
    if abs(cid) < 1000000000000:
        dialog = -1000000000000 - abs(cid)
    else:
        dialog = -abs(cid)
    info = peer_info(dialog)
    if not info or info.get("type") != "channel":
        info = peer_info(cid)
    if not info or info.get("type") != "channel":
        return TLRPC.TL_inputChannelEmpty()
    return TLRPC.TL_inputChannel(
        channel_id=int(info.get("bare_id") or abs(cid)),
        access_hash=int(info.get("access_hash") or 0))


def get_peer(dialog_id):
    dialog_id = int(dialog_id or 0)
    info = peer_info(dialog_id)
    kind = info.get("type")
    bare = int(info.get("bare_id") or abs(dialog_id))
    if kind == "channel":
        return TLRPC.TL_peerChannel(channel_id=bare)
    if kind == "chat":
        return TLRPC.TL_peerChat(chat_id=bare)
    return TLRPC.TL_peerUser(user_id=bare)


def get_user(user_id):
    info = peer_info(user_id)
    if info.get("type") != "user":
        return None
    name = info.get("name") or ""
    first, _, last = name.partition(" ")
    return TLRPC.TL_user(
        id=int(info.get("bare_id") or user_id),
        access_hash=int(info.get("access_hash") or 0),
        first_name=first,
        last_name=last or None,
        username=info.get("username") or None,
        phone=info.get("phone") or None,
        bot=bool(info.get("bot")),
        self=bool(info.get("self")))


def get_chat(chat_id):
    dialog = -abs(int(chat_id or 0))
    info = peer_info(dialog)
    kind = info.get("type")
    if kind == "channel":
        return TLRPC.TL_channel(
            id=int(info.get("bare_id") or abs(dialog)),
            access_hash=int(info.get("access_hash") or 0),
            title=info.get("name") or "",
            username=info.get("username") or None,
            megagroup=bool(info.get("megagroup")),
            broadcast=not info.get("megagroup"))
    if kind == "chat":
        return TLRPC.TL_chat(
            id=int(info.get("bare_id") or abs(dialog)),
            title=info.get("name") or "")
    return None


class _Instance(metaclass=_compat.LenientMeta):
    def __init__(self, account=0):
        self.currentAccount = account

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return _compat.Stub(type(self).__name__ + "." + item)


class ConnectionsManager(_Instance):
    RequestFlagFailOnServerErrors = 2
    RequestFlagCanCompress = 4
    RequestFlagWithoutLogin = 8
    RequestFlagTryDifferentDc = 16
    RequestFlagForceDownload = 32
    RequestFlagInvokeAfter = 64
    RequestFlagNeedQuickAck = 128
    ConnectionTypeGeneric = 1
    DEFAULT_DATACENTER_ID = 2147483647
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def sendRequest(self, request, delegate=None, *args, **kwargs):
        import client_utils
        return client_utils.send_request(request, delegate)

    def cancelRequest(self, request_id, notify=False):
        return None

    def getCurrentTime(self):
        return int(time.time())

    def getCurrentTimeMillis(self):
        return int(time.time() * 1000)

    def getConnectionState(self):
        return 3


class MessagesController(_Instance):
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def getInputPeer(self, dialog_or_peer):
        return get_input_peer(_dialog_of(dialog_or_peer))

    def getInputUser(self, user):
        if isinstance(user, tl_runtime.TLObject):
            user = getattr(user, "id", 0)
        return get_input_user(user)

    def getInputChannel(self, channel):
        if isinstance(channel, tl_runtime.TLObject):
            channel = getattr(channel, "id", 0)
        return get_input_channel(channel)

    def getPeer(self, dialog_id):
        return get_peer(dialog_id)

    def getUser(self, user_id):
        return get_user(user_id)

    def getChat(self, chat_id):
        return get_chat(chat_id)

    def putUser(self, *args, **kwargs):
        return True

    def putChat(self, *args, **kwargs):
        return True

    def putUsers(self, *args, **kwargs):
        return None

    def putChats(self, *args, **kwargs):
        return None


def _dialog_of(value):
    if isinstance(value, tl_runtime.TLObject):
        for attr, sign in (("user_id", 1), ("channel_id", -1), ("chat_id", -1)):
            bare = getattr(value, attr, None)
            if bare:
                return sign * int(bare)
        bare = getattr(value, "id", 0)
        return int(bare or 0)
    return int(value or 0)


def self_id():
    try:
        return int(_extera.self_id() or 0)
    except Exception:
        return 0


class UserConfig(_Instance):
    selectedAccount = 0
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    @property
    def clientUserId(self):
        return self_id()

    def getClientUserId(self):
        return self_id()

    def getCurrentUser(self):
        return get_user(self_id())

    def isClientActivated(self):
        return self_id() != 0

    def isPremium(self):
        return False

    def getNewMessageId(self):
        return 0



class ContactsController(_Instance):
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    @property
    def contacts(self):
        return tl_runtime.ArrayList()

    @property
    def users(self):
        return tl_runtime.ArrayList()

    @property
    def usersDict(self):
        return {}

    def isLoadingContacts(self):
        return False

    def loadContacts(self, fromCache=False, delay=0):
        return None

    def deleteContact(self, user):
        return None


class MediaDataController(_Instance):
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def getStickerSets(self, type_id=0):
        return tl_runtime.ArrayList()

    def getRecentStickers(self, type_id=0):
        return tl_runtime.ArrayList()

    def getRecentReactions(self):
        return tl_runtime.ArrayList()


class SendMessagesHelper(_Instance):
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def sendMessage(self, *args, **kwargs):
        import client_utils
        if len(args) == 1 and isinstance(args[0], dict):
            return client_utils.send_message(args[0], account=self.currentAccount)
        elif len(args) >= 2:
            return client_utils.send_text(args[0], args[1], account=self.currentAccount)
        return client_utils.send_message(kwargs, account=self.currentAccount)

    def prepareSending(self, *args, **kwargs):
        return None


class ChatActivity(_Instance):
    def __init__(self, dialog_id=0):
        super().__init__(0)
        self._dialog_id = int(dialog_id or 0)

    def getDialogId(self):
        return self._dialog_id

    def getCurrentChat(self):
        return get_chat(self._dialog_id) if self._dialog_id < 0 else None

    def getCurrentUser(self):
        return get_user(self._dialog_id) if self._dialog_id > 0 else None

    def getCurrentEncryptedChat(self):
        return None

    def getCurrentAccount(self):
        return 0

    def getMessagesController(self):
        return MessagesController.getInstance(0)

    def getConnectionsManager(self):
        return ConnectionsManager.getInstance(0)

    def getUserConfig(self):
        return UserConfig.getInstance(0)

    def getTopicId(self):
        return 0

    def getThreadId(self):
        return 0

    def isInScheduleMode(self):
        return False

    def getChatMode(self):
        return 0

    def getClass(self):
        return tl_runtime._ClassInfo("ChatActivity")

    def getParentActivity(self):
        return _compat.Stub("LaunchActivity")

    def getContext(self):
        return _compat.Stub("Context")


def current_fragment():
    try:
        dialog = int(_extera.current_peer() or 0)
    except Exception:
        dialog = 0
    if not dialog:
        return None
    return ChatActivity(dialog)


class RequestDelegate:
    def __init__(self, fn=None):
        self._fn = fn

    def run(self, response, error):
        if self._fn:
            self._fn(response, error)


class FileLoader(_Instance):
    _instances = {}

    MEDIA_DIR_IMAGE = 0
    MEDIA_DIR_AUDIO = 1
    MEDIA_DIR_VIDEO = 2
    MEDIA_DIR_DOCUMENT = 3
    MEDIA_DIR_CACHE = 4

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    @staticmethod
    def getDirectory(type_id=0):
        try:
            cache_dir = _extera.get_cache_dir()
            if cache_dir and os.path.isdir(cache_dir):
                return cache_dir
        except Exception:
            pass
        return tempfile.gettempdir()

    @staticmethod
    def checkDirectory(type_id=0):
        d = FileLoader.getDirectory(type_id)
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    @staticmethod
    def getInternalCacheDir():
        return FileLoader.checkDirectory(FileLoader.MEDIA_DIR_CACHE)

    def loadFile(self, obj, ext=None, priority=1, *args, **kwargs):
        if isinstance(obj, str) and os.path.exists(obj):
            return obj
        return ""

    def cancelLoadFile(self, obj):
        pass

    def isLoadingFile(self, fileName):
        return False

    @classmethod
    def getPathToMessage(cls, message):
        if not message:
            return ""
        media = getattr(message, "media", None)
        if not media and isinstance(message, dict):
            media = message.get("media")
        if not media:
            return ""
        doc = getattr(media, "document", None) or getattr(media, "photo", None)
        if isinstance(doc, dict):
            return str(doc.get("path") or "")
        if hasattr(doc, "path"):
            return str(doc.path or "")
        return ""

    @classmethod
    def getPathToAttach(cls, attach, ext=None, *args, **kwargs):
        if hasattr(attach, "path"):
            return str(attach.path or "")
        if isinstance(attach, dict):
            return str(attach.get("path") or "")
        return ""


class NotificationCenter(_Instance):
    _instances = {}
    _global_instance = None

    didLoadedReplyMessages = 1
    messagesDidLoad = 2
    didReceivedNewMessages = 3
    updateInterfaces = 4
    dialogsNeedReload = 5
    fileDidLoad = 6
    fileDidFailToLoad = 7
    fileLoadProgressChanged = 8
    mediaDidLoad = 9
    currentUserShowStatus = 10
    themeNeedReload = 11
    emojiLoaded = 12
    closeChats = 13
    botKeyboardDidLoad = 14
    chatInfoDidLoad = 15
    userInfoDidLoad = 16
    pinnedInfoDidLoad = 17
    suggestedFiltersLoaded = 18

    def __init__(self, account=0):
        super().__init__(account)
        self._observers = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    @classmethod
    def getGlobalInstance(cls):
        if cls._global_instance is None:
            cls._global_instance = cls(0)
        return cls._global_instance

    def addObserver(self, observer, notification_id: int):
        if observer is None:
            return
        notification_id = int(notification_id)
        observers = self._observers.setdefault(notification_id, [])
        if observer not in observers:
            observers.append(observer)

    def removeObserver(self, observer, notification_id: int):
        notification_id = int(notification_id)
        if notification_id in self._observers:
            self._observers[notification_id] = [
                obs for obs in self._observers[notification_id] if obs != observer
            ]

    def postNotificationName(self, notification_id: int, *args):
        notification_id = int(notification_id)
        observers = list(self._observers.get(notification_id, []))
        for obs in observers:
            try:
                if hasattr(obs, "didReceivedNotification"):
                    obs.didReceivedNotification(notification_id, self.currentAccount, args)
                elif callable(obs):
                    try:
                        obs(notification_id, self.currentAccount, *args)
                    except TypeError:
                        obs(*args)
            except Exception:
                pass


class DownloadController(_Instance):
    _instances = {}

    AUTODOWNLOAD_TYPE_PHOTO = 1
    AUTODOWNLOAD_TYPE_AUDIO = 2
    AUTODOWNLOAD_TYPE_VIDEO = 4
    AUTODOWNLOAD_TYPE_DOCUMENT = 8

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def canDownloadMedia(self, type_flag, size=0):
        return True

    def checkAutodownloadSettings(self):
        return True

    def getCurrentDownloadArchive(self):
        return None


class MessagesStorage(_Instance):
    _instances = {}

    @classmethod
    def getInstance(cls, account=0):
        account = int(account or 0)
        if account not in cls._instances:
            cls._instances[account] = cls(account)
        return cls._instances[account]

    def getDatabase(self):
        return _compat.Stub("SQLiteDatabase")

    def getStorageQueue(self):
        import client_utils
        return client_utils.get_queue_by_name("storage_queue")


class MediaController(_Instance):
    _instance = None

    @classmethod
    def getInstance(cls):
        if cls._instance is None:
            cls._instance = cls(0)
        return cls._instance

    def playMessage(self, message):
        return True

    def pauseMessage(self, message):
        return True

    def stopAudio(self):
        return True

    def isPlayingMessage(self, message):
        return False

    def getPlayingMessageObject(self):
        return None


def install(shims):
    tgnet = shims.setdefault("org.telegram.tgnet", {})
    tgnet.update({
        "TLRPC": TLRPC,
        "TLObject": tl_runtime.TLObject,
        "ConnectionsManager": ConnectionsManager,
        "RequestDelegate": RequestDelegate,
    })
    tl = shims.setdefault("org.telegram.tgnet.tl", {})
    for name in ("TL_stars", "TL_account", "TL_bots", "TL_stories",
                 "TL_payments", "TL_chatlists", "TL_fragment", "TL_premium",
                 "TL_smsjobs", "TL_phone", "TL_business", "TL_stats",
                 "TL_channels", "TL_messages", "TL_contacts", "TL_users",
                 "TL_photos", "TL_upload", "TL_help", "TL_updates"):
        tl[name] = tl_runtime._Namespace(name)
    messenger = shims.setdefault("org.telegram.messenger", {})
    messenger["MessagesController"] = MessagesController
    messenger["UserConfig"] = UserConfig
    messenger["ContactsController"] = ContactsController
    messenger["MediaDataController"] = MediaDataController
    messenger["SendMessagesHelper"] = SendMessagesHelper
    messenger["FileLoader"] = FileLoader
    messenger["DownloadController"] = DownloadController
    messenger["NotificationCenter"] = NotificationCenter
    messenger["MessagesStorage"] = MessagesStorage
    messenger["MediaController"] = MediaController
    shims.setdefault("org.telegram.ui", {})["ChatActivity"] = ChatActivity
