# MolView GNOME — GTK4/libadwaita + Mol*

A modular Python proof of concept for inspecting macromolecular structures with a native GNOME interface and a Mol* molecular viewport embedded in WebKitGTK 6.0.

**Status:** proof of concept. The native shell, file/PDB loading workflow, component inventory, and sequence display are implemented in source. Mol*'s frontend bundle is built locally from the pinned npm dependency; it is intentionally not vendored into this source archive. Test it against your installed GTK/WebKitGTK/GPU stack before treating it as a production scientific instrument.

## Design decision: is Mol* native-looking?

Mol* itself is still a WebGL renderer hosted inside WebKitGTK; it is not a GTK widget. This application uses `PluginContext` without Mol*'s React UI, so the visible controls are GTK/libadwaita widgets. The viewport is a bare canvas. The application now starts in a viewer-first state with an opaque light background; theme and transparency toggles are deliberately absent from the primary UI.

## Features in this PoC

- Native GTK4/libadwaita window with a viewer-first layout: local Open button and RCSB PDB ID entry in the header bar, with the inspection sidebar hidden by default.
- Open local PDB and mmCIF files.
- Load four-character PDB IDs from the RCSB PDB over HTTPS.
- Hide Mol*'s default web UI; render only the protein viewport.
- Protein sequence display by chain.
- Components inventory from the Mol* representation preset, including polymer, ligands, water, ions, carbohydrates, lipids, and non-standard components when present. Each group can be selected/focused, hidden/shown, or deleted from the current view without modifying the source file.
- Representation preset selector in the header bar: Cartoon, Cartoon + ligands, Atom detail, and Molecular surface.
- A header-bar Reset menu with Reset Zoom, Orient Axes, and Reset Axes commands.
- A title-bar illumination icon toggles Mol* global illumination.
- Settings page with Perspective/Orthographic camera projection and native on/off switches for ambient occlusion, shadows, and outline.
- A compact 780×540 default window (about one-third the area of the former 1360×920 default), with a 600×420 minimum request.
- A consistent light molecular canvas by default; visual preferences are deliberately kept out of the default viewing experience.
- JavaScript/native bridge with message parsing and exception reporting.
- Command-line and desktop `Open With` support for PDB and mmCIF structure paths; user-level MIME registration is provided for `.pdb`, `.ent`, `.cif`, and `.mmcif`. WebKit blocks top-level navigation away from its bundled viewer page; drag-and-drop is intentionally disabled.
- Verbose Python, WebKit, JavaScript, and Mol* diagnostics with rotating log files.

## Dependencies

The GTK app uses system libraries through PyGObject. Exact package names depend on your distribution.

Typical Fedora packages (install inside a Toolbox or development container):

```sh
sudo dnf install \
  python3 python3-gobject gtk4 libadwaita \
  webkitgtk6.0 nodejs npm
```

For compile-time/header dependencies needed by packaging work, add the corresponding `*-devel` packages, typically `gtk4-devel`, `libadwaita-devel`, `webkitgtk6.0-devel`, and `gobject-introspection-devel`.

Python modules are in `src/`; no pip installation is required for the app itself.

## Build the Mol* frontend (one-time, and after changing the TS sources)

Requires Node.js/npm and network access to download the pinned package the first time. Once installed, runtime rendering does not require a CDN.

```sh
cd molview-gnome
npm install
npm run build
```

This creates `web/dist/index.html` and `web/dist/viewer.js`. Mol* is pinned to `5.13.1` in `package.json` to avoid silently changing behavior on a future release.

## Run from source

```sh
cd molview-gnome
PYTHONPATH=src python3 -m molview
```

Open a structure directly from the terminal (paths with spaces are supported when quoted):

```sh
./run-dev.sh "/path/to/structure.pdb"
# Or, from the project root:
PYTHONPATH=src python3 -m molview "/path/to/structure.cif"
```

The application uses Gio `HANDLES_OPEN`; invoking the launcher with a file path forwards that file to the running application if one already exists.

Open a local `.pdb`, `.ent`, `.cif`, or `.mmcif` file using the Open button, or enter a four-character PDB identifier such as `1CRN`. PDB ID loading uses `https://files.rcsb.org/download/<ID>.cif` and therefore requires network access.

## Install as a desktop app and default structure-file opener

After the Mol* frontend is built, run this from the project directory:

```sh
./packaging/install-user.sh
```

