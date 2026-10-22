"""Source-level checks for file opening and desktop registration."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class DesktopIntegrationTests(unittest.TestCase):
    def test_desktop_entry_registers_supported_mime_types(self):
        desktop = (ROOT / "packaging/org.example.MolView.desktop").read_text(encoding="utf-8")
        self.assertIn("Exec=molview-gnome %f", desktop)
        self.assertIn("chemical/x-pdb", desktop)
        self.assertIn("chemical/x-mmcif", desktop)
        self.assertIn("chemical/x-cif", desktop)

    def test_mime_definition_is_valid_and_covers_supported_suffixes(self):
        source = ROOT / "packaging/org.example.MolView.mime.xml"
        root = ET.parse(source).getroot()
        globs = {item.attrib.get("pattern") for item in root.iter() if item.tag.endswith("glob")}
        self.assertTrue({"*.pdb", "*.ent", "*.cif", "*.mmcif"}.issubset(globs))

    def test_application_handles_gio_open_requests(self):
        source = (ROOT / "src/molview/application.py").read_text(encoding="utf-8")
        entry = (ROOT / "src/molview/__main__.py").read_text(encoding="utf-8")
        self.assertIn("Gio.ApplicationFlags.HANDLES_OPEN", source)
        self.assertIn('self.connect("open", self._on_open_files)', source)
        self.assertIn("app.run(sys.argv)", entry)

    def test_drag_and_drop_is_removed(self):
        for filename in ("src/molview/main_window.py", "src/molview/molecular_viewport.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn("Gtk.DropTarget", source)
            self.assertNotIn("open-file-request", source)

    def test_sequence_uses_source_sequences_before_molstar_fallback(self):
        source = (ROOT / "web/src/viewer.ts").read_text(encoding="utf-8")
        parser = (ROOT / "web/src/sequence-parser.ts").read_text(encoding="utf-8")
        self.assertIn("parsePdbSequences", source)
        self.assertIn("SEQRES", parser)
        self.assertIn("parseMmCifSequences", source)
        self.assertIn("collectPolymerSequences", source)
        self.assertIn("sequence-summary-complete", source)
        self.assertIn("detectStructureFormat", source)

    def test_inspector_replaces_pocket_and_residue_tools_with_components(self):
        main_window = (ROOT / "src/molview/main_window.py").read_text(encoding="utf-8")
        viewer = (ROOT / "web/src/viewer.ts").read_text(encoding="utf-8")
        self.assertIn('add_titled(self._build_components_page(), "components", "Components")', main_window)
        self.assertIn("Select", main_window)
        self.assertIn('Gtk.Button(label="Delete")', main_window)
        self.assertIn("component.refs", viewer)
        self.assertIn("validComponentRefs(value)", viewer)
        self.assertNotIn("_build_pocket_page", main_window)
        self.assertNotIn("_build_residue_page", main_window)
        self.assertNotIn("findPocket", viewer)
        self.assertNotIn("focusResidue", viewer)

    def test_webkit_action_result_is_synchronous_and_promise_errors_are_bridged(self):
        source = (ROOT / "src/molview/molecular_viewport.py").read_text(encoding="utf-8")
        self.assertIn("result.catch(reportError)", source)
        self.assertIn("return true;", source)
        self.assertIn("cannot deserialize a Promise", source)

    def test_titlebar_contains_representation_reset_menu_and_illumination_toggle(self):
        source = (ROOT / "src/molview/main_window.py").read_text(encoding="utf-8")
        self.assertIn("self.set_default_size(780, 540)", source)
        self.assertIn("header.pack_end(self.representation_combo)", source)
        self.assertIn("header.pack_end(self.reset_menu_button)", source)
        self.assertIn("header.pack_end(self.illumination_button)", source)
        self.assertIn('reset_menu.append("Reset Zoom", "win.reset-zoom")', source)
        self.assertIn('reset_menu.append("Orient Axes", "win.orient-axes")', source)
        self.assertIn('reset_menu.append("Reset Axes", "win.reset-axes")', source)

    def test_settings_page_exposes_molstar_projection_and_render_effects(self):
        source = (ROOT / "src/molview/main_window.py").read_text(encoding="utf-8")
        viewer = (ROOT / "web/src/viewer.ts").read_text(encoding="utf-8")
        for setting in ("Perspective", "Orthographic", "Ambient occlusion", "Shadows", "Outline"):
            self.assertIn(setting, source)
        self.assertIn("setCameraMode", viewer)
        self.assertIn("setRenderSetting", viewer)
        self.assertIn("setIllumination", viewer)
        self.assertIn("PluginCommands.Camera.OrientAxes", viewer)
        self.assertIn("PluginCommands.Camera.ResetAxes", viewer)
        self.assertIn("titlebar-render-settings-2026-10-20-r2", viewer)


if __name__ == "__main__":
    unittest.main()
