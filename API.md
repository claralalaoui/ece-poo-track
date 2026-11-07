# API of the Deauville festival

All routes answer JSON. The base is `/api`. The website is served on `/` and
the admin on `/admin/`.

## Read

| Route | Answer |
| --- | --- |
| `GET /api/festival` | `name`, `first_day`, `last_day`, `days` (every day of the festival) |
| `GET /api/venues` | list of `slug`, `name`, `capacity`, `address` |
| `GET /api/artists` | list of `slug`, `name`, sorted by `slug` |
| `GET /api/artists/{slug}` | `slug`, `name`, `bio`, `photo_url`, `performances` (list of performances) |
| `GET /api/programme` | every performance, sorted by `start` |
| `GET /api/programme?day=2027-06-11` | only the performances of that festival day (a show at 01:00 belongs to the day before) |
| `GET /api/programme?venue=la-cabane` | only the performances of that venue |
| `GET /api/performances/{id}` | one performance |
| `GET /api/now?at=2027-06-10T21:00` | `now_playing` and `up_next`; without `at`, the real time |

`day` and `venue` can be combined. A day outside the festival gives an empty
list.

A performance has: `id`, `kind` (`solo`, `lineup` or `workshop`), `title`,
`venue`, `venue_name`, `start`, `end`, `duration_minutes`, `festival_day`,
`description`, `summary`, `capacity`, `artists`, then the fields of its kind:

- solo: `artist`, `min_age`
- lineup: `host`, `acts`
- workshop: `teacher`, `max_participants`, `places`, `participants`, `places_left`

The `id` is the venue and the start: `la-cabane-2027-06-11-1030`.

## Write (admin)

| Route | Does | Answer |
| --- | --- | --- |
| `POST /api/performances` | adds a performance (body: the fields of its kind) | `201` and the performance |
| `PUT /api/performances/{id}` | replaces a performance; the `id` changes when the venue or the start changes | `200` and the performance |
| `DELETE /api/performances/{id}` | cancels it | `204`, no body |
| `POST /api/performances/{id}/participants` | registers `{"name": ...}` in a workshop | `201` and the workshop |
| `POST /api/artists` | adds an artist (`name`, `bio`, `photo_url`) | `201` and the artist |

A refused request changes nothing: the data file is written only when the
whole request succeeded.

## Errors

The body is always `{"detail": "..."}`.

| Status | When |
| --- | --- |
| `404` | unknown performance id, unknown artist slug, unknown `venue` in the filter |
| `409` | the slot is taken (venue or artist, 30 minutes of break between two performances), the workshop is full, a participant or an artist already exists |
| `422` | a missing or badly typed field, a bad date, an unknown kind, venue or artist in the body, a rule broken (duration 1 to 360, a lineup needs two acts, ...), a blank name, a registration in a performance that is not a workshop |
| `500` | the data file is damaged or cannot be read or written |
