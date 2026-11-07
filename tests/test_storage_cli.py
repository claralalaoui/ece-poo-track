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
    assert "Dates: 2027-06-10 to 2027-06-13" in output


def test_programme_of_a_day(copy_of_data):
    code, output = run("--data", str(copy_of_data), "programme", "2027-06-11")
    assert code == 0
    assert "20:30 - Tall Tales (grand-casino)" in output


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
    assert "cancelled" in output
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
