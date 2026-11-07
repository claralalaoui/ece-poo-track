"""Venues and artists: small, and frozen so nobody can change them."""

import re
import unicodedata
from dataclasses import dataclass


def make_slug(name: str) -> str:
    """Convert a name into a URL-friendly slug."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


@dataclass(frozen=True)
class Venue:
    name: str
    capacity: int
    address: str = ""

    @property
    def slug(self) -> str:
        return make_slug(self.name)


@dataclass(frozen=True)
class Artist:
    name: str
    bio: str = ""
    photo_url: str = ""

    @property
    def slug(self) -> str:
        return make_slug(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Artist):
            return NotImplemented
        return self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)


def tidy(name: str) -> str:
    """A name without extra spaces: 'Lou   M.' -> 'Lou M.'."""
    return " ".join(str(name).split())
