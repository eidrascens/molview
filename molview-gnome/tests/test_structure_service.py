"""Small unit tests for structure input validation (no GTK import required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from molview.errors import StructureIOError
from molview.structure_service import read_structure_file, validate_pdb_id


class StructureServiceTests(unittest.TestCase):
    def test_validates_conventional_pdb_id(self) -> None:
        self.assertEqual(validate_pdb_id("1crn"), "1CRN")

    def test_rejects_invalid_pdb_id(self) -> None:
        with self.assertRaises(StructureIOError):
            validate_pdb_id("1CRN;DROP TABLE")
        with self.assertRaises(StructureIOError):
            validate_pdb_id("abc")

    def test_reads_text_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.pdb"
            path.write_text("HEADER    TEST STRUCTURE\nEND\n", encoding="utf-8")
            text, name = read_structure_file(path)
            self.assertIn("HEADER", text)
            self.assertEqual(name, "tiny.pdb")

    def test_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.xyz"
            path.write_text("not a PDB", encoding="utf-8")
            with self.assertRaises(StructureIOError):
                read_structure_file(path)


if __name__ == "__main__":
    unittest.main()
