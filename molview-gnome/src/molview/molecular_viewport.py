"""WebKitGTK 6.0 host for the Mol* viewport and verbose diagnostics."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gdk, GLib, Gtk, WebKit  # noqa: E402

from .errors import ViewerUnavailableError

LOGGER = logging.getLogger(__name__)
class MolecularViewport(Gtk.Box):
    """Embedded Mol* viewport; native GTK owns all controls and file opening."""

    def __init__(self, on_message: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._on_message = on_message
        self._ready = False
        self._frontend_available = False
        self._pending_structure: tuple[str, str] | None = None
        self._asset_dir = self._find_asset_dir()
        index = self._asset_dir / "index.html"
        self._index_uri = index.as_uri() if index.is_file() else None
        LOGGER.info("Initializing WebKitGTK viewport; assets=%s", self._asset_dir)
        LOGGER.debug("Expected Mol* index=%s, bundle=%s", index, self._asset_dir / "viewer.js")

        self._content_manager = WebKit.UserContentManager.new()
        # Connect first, then register to avoid missing early page messages.
        self._content_manager.connect(
            "script-message-received::native", self._on_script_message
        )
        if not self._content_manager.register_script_message_handler("native", None):
            raise RuntimeError("Could not register the WebKitGTK JavaScript message handler.")

        self.webview = WebKit.WebView(user_content_manager=self._content_manager)
        transparent = Gdk.RGBA()
        transparent.red = transparent.green = transparent.blue = 0.0
        transparent.alpha = 0.0
        self.webview.set_background_color(transparent)
        settings = self.webview.get_settings()
        try:
            settings.set_enable_developer_extras(
                os.environ.get("MOLVIEW_WEBKIT_INSPECTOR", "0") == "1"
            )
            settings.set_enable_write_console_messages_to_stdout(True)
        except (AttributeError, TypeError, GLib.Error):
            LOGGER.debug("One or more WebKit diagnostic settings are unavailable", exc_info=True)

        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.connect("load-failed", self._on_load_failed)
        self.webview.connect("decide-policy", self._on_decide_policy)
        self.webview.connect("web-process-terminated", self._on_web_process_terminated)
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)
        self.append(self.webview)

        bundle = self._asset_dir / "viewer.js"
        if not index.is_file() or not bundle.is_file():
            missing = [str(item) for item in (index, bundle) if not item.is_file()]
            LOGGER.error("Mol* frontend assets missing: %s", missing)
            self.webview.load_html(
                """<!doctype html><html><body style="font:14px sans-serif;padding:24px">
                <h3>Mol* frontend not built</h3>
                <p>From the project directory, run <code>npm install</code> and
                <code>npm run build</code>, then restart MolView GNOME.</p>
                </body></html>"""
            )
            GLib.idle_add(self._on_message, {
                "type": "error",
                "message": "Mol* frontend assets are missing. Run `npm install && npm run build` in the project directory.",
            })
        else:
            self._frontend_available = True
            LOGGER.info("Loading bundled Mol* entry page: %s", self._index_uri)
            self.webview.load_uri(self._index_uri)

    @staticmethod
    def _find_asset_dir() -> Path:
        override = os.environ.get("MOLVIEW_WEB_ASSETS")
        if override:
            return Path(override).expanduser().resolve()
        project_root = Path(__file__).resolve().parents[2]
        return project_root / "web" / "dist"

    def _on_decide_policy(self, _webview: Any, decision: Any, decision_type: Any) -> bool:
        """Prevent accidental navigation away from the bundled viewer page."""
        if decision_type != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        try:
            # WebKitGTK 6 prefers NavigationPolicyDecision.navigation_action;
            # older APIs exposed the request directly on the decision.
            action = decision.get_navigation_action() if hasattr(decision, "get_navigation_action") else None
            request = action.get_request() if action is not None else decision.get_request()
            uri = request.get_uri() if request is not None else ""
        except Exception:
            LOGGER.exception("Could not inspect WebKit navigation request")
            return False
        if not uri or uri == self._index_uri:
            return False

        LOGGER.warning("Blocked unexpected WebKit top-level navigation: %s", uri)
        decision.ignore()
        return True

    def _on_load_changed(self, webview: Any, event: Any) -> None:
        try:
            event_name = getattr(event, "value_nick", str(event))
            LOGGER.info("WebKit load-changed: event=%s uri=%s", event_name, webview.get_uri())
        except Exception:
            LOGGER.exception("Could not inspect WebKit load-changed event")

    def _on_script_message(self, _manager: Any, value: Any) -> None:
        """Parse JS-to-Python bridge messages; record all messages in the log."""
        try:
            js_value = value.get_js_value() if hasattr(value, "get_js_value") else value
            raw = js_value.to_string() if hasattr(js_value, "to_string") else str(js_value)
            message = json.loads(raw)
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                raise ValueError("Bridge message must be a JSON object with a string 'type'.")
            kind = message["type"]
            LOGGER.debug("JS bridge [%s]: %s", kind, json.dumps(message, ensure_ascii=False, default=str)[:5000])
            if kind in {"console-error", "js-error", "unhandled-rejection", "error"}:
                LOGGER.error("Frontend reported %s: %s", kind, message.get("message", message))
            elif kind == "console-warning":
                LOGGER.warning("Frontend reported warning: %s", message.get("message", message))
            elif kind in {"molstar-log", "diagnostics", "render-diagnostics"}:
                LOGGER.info("Frontend %s: %s", kind, message)
            if kind == "ready":
                self._ready = True
            self._on_message(message)
            if kind == "ready" and self._pending_structure is not None:
                GLib.idle_add(self._load_pending_structure)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            LOGGER.exception("Invalid message from molecular viewer")
            self._on_message({"type": "error", "message": f"Invalid message from molecular viewer: {exc}"})
        except Exception as exc:  # defensive boundary around GI/JavaScriptCore conversions
            LOGGER.exception("Could not process viewer message")
            self._on_message({"type": "error", "message": f"Could not process viewer message: {exc}"})

    def _on_load_failed(self, _webview: Any, event: Any, uri: str, error: GLib.Error) -> bool:
        LOGGER.error(
            "WebKit load failed: event=%s uri=%s domain=%s code=%s message=%s",
            getattr(event, "value_nick", str(event)), uri, getattr(error, "domain", "?"),
            getattr(error, "code", "?"), error.message,
        )
        self._on_message({
            "type": "error",
            "message": f"WebKit load failed for {uri}: {error.message} (domain={getattr(error, 'domain', '?')}, code={getattr(error, 'code', '?')}). See ~/.local/state/molview-gnome/molview.log.",
        })
        return True

    def _on_web_process_terminated(self, _webview: Any, reason: Any) -> None:
        self._ready = False
        LOGGER.critical("WebKit web process terminated: %s", reason)
        self._on_message({
            "type": "error",
            "message": f"The WebKit web process exited ({reason}). See ~/.local/state/molview-gnome/molview.log for diagnostics.",
        })

    def load_structure_text(self, text: str, name: str) -> None:
        """Pass structure content to JavaScript as typed GVariant arguments."""
        LOGGER.info("Request to load structure: name=%s chars=%d viewer_ready=%s", name, len(text), self._ready)
        if not self._frontend_available:
            raise ViewerUnavailableError(
                "Mol* frontend assets are missing. Run `npm install && npm run build` in the project directory."
            )
        if not self._ready:
            self._pending_structure = (text, name)
            LOGGER.info("Queued structure until Mol* is ready: %s", name)
            self._on_message({"type": "info", "message": f"Waiting for the molecular renderer before loading {name}…"})
            return
        self._dispatch_structure(text, name)

    def _load_pending_structure(self) -> bool:
        pending = self._pending_structure
        self._pending_structure = None
        if pending is not None:
            try:
                self._dispatch_structure(*pending)
            except Exception as exc:
                LOGGER.exception("Could not dispatch queued structure")
                self._on_message({"type": "error", "message": f"Could not dispatch queued structure: {exc}"})
        return GLib.SOURCE_REMOVE

    def _dispatch_structure(self, text: str, name: str) -> None:
        try:
            arguments = GLib.Variant("a{sv}", {
                "text": GLib.Variant("s", text),
                "name": GLib.Variant("s", name),
            })
            LOGGER.debug("Calling window.proteinViewer.loadStructureText for %s", name)
            self.webview.call_async_javascript_function(
                "return await window.proteinViewer.loadStructureText(text, name);",
                -1, arguments, None, None, None,
                self._on_javascript_finished, {"operation": f"load {name}"},
            )
        except (GLib.Error, TypeError, ValueError) as exc:
            LOGGER.exception("Could not pass %s to the Mol* frontend", name)
            raise ViewerUnavailableError(f"Could not pass the structure to Mol*: {exc}") from exc

    def call(self, method: str, *args: Any) -> None:
        """Invoke a named viewer action without returning a JS Promise to WebKit.

        WebKitGTK's evaluate_javascript_finish() cannot deserialize a Promise
        result. The JavaScript wrapper therefore returns a boolean immediately
        and forwards asynchronous completion/errors through the native message
        bridge instead.
        """
        if not self._ready:
            LOGGER.warning("Viewer action requested before ready: %s(%r)", method, args)
            self._on_message({"type": "error", "message": "The molecular viewer is not ready yet."})
            return
        encoded_args = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        encoded_method = json.dumps(method)
        script = f"""(() => {{
          const reportError = (error) => {{
            const detail = {{
              type: 'error',
              message: error && error.message ? String(error.message) : String(error),
              stack: error && error.stack ? String(error.stack) : ''
            }};
            try {{ window.webkit.messageHandlers.native.postMessage(JSON.stringify(detail)); }}
            catch (_) {{ console.error('Could not send viewer action error to Python', error); }}
          }};
          try {{
            const api = window.proteinViewer;
            const method = {encoded_method};
            if (!api || typeof api[method] !== 'function')
              throw new Error('Viewer API is not ready or does not expose this action.');
            const result = api[method](...{encoded_args});
            if (result && typeof result.then === 'function') result.catch(reportError);
            return true;
          }} catch (error) {{
            reportError(error);
            return false;
          }}
        }})()"""
        try:
            LOGGER.debug("Calling Mol* API method=%s args=%s", method, encoded_args[:1000])
            self.webview.evaluate_javascript(
                script, -1, None, None, None, self._on_javascript_finished,
                {"operation": method},
            )
        except (GLib.Error, TypeError) as exc:
            LOGGER.exception("Could not invoke Mol* action %s", method)
            self._on_message({"type": "error", "message": f"Could not run viewer action {method}: {exc}"})

    def _on_javascript_finished(self, webview: Any, result: Any, user_data: Any = None) -> None:
        operation = user_data.get("operation", "viewer action") if isinstance(user_data, dict) else "viewer action"
        try:
            if isinstance(user_data, dict) and str(operation).startswith("load "):
                value = webview.call_async_javascript_function_finish(result)
            else:
                value = webview.evaluate_javascript_finish(result)
            LOGGER.debug("JavaScript operation completed: %s result=%s", operation, value)
        except Exception as exc:
            LOGGER.exception("JavaScript operation failed: %s", operation)
            self._on_message({
                "type": "error",
                "message": f"JavaScript failed during {operation}: {exc}. See ~/.local/state/molview-gnome/molview.log.",
            })

    def reload_viewer(self) -> None:
        """Reload the bundled viewer page after a crash or initialization issue."""
        index = self._asset_dir / "index.html"
        if index.is_file():
            self._ready = False
            self._frontend_available = (self._asset_dir / "viewer.js").is_file()
            self._index_uri = index.as_uri()
            LOGGER.info("Reloading bundled Mol* viewer: %s", self._index_uri)
            self.webview.load_uri(self._index_uri)
        else:
            LOGGER.error("Cannot reload Mol* page; index.html is missing: %s", index)
            self._on_message({"type": "error", "message": "Mol* frontend assets are still missing."})
