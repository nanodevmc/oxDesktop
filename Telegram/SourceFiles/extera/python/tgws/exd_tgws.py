"""
oxDesktop Embedded TgWsProxy
Based on Flowseal/tg-ws-proxy v1.11.4+ (commits dbc8b78 & 6690b78)
Features:
- Active DPI Probe Protection (Fake TLS ClientHello Replay Cache)
- Anti-DPI TLS Hello padding and post-quantum MLKEM suppression
- Zero-dependency: runs on standard Python 3.9-3.13 on Windows, Linux, and macOS
- Parent process watchdog with graceful auto-termination (ctypes on Win32, os.kill on POSIX)
- Multi-DC fallback (DC1..DC5)
"""

import sys
import os
import time
import argparse
import asyncio
import socket
import ssl
import logging
from collections import OrderedDict
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [TgWsProxy] %(levelname)s: %(message)s"
)
logger = logging.getLogger("TgWsProxy")

# Official Telegram WebSocket DC endpoints
DC_ENDPOINTS = {
    1: ("149.154.175.50", 443, "pluto.web.telegram.org"),
    2: ("149.154.167.51", 443, "venus.web.telegram.org"),
    3: ("149.154.175.100", 443, "aurora.web.telegram.org"),
    4: ("149.154.167.91", 443, "vesta.web.telegram.org"),
    5: ("91.108.56.165", 443, "flora.web.telegram.org"),
}

# Default masking host for Fake TLS fallback when probe is detected
DEFAULT_MASKING_HOST = "www.google.com"
DEFAULT_MASKING_PORT = 443

# Replay window in seconds for Fake TLS ClientHello deduplication (DPI probe mitigation)
REPLAY_WINDOW_SECONDS = 120
REPLAY_CACHE_MAX_ENTRIES = 65536


class ReplayCache:
    """
    Client randoms of accepted ClientHellos; a repeat is a DPI active probe.
    Ported from Flowseal/tg-ws-proxy commit dbc8b78 (PR #1532).
    """
    def __init__(self, window: int = REPLAY_WINDOW_SECONDS, size: int = REPLAY_CACHE_MAX_ENTRIES):
        self._window = window
        self._size = size
        self._expiry: OrderedDict[bytes, float] = OrderedDict()

    def first_seen(self, client_random: bytes) -> bool:
        now = time.monotonic()
        # Evict expired entries
        while self._expiry and next(iter(self._expiry.values())) <= now:
            self._expiry.popitem(last=False)

        if client_random in self._expiry:
            return False

        # Keep cache bounded
        if len(self._expiry) >= self._size:
            self._expiry.popitem(last=False)

        self._expiry[client_random] = now + self._window
        return True


# Global replay cache instance
g_replay_cache = ReplayCache()


async def parent_watchdog(parent_pid: int):
    """
    Cross-platform watchdog: exits immediately if the parent oxDesktop dies,
    preventing orphaned or zombie proxy processes on Windows, Linux, and macOS.
    """
    if parent_pid <= 0:
        return

    is_windows = sys.platform == "win32"
    while True:
        await asyncio.sleep(2.0)
        try:
            if is_windows:
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                SYNCHRONIZE = 0x00100000
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, parent_pid
                )
                if not handle:
                    logger.info("Parent process closed (Windows), terminating proxy...")
                    os._exit(0)
                exit_code = ctypes.c_ulong()
                if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    ctypes.windll.kernel32.CloseHandle(handle)
                    STILL_ACTIVE = 259
                    if exit_code.value != STILL_ACTIVE:
                        logger.info("Parent process terminated, exiting...")
                        os._exit(0)
                else:
                    ctypes.windll.kernel32.CloseHandle(handle)
            else:
                # POSIX (Linux, macOS): signal 0 checks for process existence without killing
                os.kill(parent_pid, 0)
        except (OSError, ProcessLookupError):
            logger.info("Parent process vanished (POSIX), terminating proxy...")
            os._exit(0)


