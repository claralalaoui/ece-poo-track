"""Step 12: the whole contract of API.md, tested through HTTP.

    uv run pytest tests/test_api.py -v

`TestClient` calls the application directly, without a server. Every test
builds its own application around a copy of the data in `tmp_path`: the file
`data/festival.json` is never written.
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deauville.api import create_app
from deauville.festival import Festival
from deauville.storage import JsonStorage, Storage

DATA_FILE = Path(__file__).parent.parent / "data" / "festival.json"


@pytest.fixture
def copy_of_data(tmp_path) -> Path:
    path = tmp_path / "festival.json"
    shutil.copy(DATA_FILE, path)
    return path


@pytest.fixture
def client(copy_of_data) -> TestClient:
    return TestClient(create_app(JsonStorage(copy_of_data)))


def solo_body(**changes) -> dict:
    """A solo show in a free slot (Le Kiosque, 12:00 on the first day)."""
    body = {
        "kind": "solo",
        "title": "Late night",
        "venue": "le-kiosque",
        "start": "2027-06-10T12:00",
        "duration_minutes": 45,
        "artist": "nora-lebrun",
    }
    return {**body, **changes}


def lineup_body(**changes) -> dict:
    body = {
        "kind": "lineup",
        "title": "Tiny gala",
        "venue": "le-kiosque",
        "start": "2027-06-10T12:00",
        "duration_minutes": 60,
        "host": "paul-kerbrat",
        "acts": ["nora-lebrun", "max-pellerin"],
    }
    return {**body, **changes}


def workshop_body(**changes) -> dict:
    body = {
        "kind": "workshop",
        "title": "Tiny workshop",
        "venue": "le-kiosque",
        "start": "2027-06-10T12:00",
        "duration_minutes": 60,
        "teacher": "ines-moreau",
        "max_participants": 2,
    }
    return {**body, **changes}


def file_content(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- Read. ---


def test_festival(client):
    response = client.get("/api/festival")
    assert response.status_code == 200
    body = response.json()
    assert body["first_day"] == "2027-06-10"
    assert body["last_day"] == "2027-06-13"
    assert body["days"] == [
        "2027-06-10",
        "2027-06-11",
        "2027-06-12",
        "2027-06-13",
    ]


def test_venues(client):
    response = client.get("/api/venues")
    assert response.status_code == 200
    venues = response.json()
    assert len(venues) == 4
    assert set(venues[0]) == {"slug", "name", "capacity", "address"}


def test_artists_are_sorted_by_slug(client):
    response = client.get("/api/artists")
    assert response.status_code == 200
    artists = response.json()
    assert len(artists) == 12
    assert set(artists[0]) == {"slug", "name"}
    slugs = [artist["slug"] for artist in artists]
    assert slugs == sorted(slugs)


def test_one_artist_with_their_performances(client):
    response = client.get("/api/artists/nora-lebrun")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nora Lebrun"
    assert set(body) == {"slug", "name", "bio", "photo_url", "performances"}
    assert body["performances"]
    for performance in body["performances"]:
        assert "nora-lebrun" in [a["slug"] for a in performance["artists"]]


def test_unknown_artist_is_404(client):
    response = client.get("/api/artists/nobody")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_programme_is_sorted_by_start(client):
    response = client.get("/api/programme")
    assert response.status_code == 200
    starts = [p["start"] for p in response.json()]
    assert len(starts) == 23
    assert starts == sorted(starts)


def test_programme_filtered_by_day(client):
    response = client.get("/api/programme", params={"day": "2027-06-11"})
    assert response.status_code == 200
    performances = response.json()
    assert performances
    assert {p["festival_day"] for p in performances} == {"2027-06-11"}


def test_programme_filtered_by_venue(client):
    response = client.get("/api/programme", params={"venue": "la-cabane"})
    assert response.status_code == 200
    performances = response.json()
    assert performances
    assert {p["venue"] for p in performances} == {"la-cabane"}


def test_programme_filtered_by_day_and_venue(client):
    params = {"day": "2027-06-11", "venue": "la-cabane"}
    response = client.get("/api/programme", params=params)
    assert response.status_code == 200
    performances = response.json()
    assert performances
    assert {p["venue"] for p in performances} == {"la-cabane"}
    assert {p["festival_day"] for p in performances} == {"2027-06-11"}


def test_programme_of_a_day_outside_the_festival_is_empty(client):
    response = client.get("/api/programme", params={"day": "2027-07-01"})
    assert response.status_code == 200
    assert response.json() == []


def test_programme_with_an_unknown_venue_is_404(client):
    response = client.get("/api/programme", params={"venue": "nowhere"})
    assert response.status_code == 404


def test_programme_with_a_bad_day_is_422(client):
    response = client.get("/api/programme", params={"day": "tomorrow"})
    assert response.status_code == 422


def test_one_performance(client):
    response = client.get("/api/performances/la-cabane-2027-06-11-1030")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "workshop"
    assert body["title"] == "Improv for Beginners"
    assert body["places_left"] == body["places"] - len(body["participants"])


def test_unknown_performance_is_404(client):
    assert client.get("/api/performances/nope").status_code == 404


def test_now_playing_and_up_next(client):
    response = client.get("/api/now", params={"at": "2027-06-10T21:00"})
    assert response.status_code == 200
    body = response.json()
    playing = {p["id"] for p in body["now_playing"]}
    assert "grand-casino-2027-06-10-2030" in playing
    assert body["up_next"]
    for performance in body["up_next"]:
        assert performance["start"] > "2027-06-10T21:00"


def test_now_with_a_bad_date_is_422(client):
    assert client.get("/api/now", params={"at": "later"}).status_code == 422


def test_now_without_at_uses_the_real_time(client):
    response = client.get("/api/now")
    assert response.status_code == 200
    assert response.json()["now_playing"] == []  # the festival is in 2027


# --- Write: add. ---


def test_add_a_solo_show(client, copy_of_data):
    response = client.post("/api/performances", json=solo_body())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "le-kiosque-2027-06-10-1200"
    assert body["kind"] == "solo"
    assert client.get(f"/api/performances/{body['id']}").status_code == 200
    # Written in the file: a new application sees it.
    other = TestClient(create_app(JsonStorage(copy_of_data)))
    assert other.get(f"/api/performances/{body['id']}").status_code == 200


def test_add_a_lineup(client):
    response = client.post("/api/performances", json=lineup_body())
    assert response.status_code == 201
    assert response.json()["acts"] == ["nora-lebrun", "max-pellerin"]


def test_add_a_workshop(client):
    response = client.post("/api/performances", json=workshop_body())
    assert response.status_code == 201
    assert response.json()["places"] == 2


def test_add_in_a_taken_slot_is_409_and_changes_nothing(client, copy_of_data):
    assert client.post("/api/performances", json=solo_body()).status_code == 201
    before = file_content(copy_of_data)
    response = client.post("/api/performances", json=solo_body(title="Again"))
    assert response.status_code == 409
    assert "busy" in response.json()["detail"]
    assert file_content(copy_of_data) == before


def test_add_needs_a_break_of_30_minutes_in_the_venue(client):
    assert client.post("/api/performances", json=solo_body()).status_code == 201
    # The first one ends at 12:45: 13:00 is too early, 13:15 is fine.
    too_early = solo_body(start="2027-06-10T13:00", artist="max-pellerin")
    assert client.post("/api/performances", json=too_early).status_code == 409
    fine = solo_body(start="2027-06-10T13:15", artist="max-pellerin")
    assert client.post("/api/performances", json=fine).status_code == 201


def test_add_an_artist_in_two_places_at_once_is_409(client):
    assert client.post("/api/performances", json=solo_body()).status_code == 201
    elsewhere = solo_body(venue="la-cabane")  # same time, same artist
    assert client.post("/api/performances", json=elsewhere).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"venue": "nowhere"},
        {"artist": "nobody"},
        {"kind": "opera"},
        {"duration_minutes": 0},
        {"duration_minutes": 361},
        {"start": "tomorrow"},
        {"title": "   "},
        {"min_age": 19},
    ],
)
def test_add_with_an_invalid_value_is_422(client, copy_of_data, changes):
    before = file_content(copy_of_data)
    response = client.post("/api/performances", json=solo_body(**changes))
    assert response.status_code == 422
    assert "detail" in response.json()
    assert file_content(copy_of_data) == before


def test_add_with_a_missing_field_is_422(client):
    body = solo_body()
    del body["title"]
    assert client.post("/api/performances", json=body).status_code == 422


def test_add_with_a_text_instead_of_a_number_is_422(client):
    body = solo_body(duration_minutes="long")
    assert client.post("/api/performances", json=body).status_code == 422


def test_add_a_lineup_with_one_act_is_422(client):
    body = lineup_body(acts=["nora-lebrun"])
    assert client.post("/api/performances", json=body).status_code == 422


def test_add_a_lineup_with_the_host_as_an_act_is_422(client):
    body = lineup_body(acts=["paul-kerbrat", "nora-lebrun"])
    assert client.post("/api/performances", json=body).status_code == 422


def test_add_a_lineup_too_short_for_its_acts_is_422(client):
    # 10 minutes per act and 3 per change: 4 acts need 49 minutes at least.
    body = lineup_body(
        duration_minutes=30,
        acts=["nora-lebrun", "max-pellerin", "lea-fontaine", "karim-benali"],
    )
    assert client.post("/api/performances", json=body).status_code == 422


# --- Write: replace. ---


def test_replace_keeps_the_id_when_the_slot_stays(client):
    client.post("/api/performances", json=solo_body())
    response = client.put(
        "/api/performances/le-kiosque-2027-06-10-1200",
        json=solo_body(title="Renamed"),
    )
    assert response.status_code == 200
    assert response.json()["id"] == "le-kiosque-2027-06-10-1200"
    assert response.json()["title"] == "Renamed"


def test_replace_that_changes_the_id(client):
    client.post("/api/performances", json=solo_body())
    old_id = "le-kiosque-2027-06-10-1200"
    response = client.put(
        f"/api/performances/{old_id}",
        json=solo_body(start="2027-06-10T14:00"),
    )
    assert response.status_code == 200
    assert response.json()["id"] == "le-kiosque-2027-06-10-1400"
    assert client.get(f"/api/performances/{old_id}").status_code == 404
    assert client.get("/api/performances/le-kiosque-2027-06-10-1400").status_code == 200


def test_replace_in_a_busy_slot_is_409_and_changes_nothing(client, copy_of_data):
    client.post("/api/performances", json=solo_body())
    before = file_content(copy_of_data)
    # Le Kiosque is busy at 22:30 (Open Mic Night).
    response = client.put(
        "/api/performances/le-kiosque-2027-06-10-1200",
        json=solo_body(start="2027-06-10T22:30"),
    )
    assert response.status_code == 409
    assert file_content(copy_of_data) == before
    assert client.get("/api/performances/le-kiosque-2027-06-10-1200").status_code == 200


def test_replace_with_an_invalid_value_is_422_and_changes_nothing(client, copy_of_data):
    client.post("/api/performances", json=solo_body())
    before = file_content(copy_of_data)
    response = client.put(
        "/api/performances/le-kiosque-2027-06-10-1200",
        json=solo_body(duration_minutes=0),
    )
    assert response.status_code == 422
    assert file_content(copy_of_data) == before


def test_replace_an_unknown_performance_is_404(client):
    response = client.put("/api/performances/nope", json=solo_body())
    assert response.status_code == 404


# --- Write: cancel. ---


def test_cancel(client):
    performance_id = "la-cabane-2027-06-11-1030"
    response = client.delete(f"/api/performances/{performance_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/performances/{performance_id}").status_code == 404
    ids = [p["id"] for p in client.get("/api/programme").json()]
    assert performance_id not in ids
    assert len(ids) == 22


def test_cancel_twice_is_404(client):
    performance_id = "la-cabane-2027-06-11-1030"
    assert client.delete(f"/api/performances/{performance_id}").status_code == 204
    assert client.delete(f"/api/performances/{performance_id}").status_code == 404


def test_cancel_an_unknown_performance_is_404(client):
    assert client.delete("/api/performances/nope").status_code == 404


# --- Write: participants. ---


def test_register_a_participant(client):
    url = "/api/performances/la-cabane-2027-06-11-1030/participants"
    before = client.get("/api/performances/la-cabane-2027-06-11-1030").json()
    response = client.post(url, json={"name": "Clara L."})
    assert response.status_code == 201
    body = response.json()
    assert "Clara L." in body["participants"]
    assert body["places_left"] == before["places_left"] - 1


def test_register_twice_is_409(client):
    url = "/api/performances/la-cabane-2027-06-11-1030/participants"
    assert client.post(url, json={"name": "Clara L."}).status_code == 201
    assert client.post(url, json={"name": "Clara L."}).status_code == 409


def test_register_in_a_full_workshop_is_409_and_changes_nothing(client, copy_of_data):
    created = client.post("/api/performances", json=workshop_body()).json()
    url = f"/api/performances/{created['id']}/participants"
    assert client.post(url, json={"name": "Ana"}).status_code == 201
    assert client.post(url, json={"name": "Ben"}).status_code == 201
    before = file_content(copy_of_data)
    response = client.post(url, json={"name": "Cleo"})
    assert response.status_code == 409
    assert "full" in response.json()["detail"]
    assert file_content(copy_of_data) == before


def test_register_in_something_that_is_not_a_workshop_is_422(client):
    url = "/api/performances/theatre-des-planches-2027-06-10-2100/participants"
    assert client.post(url, json={"name": "Clara L."}).status_code == 422


def test_register_with_a_blank_name_is_422(client):
    url = "/api/performances/la-cabane-2027-06-11-1030/participants"
    assert client.post(url, json={"name": "   "}).status_code == 422


def test_register_without_a_name_is_422(client):
    url = "/api/performances/la-cabane-2027-06-11-1030/participants"
    assert client.post(url, json={}).status_code == 422


def test_register_in_an_unknown_performance_is_404(client):
    response = client.post("/api/performances/nope/participants", json={"name": "A"})
    assert response.status_code == 404


# --- Write: artists. ---


def test_add_an_artist(client):
    body = {"name": "Jo Test", "bio": "New.", "photo_url": ""}
    response = client.post("/api/artists", json=body)
    assert response.status_code == 201
    assert response.json()["slug"] == "jo-test"
    assert response.json()["performances"] == []
    assert client.get("/api/artists/jo-test").status_code == 200
    assert "jo-test" in [a["slug"] for a in client.get("/api/artists").json()]


def test_add_an_artist_who_exists_is_409(client):
    response = client.post("/api/artists", json={"name": "Hugo Lemaire"})
    assert response.status_code == 409


def test_add_an_artist_with_a_blank_name_is_422(client):
    assert client.post("/api/artists", json={"name": "  "}).status_code == 422


def test_add_an_artist_without_a_name_is_422(client):
    assert client.post("/api/artists", json={"bio": "x"}).status_code == 422


# --- 500: the file. ---


class FailingSave(Storage):
    """A storage that reads fine and cannot write (full disk, read-only folder)."""

    def __init__(self, inner: Storage):
        self.inner = inner

    def load(self) -> Festival:
        return self.inner.load()

    def save(self, festival: Festival) -> None:
        raise OSError("disk full")


def test_a_file_that_cannot_be_written_is_500(copy_of_data):
    app = create_app(FailingSave(JsonStorage(copy_of_data)))
    client = TestClient(app, raise_server_exceptions=False)
    before = file_content(copy_of_data)
    response = client.post("/api/performances", json=solo_body())
    assert response.status_code == 500
    assert "detail" in response.json()
    assert file_content(copy_of_data) == before


def test_a_damaged_file_is_500(copy_of_data):
    copy_of_data.write_text("{ not json", encoding="utf-8")
    client = TestClient(create_app(JsonStorage(copy_of_data)))
    response = client.get("/api/programme")
    assert response.status_code == 500
    assert "detail" in response.json()


def test_a_file_with_wrong_data_is_500(copy_of_data):
    data = file_content(copy_of_data)
    data["performances"][0]["kind"] = "opera"
    copy_of_data.write_text(json.dumps(data), encoding="utf-8")
    client = TestClient(create_app(JsonStorage(copy_of_data)))
    assert client.get("/api/programme").status_code == 500


def test_a_missing_file_is_500(tmp_path):
    client = TestClient(
        create_app(JsonStorage(tmp_path / "missing.json")),
        raise_server_exceptions=False,
    )
    assert client.get("/api/festival").status_code == 500


# --- The application is built by a function: two apps never share anything. ---


def test_two_applications_are_independent(copy_of_data, tmp_path):
    other_file = tmp_path / "other.json"
    shutil.copy(DATA_FILE, other_file)
    first = TestClient(create_app(JsonStorage(copy_of_data)))
    second = TestClient(create_app(JsonStorage(other_file)))
    first.delete("/api/performances/la-cabane-2027-06-11-1030")
    assert second.get("/api/performances/la-cabane-2027-06-11-1030").status_code == 200


def test_the_real_data_file_is_never_written(client):
    before = DATA_FILE.read_bytes()
    client.post("/api/performances", json=solo_body())
    client.delete("/api/performances/la-cabane-2027-06-11-1030")
    assert DATA_FILE.read_bytes() == before
