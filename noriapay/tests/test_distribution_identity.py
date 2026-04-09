from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import noriapay

ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "noriapay"


def test_project_metadata_uses_noriapay_distribution_name() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["name"] == PROJECT_NAME


def test_import_package_name_is_noriapay() -> None:
    assert noriapay.__name__ == PROJECT_NAME
    assert (ROOT / "src" / PROJECT_NAME).is_dir()
    assert not (ROOT / "src" / "noriapay_py").exists()
    assert not (ROOT / "src" / "noria_pay").exists()
    assert not (ROOT / "src" / "noria_payments").exists()


def test_pkg_info_uses_noriapay_distribution_name() -> None:
    pkg_info_path = ROOT / "src" / "noriapay.egg-info" / "PKG-INFO"
    if not pkg_info_path.exists():
        pytest.skip("PKG-INFO is not present in this checkout.")

    pkg_info = pkg_info_path.read_text()
    assert "Name: noriapay" in pkg_info
    assert "Name: noriapay-py" not in pkg_info


def test_built_artifacts_keep_noriapay_prefix() -> None:
    dist_dir = ROOT / "dist"
    if not dist_dir.exists():
        pytest.skip("No dist directory is present in this checkout.")

    artifacts = [
        path.name
        for path in dist_dir.iterdir()
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    ]
    if not artifacts:
        pytest.skip("No build artifacts are present in dist/.")

    assert all(name.startswith("noriapay-") for name in artifacts)
