from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator


def _windows_long_path(path: Path | str) -> str:
    resolved = Path(path)
    if os.name != "nt":
        return str(resolved)
    text = str(resolved)
    if text.startswith("\\\\?\\"):
        return text
    if not resolved.is_absolute():
        resolved = resolved.resolve()
        text = str(resolved)
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def _strip_windows_long_path_prefix(text: str) -> str:
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    if text.startswith("\\\\?\\"):
        return text[4:]
    return text


def read_text(path: Path | str, *, encoding: str = "utf-8", errors: str = "strict", newline: str | None = None) -> str:
    with open(_windows_long_path(path), "r", encoding=encoding, errors=errors, newline=newline) as handle:
        return handle.read()


def write_text(
    path: Path | str,
    data: str,
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
    newline: str | None = None,
) -> None:
    target = Path(path)
    os.makedirs(_windows_long_path(target.parent), exist_ok=True)
    with open(_windows_long_path(target), "w", encoding=encoding, errors=errors, newline=newline) as handle:
        handle.write(data)


def read_bytes(path: Path | str) -> bytes:
    with open(_windows_long_path(path), "rb") as handle:
        return handle.read()


def write_bytes(path: Path | str, data: bytes) -> None:
    target = Path(path)
    os.makedirs(_windows_long_path(target.parent), exist_ok=True)
    with open(_windows_long_path(target), "wb") as handle:
        handle.write(data)


def rename(path: Path | str, target: Path | str) -> None:
    source = Path(path)
    destination = Path(target)
    os.makedirs(_windows_long_path(destination.parent), exist_ok=True)
    os.replace(_windows_long_path(source), _windows_long_path(destination))


def relative_path(path: Path | str, root: Path | str) -> str:
    path_text = _strip_windows_long_path_prefix(_windows_long_path(path))
    root_text = _strip_windows_long_path_prefix(_windows_long_path(root))
    return os.path.relpath(path_text, root_text)


def exists(path: Path | str) -> bool:
    return os.path.exists(_windows_long_path(path))


def is_file(path: Path | str) -> bool:
    return os.path.isfile(_windows_long_path(path))


def is_dir(path: Path | str) -> bool:
    return os.path.isdir(_windows_long_path(path))


def iter_files(root: Path | str) -> Iterator[Path]:
    root_path = Path(root)
    if not is_dir(root_path):
        return
    for current_root, _dirs, files in os.walk(_windows_long_path(root_path)):
        current = Path(current_root)
        for name in files:
            yield current / name


def iter_markdown_files(root: Path | str) -> Iterator[Path]:
    for path in iter_files(root):
        if path.suffix.lower() == ".md":
            yield path
