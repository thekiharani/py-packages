from __future__ import annotations

import os
from collections.abc import Mapping

from .exceptions import ConfigurationError
from .types import Environment


def resolve_environ(environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return environ if environ is not None else os.environ


def get_optional_env(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    value = resolve_environ(environ).get(name)
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def get_required_env(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    value = get_optional_env(name, environ=environ)
    if value is None:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def get_env_float(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> float | None:
    value = get_optional_env(name, environ=environ)
    if value is None:
        return None

    try:
        return float(value)
    except ValueError as error:
        raise ConfigurationError(f"Environment variable {name} must be a valid float.") from error


def get_env_environment(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    default: Environment = "sandbox",
) -> Environment:
    value = get_optional_env(name, environ=environ)
    if value is None:
        return default

    if value not in ("sandbox", "production"):
        raise ConfigurationError(f"Environment variable {name} must be 'sandbox' or 'production'.")

    return value
