# MolView GNOME patch notes — Components and sequence reliability

## Native inspector

- Removed the binding-pocket and manual residue-analysis pages.
- Added a Components page listing Mol*'s current structure component groups (polymer, ligands, water, ions, carbohydrates, lipids, non-standard residues, and coarse-grained structure when present).
- Each component group can be selected/focused, hidden/shown, or deleted from the current visualization. Removing a component affects the current Mol* view only; it does not edit the original PDB/mmCIF file. Changing representation or reloading may restore components provided by that preset.
- Kept the sequence page. The inspector remains a left sidebar and is hidden by default.

## Sequence viewer fix

- The previously reported log showed Mol* was rendering the protein but the native sequence payload contained only `X` residues. The code now parses amino-acid names from PDB `SEQRES` records and selects between SEQRES and coordinate-derived sequences by known-residue quality. Coordinate fallback preserves standard `ATOM` residue order and maps common modified amino acids.
- For mmCIF, it reads `_entity_poly.pdbx_seq_one_letter_code_can` (falling back to `_entity_poly.pdbx_seq_one_letter_code`) and maps entity sequences to author chain IDs through `_struct_asym` and `_atom_site` loops. If the entity sequence is all-X or poorer than coordinate metadata, observed `_atom_site` residue names are used. Structure format is sniffed from content rather than relying only on the filename extension.
- Mol* model sequence remains a fallback, and diagnostic messages report each chain's source, length, and sequence sample. This change directly addresses the `sequence: "XXXX..."` payload in the supplied log.

## WebKitGTK action bridge

- The supplied log showed every `evaluate_javascript_finish()` action could fail with `WebKitJavascriptError: Unsupported result type (601)` because the outer JavaScript expression returned a Promise.
- Actions now return a synchronous boolean to WebKit while asynchronous failures are caught and forwarded to Python through the native message bridge.

## Verification boundary

- Python syntax checks and unit/source tests should run without GTK/WebKit installed.
- The application still needs a live Mol*/WebKitGTK build on the target GNOME workstation to verify the component manager objects and sequence output against the actual PDB/mmCIF files.

## Follow-up diagnostics from the supplied log

- The reported `structure-loaded` payload contained only `X` for chains A and B. The standalone sequence parser is now exported from its own module (so the bundler can actually include it), checks file contents to distinguish mmCIF from PDB regardless of extension, compares `SEQRES`/entity sequences with coordinate-derived residue codes, and omits unknown-only output. A no-sequence case now displays an explicit empty-state message and records the parser's source/chain samples in the debug log.
- The reported `Unsupported result type (601)` came from returning JavaScript Promises to `evaluate_javascript_finish()`. The native bridge now expects synchronous booleans for ordinary actions, with asynchronous Promise failures forwarded through the message channel.
- Component preset values are treated as arrays of structure component refs grouped by category, matching Mol*'s Components model. This is necessary for polymer, ligand, water, ion and carbohydrate rows to appear in the GTK sidebar.
- `ready` diagnostics now include `frontendBuild: components-sequence-2026-10-20-r1`; verify this value in the log after running `npm run build` to confirm that the updated bundle is active.


## Header-bar rendering controls and compact window (2026-10-20)

- Kept the representation selector in the header bar and reduced its width for the compact window.
- Added a Reset drop-down with Reset Zoom, Orient Axes, and Reset Axes.
- Added a clickable global-illumination icon in the header bar.
- Settings page exposes Perspective/Orthographic camera projection and toggle switches for ambient occlusion, shadows, and outline, synchronized from Mol* canvas settings.
- Changed the default window size to 780×540 (about one third of the former 1360×920 area), with a 600×420 minimum size request.
- Updated frontend build identifier to `titlebar-render-settings-2026-10-20-r2`.
- Verification: Python source compiles and source-level/unit tests pass. Full GTK/WebKit/WebGL runtime still requires testing on the target workstation because this build environment lacks GTK runtime and npm dependencies.
