"""Step 11: the storage behind an interface, and the command line.

    uv run pytest tests/test_storage_cli.py -v

Every test works on a copy of the data (`tmp_path`) or in memory: the file
`data/festival.json` is never written.
"""

import contextlib
import io
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from deauville.cli import main
from deauville.errors import InvalidDataError
from deauville.festival import Festival
from deauville.performances import SoloShow
from deauville.storage import JsonStorage, MemoryStorage, Storage

DATA_FILE = Path(__file__).parent.parent / "data" / "festival.json"


@pytest.fixture
def data() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def copy_of_data(tmp_path) -> Path:
    path = tmp_path / "festival.json"
    shutil.copy(DATA_FILE, path)
    return path


def run(*args: str) -> tuple[int, str]:
    """Run the command line, return its exit code and what it printed."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(list(args))
    return code, output.getvalue()


def new_show(festival: Festival) -> SoloShow:
    return festival.build_performance(
        {
            "kind": "solo",
            "title": "Late night",
            "venue": "le-kiosque",
            "start": "2027-06-10T12:00",
            "duration_minutes": 45,
            "artist": "nora-lebrun",
        }
    )


# --- The interface and its two storages. ---


def test_the_interface_cannot_be_created():
    with pytest.raises(TypeError):
        Storage()


def test_both_storages_are_storages(copy_of_data, data):
    assert isinstance(JsonStorage(copy_of_data), Storage)
    assert isinstance(MemoryStorage(data), Storage)


@pytest.mark.parametrize("kind", ["json", "memory"])
def test_what_is_saved_is_loaded_again(kind, copy_of_data, data):
    storage = JsonStorage(copy_of_data) if kind == "json" else MemoryStorage(data)
    festival = storage.load()
    count = len(festival.performances)
    festival.add(new_show(festival))
    storage.save(festival)

    assert len(storage.load().performances) == count + 1


def test_a_change_that_is_not_saved_is_not_kept(data):
    storage = MemoryStorage(data)
    festival = storage.load()
    festival.add(new_show(festival))  # no save

    assert len(storage.load().performances) == len(festival.performances) - 1


def test_the_memory_storage_keeps_its_own_copy(data):
    storage = MemoryStorage(data)
    data["performances"].clear()
    assert len(storage.load().performances) > 0


def test_a_missing_file_is_an_os_error(tmp_path):
    with pytest.raises(OSError):
        JsonStorage(tmp_path / "nothing.json").load()


def test_a_damaged_file_is_refused(tmp_path):
    path = tmp_path / "festival.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(InvalidDataError):
        JsonStorage(path).load()
    with pytest.raises(InvalidDataError):
        MemoryStorage({"name": "x"}).load()


def test_saving_leaves_no_temporary_file(copy_of_data):
    storage = JsonStorage(copy_of_data)
    storage.save(storage.load())
    assert [p.name for p in copy_of_data.parent.iterdir()] == ["festival.json"]


# --- The command line. ---


def test_no_command_prints_the_summary(copy_of_data):
    code, output = run("--data", str(copy_of_data))
    assert code == 0
    assert output == (
        "Deauville Festival du Rire 2027\n"
        "From 2027-06-10 to 2027-06-13\n"
        "4 venues, 12 artists, 23 performances\n"
    )


def test_programme_of_a_day(copy_of_data):
    code, output = run("--data", str(copy_of_data), "programme", "2027-06-11")
    assert code == 0
    assert output.startswith("Programme for Friday 11 June:\n")
    assert "20:30-21:50 | Grand Casino | Tall Tales (solo)" in output


def test_the_option_data_works_after_the_command_too(copy_of_data):
    code, output = run("programme", "2027-06-11", "--data", str(copy_of_data))
    assert code == 0
    assert "Tall Tales" in output


def test_an_unknown_artist_is_an_error_message(copy_of_data):
    code, output = run("--data", str(copy_of_data), "artist", "nobody")
    assert code == 1
    assert output.startswith("Error: ")


def test_cancel_changes_the_file(copy_of_data):
    code, output = run(
        "--data", str(copy_of_data), "cancel", "grand-casino-2027-06-11-2030"
    )
    assert code == 0
    assert output == "Cancelled: Tall Tales\n"
    assert "grand-casino-2027-06-11-2030" not in copy_of_data.read_text("utf-8")


def test_cancelling_twice_is_an_error(copy_of_data):
    arguments = ("--data", str(copy_of_data), "cancel", "grand-casino-2027-06-11-2030")
    assert run(*arguments)[0] == 0
    code, output = run(*arguments)
    assert code == 1
    assert "No performance" in output


def test_a_bad_date_is_refused_by_the_parser(copy_of_data):
    with pytest.raises(SystemExit) as stop:
        run("--data", str(copy_of_data), "now", "yesterday")
    assert stop.value.code == 2


def test_the_real_data_file_is_never_written(copy_of_data):
    before = DATA_FILE.read_bytes()
    run("--data", str(copy_of_data), "cancel", "grand-casino-2027-06-11-2030")
    assert DATA_FILE.read_bytes() == before


# --- The outputs of the course sheets (steps 03 to 05), word for word. ---


def test_venues_with_their_slug_and_the_total(copy_of_data):
    code, output = run("--data", str(copy_of_data), "venues")
    assert code == 0
    assert output == (
        "grand-casino: Grand Casino, 650 seats\n"
        "theatre-des-planches: Théâtre des Planches, 320 seats\n"
        "le-kiosque: Le Kiosque, 120 seats\n"
        "la-cabane: La Cabane, 40 seats\n"
        "Total: 1130 seats\n"
    )


def test_an_artist_with_the_festival_day_and_the_role(copy_of_data):
    code, output = run("--data", str(copy_of_data), "artist", "max-pellerin")
    assert code == 0
    assert output == (
        "Max Pellerin\n"
        "Thu 10 20:30-22:30 | Grand Casino | Opening Gala (act)\n"
        "Fri 11 23:30-00:30 | Le Kiosque | Late Laughs (solo)\n"
        "Sat 12 21:00-22:40 | Théâtre des Planches | Deauville Comedy Club (host)\n"
        "Sun 13 20:30-22:40 | Grand Casino | Closing Gala (act)\n"
    )


def test_a_teacher_has_the_role_teacher(copy_of_data):
    code, output = run("--data", str(copy_of_data), "artist", "ines-moreau")
    assert code == 0
    assert "(teacher)" in output


def test_after_hours_is_on_the_programme_of_friday(copy_of_data):
    code, output = run("--data", str(copy_of_data), "programme", "2027-06-11")
    assert code == 0
    assert output.splitlines()[-1] == "01:00-02:00 | Le Kiosque | After Hours (lineup)"


def test_now_and_up_next(copy_of_data):
    code, output = run("--data", str(copy_of_data), "now", "2027-06-11T21:00")
    assert code == 0
    assert output == (
        "On stage at 2027-06-11 21:00:\n"
        "- Tall Tales at Grand Casino, until 21:50\n"
        "Up next:\n"
        "- 21:30-22:40 | Théâtre des Planches | Straight Face (solo)\n"
        "- 23:30-00:30 | Le Kiosque | Late Laughs (solo)\n"
        "- 01:00-02:00 | Le Kiosque | After Hours (lineup)\n"
    )


def test_a_bad_day_says_what_is_wrong(copy_of_data):
    code, output = run("--data", str(copy_of_data), "programme", "June-11")
    assert code == 1
    assert output == "Error: 'June-11' is not a day, use YYYY-MM-DD.\n"


def test_a_day_outside_the_festival_says_so(copy_of_data):
    code, output = run("--data", str(copy_of_data), "programme", "2027-06-14")
    assert code == 1
    assert output == "Error: 2027-06-14 is not a day of the festival.\n"


def add_with(copy_of_data: Path, *answers: str) -> tuple[int, str]:
    """Run `deauville add`, answering its five questions."""
    with patch("builtins.input", side_effect=list(answers)):
        return run("--data", str(copy_of_data), "add")


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        (
            ("Too Late", "karim-benali", "le-kiosque", "2027-06-12T02:15", "30"),
            "Error: Le Kiosque is busy with After Hours (2027-06-12 01:00-02:00).",
        ),
        (
            ("X", "max-pellerin", "la-cabane", "2027-06-11T23:00", "30"),
            "Error: Max Pellerin is on stage in Late Laughs.",
        ),
        (
            ("X", "karim-benali", "la-cabane", "2027-06-14T08:00", "30"),
            "Error: 2027-06-14 is not a day of the festival.",
        ),
        (
            ("X", "karim-benali", "la-cabane", "2027-06-13T08:00", "half an hour"),
            "Error: 'half an hour' is not a number of minutes.",
        ),
    ],
)
def test_add_refuses_with_a_sentence(copy_of_data, answers, message):
    before = copy_of_data.read_text("utf-8")
    code, output = add_with(copy_of_data, *answers)
    assert code == 1
    assert output == message + "\n"
    assert copy_of_data.read_text("utf-8") == before


def test_add_then_cancel(copy_of_data):
    answers = ("Morning Coffee", "karim-benali", "la-cabane", "2027-06-13T08:00", "30")
    code, output = add_with(copy_of_data, *answers)
    assert code == 0
    assert output == "Added: la-cabane-2027-06-13-0800\n"
    code, output = run("--data", str(copy_of_data), "programme", "2027-06-13")
    assert output.splitlines()[1] == "08:00-08:30 | La Cabane | Morning Coffee (solo)"
    code, output = run(
        "--data", str(copy_of_data), "cancel", "la-cabane-2027-06-13-0800"
    )
    assert output == "Cancelled: Morning Coffee\n"


def test_the_name_of_the_festival_has_no_stray_characters(data):
    assert data["name"] == "Deauville Festival du Rire 2027"
