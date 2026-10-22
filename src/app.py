from typing import Self

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, Gtk

from src.version import __version__


class MolView(Adw.Application):
    def __init__(self: Self) -> None:
        super().__init__(
            application_id="org.molview.MolView",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._window: MainWindow | None = None
        self.connect("open", self._on_open_files)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def _on_about(
        self: Self,
        _action: Gio.SimpleAction,
        _parameter: object
    ) -> None:
        dialog = Gtk.AboutDialog(
                transient_for=self._window, modal=True
            )
        dialog.set_program_name("MolView")
        dialog.set_version(__version__)
        dialog.set_comments("GTK4 Interface for Mol*.")
        dialog.set_license_type(Gtk.License.GPL_3_0_ONLY)
        dialog.present()
