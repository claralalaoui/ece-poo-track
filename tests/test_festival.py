"""Steps 09 and 10: the three kinds, their rules, and the doors that are closed.

    uv run pytest tests/test_festival.py -v

Nothing here writes `data/festival.json`: the festival is built in memory, and
the saving tests use a folder of their own.
"""

from pathlib import Path

import pytest

from deauville.errors import (
    ConflictError,
    FestivalError,
    InvalidDataError,
    InvalidPerformanceError,
    InvalidValueError,
    NotFoundError,
)
from deauville.festival import Festival
from deauville.models import Artist, Venue
from deauville.performances import Lineup, Performance, SoloShow, Workshop
from deauville.storage import JsonStorage

ROOT = Path(__file__).parent.parent
NAMES = [
    "Nora Lebrun",
    "Maya Choukri",
    "Hugo Lemaire",
    "Tom Vasseur",
    "Inès Moreau",
    "Léa Fontaine",
    "Karim Benali",
]


@pytest.fixture
def festival() -> Festival:
    """A small festival, in memory, with a solo of Maya Choukri at Le Kiosque."""
    festival = Festival(
        "Test",
        "2027-06-10",
        "2027-06-13",
        venues=[
            Venue("Grand Casino", 650),
            Venue("Le Kiosque", 120),
            Venue("La Cabane", 40),
        ],
        artists=[Artist(name) for name in NAMES],
    )
    festival.add(solo(festival, "2027-06-13T15:00", artist="maya-choukri", minutes=60))
    return festival


def solo(festival, start, artist="nora-lebrun", venue="le-kiosque", minutes=45, **more):
    """A solo show, built the way a request body is."""
    body = {
        "kind": "solo",
        "title": "A solo",
        "venue": venue,
        "start": start,
        "duration_minutes": minutes,
        "artist": artist,
    }
    return festival.build_performance({**body, **more})


def lineup(festival, acts, minutes, host="tom-vasseur", start="2027-06-12T20:00"):
    return festival.build_performance(
        {
            "kind": "lineup",
            "title": "A lineup",
            "venue": "grand-casino",
            "start": start,
            "duration_minutes": minutes,
            "host": host,
            "acts": acts,
        }
    )


def workshop(festival, places, venue="grand-casino", participants=()):
    return festival.build_performance(
        {
            "kind": "workshop",
            "title": "A workshop",
            "venue": venue,
            "start": "2027-06-11T10:00",
            "duration_minutes": 90,
            "teacher": "ines-moreau",
            "max_participants": places,
            "participants": list(participants),
        }
    )


# --- Step 09: one family, three kinds. ---


def test_a_performance_cannot_be_created_directly():
    with pytest.raises(TypeError):
        Performance("Nothing", Venue("Somewhere", 10), "2027-06-10T10:00", 30)


def test_each_kind_is_its_own_class(festival):
    assert isinstance(solo(festival, "2027-06-11T10:00"), SoloShow)
    assert isinstance(lineup(festival, ["maya-choukri", "hugo-lemaire"], 40), Lineup)
    assert isinstance(workshop(festival, 10), Workshop)


def test_each_kind_writes_its_own_summary(festival):
    two_acts = lineup(festival, ["maya-choukri", "hugo-lemaire"], 40)
    assert two_acts.summary() == (
        "hosted by Tom Vasseur, with Maya Choukri, Hugo Lemaire"
    )
    assert solo(festival, "2027-06-11T10:00", artist="lea-fontaine").summary() == (
        "Léa Fontaine"
    )
    assert workshop(festival, 12, participants=["Lou M."]).summary() == (
        "with Inès Moreau, 1/12 places taken"
    )


def test_the_summaries_of_the_data_file():
    festival = JsonStorage(ROOT / "data" / "festival.json").load()
    summaries = {
        "le-kiosque-2027-06-12-0100": (
            "hosted by Tom Vasseur, with Hugo Lemaire, Maya Choukri"
        ),
        "la-cabane-2027-06-11-1030": "with Inès Moreau, 3/12 places taken",
        "grand-casino-2027-06-11-2030": "Léa Fontaine",
    }
    for performance_id, summary in summaries.items():
        assert festival.get_performance(performance_id).summary() == summary


