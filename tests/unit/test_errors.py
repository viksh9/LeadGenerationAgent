from pathlib import Path

import pytest

from collectors.json_collector import JsonFileCollector
from config.exceptions import CollectorError


def test_json_collector_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(CollectorError):
        JsonFileCollector(missing).collect()


def test_json_collector_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CollectorError):
        JsonFileCollector(bad).collect()
