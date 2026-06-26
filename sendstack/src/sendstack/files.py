"""Filesystem conveniences for building email payloads from local files.

The SendStack API accepts strings (``html``/``text``) and base64 (``attachments``).
These helpers do the read-and-encode step so callers don't repeat it. They use
only the standard library, so they add no dependencies.

The returned attachment ``dict`` uses the snake_case wire field names, so it can
be dropped straight into ``emails.send({"attachments": [...]})``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

PathLike = str | os.PathLike[str]

__all__ = [
    "html_from_file",
    "text_from_file",
    "attachment_from_file",
    "attachment_from_bytes",
]


def html_from_file(path: PathLike, *, encoding: str = "utf-8") -> str:
    """Read a text file (e.g. an HTML template) into a string for ``html``."""
    return Path(path).read_text(encoding=encoding)


def text_from_file(path: PathLike, *, encoding: str = "utf-8") -> str:
    """Read a text file (e.g. a ``.txt`` body) into a string for ``text``."""
    return Path(path).read_text(encoding=encoding)


def attachment_from_file(
    path: PathLike,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    inline: bool | None = None,
    content_id: str | None = None,
) -> dict[str, Any]:
    """Read a file from disk into a base64 attachment dict.

    ``filename`` defaults to the file's basename. The result is ready to drop
    into ``emails.send({"attachments": [...]})``.
    """
    data = Path(path).read_bytes()
    return attachment_from_bytes(
        data,
        filename=filename if filename is not None else Path(os.fspath(path)).name,
        content_type=content_type,
        inline=inline,
        content_id=content_id,
    )


def attachment_from_bytes(
    data: bytes,
    *,
    filename: str,
    content_type: str | None = None,
    inline: bool | None = None,
    content_id: str | None = None,
) -> dict[str, Any]:
    """Encode in-memory bytes (e.g. a generated PDF) into a base64 attachment dict.

    ``filename`` is required since there is no path to derive one from.
    """
    attachment: dict[str, Any] = {
        "filename": filename,
        "content_base64": base64.b64encode(data).decode("ascii"),
    }
    if content_type is not None:
        attachment["content_type"] = content_type
    if inline is not None:
        attachment["inline"] = inline
    if content_id is not None:
        attachment["content_id"] = content_id
    return attachment
