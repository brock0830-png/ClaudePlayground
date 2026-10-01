"""Configuration: .env lookup, data layout under DATA_ROOT, and storage backend.

Setup A (own computer): DATA_ROOT is the Google Drive for desktop folder; files written
there upload automatically.
Setup B (cloud session): DATA_ROOT is a local staging folder and RCLONE_REMOTE names the
Drive folder (e.g. `gdrive:uw_gamma_data`); finished files are copied with rclone,
verified with `rclone check`, then deleted locally. Nothing on Drive is ever deleted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]          # gamma_nodes/
RESULTS = PROJECT / "results"
WORK = PROJECT / "_work"                               # local scratch, gitignored


def read_dotenv() -> dict[str, str]:
    for p in (Path.cwd() / ".env", PROJECT / ".env", PROJECT.parent / ".env"):
        if p.is_file():
            out = {}
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
            return out
    return {}


def setting(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or read_dotenv().get(name) or default


@dataclass(frozen=True)
class Config:
    api_key: str | None
    data_root: Path
    rclone_remote: str | None   # None = setup A (DATA_ROOT is the synced Drive folder)

    @property
    def setup(self) -> str:
        return "B" if self.rclone_remote else "A"


def load(require_key: bool = True) -> Config:
    key = setting("UW_API_KEY") or setting("UW_API_TOKEN")
    root = setting("DATA_ROOT")
    if require_key and not key:
        raise SystemExit("UW_API_KEY is not set (environment or gamma_nodes/.env)")
    if not root:
        raise SystemExit("DATA_ROOT is not set (environment or gamma_nodes/.env)")
    root_p = Path(os.path.expandvars(os.path.expanduser(root)))
    root_p.mkdir(parents=True, exist_ok=True)
    return Config(api_key=key, data_root=root_p, rclone_remote=setting("RCLONE_REMOTE") or None)
