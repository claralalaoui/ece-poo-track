"""The command line: `deauville programme 2027-06-11`, `deauville serve`.

Every command receives a storage; the option `--data FILE` chooses another
data file (handy for tests and for the trainer).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Optional

from deauville.errors import FestivalError
from deauville.festival import Festival
from deauville.storage import JsonStorage, Storage

# --- Printing. ---


def print_summary(festival: Festival) -> None:
    """Print a summary of the festival."""
    print(festival)


def print_venues(festival: Festival) -> None:
    """Print all festival venues."""
    for venue in festival.venues:
        print(venue)


def print_programme(festival: Festival, day: Optional[str] = None) -> None:
    """Print the festival programme."""
    for performance in festival.programme(day=day):
        print(performance)


def print_artist(festival: Festival, artist_slug: str) -> None:
    """Print performances involving an artist."""
    for performance in festival.performances_by_artist(artist_slug):
        print(performance)


def print_now(festival: Festival, at: datetime) -> None:
    """Print performances playing now and coming up next."""
    print("On stage now:")
    for performance in festival.now_playing(at):
        print(performance)

    print("Up next:")
    for performance in festival.up_next(at):
        print(performance)


# --- Commands: each one gets the storage and the parsed arguments. ---


def command_summary(storage: Storage, args: argparse.Namespace) -> None:
    print_summary(storage.load())


def command_venues(storage: Storage, args: argparse.Namespace) -> None:
    print_venues(storage.load())


def command_programme(storage: Storage, args: argparse.Namespace) -> None:
    print_programme(storage.load(), args.day)


def command_artist(storage: Storage, args: argparse.Namespace) -> None:
    print_artist(storage.load(), args.slug)


def command_now(storage: Storage, args: argparse.Namespace) -> None:
    print_now(storage.load(), args.at)


def command_add(storage: Storage, args: argparse.Namespace) -> None:
    print("Adding a performance is available in the admin: deauville serve.")


def command_cancel(storage: Storage, args: argparse.Namespace) -> None:
    festival = storage.load()
    festival.cancel(args.performance_id)
    storage.save(festival)
    print("Performance cancelled successfully.")


def command_serve(storage: Storage, args: argparse.Namespace) -> None:
    import uvicorn  # only needed here: the other commands start faster

    from deauville.api import create_app

    uvicorn.run(create_app(storage), host=args.host, port=args.port)


# --- The parser. ---


def parse_datetime(text: str) -> datetime:
    """`2027-06-11T21:00` as a datetime, or a clear message."""
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a date and time, use YYYY-MM-DDTHH:MM."
        ) from None


def build_parser() -> argparse.ArgumentParser:
    # `--data` is accepted before or after the command.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data",
        metavar="FILE",
        default=argparse.SUPPRESS,
        help="data file (default: data/festival.json)",
    )

    parser = argparse.ArgumentParser(
        prog="deauville",
        description="The programme of the Deauville Festival du Rire.",
        parents=[common],
    )
    parser.set_defaults(command=command_summary)
    commands = parser.add_subparsers(title="commands", metavar="command")

    def add(name: str, function, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(
            name, help=help_text, description=help_text, parents=[common]
        )
        sub.set_defaults(command=function)
        return sub

    add("venues", command_venues, "list the venues")
    add("programme", command_programme, "the programme of a day").add_argument(
        "day", help="YYYY-MM-DD"
    )
    add("artist", command_artist, "the performances of an artist").add_argument(
        "slug", help="slug of the artist"
    )
    add("now", command_now, "what is on stage at a given time").add_argument(
        "at", type=parse_datetime, help="YYYY-MM-DDTHH:MM"
    )
    add("add", command_add, "add a performance (see the admin)")
    add("cancel", command_cancel, "cancel a performance").add_argument(
        "performance_id", help="id of the performance"
    )
    serve = add("serve", command_serve, "start the website and the API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command line. Returns the exit code."""
    args = build_parser().parse_args(argv)
    # `--data` is missing when the user did not give it (see `build_parser`).
    storage = JsonStorage(getattr(args, "data", None))
    try:
        args.command(storage, args)
    except (FestivalError, ValueError, OSError, KeyError, TypeError) as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
