from __future__ import annotations

import tomllib
from pathlib import Path

import noriacomm

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_matches_noriacomm_identity() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["name"] == "noriacomm"
    assert noriacomm.__name__ == "noriacomm"
    assert (ROOT / "src" / "noriacomm").is_dir()


def test_legacy_noria_sms_egg_info_is_not_present() -> None:
    assert not (ROOT / "src" / "noria_sms.egg-info").exists()
