"""
oxDesktop Embedded TgWsProxy
Official Flowseal/tg-ws-proxy v1.11.4 core port.
Zero-dependency embedded Python engine for Windows, Linux, and macOS.
"""
from __future__ import annotations

import sys
import os

# Ensure the proxy package is resolvable regardless of working directory
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from proxy.tg_ws_proxy import main, run_proxy, proxy_config

if __name__ == "__main__":
    main()
