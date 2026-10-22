#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f -- "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
LIB_DIR="$HOME/.local/lib/molview-gnome"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/applications"
MIME_PACKAGES="$DATA_HOME/mime/packages"
LAUNCHER="$BIN_DIR/molview-gnome"
DESKTOP_FILE="$APP_DIR/org.example.MolView.desktop"
PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"

# Select and validate the same Python environment used to install this app. This
# supports a venv or Toolbox setup where PyGObject/WebKitGTK bindings are exposed.
if ! "$PYTHON_BIN" - <<'PY_CHECK_GI_124' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gtk, WebKit
PY_CHECK_GI_124
then
    echo "ERROR: $PYTHON_BIN cannot import GTK4, libadwaita, and WebKitGTK 6.0 through PyGObject." >&2
    echo "Activate the Python environment used to run MolView GNOME, then retry." >&2
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/web/dist/index.html" || ! -f "$PROJECT_ROOT/web/dist/viewer.js" ]]; then
    echo "Mol* frontend is not built; building the pinned frontend first..."
    cd "$PROJECT_ROOT"
    if [[ ! -d node_modules/molstar || ! -d node_modules/esbuild ]]; then
        npm install --no-audit --no-fund
    fi
    npm run build
fi

mkdir -p "$LIB_DIR/src" "$LIB_DIR/web" "$LIB_DIR/bin" "$BIN_DIR" "$APP_DIR" "$MIME_PACKAGES"
rm -f "$LAUNCHER"
rm -rf "$LIB_DIR/src/molview" "$LIB_DIR/web/dist"
cp -a "$PROJECT_ROOT/src/molview" "$LIB_DIR/src/molview"
cp -a "$PROJECT_ROOT/web/dist" "$LIB_DIR/web/dist"
install -m 0755 "$PROJECT_ROOT/bin/molview-gnome" "$LIB_DIR/bin/molview-gnome"
install -m 0644 "$PROJECT_ROOT/packaging/org.example.MolView.mime.xml" "$MIME_PACKAGES/molview-gnome.xml"

# Generate a stable launcher which uses the validated interpreter from this
# environment, regardless of PATH inherited by GNOME Shell.
python3 - "$LIB_DIR" "$LAUNCHER" "$PYTHON_BIN" <<'PY_GENERATE_LAUNCHER_124'
from pathlib import Path
import shlex
import sys

app_root, launcher_path, python_bin = sys.argv[1:]
content = "\n".join([
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    f"ROOT={shlex.quote(app_root)}",
    f"PYTHON_BIN={shlex.quote(python_bin)}",
    'exec env PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m molview "$@"',
    "",
])
Path(launcher_path).write_text(content, encoding="utf-8")
PY_GENERATE_LAUNCHER_124
chmod 0755 "$LAUNCHER"

# Desktop Exec fields have their own quoting rules; use an absolute launcher so
# GNOME works even if ~/.local/bin is not in the graphical session PATH.
python3 - "$PROJECT_ROOT/packaging/org.example.MolView.desktop" "$DESKTOP_FILE" "$LAUNCHER" <<'PY_GENERATE_DESKTOP_124'
from pathlib import Path
import re
import sys

source_path, destination_path, launcher = sys.argv[1:]
def quote_exec(value: str) -> str:
    value = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'

text = Path(source_path).read_text(encoding="utf-8")
text = re.sub(r"(?m)^Exec=.*$", f"Exec={quote_exec(launcher)} %f", text)
text = re.sub(r"(?m)^TryExec=.*$", f"TryExec={quote_exec(launcher)}", text)
Path(destination_path).write_text(text, encoding="utf-8")
PY_GENERATE_DESKTOP_124
chmod 0644 "$DESKTOP_FILE"

if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database "$DATA_HOME/mime"
else
    echo "WARNING: update-mime-database not found; MIME type definitions may not be refreshed." >&2
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR"
fi
if command -v xdg-mime >/dev/null 2>&1; then
    xdg-mime default org.example.MolView.desktop chemical/x-pdb
    xdg-mime default org.example.MolView.desktop chemical/x-mmcif
    xdg-mime default org.example.MolView.desktop chemical/x-cif
else
    echo "WARNING: xdg-mime not found; set MolView GNOME as the default app for PDB/CIF files in GNOME Settings." >&2
fi

echo
echo "MolView GNOME installed for this user."
echo "Launcher: $LAUNCHER"
echo "Desktop entry: $DESKTOP_FILE"
echo "Default handlers requested for .pdb, .ent, .cif, and .mmcif files."
echo
echo "Command-line usage:"
echo "  $LAUNCHER /path/to/structure.pdb"
echo "  $LAUNCHER /path/to/structure.cif"
echo "For a short command, ensure ~/.local/bin is on PATH and run: molview-gnome /path/to/structure.pdb"
