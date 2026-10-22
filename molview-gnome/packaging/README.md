# Packaging notes

`install-user.sh` provides a working per-user Linux desktop install for the proof of concept. Run it from the source tree after extracting the archive:

```sh
./packaging/install-user.sh
```

The script builds the pinned Mol* frontend when needed, copies the Python package and `web/dist` to `~/.local/lib/molview-gnome`, installs a launcher in `~/.local/bin`, defines the supported PDB/mmCIF MIME types, installs `org.example.MolView.desktop`, refreshes the MIME/desktop databases, and requests MolView GNOME as the default handler for `chemical/x-pdb`, `chemical/x-mmcif`, and `chemical/x-cif`. All changes are per-user.

For command-line use, invoke `~/.local/bin/molview-gnome /path/to/structure.pdb`; adding `~/.local/bin` to `PATH` permits the shorter `molview-gnome /path/to/structure.pdb`. The application registers `Gio.ApplicationFlags.HANDLES_OPEN`, so it also works through GNOME's **Open With** action and accepts a file path as a command-line argument. This proof of concept displays one structure at a time; if multiple paths are passed, it logs a warning and opens the first.

The desktop and MIME files can also be installed manually. The `.desktop` file uses `Exec=molview-gnome %F` as a template; for a reliable manual install, replace `Exec` and `TryExec` with the absolute installed launcher path. Install `org.example.MolView.mime.xml` into `$XDG_DATA_HOME/mime/packages/`, run `update-mime-database "$XDG_DATA_HOME/mime"`, then use `xdg-mime default org.example.MolView.desktop chemical/x-pdb` and the corresponding mmCIF/CIF types.

## Toolbox development

```sh
toolbox create --container molview-dev
toolbox enter molview-dev
sudo dnf install python3 python3-gobject gtk4 libadwaita webkitgtk6.0 nodejs npm shared-mime-info desktop-file-utils xdg-utils
```

Then, inside the Toolbox container:

```sh
cd /path/to/molview-gnome
npm install
npm run build
./run-dev.sh
```

Python does not need a native compilation step. The Mol* TypeScript bundle is built in the container; the app then runs with GTK4, libadwaita, and WebKitGTK from that same container. A build in Toolbox is not a self-contained host executable; for a reproducible distributable, use a Flatpak manifest with a pinned GNOME runtime and build Mol* inside the Flatpak build pipeline.

**Host versus Toolbox:** run the per-user desktop installer in the same runtime where the app will be launched. If the build lives in Toolbox, use a host-visible Python runtime for the desktop handler or customize the generated launcher to wrap the command in `toolbox run`; absolute paths inside the container do not necessarily name the same interpreter on the host.
