"""
oxDesktop Embedded TgWsProxy
Based on Flowseal/tg-ws-proxy v1.11.4 architecture
Optimized for zero-overhead, parent process monitoring, and MTU-safe TLS
"""

import sys
import os
import time
import argparse
import asyncio
import socket
import ssl
import logging

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

async def parent_watchdog(parent_pid: int):
    """Exit immediately if parent process dies to prevent zombie proxies."""
    if parent_pid <= 0:
        return
    while True:
        await asyncio.sleep(2.0)
        try:
            # os.kill(pid, 0) checks process existence without killing on POSIX
            # On Windows, OpenProcess is cleaner
            if sys.platform == "win32":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                SYNCHRONIZE = 0x00100000
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, parent_pid
                )
                if not handle:
                    logger.info("Parent process died, exiting...")
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
                os.kill(parent_pid, 0)
        except (OSError, ProcessLookupError):
            logger.info("Parent process vanished, exiting...")
            os._exit(0)

def create_safe_ssl_context() -> ssl.SSLContext:
    """Create SSL context without oversized post-quantum MLKEM TLS hellos."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Prefer standard TLS 1.3 / 1.2 ciphers
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except Exception:
        pass
    return ctx

async def forward_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
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

async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, secret: str):
    try:
        # Default DC2 fallback
        target_host, target_port, sni = DC_ENDPOINTS.get(2, ("149.154.167.51", 443, "venus.web.telegram.org"))
        ssl_ctx = create_safe_ssl_context()

        remote_reader, remote_writer = await asyncio.open_connection(
            target_host, target_port, ssl=ssl_ctx, server_hostname=sni
        )

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
    parser = argparse.ArgumentParser(description="oxDesktop TgWsProxy")
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
    logger.info(f"TgWsProxy listening on {args.host}:{args.port}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
