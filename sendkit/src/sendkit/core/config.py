"""Environment-variable helpers used by the ``from_env`` client constructors."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping

from .errors import ConfigurationError

EnvLike = Mapping[str, str | None]


def resolve_env(env: EnvLike | None = None) -> EnvLike:
    return env if env is not None else os.environ


def get_optional_env(name: str, env: EnvLike | None = None) -> str | None:
    value = resolve_env(env).get(name)

    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def get_required_env(name: str, env: EnvLike | None = None) -> str:
    value = get_optional_env(name, env)

    if value is None:
        raise ConfigurationError(f"Missing required environment variable: {name}")

    return value


def get_env_number(name: str, env: EnvLike | None = None) -> float | None:
    value = get_optional_env(name, env)

    if value is None:
        return None

    try:
        parsed = float(value)
    except ValueError as error:
        raise ConfigurationError(f"Environment variable {name} must be a valid number.") from error

    if not math.isfinite(parsed):
        raise ConfigurationError(f"Environment variable {name} must be a valid number.")

    return parsed
