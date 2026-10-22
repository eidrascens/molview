"""Run the MolView GNOME application."""

from __future__ import annotations

import logging
import sys

from .logging_setup import configure_logging


def main() -> int:
    log_path = configure_logging()
    logging.getLogger(__name__).info("Starting MolView GNOME; persistent log=%s", log_path or "unavailable")
    # Import after logging setup so any application initialization diagnostics
    # are recorded from the beginning.
    from .application import MolViewApplication

    app = MolViewApplication()
    # Pass argv explicitly so paths supplied by the shell are delivered through
    # Gio.Application's HANDLES_OPEN signal (including to an existing instance).
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
