class ScreenerError(Exception):
    """Base class for all screener.in data-pipeline failures."""


class ScreenerFetchError(ScreenerError):
    """Raised when screener.in cannot be reached or returns unusable data."""


class ScreenerSessionExpiredError(ScreenerFetchError):
    """Raised when a configured session cookie is no longer valid."""


class SectorNotFoundError(ScreenerError):
    """Raised when an unknown sector key is requested."""


class DataShapeMismatchError(ScreenerError):
    """Raised when screener.in's table layout no longer matches the expected column mapping."""
