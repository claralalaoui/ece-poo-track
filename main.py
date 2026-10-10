import json
import re
import sys
import unicodedata

from datetime import datetime, timedelta


DATA_FILE = "data/festival.json"


# Turn a name into a slug
def make_slug(name):
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


# Read the festival data
def load_festival():
    with open(DATA_FILE, encoding="utf-8") as file:
        return json.load(file)


# Find a venue using its slug
def find_venue(festival, slug):
    for venue in festival["venues"]:
        if make_slug(venue["name"]) == slug:
            return venue
    return None


# Find an artist using their slug
def find_artist(festival, slug):
    for artist in festival["artists"]:
        if make_slug(artist["name"]) == slug:
            return artist
    return None


# Print the Step 00 summary
def print_summary(festival):
    print(festival["name"])
    print(f"From {festival['first_day']} to {festival['last_day']}")
    print(
        f"{len(festival['venues'])} venues, "
        f"{len(festival['artists'])} artists, "
        f"{len(festival['performances'])} performances"
    )


# Print venues and total capacity
def print_venues(festival):
    total_seats = 0

    print("Venues:")

    for venue in festival["venues"]:
        slug = make_slug(venue["name"])
        capacity = venue["capacity"]
        total_seats += capacity

        print(f"- {venue['name']} ({slug}): {capacity} seats")

    print(f"Total: {total_seats} seats")

def performance_start(performance):
    return datetime.strptime(
        performance["start"], "%Y-%m-%dT%H:%M"
    )


def performance_end(performance):
    start = performance_start(performance)
    duration = performance["duration_minutes"]
    return start + timedelta(minutes=duration)


def festival_day(performance):
    start = performance_start(performance)

# Shows after midnight belong to the previous festival day.
    if start.hour < 6:
        start -= timedelta(days=1)

    return start.date().isoformat()

# Print the programme for one day

def print_programme(festival, day):
    days = sorted({
        festival_day(performance)
        for performance in festival["performances"]
    })

    if day not in days:
        print(f"Invalid day: {day}")
        print("Available days: " + ", ".join(days))
        return

    print(f"Performances on {day}:")

    performances = [
        performance
        for performance in festival["performances"]
        if festival_day(performance) == day
    ]

    performances.sort(key=performance_start)

    for performance in performances:
        start = performance_start(performance)
        end = performance_end(performance)
        venue = find_venue(festival, performance["venue"])
        venue_name = venue["name"] if venue else performance["venue"]

        print(
            f"- {start:%H:%M}-{end:%H:%M} | "
            f"{venue_name} | {performance['title']} | "
            f"{performance['kind']}"
        )


# Print all performances involving one artist
def print_artist(festival, slug):
    artist = find_artist(festival, slug)

    if artist is None:
        print(f"Artist not found: {slug}")
        print("Check the artist's slug and try again.")
        return

    print(f"Performances for {artist['name']}:")

    found = False

    for performance in festival["performances"]:
        roles = []

        if performance.get("artist") == slug:
            roles.append("solo")

        if performance.get("host") == slug:
            roles.append("host")

        if slug in performance.get("acts", []):
            roles.append("act")

        if performance.get("teacher") == slug:
            roles.append("teacher")

        if roles:
            found = True
            time = performance["start"]
            venue = find_venue(festival, performance["venue"])
            venue_name = venue["name"] if venue else performance["venue"]

            # We'll update the output here
            festival_date = festival_day(performance)
            start = performance_start(performance)
            end = performance_end(performance)

            print(
                f"- {festival_date} | {start:%H:%M}-{end:%H:%M} | "
                f"{venue_name} | {performance['title']} | "
                f"{', '.join(roles)}"
            )

    if not found:
        print("No performances found for this artist.")


def print_now(festival, moment_text):
    try:
        moment = datetime.strptime(moment_text, "%Y-%m-%dT%H:%M")
    except ValueError:
        print("Use the format YYYY-MM-DDTHH:MM")
        return

    performances = sorted(
        festival["performances"],
        key=performance_start
    )

    current = [
        p for p in performances
        if performance_start(p) <= moment < performance_end(p)
    ]

    upcoming = [
        p for p in performances
        if performance_start(p) > moment
    ][:3]

    print(f"On stage at {moment_text}:")

    for p in current:
        print(f"- {p['title']}")

    if not current:
        print("No performance is on stage at this moment.")

    print("\nNext 3 performances:")

    for p in upcoming:
        print(f"- {performance_start(p):%Y-%m-%d %H:%M} | {p['title']}")

    if not upcoming:
        print("No upcoming performances.")



# Show how to use the program
def print_help():
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist ARTIST-SLUG")


# Choose which command to run
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
        print_now(festival, args[1])

    else:
        print_help()


if __name__ == "__main__":
    main()


def print_now(festival, moment_text):
    try:
        moment = datetime.strptime(
            moment_text, "%Y-%m-%dT%H:%M"
        )
    except ValueError:
        print("Use the format YYYY-MM-DDTHH:MM")
        return

    performances = sorted(
        festival["performances"],
        key=performance_start
    )

    current = [
        performance
        for performance in performances
        if performance_start(performance) <= moment
        < performance_end(performance)
    ]

    upcoming = [
        performance
        for performance in performances
        if performance_start(performance) > moment
    ][:3]

    def show(performance):
        start = performance_start(performance)
        end = performance_end(performance)
        venue = find_venue(festival, performance["venue"])
        venue_name = venue["name"] if venue else performance["venue"]

        print(
            f"- {start:%Y-%m-%d %H:%M}-{end:%H:%M} | "
            f"{venue_name} | {performance['title']}"
        )

    print(f"On stage at {moment_text}:")

    if current:
        for performance in current:
            show(performance)
    else:
        print("No performance is on stage at this moment.")

    print("\nNext 3 performances:")

    if upcoming:
        for performance in upcoming:
            show(performance)
    else:
        print("No upcoming performances.")


