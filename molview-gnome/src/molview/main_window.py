"""Native libadwaita window and scientific inspection controls."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from .errors import MolViewError, ViewerUnavailableError
from .molecular_viewport import MolecularViewport
from .structure_service import download_rcsb_structure, read_structure_file

LOGGER = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Application window; state, controls, and rendering are kept separate."""

    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="MolView GNOME")
        # Roughly one third of the former 1360×920 default window area.
        # GTK may choose a larger final size when desktop scaling or content
        # minimums require it, but the initial request stays deliberately small.
        self.set_default_size(780, 540)
        self.set_size_request(600, 420)

        self._summary: dict[str, Any] | None = None
        self._component_rows: dict[Gtk.ListBoxRow, dict[str, Any]] = {}
        self._busy = False
        self._updating_settings = False

        self._build_ui()
        self._install_actions()

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(
                title="MolView",
                subtitle="",
            )
        )

        self.open_button = Gtk.Button.new_from_icon_name("document-open-symbolic")
        self.open_button.set_tooltip_text("Open a PDB or mmCIF structure (Ctrl+O)")
        self.open_button.connect("clicked", lambda *_: self._choose_structure_file())
        header.pack_start(self.open_button)

        # PDB ID loading stays in the header bar beside Open. The default window
        # remains focused on the molecular canvas, without a second toolbar row.
        self.pdb_entry = Gtk.Entry()
        self.pdb_entry.set_placeholder_text("PDB ID…")
        self.pdb_entry.set_max_length(12)
        self.pdb_entry.set_width_chars(6)
        self.pdb_entry.set_size_request(78, -1)
        self.pdb_entry.set_tooltip_text("Enter an RCSB PDB ID, e.g. 1CRN")
        self.pdb_entry.connect("activate", lambda *_: self._load_pdb_id())
        header.pack_start(self.pdb_entry)

        self.pdb_load_button = Gtk.Button(label="Load")
        self.pdb_load_button.add_css_class("suggested-action")
        self.pdb_load_button.set_tooltip_text("Load structure from RCSB PDB")
        self.pdb_load_button.connect("clicked", lambda *_: self._load_pdb_id())
        header.pack_start(self.pdb_load_button)

        # Title-bar tools are intentionally compact; the sidebar remains the
        # home for less frequently changed rendering settings.
        self.illumination_button = Gtk.ToggleButton()
        self.illumination_icon = Gtk.Image.new_from_icon_name("weather-clear-symbolic")
        self.illumination_button.set_child(self.illumination_icon)
        self.illumination_button.set_tooltip_text("Toggle global illumination")
        self.illumination_button.set_valign(Gtk.Align.CENTER)
        self.illumination_button.connect("toggled", self._on_illumination_toggled)

        reset_menu = Gio.Menu.new()
        reset_menu.append("Reset Zoom", "win.reset-zoom")
        reset_menu.append("Orient Axes", "win.orient-axes")
        reset_menu.append("Reset Axes", "win.reset-axes")
        self.reset_menu_button = Gtk.MenuButton()
        reset_contents = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        reset_contents.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        reset_contents.append(Gtk.Label(label="Reset"))
        reset_contents.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self.reset_menu_button.set_child(reset_contents)
        self.reset_menu_button.set_menu_model(reset_menu)
        self.reset_menu_button.set_tooltip_text(
            "Reset zoom, orient axes, or reset the axes orientation"
        )

        self.representation_combo = Gtk.ComboBoxText.new()
        self.representation_combo.append("cartoon", "Cartoon")
        self.representation_combo.append("cartoon-ligands", "Cartoon + ligands")
        self.representation_combo.append("atoms", "Atom detail")
        self.representation_combo.append("surface", "Molecular surface")
        self.representation_combo.set_active_id("cartoon-ligands")
        self.representation_combo.set_size_request(124, -1)
        self.representation_combo.set_tooltip_text("Choose molecular representation")
        self.representation_combo.connect("changed", self._on_representation_changed)

        menu_model = Gio.Menu.new()
        menu_model.append("About MolView GNOME", "app.about")
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name("open-menu-symbolic")
        self.menu_button.set_menu_model(menu_model)
        self.menu_button.set_tooltip_text("Main Menu")
        header.pack_end(self.menu_button)

        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_icon = Gtk.Image.new_from_icon_name("sidebar-show-symbolic")
        self.sidebar_toggle.set_child(self.sidebar_icon)
        self.sidebar_toggle.set_tooltip_text("Show or hide structure inspection sidebar")
        self.sidebar_toggle.set_active(False)
        self.sidebar_toggle.connect("toggled", self._on_sidebar_toggled)
        header.pack_end(self.sidebar_toggle)
        header.pack_end(self.illumination_button)
        header.pack_end(self.reset_menu_button)
        header.pack_end(self.representation_combo)
        root.append(header)

        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_hexpand(True)
        paned.set_position(340)
        paned.set_shrink_start_child(False)
        paned.set_resize_start_child(False)
        root.append(paned)
        self.content_paned = paned

        inspector = self._build_inspector()
        inspector.set_size_request(270, -1)
        inspector.set_margin_start(8)
        inspector.set_margin_end(8)
        inspector.set_margin_bottom(8)
        inspector.set_visible(False)
        self.inspector_sidebar = inspector
        # Gtk.Paned start child is the left-hand pane; keep the inspector on the left.
        paned.set_start_child(inspector)

        viewer_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        viewer_column.set_hexpand(True)
        viewer_column.set_vexpand(True)
        viewer_column.set_margin_start(8)
        viewer_column.set_margin_end(8)
        viewer_column.set_margin_bottom(8)
        self.viewport = MolecularViewport(self._on_viewer_message)
        self.viewport.set_hexpand(True)
        self.viewport.set_vexpand(True)
        self.viewer_overlay = Gtk.Overlay()
        self.viewer_overlay.set_child(self.viewport)
        self.placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.placeholder.set_can_target(False)
        placeholder_icon = Gtk.Image.new_from_icon_name("applications-science-symbolic")
        placeholder_icon.set_pixel_size(48)
        placeholder_icon.add_css_class("dim-label")
        self.placeholder.append(placeholder_icon)
        placeholder_title = Gtk.Label(label="Open a structure to begin")
        placeholder_title.add_css_class("title-2")
        self.placeholder.append(placeholder_title)
        placeholder_help = Gtk.Label(label="Open a local PDB/mmCIF file or enter an RCSB PDB ID above")
        placeholder_help.add_css_class("dim-label")
        self.placeholder.append(placeholder_help)
        self.viewer_overlay.add_overlay(self.placeholder)
        viewer_column.append(self.viewer_overlay)
        # The molecular canvas occupies the right-hand, expanding pane.
        paned.set_end_child(viewer_column)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0.0)
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.status_label.set_margin_start(14)
        self.status_label.set_margin_end(14)
        self.status_label.set_margin_top(4)
        self.status_label.set_margin_bottom(8)
        self.status_label.add_css_class("dim-label")
        self.status_label.set_selectable(True)
        root.append(self.status_label)

    def _on_sidebar_toggled(self, toggle: Gtk.ToggleButton) -> None:
        visible = toggle.get_active()
        self.inspector_sidebar.set_visible(visible)
        self.sidebar_icon.set_from_icon_name(
            "sidebar-hide-symbolic" if visible else "sidebar-show-symbolic"
        )
        toggle.set_tooltip_text(
            "Hide structure inspection sidebar" if visible
            else "Show structure inspection sidebar"
        )
        LOGGER.debug("Inspection sidebar visibility changed: %s", visible)

    def _install_actions(self) -> None:
        actions: list[tuple[str, Callable[[], None]]] = [
            ("open", self._choose_structure_file),
            ("reset-zoom", lambda: self._viewer_call("resetCamera")),
            ("orient-axes", lambda: self._viewer_call("orientAxes")),
            ("reset-axes", lambda: self._viewer_call("resetAxes")),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _parameter, cb=callback: cb())
            self.add_action(action)
        app = self.get_application()
        if app is not None:
            app.set_accels_for_action("win.open", ["<Primary>o"])

    def _build_inspector(self) -> Gtk.Widget:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_margin_top(8)
        self.inspector_stack = Adw.ViewStack()
        self.view_switcher = Adw.ViewSwitcher()
        self.view_switcher.set_stack(self.inspector_stack)
        container.append(self.view_switcher)
        container.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.inspector_stack.set_vexpand(True)
        container.append(self.inspector_stack)

        page = self.inspector_stack.add_titled(self._build_components_page(), "components", "Components")
        page.set_icon_name("view-list-symbolic")
        page = self.inspector_stack.add_titled(self._build_sequence_page(), "sequence", "Sequence")
        page.set_icon_name("text-x-generic-symbolic")
        page = self.inspector_stack.add_titled(self._build_settings_page(), "settings", "Settings")
        page.set_icon_name("preferences-system-symbolic")
        return container

    def _build_settings_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(12)
        page.set_margin_bottom(12)
        page.set_margin_start(8)
        page.set_margin_end(8)
        page.append(self._section_heading("Rendering settings"))

        camera_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        camera_label = Gtk.Label(label="Camera projection", xalign=0.0)
        camera_label.set_hexpand(True)
        camera_row.append(camera_label)
        self.camera_mode_combo = Gtk.ComboBoxText.new()
        self.camera_mode_combo.append("perspective", "Perspective")
        self.camera_mode_combo.append("orthographic", "Orthographic")
        self.camera_mode_combo.set_active_id("perspective")
        self.camera_mode_combo.set_size_request(140, -1)
        self.camera_mode_combo.set_tooltip_text("Choose perspective or orthographic projection")
        self.camera_mode_combo.connect("changed", self._on_camera_mode_changed)
        camera_row.append(self.camera_mode_combo)
        page.append(camera_row)

        self.occlusion_switch = self._append_switch_row(
            page,
            "Ambient occlusion",
            "Adds soft contact shading to crevices.",
            "occlusion",
            True,
        )
        self.shadow_switch = self._append_switch_row(
            page,
            "Shadows",
            "Adds depth cues from cast shadows.",
            "shadow",
            False,
        )
        self.outline_switch = self._append_switch_row(
            page,
            "Outline",
            "Draw outlines around molecular geometry.",
            "outline",
            False,
        )
        note = Gtk.Label(
            label="Global illumination is controlled from the sun icon in the title bar. Some effects may depend on GPU/WebGL support.",
            xalign=0.0,
        )
        note.set_wrap(True)
        note.add_css_class("dim-label")
        page.append(note)
        return page

    def _append_switch_row(
        self,
        parent: Gtk.Box,
        title: str,
        subtitle: str,
        setting: str,
        active: bool,
    ) -> Gtk.Switch:
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(subtitle)
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_active(active)
        switch.connect("notify::active", self._on_render_setting_toggled, setting)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        parent.append(row)
        return switch

    def _build_components_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_top(12)
        page.set_margin_bottom(12)
        page.set_margin_start(8)
        page.set_margin_end(8)
        page.append(self._section_heading("Structure components"))
        note = Gtk.Label(
            label="Select a component to highlight and focus it. Hide toggles visibility; Delete removes it from this view only and does not modify the source file.",
            xalign=0.0,
        )
        note.set_wrap(True)
        note.add_css_class("dim-label")
        page.append(note)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.component_list = Gtk.ListBox()
        self.component_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.component_list.add_css_class("boxed-list")
        scroll.set_child(self.component_list)
        page.append(scroll)

        self.component_empty = Gtk.Label(label="Open a structure to discover its components.")
        self.component_empty.set_xalign(0.0)
        self.component_empty.set_wrap(True)
        self.component_empty.add_css_class("dim-label")
        page.append(self.component_empty)
        return page

    def _build_sequence_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_top(12)
        page.set_margin_bottom(12)
        page.set_margin_start(8)
        page.set_margin_end(8)
        page.append(self._section_heading("Protein sequence"))

        chain_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chain_row.append(Gtk.Label(label="Chain", xalign=0.0))
        self.sequence_chain = Gtk.ComboBoxText.new()
        self.sequence_chain.set_hexpand(True)
        self.sequence_chain.append("", "No structure")
        self.sequence_chain.set_active_id("")
        self.sequence_chain.connect("changed", self._on_sequence_chain_changed)
        chain_row.append(self.sequence_chain)
        page.append(chain_row)

        self.sequence_info = Gtk.Label(label="Sequences will appear here after loading a structure.")
        self.sequence_info.set_xalign(0.0)
        self.sequence_info.add_css_class("dim-label")
        self.sequence_info.set_wrap(True)
        page.append(self.sequence_info)

        sequence_scroll = Gtk.ScrolledWindow()
        sequence_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sequence_scroll.set_vexpand(True)
        sequence_scroll.set_min_content_height(160)
        self.sequence_view = Gtk.TextView()
        self.sequence_view.set_editable(False)
        self.sequence_view.set_cursor_visible(False)
        self.sequence_view.set_monospace(True)
        self.sequence_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.sequence_view.set_left_margin(8)
        self.sequence_view.set_right_margin(8)
        self.sequence_view.set_top_margin(8)
        self.sequence_view.set_bottom_margin(8)
        self.sequence_view.get_buffer().set_text("No sequence loaded")
        sequence_scroll.set_child(self.sequence_view)
        page.append(sequence_scroll)

        note = Gtk.Label(label="Sequences are read from PDB SEQRES or mmCIF polymer entity metadata when available.")
        note.set_xalign(0.0)
        note.set_wrap(True)
        note.add_css_class("dim-label")
        page.append(note)
        return page

    @staticmethod
    def _section_heading(text: str) -> Gtk.Widget:
        label = Gtk.Label(label=text, xalign=0.0)
        label.add_css_class("heading")
        return label

    def _choose_structure_file(self) -> None:
        dialog = Gtk.FileChooserNative.new(
            "Open Structure", self, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel"
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name("PDB and mmCIF structures")
        for pattern in ("*.pdb", "*.PDB", "*.ent", "*.ENT", "*.cif", "*.CIF", "*.mmcif", "*.MMCIF"):
            file_filter.add_pattern(pattern)
        dialog.add_filter(file_filter)
        dialog.connect("response", self._on_file_dialog_response)
        dialog.show()

    def _on_file_dialog_response(self, dialog: Gtk.FileChooserNative, response: int) -> None:
        try:
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                path = file.get_path() if file is not None else None
                if path:
                    self.open_structure_path(path)
        finally:
            dialog.destroy()

    def open_structure_path(self, path: str) -> None:
        LOGGER.info("Open structure request: %s", path)
        self._run_io_task(lambda: read_structure_file(path), f"Opening {path}")

    def _load_pdb_id(self) -> None:
        pdb_id = self.pdb_entry.get_text().strip()
        if not pdb_id:
            self._set_status("Enter a PDB ID first.", error=True)
            self.pdb_entry.grab_focus()
            return
        self._run_io_task(lambda: download_rcsb_structure(pdb_id), f"Downloading PDB {pdb_id.upper()}")

    def _run_io_task(self, work: Callable[[], tuple[str, str]], busy_text: str) -> None:
        if self._busy:
            self._set_status("Another structure operation is already in progress.", error=True)
            return
        self._busy = True
        LOGGER.info("Starting structure I/O task: %s", busy_text)
        self._set_status(busy_text)
        self.pdb_load_button.set_sensitive(False)
        self.open_button.set_sensitive(False)

        def worker() -> None:
            try:
                LOGGER.debug("Structure I/O worker started: %s", busy_text)
                result = work()
                LOGGER.info("Structure I/O completed: name=%s characters=%d", result[1], len(result[0]))
                error: Exception | None = None
            except Exception as exc:  # thread boundary: all failures return to GTK main loop
                LOGGER.exception("Structure I/O failed: %s", busy_text)
                result = None
                error = exc

            def finish() -> bool:
                self._busy = False
                self.pdb_load_button.set_sensitive(True)
                self.open_button.set_sensitive(True)
                if error is not None:
                    LOGGER.error("Structure I/O task failed: %s", error)
                    self._set_status(str(error), error=True)
                    return GLib.SOURCE_REMOVE
                assert result is not None
                try:
                    LOGGER.debug("Dispatching %s to the embedded viewer", result[1])
                    self.viewport.load_structure_text(result[0], result[1])
                except (MolViewError, GLib.Error, RuntimeError, TypeError) as exc:
                    LOGGER.exception("Could not dispatch structure to Mol*")
                    self._set_status(str(exc), error=True)
                else:
                    self._set_status(f"Sending {result[1]} to Mol*…")
                return GLib.SOURCE_REMOVE

            GLib.idle_add(finish)

        threading.Thread(target=worker, name="structure-io", daemon=True).start()

    def _on_viewer_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "ready":
            self._set_status("Mol* is ready. Open a PDB/mmCIF file or load a PDB ID.")
        elif kind == "loading":
            self.placeholder.set_visible(True)
            self._set_status(f"Parsing {message.get('name', 'structure')}…")
        elif kind == "structure-loaded":
            self._summary = message
            self.placeholder.set_visible(False)
            self._populate_structure_summary(message)
            name = message.get("name", "structure")
            residues = message.get("proteinResidueCount", 0)
            chain_count = len(message.get("chains", []))
            component_count = len(message.get("components", []))
            self._set_status(f"Loaded {name} · {residues} sequence residues · {chain_count} chains · {component_count} components")
        elif kind == "components-updated":
            self._populate_components(message.get("components", []))
            if self._summary is not None:
                self._summary["components"] = message.get("components", [])
        elif kind == "component-selected":
            self._set_status(f"Selected {message.get('label', 'component')}.")
        elif kind == "component-removed":
            self._set_status(f"Removed {message.get('label', 'component')} from the current view. The source file is unchanged.")
        elif kind == "representation-changed":
            self._set_status(f"Representation changed to {message.get('name', 'selected preset')}.")
        elif kind == "settings-state":
            settings = message.get("settings", {})
            if isinstance(settings, dict):
                self._apply_viewer_settings(settings)
        elif kind == "settings-updated":
            settings = message.get("settings", {})
            if isinstance(settings, dict):
                self._apply_viewer_settings(settings)
        elif kind == "error":
            self._set_status(str(message.get("message", "Unknown viewer error.")), error=True)

    def _populate_structure_summary(self, summary: dict[str, Any]) -> None:
        chains = summary.get("chains", [])
        self._replace_combo_items(
            self.sequence_chain,
            [(str(chain.get("id", "")), str(chain.get("id", ""))) for chain in chains],
        )
        if not chains:
            self.sequence_info.set_text(
                "Structure loaded, but no recognised amino-acid sequence was recovered. "
                "Check the log for source-format and residue-code diagnostics."
            )
            self.sequence_view.get_buffer().set_text("Sequence unavailable for this structure")
        else:
            self._update_sequence_view()
        self._populate_components(summary.get("components", []))

    def _populate_components(self, components: list[dict[str, Any]]) -> None:
        self._clear_listbox(self.component_list)
        self._component_rows.clear()
        for component in components:
            component_id = str(component.get("id", ""))
            if not component_id:
                continue
            row = Gtk.ListBoxRow()
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            content.set_margin_top(8)
            content.set_margin_bottom(8)
            content.set_margin_start(10)
            content.set_margin_end(10)

            title = Gtk.Label(
                label=f"{component.get('label', 'Component')} · {int(component.get('atomCount', 0)):,} atoms",
                xalign=0.0,
            )
            title.add_css_class("heading")
            title.set_wrap(True)
            content.append(title)

            state = "Hidden" if component.get("hidden") else "Visible"
            category = str(component.get("category", "component"))
            subtitle = Gtk.Label(label=f"{category} · {state}", xalign=0.0)
            subtitle.add_css_class("dim-label")
            subtitle.set_wrap(True)
            content.append(subtitle)

            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            select_button = Gtk.Button(label="Select")
            select_button.connect("clicked", lambda _button, cid=component_id: self._select_component(cid))
            actions.append(select_button)

            visibility_button = Gtk.Button(label="Show" if component.get("hidden") else "Hide")
            visibility_button.connect("clicked", lambda _button, cid=component_id: self._toggle_component(cid))
            actions.append(visibility_button)

            remove_button = Gtk.Button(label="Delete")
            remove_button.add_css_class("destructive-action")
            remove_button.set_tooltip_text("Delete this component from the current view only; the source structure file is unchanged.")
            remove_button.connect("clicked", lambda _button, cid=component_id: self._remove_component(cid))
            actions.append(remove_button)
            content.append(actions)

            row.set_child(content)
            self.component_list.append(row)
            self._component_rows[row] = component

        self.component_empty.set_visible(not bool(components))
        if not components:
            self.component_empty.set_text(
                "No components were returned by the current Mol* representation preset."
                if self._summary is not None
                else "Open a structure to discover its components."
            )

    def _select_component(self, component_id: str) -> None:
        self._viewer_call("selectComponent", component_id)

    def _toggle_component(self, component_id: str) -> None:
        self._viewer_call("toggleComponentVisibility", component_id)

    def _remove_component(self, component_id: str) -> None:
        self._viewer_call("removeComponent", component_id)

    @staticmethod
    def _replace_combo_items(combo: Gtk.ComboBoxText, items: list[tuple[str, str]]) -> None:
        combo.remove_all()
        for item_id, label in items:
            combo.append(item_id, label)
        if items:
            combo.set_active(0)

    def _on_sequence_chain_changed(self, _combo: Gtk.ComboBoxText) -> None:
        self._update_sequence_view()

    def _update_sequence_view(self) -> None:
        chain_id = self.sequence_chain.get_active_id()
        chain_data = None
        if self._summary and chain_id:
            chain_data = next((c for c in self._summary.get("chains", []) if str(c.get("id")) == chain_id), None)
        if not chain_data:
            self.sequence_info.set_text("Sequences will appear here after loading a protein structure.")
            self.sequence_view.get_buffer().set_text("No sequence loaded")
            return
        sequence = str(chain_data.get("sequence", ""))
        LOGGER.debug("Rendering sequence for chain %s: residues=%d sample=%s", chain_id, len(sequence), sequence[:40])
        self.sequence_info.set_text(f"Chain {chain_id} · {chain_data.get('residueCount', len(sequence))} residues")
        lines = [f"{index + 1:>5}  {sequence[index:index + 60]}" for index in range(0, len(sequence), 60)]
        self.sequence_view.get_buffer().set_text("\n".join(lines) if lines else "No amino-acid sequence found")

    def _on_representation_changed(self, combo: Gtk.ComboBoxText) -> None:
        preset = combo.get_active_id()
        if preset:
            self._viewer_call("setRepresentation", preset)

    def _on_camera_mode_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._updating_settings:
            return
        mode = combo.get_active_id()
        if mode in {"perspective", "orthographic"}:
            self._viewer_call("setCameraMode", mode)

    def _on_render_setting_toggled(
        self, switch: Gtk.Switch, _pspec: Any, setting: str
    ) -> None:
        if self._updating_settings:
            return
        self._viewer_call("setRenderSetting", setting, switch.get_active())

    def _on_illumination_toggled(self, toggle: Gtk.ToggleButton) -> None:
        if self._updating_settings:
            return
        enabled = toggle.get_active()
        toggle.set_tooltip_text(
            "Disable global illumination" if enabled else "Enable global illumination"
        )
        self._viewer_call("setIllumination", enabled)

    def _apply_viewer_settings(self, settings: dict[str, Any]) -> None:
        self._updating_settings = True
        try:
            camera_mode = str(settings.get("cameraMode", "perspective"))
            if camera_mode in {"perspective", "orthographic"}:
                self.camera_mode_combo.set_active_id(camera_mode)
            self.occlusion_switch.set_active(bool(settings.get("occlusion", True)))
            self.shadow_switch.set_active(bool(settings.get("shadow", False)))
            self.outline_switch.set_active(bool(settings.get("outline", False)))
            illumination = bool(settings.get("illumination", False))
            self.illumination_button.set_active(illumination)
            self.illumination_button.set_tooltip_text(
                "Disable global illumination" if illumination else "Enable global illumination"
            )
        finally:
            self._updating_settings = False

    def _viewer_call(self, method: str, *args: Any) -> None:
        try:
            self.viewport.call(method, *args)
        except (ViewerUnavailableError, GLib.Error, RuntimeError, TypeError) as exc:
            self._set_status(str(exc), error=True)

    @staticmethod
    def _clear_listbox(listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            listbox.remove(child)
            child = next_child

    def _set_status(self, message: str, error: bool = False) -> None:
        (LOGGER.error if error else LOGGER.info)("UI status: %s", message)
        self.status_label.set_text(message)
        if error:
            self.status_label.add_css_class("error")
        else:
            self.status_label.remove_css_class("error")