def test_minimum_age_is_between_0_and_18(festival):
    for age in (0, 16, 18):
        assert solo(festival, "2027-06-11T10:00", min_age=age).min_age == age
    for age in (-1, 19):
        with pytest.raises(InvalidPerformanceError, match="minimum age"):
            solo(festival, "2027-06-11T10:00", min_age=age)


def test_a_lineup_needs_two_acts(festival):
    with pytest.raises(InvalidPerformanceError, match="at least two acts"):
        lineup(festival, ["maya-choukri"], 60)


def test_an_act_cannot_be_listed_twice(festival):
    with pytest.raises(InvalidPerformanceError, match="twice"):
        lineup(festival, ["maya-choukri", "maya-choukri"], 60)


def test_the_host_is_not_an_act(festival):
    with pytest.raises(InvalidPerformanceError, match="host"):
        lineup(festival, ["maya-choukri", "tom-vasseur"], 60)


def test_a_lineup_needs_10_minutes_per_act_and_3_per_change(festival):
    acts = ["maya-choukri", "hugo-lemaire", "lea-fontaine"]
    with pytest.raises(InvalidPerformanceError, match="36"):
        lineup(festival, acts, 35)  # 3 x 10 + 2 x 3 = 36
    assert lineup(festival, acts, 36).duration_minutes == 36


def test_a_workshop_has_at_least_one_place(festival):
    with pytest.raises(InvalidPerformanceError, match="at least one place"):
        workshop(festival, 0)


def test_the_places_never_exceed_the_seats_of_the_venue(festival):
    big = workshop(festival, 999, venue="grand-casino")
    festival.add(big)
    assert festival.get_performance(big.id).places == 650
    assert big.places_left == 650
    assert workshop(festival, 999, venue="la-cabane").places == 40
    assert workshop(festival, 12, venue="la-cabane").places == 12


def test_a_workshop_cannot_start_over_full(festival):
    with pytest.raises(InvalidPerformanceError, match="places"):
        workshop(festival, 2, participants=["A", "B", "C"])


def test_every_kind_has_its_own_fields_in_its_view(festival):
    one_solo = solo(festival, "2027-06-11T10:00", min_age=16).to_view()
    assert one_solo["artist"] == "nora-lebrun"
    assert one_solo["min_age"] == 16
    assert "host" not in one_solo and "places_left" not in one_solo

    view = lineup(festival, ["maya-choukri", "hugo-lemaire"], 40).to_view()
    assert view["host"] == "tom-vasseur"
    assert view["acts"] == ["maya-choukri", "hugo-lemaire"]
    assert [a["name"] for a in view["artists"]] == [
        "Tom Vasseur",
        "Maya Choukri",
        "Hugo Lemaire",
    ]

    view = workshop(festival, 12, participants=["Lou M."]).to_view()
    assert view["teacher"] == "ines-moreau"
    assert view["max_participants"] == 12
    assert view["participants"] == ["Lou M."]
    assert view["places_left"] == 11


def test_the_kind_chooses_the_class_in_one_place_only():
    for path in (ROOT / "src" / "deauville").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "kind ==" not in source, path.name
        assert "kind !=" not in source, path.name


def test_an_unknown_kind_is_refused(festival):
    with pytest.raises(InvalidPerformanceError, match="Unknown kind"):
        festival.build_performance({"kind": "circus"})


# --- Step 09/10: the rules of the festival, through the festival. ---


def test_a_solo_show_is_listed(festival):
    show = solo(festival, "2027-06-13T11:00")
    festival.add(show)
    assert show.id == "le-kiosque-2027-06-13-1100"
    assert show in festival.programme(day="2027-06-13")


def test_a_busy_venue_is_refused(festival):
    festival.add(solo(festival, "2027-06-13T11:00"))
    with pytest.raises(ConflictError, match="Le Kiosque is busy"):
        festival.add(solo(festival, "2027-06-13T11:30", artist="hugo-lemaire"))


