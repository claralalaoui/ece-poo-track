"""Performances: what every kind shares, then one class per kind."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from deauville.errors import (
    ConflictError,
    InvalidPerformanceError,
)
from deauville.models import Artist, Venue, tidy

if TYPE_CHECKING:
    from deauville.festival import Festival


def _required(data: dict, field: str) -> Any:
    """The value of a field of a dict, or an error that names the field."""
    value = data.get(field)
    if value is None:
        raise InvalidPerformanceError(f"Missing field '{field}'.")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Performance(ABC):
    """What every performance has. A bare `Performance` cannot be created.

    Common: title, venue, start, duration, description. Not common, so left to
    each subclass: who is on stage, the summary, the extra fields, the rules.
    """

    kind = "performance"  # each subclass replaces it

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: str,
        duration_minutes: int,
        description: str = "",
    ) -> None:
        if not str(title).strip():
            raise InvalidPerformanceError("A performance needs a title.")
        try:
            self._start_datetime = datetime.strptime(start, "%Y-%m-%dT%H:%M")
        except (TypeError, ValueError):
            raise InvalidPerformanceError(
                f"{start!r} is not a date and time, use YYYY-MM-DDTHH:MM."
            ) from None
        if not _is_int(duration_minutes):
            raise InvalidPerformanceError(
                f"{duration_minutes!r} is not a number of minutes."
            )
        if not 1 <= duration_minutes <= 360:
            raise InvalidPerformanceError("Duration must be between 1 and 360 minutes.")
        self._title = str(title).strip()
        self._venue = venue
        self._start = start
        self._duration_minutes = duration_minutes
        self._description = description or ""

    # Read-only: there is no setter, `performance.start = ...` fails. To move a
    # performance, the festival replaces it by a new one, after the rules.

    @property
    def title(self) -> str:
        return self._title

    @property
    def venue(self) -> Venue:
        return self._venue

    @property
    def start(self) -> str:
        return self._start

    @property
    def duration_minutes(self) -> int:
        return self._duration_minutes

    @property
    def description(self) -> str:
        return self._description

    @property
    def start_datetime(self) -> datetime:
        return self._start_datetime

    @property
    def end(self) -> datetime:
        return self._start_datetime + timedelta(minutes=self._duration_minutes)

    @property
    def festival_day(self) -> str:
        """The day of the festival: a show at 01:00 belongs to the day before."""
        day = self._start_datetime
        if day.hour < 6:
            day -= timedelta(days=1)
        return day.date().isoformat()

    @property
    def id(self) -> str:
        return f"{self._venue.slug}-{self._start_datetime:%Y-%m-%d-%H%M}"

    # What each kind must write itself.

    @property
    @abstractmethod
    def artists(self) -> list[Artist]:
        """Everybody on stage, in the order of the summary."""

    @abstractmethod
    def summary(self) -> str:
        """One line about who is on stage."""

    @abstractmethod
    def _own_view(self) -> dict:
        """The fields of the API view that only this kind has."""

    @abstractmethod
    def _own_data(self) -> dict:
        """The fields of the data file that only this kind has."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict, festival: "Festival") -> "Performance":
        """Read this kind from a dict (file or request body)."""

    # What is the same for every kind, written once.

    def register(self, name: str) -> None:
        """Only workshops take participants; a workshop replaces this."""
        raise InvalidPerformanceError(f"{self.title} does not take registrations.")

    def involves(self, artist_slug: str) -> bool:
        return any(artist.slug == artist_slug for artist in self.artists)

    def to_view(self) -> dict:
        """The JSON of the API: common fields, then the fields of the kind."""
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self._title,
            "venue": self._venue.slug,
            "venue_name": self._venue.name,
            "start": self._start,
            "end": self.end.isoformat(timespec="minutes"),
            "duration_minutes": self._duration_minutes,
            "festival_day": self.festival_day,
            "description": self._description,
            "summary": self.summary(),
            "capacity": self._venue.capacity,
            "artists": [
                {"slug": artist.slug, "name": artist.name} for artist in self.artists
            ],
            **self._own_view(),
        }

    def to_dict(self) -> dict:
        """The dict written in the data file."""
        return {
            "kind": self.kind,
            "title": self._title,
            "venue": self._venue.slug,
            "start": self._start,
            "duration_minutes": self._duration_minutes,
            "description": self._description,
            **self._own_data(),
        }

    @staticmethod
    def _common(data: dict, festival: "Festival") -> dict:
        """The arguments every kind takes, read from a dict."""
        return {
            "title": _required(data, "title"),
            "venue": festival.resolve_venue(_required(data, "venue")),
            "start": _required(data, "start"),
            "duration_minutes": _required(data, "duration_minutes"),
            "description": data.get("description") or "",
        }

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Performance):
            return NotImplemented
        return (self._start_datetime, self._venue.slug) < (
            other._start_datetime,
            other._venue.slug,
        )

    def __str__(self) -> str:
        return f"{self._start_datetime:%H:%M} - {self._title} ({self._venue.slug})"


