import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Validators:
    """What we need to make a conditional GET and to reuse the body on a 304."""

    etag: str | None
    last_modified: str | None
    raw_path: str
    encoding: str


class ValidatorStore(Protocol):
    def get(self, key: str) -> Validators | None: ...
    def put(self, key: str, validators: Validators) -> None: ...


class MemoryValidatorStore:
    def __init__(self) -> None:
        self._items: dict[str, Validators] = {}

    def get(self, key: str) -> Validators | None:
        return self._items.get(key)

    def put(self, key: str, validators: Validators) -> None:
        self._items[key] = validators


class FileValidatorStore:
    """JSON-file backed store so conditional GETs survive between runs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._items: dict[str, Validators] | None = None

    def _load(self) -> dict[str, Validators]:
        if self._items is None:
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                data = {}
            self._items = {key: Validators(**value) for key, value in data.items()}
        return self._items

    def get(self, key: str) -> Validators | None:
        return self._load().get(key)

    def put(self, key: str, validators: Validators) -> None:
        items = self._load()
        items[key] = validators
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({k: asdict(v) for k, v in items.items()}, indent=1),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
