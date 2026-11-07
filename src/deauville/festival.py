"""The festival: the only way in, so the rules always apply.

Everything that changes the schedule goes through a method of `Festival`, so
the rules apply whether the call comes from the command line or the API. The
festival does not know where it is stored: see `deauville.storage`.
"""

from datetime import datetime, timedelta
from typing import Optional

from deauville.errors import (
    ConflictError,
    FestivalError,
    InvalidDataError,
    InvalidPerformanceError,
    InvalidValueError,
    NotFoundError,
)
from deauville.models import Artist, Venue, tidy
from deauville.performances import KINDS, Performance

BREAK = timedelta(minutes=30)  # between two performances of a venue or an artist


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
        artist = Artist(name=tidy(name), bio=bio or "", photo_url=photo_url or "")
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

    @classmethod
    def from_dict(cls, data: dict) -> "Festival":
        """Build a festival from the dict of `to_dict`.

        The same rules apply as when an organiser adds a performance, so a
        damaged file is refused with an `InvalidDataError`.
        """
        try:
            festival = cls(
                name=data["name"],
                first_day=data["first_day"],
                last_day=data["last_day"],
                venues=[Venue(**venue) for venue in data["venues"]],
                artists=[Artist(**artist) for artist in data["artists"]],
            )
            for item in data["performances"]:
                festival.add(festival.build_performance(item))
        except FestivalError as error:
            raise InvalidDataError(f"Damaged festival data: {error}") from error
        except (KeyError, TypeError, AttributeError) as error:
            raise InvalidDataError(f"Damaged festival data: {error!r}") from error
        return festival

    def __str__(self) -> str:
        return (
            f"{self._name}\n"
            f"Dates: {self._first_day} to {self._last_day}\n"
            f"Venues: {len(self._venues)}\n"
            f"Artists: {len(self._artists)}\n"
            f"Performances: {len(self._performances)}"
        )