class SoloShow(Performance):
    """One artist alone on stage, with a minimum age."""

    kind = "solo"

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: str,
        duration_minutes: int,
        artist: Artist,
        min_age: int = 0,
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        if not _is_int(min_age) or not 0 <= min_age <= 18:
            raise InvalidPerformanceError("The minimum age must be between 0 and 18.")
        self._artist = artist
        self._min_age = min_age

    @property
    def artist(self) -> Artist:
        return self._artist

    @property
    def min_age(self) -> int:
        return self._min_age

    @property
    def artists(self) -> list[Artist]:
        return [self._artist]

    def summary(self) -> str:
        return self._artist.name

    def _own_view(self) -> dict:
        return {"artist": self._artist.slug, "min_age": self._min_age}

    def _own_data(self) -> dict:
        return {"artist": self._artist.slug, "min_age": self._min_age}

    @classmethod
    def from_dict(cls, data: dict, festival: "Festival") -> "SoloShow":
        min_age = data.get("min_age")
        return cls(
            **cls._common(data, festival),
            artist=festival.resolve_artist(_required(data, "artist")),
            min_age=0 if min_age is None else min_age,
        )


class Lineup(Performance):
    """A host and several acts, one after the other, in one evening."""

    kind = "lineup"
    ACT_MINUTES = 10  # each act
    HOST_MINUTES = 3  # the host, between two acts

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: str,
        duration_minutes: int,
        host: Artist,
        acts: list[Artist],
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        acts = list(acts)
        if len(acts) < 2:
            raise InvalidPerformanceError("A lineup needs at least two acts.")
        slugs = [act.slug for act in acts]
        for act in acts:
            if slugs.count(act.slug) > 1:
                raise InvalidPerformanceError(f"{act.name} is listed twice.")
        if host.slug in slugs:
            raise InvalidPerformanceError(
                f"{host.name} is the host, so cannot also be an act."
            )
        needed = self.ACT_MINUTES * len(acts) + self.HOST_MINUTES * (len(acts) - 1)
        if duration_minutes < needed:
            raise InvalidPerformanceError(
                f"{len(acts)} acts need at least {needed} minutes "
                f"({self.ACT_MINUTES} per act, {self.HOST_MINUTES} for the host "
                f"between two acts), got {duration_minutes}."
            )
        self._host = host
        self._acts = acts

    @property
    def host(self) -> Artist:
        return self._host

    @property
    def acts(self) -> list[Artist]:
        """A copy: appending to it changes nothing in the lineup."""
        return list(self._acts)

    @property
    def artists(self) -> list[Artist]:
        return [self._host, *self._acts]

    def summary(self) -> str:
        names = ", ".join(act.name for act in self._acts)
        return f"hosted by {self._host.name}, with {names}"

    def _own_view(self) -> dict:
        return {"host": self._host.slug, "acts": [act.slug for act in self._acts]}

    def _own_data(self) -> dict:
        return self._own_view()

    @classmethod
    def from_dict(cls, data: dict, festival: "Festival") -> "Lineup":
        return cls(
            **cls._common(data, festival),
            host=festival.resolve_artist(_required(data, "host")),
            acts=[festival.resolve_artist(slug) for slug in data.get("acts") or []],
        )


class Workshop(Performance):
    """A teacher and a limited number of participants."""

    kind = "workshop"

    def __init__(
        self,
        title: str,
        venue: Venue,
        start: str,
        duration_minutes: int,
        teacher: Artist,
        max_participants: int,
        participants: list[str] = (),
        description: str = "",
    ) -> None:
        super().__init__(title, venue, start, duration_minutes, description)
        if not _is_int(max_participants) or max_participants < 1:
            raise InvalidPerformanceError("A workshop needs at least one place.")
        self._teacher = teacher
        self._max_participants = max_participants
        names = [tidy(name) for name in participants]
        keys = [name.casefold() for name in names]
        if "" in names:
            raise InvalidPerformanceError("A participant needs a name.")
        if len(set(keys)) != len(keys):
            raise InvalidPerformanceError("A participant is registered twice.")
        if len(names) > self.places:
            raise InvalidPerformanceError(
                f"{len(names)} participants for {self.places} places."
            )
        self._participants = names

    @property
    def teacher(self) -> Artist:
        return self._teacher

    @property
    def max_participants(self) -> int:
        return self._max_participants

    @property
    def places(self) -> int:
        """The places that really exist: never more than the seats of the venue."""
        return min(self._max_participants, self._venue.capacity)

    @property
    def participants(self) -> list[str]:
        """A copy: appending to it does not register anybody."""
        return list(self._participants)

    @property
    def places_left(self) -> int:
        return self.places - len(self._participants)

    @property
    def artists(self) -> list[Artist]:
        return [self._teacher]

    def register(self, name: str) -> None:
        name = tidy(name)
        if not name:
            raise InvalidPerformanceError("A participant needs a name.")
        if name.casefold() in (other.casefold() for other in self._participants):
            raise ConflictError(f"{name} is already registered for {self.title}.")
        if self.places_left == 0:
            raise ConflictError(f"{self.title} is full ({self.places} places).")
        self._participants.append(name)

    def summary(self) -> str:
        return (
            f"with {self._teacher.name}, "
            f"{len(self._participants)}/{self.places} places taken"
        )

    def _own_view(self) -> dict:
        return {
            "teacher": self._teacher.slug,
            "max_participants": self._max_participants,
            "places": self.places,
            "participants": self.participants,
            "places_left": self.places_left,
        }

    def _own_data(self) -> dict:
        return {
            "teacher": self._teacher.slug,
            "max_participants": self._max_participants,
            "participants": self.participants,
        }

    @classmethod
    def from_dict(cls, data: dict, festival: "Festival") -> "Workshop":
        return cls(
            **cls._common(data, festival),
            teacher=festival.resolve_artist(_required(data, "teacher")),
            max_participants=_required(data, "max_participants"),
            participants=data.get("participants") or [],
        )


# The only place where the "kind" of the file chooses a class.
KINDS: dict[str, type[Performance]] = {
    "solo": SoloShow,
    "lineup": Lineup,
    "workshop": Workshop,
}