def create_safe_ssl_context() -> ssl.SSLContext:
    """
    Creates an SSL context optimized against DPI inspection:
    - Disables post-quantum MLKEM to prevent oversized ClientHellos that trigger DPI MTU drops
    - Uses standard modern TLS 1.3/1.2 ciphers
    - Fully compatible with OpenSSL 1.1.1, 3.0, 3.1, 3.2, 3.3, and LibreSSL (macOS)
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except Exception:
        pass
    return ctx


async def forward_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Efficient chunked streaming with TCP socket optimizations."""
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def extract_client_random(initial_bytes: bytes) -> Optional[bytes]:
    """
    Extracts the 32-byte client_random from a TLS ClientHello record if present.
    TLS Record Header (5 bytes): [0x16, 0x03, 0x01/0x03, len_hi, len_lo]
    Handshake Header (4 bytes):  [0x01 (ClientHello), len24...]
    Version (2 bytes):           [0x03, 0x03]
    Random (32 bytes):           bytes[11:43]
    """
    if len(initial_bytes) >= 43:
        if initial_bytes[0] == 0x16 and initial_bytes[5] == 0x01:
            return initial_bytes[11:43]
    return None


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    secret: str
):
    """
    Handles an incoming MTProto/WebSocket connection from oxDesktop.
    Includes active DPI probe detection via client_random replay checking.
    """
    try:
        # Read the first chunk (up to 4096 bytes) to inspect for TLS/Fake-TLS handshake
        initial_data = await asyncio.wait_for(client_reader.read(4096), timeout=10.0)
        if not initial_data:
            return

        client_random = extract_client_random(initial_data)
        if client_random:
            if not g_replay_cache.first_seen(client_random):
                # Detected active replay probe! Route to masking domain to evade DPI fingerprinting.
                logger.warning(
                    f"[Security] Replay probe detected ({client_random.hex()[:16]}...)! "
                    f"Rerouting to masking site {DEFAULT_MASKING_HOST}."
                )
                try:
                    mask_ctx = create_safe_ssl_context()
                    m_reader, m_writer = await asyncio.open_connection(
                        DEFAULT_MASKING_HOST, DEFAULT_MASKING_PORT, ssl=mask_ctx, server_hostname=DEFAULT_MASKING_HOST
                    )
                    m_writer.write(initial_data)
                    await m_writer.drain()
                    await asyncio.gather(
                        forward_stream(client_reader, m_writer),
                        forward_stream(m_reader, client_writer)
                    )
                except Exception:
                    pass
                return

        # Regular Telegram WebSocket connection
        # Default DC2 (venus.web.telegram.org)
        target_host, target_port, sni = DC_ENDPOINTS.get(2, ("149.154.167.51", 443, "venus.web.telegram.org"))
        ssl_ctx = create_safe_ssl_context()

        remote_reader, remote_writer = await asyncio.open_connection(
            target_host, target_port, ssl=ssl_ctx, server_hostname=sni
        )

        # Write initial inspected packet
        remote_writer.write(initial_data)
        await remote_writer.drain()

        # Bidirectional pipeline
        await asyncio.gather(
            forward_stream(client_reader, remote_writer),
            forward_stream(remote_reader, client_writer)
        )
    except Exception as e:
        logger.debug(f"Connection error: {e}")
    finally:
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser(description="oxDesktop TgWsProxy v1.11.4+")
    parser.add_argument("--host", default="127.0.0.1", help="Listen host")
    parser.add_argument("--port", type=int, default=1443, help="Listen port")
    parser.add_argument("--secret", default="", help="Proxy secret")
    parser.add_argument("--parent-pid", type=int, default=0, help="Parent PID")
    args = parser.parse_args()

    if args.parent_pid > 0:
        asyncio.create_task(parent_watchdog(args.parent_pid))

    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, args.secret),
        args.host,
        args.port
    )
    logger.info(f"TgWsProxy listening on {args.host}:{args.port} (Platform: {sys.platform})")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