def test_an_artist_on_stage_elsewhere_is_refused(festival):
    festival.add(solo(festival, "2027-06-13T11:00"))  # Nora, until 11:45
    other = solo(festival, "2027-06-13T12:00", venue="grand-casino")
    with pytest.raises(ConflictError, match="Nora Lebrun is on stage"):
        festival.add(other)


def test_an_artist_as_an_act_of_a_lineup_counts(festival):
    festival.add(solo(festival, "2027-06-12T20:30", artist="maya-choukri"))
    clash = lineup(festival, ["maya-choukri", "hugo-lemaire"], 40)  # at 20:00
    with pytest.raises(ConflictError, match="Maya Choukri is on stage"):
        festival.add(clash)


def test_thirty_minutes_after_is_enough(festival):
    festival.add(solo(festival, "2027-06-13T11:00"))  # ends 11:45
    festival.add(solo(festival, "2027-06-13T12:15"))  # exactly 30 minutes later
    assert len(festival.programme(venue="le-kiosque")) == 3


def test_a_day_outside_the_festival_is_refused(festival):
    with pytest.raises(InvalidPerformanceError, match="not a day of the festival"):
        festival.add(solo(festival, "2027-06-14T10:00"))


def test_a_show_at_one_in_the_morning_belongs_to_the_day_before(festival):
    show = solo(festival, "2027-06-14T01:00")
    festival.add(show)  # 01:00 on the 14th is still the 13th
    assert show.festival_day == "2027-06-13"


def test_a_duration_of_0_or_361_is_refused(festival):
    for minutes in (0, 361):
        with pytest.raises(InvalidPerformanceError, match="between 1 and 360"):
            solo(festival, "2027-06-11T10:00", minutes=minutes)


def test_an_unknown_venue_or_artist_is_refused(festival):
    with pytest.raises(InvalidPerformanceError, match="Unknown venue"):
        solo(festival, "2027-06-11T10:00", venue="nowhere")
    with pytest.raises(InvalidPerformanceError, match="Unknown artist"):
        solo(festival, "2027-06-11T10:00", artist="nobody")


def test_a_performance_built_outside_must_use_the_festivals_venues(festival):
    stranger = SoloShow(
        "Alien", Venue("Moon", 5), "2027-06-11T10:00", 30, Artist("Nora Lebrun")
    )
    with pytest.raises(InvalidPerformanceError, match="Unknown venue"):
        festival.add(stranger)


# --- Step 10: nobody can bypass the rules. ---


def test_the_collections_of_the_festival_are_copies(festival):
    before = len(festival.performances)
    festival.performances.append("anything")
    festival.performances.clear()
    festival.venues.clear()
    festival.artists.clear()
    assert len(festival.performances) == before
    assert len(festival.venues) == 3
    assert len(festival.artists) == len(NAMES)


def test_the_collections_of_a_lineup_and_a_workshop_are_copies(festival):
    one_lineup = lineup(festival, ["maya-choukri", "hugo-lemaire"], 40)
    one_lineup.acts.clear()
    assert len(one_lineup.acts) == 2

    one_workshop = workshop(festival, 12, participants=["Lou M."])
    one_workshop.participants.append("Intruder")
    assert one_workshop.participants == ["Lou M."]


def test_a_performance_cannot_be_changed_from_outside(festival):
    show = festival.programme()[0]
    with pytest.raises(AttributeError):
        show.start = "2027-06-10T10:00"
    with pytest.raises(AttributeError):
        show.duration_minutes = 1
    with pytest.raises(AttributeError):
        festival.venues[0].capacity = 1  # a venue is frozen too


def test_every_error_belongs_to_the_family():
    for error in (
        NotFoundError,
        ConflictError,
        InvalidValueError,
        InvalidPerformanceError,
        InvalidDataError,
    ):
        assert issubclass(error, FestivalError)


def test_one_except_catches_the_whole_family(festival):
    actions = [
        lambda: festival.get_performance("nothing-2027-06-10-1000"),
        lambda: festival.add(solo(festival, "2027-06-13T15:00")),
        lambda: festival.add(solo(festival, "2027-06-20T15:00")),
    ]
    for action in actions:
        with pytest.raises(FestivalError):
            action()


