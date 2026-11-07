"""Where the festival lives.

The rest of the program only knows `Storage`: it calls `load` and `save` and
never opens a file itself. The JSON file is one implementation, the memory is
another (handy for tests). A database would be a third, without changing the
festival classes.
"""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from deauville.errors import InvalidDataError
from deauville.festival import Festival

DEFAULT_DATA_FILE = Path("data") / "festival.json"


class Storage(ABC):
    """What every storage can do."""

    @abstractmethod
    def load(self) -> Festival:
        """Read the whole festival, rules checked."""

    @abstractmethod
    def save(self, festival: Festival) -> None:
        """Write the whole festival: all of it, or nothing."""


class JsonStorage(Storage):
    """The festival in a JSON file."""

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(path) if path else DEFAULT_DATA_FILE

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Festival:
        with open(self._path, encoding="utf-8") as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError as error:
                raise InvalidDataError(
                    f"{self._path} is not valid JSON: {error}."
                ) from error
        return Festival.from_dict(data)

    def save(self, festival: Festival) -> None:
        # Write a temporary file, then swap it in: no half-written file.
        temp = self._path.with_name(self._path.name + ".tmp")
        with open(temp, "w", encoding="utf-8") as file:
            json.dump(festival.to_dict(), file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp, self._path)


class MemoryStorage(Storage):
    """Nothing on disk: the festival is kept as a dict, like in the file."""

    def __init__(self, data: dict) -> None:
        self._data = json.loads(json.dumps(data))

    def load(self) -> Festival:
        return Festival.from_dict(json.loads(json.dumps(self._data)))

    def save(self, festival: Festival) -> None:
        self._data = festival.to_dict()
