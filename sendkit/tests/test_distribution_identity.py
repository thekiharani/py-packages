from __future__ import annotations

import tomllib
from pathlib import Path

import sendkit

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_matches_sendkit_identity() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    # Distribution name is ``noria-sendkit`` (PyPI); the import package stays ``sendkit``.
    assert pyproject["project"]["name"] == "noria-sendkit"
    assert sendkit.__name__ == "sendkit"
    assert (ROOT / "src" / "sendkit").is_dir()


def test_legacy_noriacomm_package_is_not_present() -> None:
    assert not (ROOT / "src" / "noriacomm").exists()
