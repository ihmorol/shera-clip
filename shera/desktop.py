"""Desktop shell (D30): the same loopback server in a native window via pywebview.

A shell, not a second product: the window just shows the review UI the browser would.
The browser workflow (`python -m shera`) stays the default; pywebview is an optional
[desktop] extra and is imported lazily so the CLI never pays for it.
"""
import socket
import sys
import threading
import time

import httpx
import uvicorn

from shera import config, pipeline
from shera.app import app


def _url():
    """Computed on every use: config.PORT can be repointed after this module is imported."""
    return f"http://{config.HOST}:{config.PORT}/"


def _live_server():
    """True when a Shera Clip server already answers on the configured port (reuse it)."""
    try:
        return httpx.get(_url(), timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def _port_free():
    probe = socket.socket()
    try:
        probe.bind((config.HOST, config.PORT))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _start_server():
    """Start the loopback server in a daemon thread, exactly as `python -m shera` would.
    -> the uvicorn.Server, or None when the port is taken by another program."""
    if not _port_free():
        return None
    pipeline.on_start()  # db init, ledger recovery, resume interrupted jobs
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning"))
    server.install_signal_handlers = lambda: None  # that API may only run in the main thread
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return server if server.started else None


def check_webview2():
    """Windows needs the Evergreen WebView2 runtime; other platforms use their own webview."""
    if sys.platform != "win32":
        return
    import winreg
    keys = (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A7E4C5}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A7E4C5}")
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in keys:
            try:
                with winreg.OpenKey(root, key):
                    return
            except OSError:
                pass
    raise ValueError("Microsoft Edge WebView2 is not installed, so the desktop window cannot open. "
                     "Install it from https://developer.microsoft.com/microsoft-edge/webview2/ "
                     "(preinstalled on Windows 11), or run the app in the browser with `python -m shera`.")


def run_window():
    """Open the window; blocks until it closes. Reuses a running server, else starts one
    and stops it when the window closes — the same lifetime as the terminal workflow."""
    server = None
    if not _live_server():
        server = _start_server()
        if server is None:
            raise ValueError(f"Port {config.PORT} is in use by another program, so the desktop window "
                             f"cannot open the app. Set SHERA_PORT in .env and try again.")
    import webview
    window = webview.create_window("Shera Clip", _url(), width=1280, height=800, min_size=(960, 600))
    if server is not None:
        window.events.closed += lambda: setattr(server, "should_exit", True)
    webview.start()
