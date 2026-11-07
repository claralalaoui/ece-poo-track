"""The errors of the festival: one family, so a caller can catch all of it
or only one kind."""


class FestivalError(Exception):
    """Every error of the festival. `except FestivalError` catches them all."""


class NotFoundError(FestivalError):
    """An id or a slug that does not exist (HTTP 404)."""


class ConflictError(FestivalError):
    """Valid in itself, but it clashes with what is already there (HTTP 409)."""


class InvalidValueError(FestivalError):
    """A value that is wrong whatever the festival contains (HTTP 422)."""


class InvalidPerformanceError(InvalidValueError):
    """A performance that does not respect the rules of its kind."""


class InvalidDataError(FestivalError):
    """The data file cannot be used (HTTP 500)."""
