"""Write-once storage under DATA_ROOT, plus the append-only MANIFEST.csv.

Never deletes or overwrites anything on Drive. In setup B every upload is followed by
`rclone check` on that file before the local copy is removed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gn_config import Config

MANIFEST_FIELDS = ("date", "file", "rows", "bytes", "checksum", "created_utc")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rclone(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(["rclone", *args], input=input_bytes, capture_output=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"rclone {' '.join(args)} failed: {r.stderr.decode()[-500:]}")
    return r


class Store:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    # -- existence ------------------------------------------------------------
    def exists(self, rel: str) -> bool:
        if self.cfg.rclone_remote:
            r = subprocess.run(["rclone", "lsf", f"{self.cfg.rclone_remote}/{rel}"],
                               capture_output=True, timeout=300)
            return r.returncode == 0 and r.stdout.strip() != b""
        return (self.cfg.data_root / rel).exists()

    # -- write once -----------------------------------------------------------
    def put(self, local: Path, rel: str) -> None:
        """Copy `local` to DATA_ROOT/rel. Refuses to overwrite. Verifies the copy."""
        if self.exists(rel):
            raise FileExistsError(f"{rel} already exists on Drive; refusing to overwrite")
        if self.cfg.rclone_remote:
            if local.name != Path(rel).name:
                raise ValueError("stage the file under its Drive name so rclone check can pair them")
            dest = f"{self.cfg.rclone_remote}/{rel}"
            _rclone("copyto", str(local), dest)
            _rclone("check", str(local.parent), dest.rsplit("/", 1)[0], "--one-way",
                    "--include", "/" + local.name)
            return
        dest = self.cfg.data_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        shutil.copyfile(local, tmp)
        if sha256_file(tmp) != sha256_file(local):
            tmp.unlink()
            raise RuntimeError(f"copy of {local} to {dest} does not match")
        tmp.rename(dest)

    # -- read back ------------------------------------------------------------
    def local_path(self, rel: str, work: Path) -> Path:
        """A readable local path for DATA_ROOT/rel (setup B copies it into `work`)."""
        if not self.cfg.rclone_remote:
            return self.cfg.data_root / rel
        dest = work / rel
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            _rclone("copy", f"{self.cfg.rclone_remote}/{rel}", str(dest.parent)
                    if not rel.endswith("/") else str(dest))
        return dest

    # -- append-only CSV ------------------------------------------------------
    def read_text(self, rel: str) -> str:
        if self.cfg.rclone_remote:
            if not self.exists(rel):
                return ""
            return _rclone("cat", f"{self.cfg.rclone_remote}/{rel}").stdout.decode()
        p = self.cfg.data_root / rel
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def append_csv(self, rel: str, fields: tuple[str, ...], row: dict) -> None:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
        old = self.read_text(rel)
        if not old:
            w.writeheader()
        w.writerow(row)
        if self.cfg.rclone_remote:
            # Drive has no append: write old + new, then confirm the old content is intact.
            new = (old + buf.getvalue()).encode()
            _rclone("rcat", f"{self.cfg.rclone_remote}/{rel}", input_bytes=new)
            if not self.read_text(rel).startswith(old):
                raise RuntimeError(f"append to {rel} did not preserve earlier rows")
            return
        p = self.cfg.data_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())

    # -- manifest -------------------------------------------------------------
    def manifest(self) -> list[dict]:
        txt = self.read_text("MANIFEST.csv")
        return list(csv.DictReader(io.StringIO(txt))) if txt else []

    def manifest_add(self, date: str, rel: str, rows: int, nbytes: int, checksum: str) -> None:
        self.append_csv("MANIFEST.csv", MANIFEST_FIELDS, {
            "date": date, "file": rel, "rows": rows, "bytes": nbytes, "checksum": checksum,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
