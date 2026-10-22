import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from festival import (
    ConflictError,
    Festival,
    FestivalError,
    InvalidDataError,
    InvalidValueError,
    NotFoundError,
    load_festival,
    save_festival,
)

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "web" / "public"
ADMIN_DIR = BASE_DIR / "web" / "admin"


# --- Errors: one handler turns the family into statuses; routes never try. ---

STATUS = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (InvalidValueError, 422),
    (InvalidDataError, 500),
]


def status_of(error: FestivalError) -> int:
    """The HTTP status of an error of the family (a subclass uses its parent's)."""
    for error_class, status in STATUS:
        if isinstance(error, error_class):
            return status
    return 400


@app.exception_handler(FestivalError)
def festival_error(request: Request, error: FestivalError) -> JSONResponse:
    return JSONResponse(status_code=status_of(error), content={"detail": str(error)})


# --- Bodies: the shape of the JSON the admin sends. FastAPI refuses another
# shape (a missing field, text instead of a number) with a 422 by itself. ---


class PerformanceIn(BaseModel):
    kind: str
    title: str
    venue: str
    start: str
    duration_minutes: int
    description: str = ""
    artist: Optional[str] = None  # solo
    min_age: Optional[int] = None
    host: Optional[str] = None  # lineup
    acts: list[str] = []
    teacher: Optional[str] = None  # workshop
    max_participants: Optional[int] = None
    participants: list[str] = []


class ParticipantIn(BaseModel):
    name: str


class ArtistIn(BaseModel):
    name: str
    bio: str = ""
    photo_url: str = ""


# One writer at a time, and the file is written only if nothing was refused.
LOCK = threading.Lock()


@contextmanager
def editing() -> Iterator[Festival]:
    """Load the festival, let the route change it, save. An error saves nothing."""
    with LOCK:
        festival = load_festival()
        yield festival
        save_festival(festival)


# --- Read. ---


@app.get("/api/festival")
def get_festival():
    festival = load_festival()

    first_day = date.fromisoformat(festival.first_day)
    last_day = date.fromisoformat(festival.last_day)

    days = [
        (first_day + timedelta(days=i)).isoformat()
        for i in range((last_day - first_day).days + 1)
    ]

    return {
        "name": festival.name,
        "first_day": festival.first_day,
        "last_day": festival.last_day,
        "days": days,
    }


@app.get("/api/venues")
def get_venues():
    festival = load_festival()

    return [
        {
            "slug": venue.slug,
            "name": venue.name,
            "capacity": venue.capacity,
            "address": venue.address,
        }
        for venue in festival.venues
    ]


@app.get("/api/artists")
def get_artists():
    festival = load_festival()

    artists = [
        {
            "slug": artist.slug,
            "name": artist.name,
        }
        for artist in festival.artists
    ]

    return sorted(artists, key=lambda artist: artist["slug"])


@app.get("/api/programme")
def get_programme(
    day: Optional[date] = None,
    venue: Optional[str] = None,
):
    festival = load_festival()

    if venue is not None:
        festival.get_venue(venue)  # unknown venue: NotFoundError, so 404

    performances = festival.programme(
        day=day.isoformat() if day else None,
        venue=venue,
    )

    return [performance.to_view() for performance in performances]


@app.get("/api/performances/{performance_id}")
def get_performance(performance_id: str):
    return load_festival().get_performance(performance_id).to_view()


@app.get("/api/artists/{slug}")
def get_artist(slug: str):
    festival = load_festival()
    artist = festival.get_artist(slug)
    performances = festival.performances_by_artist(slug)

    return {
        "slug": artist.slug,
        "name": artist.name,
        "bio": artist.bio,
        "photo_url": artist.photo_url,
        "performances": [performance.to_view() for performance in performances],
    }


@app.get("/api/now")
def get_now(at: Optional[datetime] = None):
    festival = load_festival()
    current_time = at or datetime.now()

    return {
        "now_playing": [
            {
                "id": p.id,
                "title": p.title,
                "venue": p.venue.slug,
                "start": p.start,
                "duration_minutes": p.duration_minutes,
            }
            for p in festival.now_playing(current_time)
        ],
        "up_next": [
            {
                "id": p.id,
                "title": p.title,
                "venue": p.venue.slug,
                "start": p.start,
                "duration_minutes": p.duration_minutes,
            }
            for p in festival.up_next(current_time)
        ],
    }


# --- Write (admin). ---


@app.post("/api/performances", status_code=201)
def add_performance(body: PerformanceIn) -> dict:
    with editing() as festival:
        performance = festival.build_performance(body.model_dump())
        festival.add(performance)
    return performance.to_view()


@app.put("/api/performances/{performance_id}")
def replace_performance(performance_id: str, body: PerformanceIn) -> dict:
    with editing() as festival:
        new = festival.build_performance(body.model_dump())
        performance = festival.replace(performance_id, new)
    return performance.to_view()


@app.delete("/api/performances/{performance_id}", status_code=204)
def cancel_performance(performance_id: str) -> None:
    with editing() as festival:
        festival.cancel(performance_id)


@app.post("/api/performances/{performance_id}/participants", status_code=201)
def register_participant(performance_id: str, body: ParticipantIn) -> dict:
    with editing() as festival:
        performance = festival.register(performance_id, body.name)
    return performance.to_view()


@app.post("/api/artists", status_code=201)
def add_artist(body: ArtistIn) -> dict:
    with editing() as festival:
        artist = festival.add_artist(body.name, body.bio, body.photo_url)
    return {
        "slug": artist.slug,
        "name": artist.name,
        "bio": artist.bio,
        "photo_url": artist.photo_url,
        "performances": [],
    }


# The admin first: the mount of "/" would answer /admin/ otherwise.
if ADMIN_DIR.is_dir():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")

if PUBLIC_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(PUBLIC_DIR), html=True),
        name="website",
    )