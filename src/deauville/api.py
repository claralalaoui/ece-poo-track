"""The API: every route of the contract, built around a storage.

`create_app(storage)` builds a new application. The server gives it the real
file, a test gives it its own copy or a memory storage.
"""

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

from deauville.errors import (
    ConflictError,
    FestivalError,
    InvalidDataError,
    InvalidValueError,
    NotFoundError,
)
from deauville.festival import Festival
from deauville.storage import Storage

DEFAULT_WEB_DIR = Path("web")

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


# --- Bodies: the shape of the JSON the admin sends. FastAPI refuses another
# shape (a missing field, text instead of a number) with a 422 by itself. ---


class PerformanceIn(BaseModel):
    """The JSON to add or replace a performance; the fields of the three kinds."""

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
    """The JSON to register a participant."""

    name: str


class ArtistIn(BaseModel):
    """The JSON to add an artist."""

    name: str
    bio: str = ""
    photo_url: str = ""


def create_app(storage: Storage, web_dir: Optional[Path] = None) -> FastAPI:
    """A new application around a storage (and the folder of the website)."""
    app = FastAPI()
    web_dir = Path(web_dir) if web_dir else DEFAULT_WEB_DIR

    @app.exception_handler(FestivalError)
    def festival_error(request: Request, error: FestivalError) -> JSONResponse:
        return JSONResponse(
            status_code=status_of(error), content={"detail": str(error)}
        )

    @app.exception_handler(OSError)
    def file_error(request: Request, error: OSError) -> JSONResponse:
        """The data file cannot be read or written: the server's fault, a 500."""
        return JSONResponse(
            status_code=500, content={"detail": "The data file cannot be used."}
        )

    # One writer at a time, and the storage is written only if nothing was refused.
    lock = threading.Lock()

    @contextmanager
    def editing() -> Iterator[Festival]:
        """Load the festival, let the route change it, save. An error saves nothing."""
        with lock:
            festival = storage.load()
            yield festival
            storage.save(festival)

    # --- Read. ---

    @app.get("/api/festival")
    def get_festival() -> dict:
        festival = storage.load()

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
    def get_venues() -> list[dict]:
        festival = storage.load()

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
    def get_artists() -> list[dict]:
        festival = storage.load()

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
    ) -> list[dict]:
        festival = storage.load()

        if venue is not None:
            festival.get_venue(venue)  # unknown venue: NotFoundError, so 404

        performances = festival.programme(
            day=day.isoformat() if day else None,
            venue=venue,
        )

        return [performance.to_view() for performance in performances]

    @app.get("/api/performances/{performance_id}")
    def get_performance(performance_id: str) -> dict:
        return storage.load().get_performance(performance_id).to_view()

    @app.get("/api/artists/{slug}")
    def get_artist(slug: str) -> dict:
        festival = storage.load()
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
    def get_now(at: Optional[datetime] = None) -> dict:
        festival = storage.load()
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
    admin_dir = web_dir / "admin"
    public_dir = web_dir / "public"
    if admin_dir.is_dir():
        admin = StaticFiles(directory=str(admin_dir), html=True)
        app.mount("/admin", admin, name="admin")
    if public_dir.is_dir():
        website = StaticFiles(directory=str(public_dir), html=True)
        app.mount("/", website, name="website")

    return app
