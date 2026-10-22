"""Structure file and RCSB PDB access, isolated from the UI layer."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import StructureIOError

MAX_STRUCTURE_BYTES = 250 * 1024 * 1024
PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
SUPPORTED_SUFFIXES = {".pdb", ".ent", ".cif", ".mmcif"}


def read_structure_file(path: str | Path) -> tuple[str, str]:
    """Read a PDB/mmCIF text file with size and format checks."""
    source = Path(path).expanduser()
    try:
        stat = source.stat()
    except OSError as exc:
        raise StructureIOError(f"Cannot access file: {exc}") from exc

    if not source.is_file():
        raise StructureIOError("The selected path is not a regular file.")
    if stat.st_size <= 0:
        raise StructureIOError("The selected structure file is empty.")
    if stat.st_size > MAX_STRUCTURE_BYTES:
        raise StructureIOError("The file is larger than the 250 MiB proof-of-concept limit.")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise StructureIOError("Unsupported file type. Choose PDB (.pdb/.ent) or mmCIF (.cif/.mmcif).")

    try:
        # PDB/mmCIF files are text. Replacement is safer than failing the whole
        # load for an uncommon non-UTF-8 metadata character.
        contents = source.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise StructureIOError(f"Could not read the structure file: {exc}") from exc

    if not contents.strip():
        raise StructureIOError("The selected structure file contains no readable text.")
    return contents, source.name


def validate_pdb_id(pdb_id: str) -> str:
    """Normalize and validate a conventional four-character wwPDB ID."""
    value = pdb_id.strip().upper()
    if not PDB_ID_RE.fullmatch(value):
        raise StructureIOError("Enter a four-character PDB ID beginning with a digit, for example 1CRN.")
    return value


def download_rcsb_structure(pdb_id: str, timeout: float = 30.0) -> tuple[str, str]:
    """Download an mmCIF entry from RCSB over HTTPS."""
    entry_id = validate_pdb_id(pdb_id)
    url = f"https://files.rcsb.org/download/{entry_id}.cif"
    request = Request(
        url,
        headers={"User-Agent": "MolView-GNOME/0.1 (scientific structure viewer)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > MAX_STRUCTURE_BYTES:
                raise StructureIOError("The remote structure is larger than the 250 MiB limit.")
            payload = response.read(MAX_STRUCTURE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise StructureIOError(f"PDB entry {entry_id} was not found at RCSB.") from exc
        raise StructureIOError(f"RCSB returned HTTP {exc.code} while downloading {entry_id}.") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise StructureIOError(f"Could not download {entry_id} from RCSB: {exc}") from exc

    if len(payload) > MAX_STRUCTURE_BYTES:
        raise StructureIOError("The downloaded structure is larger than the 250 MiB limit.")
    try:
        text = payload.decode("utf-8-sig", errors="replace")
    except UnicodeError as exc:  # defensive; replacement normally prevents this
        raise StructureIOError(f"Could not decode RCSB response: {exc}") from exc
    if not text.strip() or text.lstrip().lower().startswith("<!doctype html"):
        raise StructureIOError(f"RCSB returned no mmCIF structure for {entry_id}.")
    return text, f"{entry_id}.cif"
