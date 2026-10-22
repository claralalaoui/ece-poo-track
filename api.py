from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from typing import Optional
from festival import load_festival, make_slug

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "web" / "public"


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

    if venue is not None and not any(
        item.slug == venue for item in festival.venues
    ):
        raise HTTPException(
            status_code=404,
            detail=f"No venue '{venue}'.",
        )

    performances = festival.programme(
        day=day.isoformat() if day else None,
        venue=venue,
    )

    return [performance.to_view() for performance in performances]



@app.get("/api/performances/{performance_id}")
def get_performance(performance_id: str):
    festival = load_festival()
    performance = festival.find_performance(performance_id)

    if performance is None:
        raise HTTPException(
            status_code=404,
            detail=f"No performance '{performance_id}'.",
        )

    return performance.to_view()




@app.get("/api/artists/{slug}")
def get_artist(slug: str):
    festival = load_festival()
    artist = next(
        (item for item in festival.artists if item.slug == slug),
        None,
    )

    if artist is None:
        raise HTTPException(
            status_code=404,
            detail=f"No artist '{slug}'.",
        )

    performances = festival.performances_by_artist(slug)

    return {
        "slug": artist.slug,
        "name": artist.name,
        "bio": artist.bio,
        "photo_url": artist.photo_url,
        "performances": [
            performance.to_view() for performance in performances
        ],
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
                "venue": p.venue,
                "start": p.start,
                "duration_minutes": p.duration_minutes,
            }
            for p in festival.now_playing(current_time)
        ],
        "up_next": [
            {
                "id": p.id,
                "title": p.title,
                "venue": p.venue,
                "start": p.start,
                "duration_minutes": p.duration_minutes,
            }
            for p in festival.up_next(current_time)
        ],
    }

if PUBLIC_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(PUBLIC_DIR), html=True),
        name="website",
    )


