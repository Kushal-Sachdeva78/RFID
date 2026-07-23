"""Persistence abstraction for the RFID backend.

Route handlers depend on the Storage facade and the CollectionStore interface,
never on file paths directly. That keeps the JSON backend swappable: a future
Firestore or database implementation only has to satisfy CollectionStore, and no
route handler changes.

The JSON implementation writes atomically (temp file plus os.replace) so a crash
mid-write cannot leave a half-written file on disk.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any, Protocol, runtime_checkable

JsonDict = dict[str, Any]


@runtime_checkable
class CollectionStore(Protocol):
    """A persistent, ordered collection of JSON records."""

    def all(self) -> list[JsonDict]:
        ...

    def replace(self, items: list[JsonDict]) -> None:
        ...

    def append(self, item: JsonDict) -> JsonDict:
        ...


class JsonCollectionStore:
    """A CollectionStore backed by a single JSON file holding a list."""

    def __init__(self, path: pathlib.Path | str) -> None:
        self._path = pathlib.Path(path)

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def all(self) -> list[JsonDict]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as handle:
            text = handle.read().strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self._path.name} is not valid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"{self._path.name} must contain a JSON array")
        return data

    def replace(self, items: list[JsonDict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then atomically replace.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=self._path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_name, self._path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise

    def append(self, item: JsonDict) -> JsonDict:
        items = self.all()
        items.append(item)
        self.replace(items)
        return item


class Storage:
    """Facade grouping the named collections the app uses."""

    def __init__(self, data_dir: pathlib.Path | str) -> None:
        self._data_dir = pathlib.Path(data_dir)
        self.roster: CollectionStore = JsonCollectionStore(self._data_dir / "roster.json")
        self.logs: CollectionStore = JsonCollectionStore(
            self._data_dir / "attendance_logs.json"
        )
        # Maps a class section (matching a roster person's class_name) to the
        # class teacher notified on the third late arrival.
        self.class_teachers: CollectionStore = JsonCollectionStore(
            self._data_dir / "class_teachers.json"
        )
        # Laptop asset register and borrow records.
        self.laptops: CollectionStore = JsonCollectionStore(self._data_dir / "laptops.json")
        self.loans: CollectionStore = JsonCollectionStore(self._data_dir / "loans.json")

    @property
    def data_dir(self) -> pathlib.Path:
        return self._data_dir

    def ensure_initialised(self) -> None:
        """Create empty collection files if they do not exist yet."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for store in (self.roster, self.logs, self.class_teachers, self.laptops, self.loans):
            if isinstance(store, JsonCollectionStore) and not store.path.exists():
                store.replace([])
