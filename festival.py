import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta


DATA_FILE = "data/festival.json"


@dataclass
class Venue:
    name: str
    capacity: int
    address: str = ""

    @property
    def slug(self):
        return make_slug(self.name)


@dataclass
class Artist:
    name: str
    bio: str = ""
    photo_url: str = ""

    @property
    def slug(self):
        return make_slug(self.name)

    def __eq__(self, other):
        if not isinstance(other, Artist):
            return NotImplemented
        return self.slug == other.slug


@dataclass
class Performance:
    title: str
    kind: str
    venue: str
    start: str
    duration_minutes: int
    acts: list = field(default_factory=list)
    description: str = ""
    artist: str = None
    host: str = None
    teacher: str = None
    min_age: int = None
    max_participants: int = None
    participants: list = field(default_factory=list)

    def __post_init__(self):
        self.acts = list(self.acts or [])
        self.participants = list(self.participants or [])
        self.start_datetime

    @property
    def start_datetime(self):
        return datetime.strptime(self.start, "%Y-%m-%dT%H:%M")

    @property
    def end(self):
        return self.start_datetime + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self):
        day = self.start_datetime
        if day.hour < 6:
            day -= timedelta(days=1)
        return day.date().isoformat()

    @property
    def id(self):
        return f"{self.venue}-{self.start_datetime:%Y-%m-%d-%H%M}"

    def involves(self, artist_slug):
        artists = {self.artist, self.host, self.teacher}
        artists.update(self.acts)
        return artist_slug in artists

    def to_view(self):
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "venue": self.venue,
            "start": self.start,
            "end": self.end.isoformat(),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
            "artist": self.artist,
            "host": self.host,
            "teacher": self.teacher,
            "acts": self.acts,
            "festival_day": self.festival_day,
        }

    def __lt__(self, other):
        if not isinstance(other, Performance):
            return NotImplemented
        return (
            self.start_datetime,
            self.venue,
        ) < (
            other.start_datetime,
            other.venue,
        )

    def __str__(self):
        return f"{self.start_datetime:%H:%M} - {self.title} ({self.venue})"


def load_festival():
    """Load festival data and convert dictionaries into objects."""
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    venues = [Venue(**venue) for venue in data["venues"]]
    artists = [Artist(**artist) for artist in data["artists"]]
    performances = [
        Performance(**performance)
        for performance in data["performances"]
    ]

    return Festival(
        name=data["name"],
        first_day=data["first_day"],
        last_day=data["last_day"],
        venues=venues,
        artists=artists,
        _performances=performances,
    )




