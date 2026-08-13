"""
Wraps the Flask app (server.py) in a native OS window via pywebview, so
VideoCheck feels like a real desktop app instead of "go open a browser tab".

pywebview uses the OS's built-in webview control — WebView2 on Windows,
WKWebView on macOS, WebKitGTK on Linux — so there's no bundled browser
engine and no separate window chrome/tabs/address bar.

If pywebview (or its native runtime, e.g. WebView2 on a bare Windows VM
that doesn't have it) isn't available, this falls back to opening a normal
browser tab rather than crashing — same server, same UI, just less native.
"""
import threading
import webbrowser

from .config import Config
from .pipeline import VideoPipeline
from .server import create_app


def _fallback_to_browser(url: str, reason: str) -> None:
    print(f"[desktop] Native window unavailable ({reason}) — opening a browser tab instead.")
    print("[desktop] Tip: on Windows, install the Microsoft Edge WebView2 Runtime:")
    print("[desktop]   https://developer.microsoft.com/microsoft-edge/webview2/")
    webbrowser.open(url)
    input("VideoCheck is running in your browser. Press Enter here to stop the server.\n")


def run_desktop(pipeline: VideoPipeline, config: Config,
                 host: str = "127.0.0.1", port: int = 8765) -> None:
    app = create_app(pipeline, config)

    def _serve() -> None:
        app.run(host=host, port=port, debug=False, use_reloader=False)

    threading.Thread(target=_serve, daemon=True).start()
    url = f"http://{host}:{port}/"

    try:
        import webview
    except ImportError:
        _fallback_to_browser(url, "pywebview not installed")
        return

    try:
        webview.create_window("VideoCheck", url, width=1040, height=820, min_size=(760, 600))
        webview.start()
    except Exception as exc:
        _fallback_to_browser(url, str(exc))
