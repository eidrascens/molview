"""Runtime tests for the dependency-light TypeScript sequence parser."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("tsc") and shutil.which("node"), "requires Node.js and TypeScript compiler")
class SequenceParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="molview-sequence-tests-")
        cls.compiled_dir = Path(cls._tmp.name)
        subprocess.run(
            [
                "tsc", "--target", "ES2022", "--module", "commonjs",
                "--outDir", str(cls.compiled_dir), str(ROOT / "web/src/sequence-parser.ts"),
            ],
            check=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        cls.module_path = cls.compiled_dir / "sequence-parser.js"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _node(self, script: str) -> None:
        completed = subprocess.run(
            ["node", "-e", script, str(self.module_path)],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_pdb_seqres_produces_real_one_letter_sequence(self) -> None:
        self._node(r"""
const assert = require('node:assert/strict');
const parser = require(process.argv[1]);
const pdb = `HEADER    TEST STRUCTURE
SEQRES   1 A    6  MET GLY SER HIS LYS LEU
SEQRES   1 B    3  ALA GLY VAL
END
`;
const parsed = parser.parsePdbSequences(pdb);
assert.deepEqual(parsed.map(chain => [chain.id, chain.sequence]), [['A', 'MGSHKL'], ['B', 'AGV']]);
""")

    def test_pdb_atom_coordinate_fallback_and_unknowns(self) -> None:
        self._node(r"""
const assert = require('node:assert/strict');
const parser = require(process.argv[1]);
function atom(serial, atomName, residue, chain, seq) {
  return `ATOM  ${String(serial).padStart(5, ' ')} ${atomName.padEnd(4, ' ')} ${residue.padStart(3, ' ')} ${chain}${String(seq).padStart(4, ' ')}    0.000   0.000   0.000  1.00 20.00           C`;
}
const pdb = [atom(1, 'CA', 'ALA', 'A', 1), atom(2, 'N', 'ALA', 'A', 1), atom(3, 'CA', 'GLY', 'A', 2), atom(4, 'CA', 'VAL', 'A', 3)].join('\n');
const parsed = parser.parsePdbSequences(pdb);
assert.equal(parsed[0].id, 'A');
assert.equal(parsed[0].sequence, 'AGV');
""")

    def test_pdb_unknown_seqres_prefers_known_coordinate_fallback(self) -> None:
        self._node(r"""
const assert = require('node:assert/strict');
const parser = require(process.argv[1]);
function atom(serial, residue, seq) {
  return `ATOM  ${String(serial).padStart(5, ' ')} ${'CA'.padEnd(4, ' ')} ${residue.padStart(3, ' ')} A${String(seq).padStart(4, ' ')}    0.000   0.000   0.000  1.00 20.00           C`;
}
const pdb = [
  'SEQRES   1 A    3  UNK UNK UNK',
  atom(1, 'MET', 1), atom(2, 'GLY', 2), atom(3, 'SER', 3)
].join('\n');
const parsed = parser.parsePdbSequences(pdb);
assert.deepEqual(parsed.map(chain => [chain.id, chain.sequence]), [['A', 'MGS']]);
""")

    def test_mmcif_bad_entity_sequence_uses_observed_residue_names(self) -> None:
        self._node(r"""
const assert = require('node:assert/strict');
const parser = require(process.argv[1]);
const cif = `data_test
loop_
_entity_poly.entity_id
_entity_poly.type
_entity_poly.pdbx_seq_one_letter_code_can
1 'polypeptide(L)' XXXXXX
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
loop_
_atom_site.group_PDB
_atom_site.label_asym_id
_atom_site.auth_asym_id
_atom_site.label_comp_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
ATOM A A MET 1 ?
ATOM A A GLY 2 ?
ATOM A A SER 3 ?
ATOM A A HIS 4 ?
#
`;
assert.equal(parser.detectStructureFormat('renamed.pdb', cif), 'mmcif');
const parsed = parser.parseMmCifSequences(cif);
assert.deepEqual(parsed.map(chain => [chain.id, chain.sequence]), [['A', 'MGSH']]);
""")


if __name__ == "__main__":
    unittest.main()
