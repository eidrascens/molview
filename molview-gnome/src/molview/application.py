"""Application lifecycle and global actions."""

from __future__ import annotations

import logging

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from . import __version__
from .main_window import MainWindow

LOGGER = logging.getLogger(__name__)


class MolViewApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="org.example.MolView",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._window: MainWindow | None = None
        self.connect("open", self._on_open_files)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def do_activate(self) -> None:
        LOGGER.debug("Application activate signal")
        if self._window is None:
            self._window = MainWindow(application=self)
        self._window.present()

    def _on_open_files(self, _app: Gio.Application, files: list[Gio.File], _n_files: int, _hint: str) -> None:
        """Handle desktop/file-manager Open With and CLI path arguments."""
        LOGGER.info("Application received file-open request for %d item(s)", len(files))
        self.do_activate()
        if not files or self._window is None:
            return

        # MolView is a single-document viewer: open the first input and state
        # clearly in the log when a caller supplies a batch of paths.
        if len(files) > 1:
            LOGGER.warning(
                "Received %d structure paths; this viewer displays one structure at a time. Opening the first path.",
                len(files),
            )
        file = files[0]
        path = file.get_path()
        if path:
            self._window.open_structure_path(path)
        else:
            LOGGER.error("Cannot open non-local GFile from command line: %s", file.get_uri())

    def _on_about(self, _action: Gio.SimpleAction, _parameter: object) -> None:
        dialog = Gtk.AboutDialog(transient_for=self._window, modal=True)
        dialog.set_program_name("MolView GNOME")
        dialog.set_version(__version__)
        dialog.set_comments("A native GNOME shell for Mol* macromolecular visualization.")
        dialog.set_website("https://molstar.org/")
        dialog.set_website_label("Mol* project")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.present()
