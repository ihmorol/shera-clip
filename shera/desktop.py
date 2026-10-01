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
    """True when a Shera Clip server already answers on the configured port (reuse it).
    The page must carry the app's own branding, so a foreign program squatting on the
    port is not mistaken for Shera Clip and rendered in our window."""
    try:
        r = httpx.get(_url(), timeout=1.0)
        return r.status_code == 200 and b"Shera Clip" in r.content
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
    """Start the loopback server in a background thread, exactly as `python -m shera` would.
    -> (server, thread), or (None, None) when the port is taken by another program. Raises
    with the real cause when the server fails some other way, instead of waiting it out."""
    if not _port_free():
        return None, None
    pipeline.on_start()  # db init, ledger recovery, resume interrupted jobs
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning"))
    server.install_signal_handlers = lambda: None  # that API may only run in the main thread
    failure = {}

    def _serve():
        try:
            server.run()
        except BaseException as e:  # a startup failure must surface, not die in the thread
            failure["error"] = e

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        if failure:
            raise ValueError(f"The desktop server could not start: {failure['error']!r}")
        time.sleep(0.05)
    if not server.started:
        return None, None
    return server, thread


def check_webview2():
    """Windows needs the Evergreen WebView2 runtime; other platforms use their own webview."""
    if sys.platform != "win32":
        return
    import winreg
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in (rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}",
                    rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"):
            try:
                with winreg.OpenKey(root, sub):
                    return
            except OSError:
                pass
    from pathlib import Path
    if Path("C:/Program Files (x86)/Microsoft/EdgeWebView/Application").is_dir():
        return
    raise ValueError("Microsoft Edge WebView2 is not installed, so the desktop window cannot open. "
                     "Install it from https://developer.microsoft.com/microsoft-edge/webview2/ "
                     "(preinstalled on Windows 11), or run the app in the browser with `python -m shera`.")


def run_window():
    """Open the window; blocks until it closes. Reuses a running server, else starts one
    and stops it (gracefully, bounded) when the window closes. -> "started" | "reused"."""
    server = thread = None
    if not _live_server():
        server, thread = _start_server()
        if server is None:
            raise ValueError(f"Port {config.PORT} is in use by another program, so the desktop window "
                             f"cannot open the app. Set SHERA_PORT in .env and try again.")
    import webview
    window = webview.create_window("Shera Clip", _url(), width=1280, height=800, min_size=(960, 600))
    if server is not None:
        window.events.closed += lambda: setattr(server, "should_exit", True)
    webview.start()
    if server is not None:  # deterministic stop even if the closed event raced the exit
        server.should_exit = True
        thread.join(timeout=10)
    return "reused" if server is None else "started"
