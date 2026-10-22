"""Application-specific exceptions."""


class MolViewError(Exception):
    """Base class for errors suitable for presenting to the user."""


class StructureIOError(MolViewError):
    """Raised when a structure cannot be read or fetched."""


class ViewerUnavailableError(MolViewError):
    """Raised when the locally built Mol* frontend is missing."""