def test_moving_a_performance_changes_its_id(festival):
    show = solo(festival, "2027-06-13T11:00")
    festival.add(show)
    moved = festival.replace(show.id, solo(festival, "2027-06-13T12:00"))
    assert moved.id == "le-kiosque-2027-06-13-1200"
    with pytest.raises(NotFoundError):
        festival.get_performance("le-kiosque-2027-06-13-1100")
    assert festival.get_performance("le-kiosque-2027-06-13-1200") is moved


def test_a_refused_move_leaves_the_schedule_as_it_was(festival):
    show = solo(festival, "2027-06-13T11:00")
    festival.add(show)
    festival.replace(show.id, solo(festival, "2027-06-13T12:00"))
    before = [p.id for p in festival.performances]

    # Maya Choukri plays at Le Kiosque at 15:00.
    with pytest.raises(ConflictError):
        festival.replace(
            "le-kiosque-2027-06-13-1200", solo(festival, "2027-06-13T15:00")
        )

    assert [p.id for p in festival.performances] == before
    still_there = festival.get_performance("le-kiosque-2027-06-13-1200")
    assert still_there.start.endswith("12:00")


def test_moving_an_unknown_performance_is_not_found(festival):
    with pytest.raises(NotFoundError):
        festival.replace("nothing-2027-06-10-1000", solo(festival, "2027-06-11T10:00"))


def test_cancelling_twice(festival):
    festival.cancel("le-kiosque-2027-06-13-1500")
    with pytest.raises(NotFoundError):
        festival.cancel("le-kiosque-2027-06-13-1500")


def test_a_participant_cannot_register_twice(festival):
    festival.add(workshop(festival, 5))
    festival.register("grand-casino-2027-06-11-1000", "Lou M.")
    for name in ("Lou M.", "lou   m."):
        with pytest.raises(ConflictError, match="already registered"):
            festival.register("grand-casino-2027-06-11-1000", name)


def test_a_full_workshop_refuses(festival):
    festival.add(workshop(festival, 1))
    festival.register("grand-casino-2027-06-11-1000", "Lou M.")
    with pytest.raises(ConflictError, match="full"):
        festival.register("grand-casino-2027-06-11-1000", "Yanis B.")


def test_only_a_workshop_takes_registrations(festival):
    with pytest.raises(InvalidPerformanceError, match="registrations"):
        festival.register("le-kiosque-2027-06-13-1500", "Lou M.")
    with pytest.raises(NotFoundError):
        festival.register("nothing-2027-06-10-1000", "Lou M.")


def test_an_artist_exists_once_whatever_the_spelling(festival):
    artist = festival.add_artist("Zoé Tanguy")
    assert artist.slug == "zoe-tanguy"
    with pytest.raises(ConflictError, match="already exists"):
        festival.add_artist("zoe tanguy")
    with pytest.raises(InvalidValueError):
        festival.add_artist("   ")


# --- Saving and loading. ---


def test_what_is_changed_is_saved(festival, tmp_path):
    festival.add(solo(festival, "2027-06-13T11:00"))
    festival.add_artist("Zoé Tanguy")
    festival.add(workshop(festival, 12, participants=["Lou M."]))
    path = tmp_path / "festival.json"

    JsonStorage(path).save(festival)
    again = JsonStorage(path).load()

    assert [p.id for p in again.performances] == [p.id for p in festival.performances]
    assert again.get_artist("zoe-tanguy").name == "Zoé Tanguy"
    assert again.get_performance("grand-casino-2027-06-11-1000").participants == [
        "Lou M."
    ]


def test_the_data_file_has_no_empty_fields_of_other_kinds(festival, tmp_path):
    path = tmp_path / "festival.json"
    JsonStorage(path).save(festival)
    assert "null" not in path.read_text(encoding="utf-8")


def test_a_damaged_file_is_an_error_of_the_family(tmp_path):
    path = tmp_path / "festival.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(InvalidDataError):
        JsonStorage(path).load()
    path.write_text('{"name": "x"}', encoding="utf-8")
    with pytest.raises(InvalidDataError):
        JsonStorage(path).load()
