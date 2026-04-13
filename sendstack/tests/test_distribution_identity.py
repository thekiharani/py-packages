from __future__ import annotations

import tomllib
from pathlib import Path

import sendstack

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_matches_sendstack_identity() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["name"] == "sendstack"
    assert sendstack.__name__ == "sendstack"
    assert (ROOT / "src" / "sendstack").is_dir()
