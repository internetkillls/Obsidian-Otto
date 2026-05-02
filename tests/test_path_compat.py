from __future__ import annotations

from otto.path_compat import windows_path_to_wsl


def test_windows_path_to_wsl_converts_drive_paths():
    assert windows_path_to_wsl(r"C:\Users\joshu\Josh Obsidian") == "/mnt/c/Users/joshu/Josh Obsidian"
    assert windows_path_to_wsl("D:/Work/Repo") == "/mnt/d/Work/Repo"


def test_windows_path_to_wsl_leaves_existing_unix_paths():
    assert windows_path_to_wsl("/mnt/c/Users/joshu/Obsidian-Otto") == "/mnt/c/Users/joshu/Obsidian-Otto"
