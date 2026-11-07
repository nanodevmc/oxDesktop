import asyncio
from asyncio import Future
from typing import List, Optional, Any

from android_utils import run_on_ui_thread
from client_utils import get_file_loader, get_notification_center, NotificationCenterDelegate

from org.telegram.tgnet import TLRPC
from org.telegram.messenger import FileLoader, MessageObject, NotificationCenter, ImageLocation

from .async_tools import _safe_set_future_result, async_manager
from .logs import _logger


class _MediaDownloadObserver:
    def __init__(self, target_file_name: str, future: Future):
        self.target_file_name = target_file_name
        self.future = future
        self.delegate = NotificationCenterDelegate()
        self.delegate.didReceivedNotification = self.notification_received

    # noinspection PyUnusedLocal
    def notification_received(self, notification_id: int, account: int, args: List[Any]):
        if not args or not args[0]:
            return

        file_name = str(args[0])
        if file_name != self.target_file_name:
            return

        if self.future.done():
            return

        loop = async_manager.loop
        if notification_id == NotificationCenter.fileLoaded:
            _logger.debug(f"File '{self.target_file_name}' downloaded successfully.")
            _safe_set_future_result(self.future, True)
        elif notification_id == NotificationCenter.fileLoadFailed:
            _logger.debug(f"File '{self.target_file_name}' download failed.")
            _safe_set_future_result(self.future, False)


async def ensure_media_downloaded(msg_obj: MessageObject) -> bool:
    media: Optional[TLRPC.MessageMedia] = MessageObject.getMedia(msg_obj)
    if not media:
        _logger.debug(f"Media not found in MessageObject: {msg_obj}")
        return False

    file_loader = get_file_loader()
    attachment = media.photo or media.document
    file_name = FileLoader.getAttachFileName(attachment)
    file_path = file_loader.getPathToAttach(attachment, True)

    if file_path and file_path.exists() and file_path.length() > 0:
        _logger.debug(f"Media already exists: {file_path.getAbsolutePath()}")
        return True

    _logger.debug(f"Starting download for {file_name}...")

    future = asyncio.get_running_loop().create_future()
    observer = _MediaDownloadObserver(file_name, future)
    nc = get_notification_center()

    def start_download():
        nc.addObserver(observer.delegate, NotificationCenter.fileLoaded)
        nc.addObserver(observer.delegate, NotificationCenter.fileLoadFailed)

        if msg_obj.isPhoto():
            location = ImageLocation.getForPhoto(
                FileLoader.getClosestPhotoSizeWithSize(media.photo.sizes, 9999),
                media.photo
            )
            file_loader.loadFile(location, "image", "jpg", 1, 1)
        else:
            file_loader.loadFile(media.document, None, 1, 1)

    def stop_download():
        nc.removeObserver(observer.delegate, NotificationCenter.fileLoaded)
        nc.removeObserver(observer.delegate, NotificationCenter.fileLoadFailed)

    run_on_ui_thread(start_download)
    try:
        success = await future
    except Exception:
        _logger.error(f"Exception during download:", exc_info=True)
        success = False
    run_on_ui_thread(stop_download)

    return success
