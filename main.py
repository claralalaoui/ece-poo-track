import sys
from datetime import datetime

from festival import (
    FestivalError,
    load_festival,
    print_summary,
    print_venues,
    print_programme,
    print_artist,
    print_now,
    cancel_performance,
)


def print_help():
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist ARTIST-SLUG")
    print("  uv run main.py now YYYY-MM-DDTHH:MM")
    print("  uv run main.py add")
    print("  uv run main.py cancel PERFORMANCE-ID")


def main():
    festival = load_festival()
    args = sys.argv[1:]

    if len(args) == 0:
        print_summary(festival)

    elif args == ["venues"]:
        print_venues(festival)

    elif len(args) == 2 and args[0] == "programme":
        print_programme(festival, args[1])

    elif len(args) == 2 and args[0] == "artist":
        print_artist(festival, args[1])

    elif len(args) == 2 and args[0] == "now":
        print_now(festival, datetime.fromisoformat(args[1]))

    elif args == ["add"]:
        print("Adding a performance is not available through this command yet.")

    elif len(args) == 2 and args[0] == "cancel":
        try:
            cancel_performance(festival, args[1])
            print("Performance cancelled successfully.")

        except FestivalError as error:
            print(f"Error: {error}")


    else:
        print_help()


if __name__ == "__main__":
    try:
        main()
    except (FestivalError, ValueError, OSError, KeyError, TypeError) as error:
        print(f"Error: {error}")
        sys.exit(1)


