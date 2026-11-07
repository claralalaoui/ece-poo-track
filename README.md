# Deauville – Festival du Rire

A small program for the programme of a comedy festival: venues, artists and
three kinds of performances (solo shows, line-ups, workshops). It checks the
rules of the schedule, saves everything in a JSON file, and can be used from
the command line or through an HTTP API.

Python 3.12, FastAPI, uv, pytest, ruff.

## Install and run

You need [uv](https://docs.astral.sh/uv/). Then:

```bash
git clone <the url of this repository>
cd <the folder>
uv sync
```

Command line:

```bash
uv run deauville                       # summary of the festival
uv run deauville venues                # the venues
uv run deauville programme 2027-06-11  # the programme of a day
uv run deauville artist nora-lebrun    # an artist and their performances
uv run deauville now 2027-06-10T21:00  # what is playing, what is next
uv run deauville add                   # asks 5 questions, adds a solo show
uv run deauville cancel <id>           # cancel a performance
uv run deauville --help                # everything else (add, ...)
```

Server (API on `http://127.0.0.1:8000/api/...`, documentation of the routes
on `http://127.0.0.1:8000/docs`):

```bash
uv run deauville serve
```

Every command accepts `--data some_file.json` to work on another data file
than `data/festival.json`.

Tests, style, package:

```bash
uv run pytest
uv run ruff format .
uv run ruff check .
uv build
```

The routes and their errors are described in [API.md](API.md).

## Structure, and why

```
src/deauville/
  errors.py        the family of errors
  models.py        Venue and Artist (they never change)
  performances.py  Performance and its three kinds
  festival.py      Festival: the schedule and its rules
  storage.py       Storage, JsonStorage, MemoryStorage
  api.py           create_app(storage): the HTTP routes
  cli.py           the command line
tests/             test_festival.py, test_storage_cli.py, test_api.py
data/festival.json the data
```

- **`Performance`** is an abstract class: it holds what every performance has
  (title, venue, start, duration, the end, the festival day) and forces each
  kind to write its own summary, its own fields and its own checks.
  `SoloShow`, `Lineup` and `Workshop` inherit from it. A dictionary `KINDS`
  is the only place where the word `kind` chooses a class, so a fourth kind
  means one new class and one line.
- **Encapsulation.** Attributes start with `_` and are read through
  properties, with no setter. Lists are given as copies. `Venue` and `Artist`
  are frozen dataclasses. The only way to change the schedule is through the
  methods of `Festival` (`add`, `replace`, `cancel`, `register`,
  `add_artist`), so nobody can put the schedule in a state that breaks a rule.
- **Where the rules live.** The rules of one performance (duration 1 to 360,
  a line-up needs two different acts and enough time, a workshop has at least
  one place, the minimum age) are in its class, in `performances.py`. The
  rules that need the whole schedule (a venue or an artist cannot be in two
  places, 30 minutes of break, the day must be in the festival, a
  workshop is not full) are in `Festival`. The API and the command line contain no rule: they ask the
  festival and show the answer.
- **How errors say which rule.** Every error is one of our own classes, all
  children of `FestivalError`, each with a message that says which rule was
  broken and with which value. `NotFoundError` is a 404, `ConflictError` a
  409, `InvalidValueError` (and `InvalidPerformanceError`) a 422,
  `InvalidDataError` (a damaged file) a 500. One handler in `api.py` turns the
  family into statuses, so no route has a `try`. The command line catches
  `FestivalError` and prints `Error: ...`.
- **Storage apart.** `Storage` is an abstract class with `load()` and
  `save()`. `JsonStorage` writes a temporary file and replaces the real one,
  so a crash never leaves half a file. `MemoryStorage` is used by tests.
  `create_app(storage)` builds the application around any storage; the
  server gives it the real file, each test a copy. A change is loaded,
  made, and saved only if nothing was refused.
- **What would change with a database.** Only `storage.py`: a third class
  (for example `SqlStorage`) with the same `load()` and `save()`, and an
  option to choose it. The classes of the festival and the routes would not
  change. The price: `load()` reads everything each time, which is fine for
  a few dozen performances and not for thousands. A database would need
  `Festival` to ask for what it needs (the performances of one venue) instead
  of holding everything in memory.

## What is done, what is not

Done: the three kinds of performances and all the rules of the brief, the
family of errors, the storage behind an interface, the command line, every
route of `API.md` with a test for each behaviour, the package
(`uv build`), ruff clean, annotations and docstrings in `src/`.

Not done:

- The website and the admin pages (`web/`): they were not in my starter, so
  `/` and `/admin/` answer `404`. The server mounts them as soon as a `web/`
  folder with `public/` and `admin/` is next to `src/`. I could not test them.
- The second storage in SQLite (extension).
- The tests are not annotated (pytest functions).

## Known bugs and limits

- The festival is held in memory and the whole file is read for every
  request, and written for every change: fine here, slow for a big festival.
- A lock allows one writer at a time inside one server process. Two server
  processes on the same file would not protect each other.
- A participant is only a name: two different people with the same name
  cannot register in the same workshop.