Run this on the same Linux host/runtime that should launch the app from GNOME Files. It installs the Python source and bundled frontend under `~/.local/lib/molview-gnome`, installs a launcher in `~/.local/bin`, registers MIME types for `.pdb`, `.ent`, `.cif`, and `.mmcif`, creates the GNOME desktop entry, and requests MolView GNOME as the default handler. If you develop inside Toolbox, the host desktop launcher needs a host-visible Python runtime or an explicit `toolbox run` wrapper; a container Python path does not automatically refer to the same interpreter on the host. It is a per-user install and does not require `sudo`. If a file manager does not immediately refresh its associations, log out and back in, then check **Settings → Apps → Default Apps** or the file's **Open With** menu.

Command-line use after installation:

```sh
~/.local/bin/molview-gnome "/path/to/2J1P.pdb"
```

For the shorter `molview-gnome` command, ensure `~/.local/bin` is on your terminal's `PATH`.

## Build/run inside Toolbox

The app is Python and does not compile to a native executable. Build the Mol* JS bundle inside the container, then run the Python app in the same container. If you want to launch it from the host, the host still needs compatible GTK4, libadwaita, WebKitGTK 6.0 and PyGObject runtime libraries; a Toolbox build does not bundle those libraries into the app. For a self-contained deployment, package the application with Flatpak instead.

## Debugging and logs

Logging defaults to `DEBUG` and is written to both the launching terminal and `~/.local/state/molview-gnome/molview.log` (or `$XDG_STATE_HOME/molview-gnome/molview.log`). The log rotates at 3 MiB with three backups. To capture a terminal log separately:

```sh
MOLVIEW_LOG_LEVEL=DEBUG ./run-dev.sh 2>&1 | tee ~/molview-console.log
```

To ask WebKitGTK to enable developer extras, run `MOLVIEW_WEBKIT_INSPECTOR=1 ./run-dev.sh`. The logs include WebKit page-load events and error domain/code, JS exceptions/unhandled promise rejections, Mol* log entries, parse steps, loaded element/unit counts, canvas dimensions, the frontend build identifier, sequence parser source and per-chain samples. Redact local paths or private structure metadata before sharing logs.

The inspector is hidden when the application starts so the molecular canvas is the primary view. Use the sidebar toggle in the header bar to reveal scientific inspection tools. The app uses an opaque light canvas by default because transparent WebGL compositing varies by graphics stack.

## Controls

- `Ctrl+O` or the Open icon: open a local structure.
- Header-bar PDB ID field + **Load**: fetch a PDB entry. Press Enter while in the ID field to load it.
- Sidebar toggle: reveal or hide the structure-inspection tools.
- **Representation** in the header bar: change the Mol* preset.
- **Reset** in the header bar: choose Reset Zoom, Orient Axes, or Reset Axes.
- **Illumination** in the header bar: click the sun symbol to toggle global illumination.
- **Settings** in the inspector sidebar: choose perspective/orthographic camera projection and toggle ambient occlusion, shadows, or outline.
- **Components** page: select/focus a component group, hide/show it, or delete it from the current view. Deleting a group does not alter the source structure file.
- **Sequence** page: choose a chain and read its one-letter amino-acid sequence. The parser prioritizes PDB `SEQRES` and mmCIF entity sequences, then falls back to coordinate residue names; unknown-only chains are not falsely displayed as all-X sequences.

## Scientific limitations

This is a visualization proof of concept, not a validated structural-biology analysis package. Component groups come from Mol*'s representation preset and may not classify every non-polymer as a biologically relevant ligand. Removing a component affects the current visualization state, not the original PDB/mmCIF data. Sequence extraction can be incomplete for unusual modified residues or files lacking sequence metadata and standard residue codes; the log includes source format, parser choice, chain lengths, and sequence samples to help diagnose this. Validate structures and sequence outputs before using them in research conclusions.

## Project layout

```text
src/molview/
  __main__.py        application entry point
  application.py    Adw.Application lifecycle and actions
  main_window.py    native interface and inspector panels
  molecular_viewport.py  WebKitGTK wrapper, navigation guard and JS bridge
  logging_setup.py       terminal + rotating persistent diagnostics
  structure_service.py   local file and RCSB PDB I/O
  errors.py         domain exceptions
web/
  index.html        bare canvas page, no Mol* web UI
  src/viewer.ts         Mol* engine, component groups, sequence summary, render controls
  src/sequence-parser.ts  PDB/mmCIF sequence parsing and content-based format detection
scripts/build.mjs  local Mol* bundling
```

## Licensing

MolView GNOME source in this PoC is provided under the MIT license (see `LICENSE`). Mol* is separately MIT-licensed; the npm-installed distribution's license and notices should be preserved when redistributing a packaged app. See <https://github.com/molstar/molstar>.

Packaging/Toolbox notes are in [`packaging/README.md`](packaging/README.md); the desktop and AppStream files are templates, not an installable package by themselves.
