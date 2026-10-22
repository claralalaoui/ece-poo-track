"""The festival: venues, artists, three kinds of performances and the rules.

Everything that changes the schedule goes through a method of `Festival`, so
the rules always apply, whether the call comes from the command line or the API.
"""

import json
import os
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

DATA_FILE = "data/festival.json"
BREAK = timedelta(minutes=30)  # between two performances of a venue or an artist


# --- Errors: one family, so a caller can catch all of it or only one kind. ---


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


# --- Venues and artists: small, and frozen so nobody can change them. ---


def make_slug(name: str) -> str:
    """Convert a name into a URL-friendly slug."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


@dataclass(frozen=True)
class Venue:
    name: str
    capacity: int
    address: str = ""

    @property
    def slug(self) -> str:
        return make_slug(self.name)


@dataclass(frozen=True)
class Artist:
    name: str
    bio: str = ""
    photo_url: str = ""

    @property
    def slug(self) -> str:
        return make_slug(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Artist):
            return NotImplemented
        return self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)


def _required(data: dict, field: str):
    """The value of a field of a dict, or an error that names the field."""
    value = data.get(field)
    if value is None:
        raise InvalidPerformanceError(f"Missing field '{field}'.")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _tidy(name: str) -> str:
    """A name without extra spaces: 'Lou   M.' -> 'Lou M.'."""
    return " ".join(str(name).split())


# --- Performances: what every kind shares, then one class per kind. ---


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
            raise InvalidPerformanceError(
                "Duration must be between 1 and 360 minutes."
            )
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
        names = [_tidy(name) for name in participants]
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
        name = _tidy(name)
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


# --- The festival: the only way in, so the rules always apply. ---


class Festival:
    def __init__(
        self,
        name: str,
        first_day: str,
        last_day: str,
        venues: list[Venue] = (),
        artists: list[Artist] = (),
    ) -> None:
        self._name = name
        self._first_day = first_day
        self._last_day = last_day
        self._venues = list(venues)
        self._artists = list(artists)
        self._performances: list[Performance] = []

    # Read-only. The collections come back as copies.

    @property
    def name(self) -> str:
        return self._name

    @property
    def first_day(self) -> str:
        return self._first_day

    @property
    def last_day(self) -> str:
        return self._last_day

    @property
    def venues(self) -> list[Venue]:
        return list(self._venues)

    @property
    def artists(self) -> list[Artist]:
        return list(self._artists)

    @property
    def performances(self) -> list[Performance]:
        return list(self._performances)

    # Finding.

    def get_venue(self, slug: str) -> Venue:
        for venue in self._venues:
            if venue.slug == slug:
                return venue
        raise NotFoundError(f"No venue '{slug}'.")

    def get_artist(self, slug: str) -> Artist:
        for artist in self._artists:
            if artist.slug == slug:
                return artist
        raise NotFoundError(f"No artist '{slug}'.")

    def get_performance(self, performance_id: str) -> Performance:
        for performance in self._performances:
            if performance.id == performance_id:
                return performance
        raise NotFoundError(f"No performance '{performance_id}'.")

    def resolve_venue(self, slug: str) -> Venue:
        """The venue of a slug found inside a body or a file: unknown = invalid."""
        try:
            return self.get_venue(slug)
        except NotFoundError:
            raise InvalidPerformanceError(f"Unknown venue '{slug}'.") from None

    def resolve_artist(self, slug: str) -> Artist:
        try:
            return self.get_artist(slug)
        except NotFoundError:
            raise InvalidPerformanceError(f"Unknown artist '{slug}'.") from None

    def build_performance(self, data: dict) -> Performance:
        """A performance of the right class from a dict. Nothing is added yet."""
        kind = data.get("kind")
        if kind not in KINDS:
            raise InvalidPerformanceError(
                f"Unknown kind {kind!r}, use one of: {', '.join(KINDS)}."
            )
        return KINDS[kind].from_dict(data, self)

    # Changing: each method checks everything first, then changes.

    def add(self, performance: Performance) -> None:
        self._check(performance)
        self._performances.append(performance)

    def replace(self, performance_id: str, new: Performance) -> Performance:
        """Put `new` in the place of a performance. A refusal changes nothing."""
        old = self.get_performance(performance_id)
        self._check(new, ignore=old)  # a show may keep its own slot
        self._performances[self._performances.index(old)] = new
        return new

    def cancel(self, performance_id: str) -> Performance:
        performance = self.get_performance(performance_id)
        self._performances.remove(performance)
        return performance

    def register(self, performance_id: str, name: str) -> Performance:
        performance = self.get_performance(performance_id)
        performance.register(name)
        return performance

    def add_artist(self, name: str, bio: str = "", photo_url: str = "") -> Artist:
        artist = Artist(name=_tidy(name), bio=bio or "", photo_url=photo_url or "")
        if artist.slug == "":
            raise InvalidValueError("An artist needs a name with letters or digits.")
        for existing in self._artists:
            if existing == artist:
                raise ConflictError(f"{existing.name} already exists.")
        self._artists.append(artist)
        return artist

    def _check(
        self, performance: Performance, ignore: Optional[Performance] = None
    ) -> None:
        """The rules that need the whole festival."""
        if performance.venue not in self._venues:
            raise InvalidPerformanceError(f"Unknown venue '{performance.venue.slug}'.")
        for artist in performance.artists:
            if artist not in self._artists:
                raise InvalidPerformanceError(f"Unknown artist '{artist.slug}'.")

        day = performance.festival_day
        if not self._first_day <= day <= self._last_day:
            raise InvalidPerformanceError(f"{day} is not a day of the festival.")

        for other in self._performances:
            if other is ignore:
                continue
            too_close = (
                performance.start_datetime < other.end + BREAK
                and other.start_datetime < performance.end + BREAK
            )
            if not too_close:
                continue
            if other.venue.slug == performance.venue.slug:
                when = f"{other.start_datetime:%Y-%m-%d %H:%M}-{other.end:%H:%M}"
                raise ConflictError(
                    f"{other.venue.name} is busy with {other.title} ({when})."
                )
            for artist in performance.artists:
                if artist in other.artists:
                    raise ConflictError(f"{artist.name} is on stage in {other.title}.")

    # Reading.

    def programme(
        self, day: Optional[str] = None, venue: Optional[str] = None
    ) -> list[Performance]:
        return [
            p
            for p in sorted(self._performances)
            if (day is None or p.festival_day == str(day))
            and (venue is None or p.venue.slug == venue)
        ]

    def performances_by_artist(self, artist_slug: str) -> list[Performance]:
        self.get_artist(artist_slug)  # unknown slug: NotFoundError
        return sorted(p for p in self._performances if p.involves(artist_slug))

    def now_playing(self, at: datetime) -> list[Performance]:
        return [p for p in self._performances if p.start_datetime <= at < p.end]

    def up_next(self, at: datetime) -> list[Performance]:
        return sorted(p for p in self._performances if p.start_datetime > at)[:3]

    def to_dict(self) -> dict:
        """The dict written in the data file."""
        return {
            "name": self._name,
            "first_day": self._first_day,
            "last_day": self._last_day,
            "venues": [
                {"name": v.name, "capacity": v.capacity, "address": v.address}
                for v in self._venues
            ],
            "artists": [
                {"name": a.name, "bio": a.bio, "photo_url": a.photo_url}
                for a in self._artists
            ],
            "performances": [p.to_dict() for p in self._performances],
        }

    def __str__(self) -> str:
        return (
            f"{self._name}\n"
            f"Dates: {self._first_day} to {self._last_day}\n"
            f"Venues: {len(self._venues)}\n"
            f"Artists: {len(self._artists)}\n"
            f"Performances: {len(self._performances)}"
        )


# --- The data file. ---


def load_festival(path: Optional[Union[str, Path]] = None) -> Festival:
    """Read the data file. The same rules apply as when an organiser adds."""
    path = path or DATA_FILE
    with open(path, encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as error:
            raise InvalidDataError(f"{path} is not valid JSON: {error}.") from error
    try:
        festival = Festival(
            name=data["name"],
            first_day=data["first_day"],
            last_day=data["last_day"],
            venues=[Venue(**venue) for venue in data["venues"]],
            artists=[Artist(**artist) for artist in data["artists"]],
        )
        for item in data["performances"]:
            festival.add(festival.build_performance(item))
    except FestivalError as error:
        raise InvalidDataError(f"Damaged data file {path}: {error}") from error
    except (KeyError, TypeError, AttributeError) as error:
        raise InvalidDataError(f"Damaged data file {path}: {error!r}") from error
    return festival


def save_festival(
    festival: Festival, path: Optional[Union[str, Path]] = None
) -> None:
    """Write the data file: all of it, or nothing (no half-written file)."""
    path = Path(path or DATA_FILE)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as file:
        json.dump(festival.to_dict(), file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp, path)


def add_performance(festival: Festival, performance: Performance) -> None:
    """Add a performance and save the festival."""
    festival.add(performance)
    save_festival(festival)


def cancel_performance(festival: Festival, performance_id: str) -> Performance:
    """Cancel a performance and save the festival."""
    performance = festival.cancel(performance_id)
    save_festival(festival)
    return performance


# --- Printing, for the command line. ---


def print_summary(festival: Festival) -> None:
    """Print a summary of the festival."""
    print(festival)


def print_venues(festival: Festival) -> None:
    """Print all festival venues."""
    for venue in festival.venues:
        print(venue)


def print_programme(festival: Festival, day: Optional[str] = None) -> None:
    """Print the festival programme."""
    for performance in festival.programme(day=day):
        print(performance)


def print_artist(festival: Festival, artist_slug: str) -> None:
    """Print performances involving an artist."""
    for performance in festival.performances_by_artist(artist_slug):
        print(performance)


def print_now(festival: Festival, at: datetime) -> None:
    """Print performances playing now and coming up next."""
    print("On stage now:")
    for performance in festival.now_playing(at):
        print(performance)

    print("Up next:")
    for performance in festival.up_next(at):
        print(performance)