def make_slug(name):
    """Convert a name into a URL-friendly slug."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")




def save_festival(festival):
    """Save festival objects back to the JSON file."""
    data = {
        "name": festival.name,
        "first_day": festival.first_day,
        "last_day": festival.last_day,
        "venues": [
            {
                "name": venue.name,
                "capacity": venue.capacity,
                "address": venue.address,
            }
            for venue in festival.venues
        ],
        "artists": [
            {
                "name": artist.name,
                "bio": artist.bio,
                "photo_url": artist.photo_url,
            }
            for artist in festival.artists
        ],
        "performances": [
            {
                "title": p.title,
                "kind": p.kind,
                "venue": p.venue,
                "start": p.start,
                "duration_minutes": p.duration_minutes,
                "description": p.description,
                "artist": p.artist,
                "host": p.host,
                "teacher": p.teacher,
                "acts": p.acts,
                "min_age": p.min_age,
                "max_participants": p.max_participants,
                "participants": p.participants,
            }
            for p in festival.performances
        ],
    }

    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")




def find_venue(festival, slug):
    """Find a venue by its slug."""
    return next(
        (venue for venue in festival.venues if venue.slug == slug),
        None,
    )


def find_artist(festival, slug):
    """Find an artist by their slug."""
    return next(
        (artist for artist in festival.artists if artist.slug == slug),
        None,
    )




def performance_start(performance):
    """Return the start datetime of a performance."""
    return performance.start_datetime


def performance_end(performance):
    """Return the end datetime of a performance."""
    return performance.end




def festival_day(performance):
    """Return the festival day of a performance."""
    return performance.festival_day



def performance_artists(performance):
    """Return all artist slugs involved in a performance."""
    artists = {
        performance.artist,
        performance.host,
        performance.teacher,
        *performance.acts,
    }
    artists.discard(None)
    return artists



def performance_id(performance):
    """Return the unique ID of a performance."""
    return performance.id





def validate_performance(festival, new_performance):
    """Validate a performance before adding it to the festival."""
    venue = find_venue(festival, new_performance.venue)
    if venue is None:
        raise ValueError(f"Unknown venue '{new_performance.venue}'.")

    artist_slugs = {
        new_performance.artist,
        new_performance.host,
        new_performance.teacher,
        *new_performance.acts,
    }
    artist_slugs.discard(None)

    for artist_slug in artist_slugs:
        if find_artist(festival, artist_slug) is None:
            raise ValueError(f"Unknown artist '{artist_slug}'.")

    if not 1 <= new_performance.duration_minutes <= 360:
        raise ValueError("Duration must be between 1 and 360 minutes.")

    day = new_performance.festival_day
    if not festival.first_day <= day <= festival.last_day:
        raise ValueError("Performance is outside the festival dates.")

    start = new_performance.start_datetime
    end = new_performance.end

    for existing in festival.performances:
        existing_start = existing.start_datetime
        existing_end = existing.end

        same_venue = existing.venue == new_performance.venue
        shared_artists = any(existing.involves(a) for a in artist_slugs)

        if same_venue or shared_artists:
            if (
                start < existing_end + timedelta(minutes=30)
                and end + timedelta(minutes=30) > existing_start
            ):
                raise ValueError(
                    "A performance needs a 30-minute break "
                    "at the same venue or for the same artist."
                )






def add_performance(festival, new_performance):
    """Add a performance and save the festival."""
    festival.add(new_performance)
    save_festival(festival)


def cancel_performance(festival, performance_id):
    """Cancel a performance and save the festival."""
    performance = festival.cancel(performance_id)
    save_festival(festival)
    return performance





def print_summary(festival):
    """Print a summary of the festival."""
    print(festival)




def print_venues(festival):
    """Print all festival venues."""
    for venue in festival.venues:
        print(venue)


def print_programme(festival, day=None):
    """Print the festival programme."""
    for performance in festival.programme(day=day):
        print(performance)


def print_artist(festival, artist_slug):
    """Print performances involving an artist."""
    performances = festival.performances_by_artist(artist_slug)
    for performance in performances:
        print(performance)




def print_now(festival, at):
    """Print performances playing now and coming up next."""
    now_playing = festival.now_playing(at)
    up_next = festival.up_next(at)

    print("On stage now:")
    for performance in now_playing:
        print(performance)

    print("Up next:")
    for performance in up_next:
        print(performance)


@dataclass
class Festival:
    name: str
    first_day: str
    last_day: str
    venues: list = field(default_factory=list)
    artists: list = field(default_factory=list)
    _performances: list = field(default_factory=list)

    @property
    def performances(self):
        return list(self._performances)

    def add(self, performance):
        data = {
            "name": self.name,
            "first_day": self.first_day,
            "last_day": self.last_day,
            "venues": self.venues,
            "artists": self.artists,
            "performances": self.performances,
        }
        validate_performance(self, performance)
        self._performances.append(performance)

    def find_performance(self, performance_id):
        return next(
            (p for p in self._performances if p.id == performance_id),
            None,
        )

    def cancel(self, performance_id):
        performance = self.find_performance(performance_id)
        if performance is None:
            raise ValueError(f"Unknown performance '{performance_id}'.")
        self._performances.remove(performance)
        return performance

    def programme(self, day=None, venue=None):
        performances = sorted(self._performances)
        return [
            p for p in performances
            if (day is None or p.festival_day == str(day))
            and (venue is None or p.venue == venue)
        ]

    def performances_by_artist(self, artist_slug):
        if find_artist(self, artist_slug) is None:
            raise ValueError(f"Unknown artist '{artist_slug}'.")

        return sorted(
            p for p in self._performances if p.involves(artist_slug)
        )

    def now_playing(self, at):
        return [
            p for p in self._performances
            if p.start_datetime <= at < p.end
        ]

    def up_next(self, at):
        return sorted(
            p for p in self._performances if p.start_datetime > at
        )[:3]

    def __str__(self):
        return (
            f"{self.name}\n"
            f"Dates: {self.first_day} to {self.last_day}\n"
            f"Venues: {len(self.venues)}\n"
            f"Artists: {len(self.artists)}\n"
            f"Performances: {len(self._performances)}"
        )