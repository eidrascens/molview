# Architecture and implementation notes

## Separation of concerns

- `MainWindow` owns libadwaita layout, user input, status/error presentation, and view state.
- `StructureService` owns synchronous worker-thread file and RCSB I/O plus basic input validation. It does not depend on GTK.
- `MolecularViewport` owns the WebKitGTK lifecycle, WebView lifecycle, JavaScript entry-point invocation, and bridge decoding. It does not parse molecular data itself.
- `web/src/viewer.ts` owns the Mol* `PluginContext`, structure metadata extraction, representation presets, and component-group operations. `web/src/sequence-parser.ts` independently parses PDB/mmCIF sequence metadata and coordinate residue fallbacks.

## Data flow

1. GTK's file chooser or PDB ID entry starts a background Python I/O task.
2. The main-loop callback passes the text and filename to `MolecularViewport`.
3. WebKitGTK transfers structure data as a `GVariant` argument to a named JavaScript function, avoiding string interpolation of user data into executable code.
4. Mol* parses PDB/mmCIF and applies its default representation preset.
5. A narrow JSON message channel informs GTK about structure chains/sequences, component groups, selection/visibility/removal results, diagnostics, and errors.
6. GTK builds/updates its own widgets. It never embeds Mol*'s React controls.

## Viewport background strategy

The normal startup configuration uses an opaque light background because it is reliable across WebKitGTK and GPU combinations. The Mol* frontend retains a programmatic transparent-background setting for future use, but the native interface does not expose a light/dark or transparency toggle. A truly transparent WebGL surface still depends on the target WebKitGTK/GPU compositing path.

## Error boundaries

- Disk and HTTP errors become `StructureIOError` messages.
- The worker thread never mutates GTK widgets directly; it marshals results onto the GLib main loop.
- The WebKit bridge validates that messages are JSON objects with a string `type`.
- JS viewer actions catch errors and forward them through the bridge; Python callbacks also catch GI/WebKit failures.
- Missing bundled frontend assets are reported in-app with instructions to run the frontend build.

## Scope boundaries

The sequence and component inventory are intended as proof-of-concept inspection tools. Component groups are supplied by Mol* representation presets; a component that is deleted from the current visualization may reappear after changing representation or reloading the file. Sequence extraction prioritizes source text (`SEQRES` or mmCIF entity metadata) and falls back to observed residue names; unknown-only sequences are omitted rather than displayed as misleading X-only output. Production work should add integration tests against representative PDB/mmCIF edge cases, accessibility review, and reproducible Flatpak packaging.


## Diagnostics and WebKit navigation

The GTK layer owns file selection and receives local paths through Gio.Application for command-line and desktop `Open With` invocations. Drag-and-drop is deliberately disabled; WebKit is not allowed to navigate its main frame away from the bundled viewer page. Python logs go to stderr and a rotating file under `$XDG_STATE_HOME/molview-gnome/`. Frontend uncaught errors, console warnings/errors, Mol* log events, canvas dimensions, parse stages and post-load structure counts are bridged to Python. The viewport starts with an opaque background; transparency remains an experimental programmatic option because WebKit/WebGL alpha compositing differs by driver.
