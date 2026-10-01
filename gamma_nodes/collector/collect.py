#!/usr/bin/env python3
"""Live collector for the 0DTE gamma-node study (ground truth for the step-3 gate).

Every 5 minutes from 09:35 to 16:00 US/Eastern on NYSE trading days it saves the
raw JSON of:

  spx_expiry_strike_pN  /api/stock/SPX/spot-exposures/expiry-strike?expirations[]=<today>
  xsp_expiry_strike_pN  /api/stock/XSP/spot-exposures/expiry-strike?expirations[]=<today>
  spx_gex_levels_vol    /api/stock/SPX/gex-levels?source=vol
  spx_gex_levels_oi     /api/stock/SPX/gex-levels?source=oi
  spx_quote             /api/stock/SPX/quote
  spx_spot_1m           /api/stock/SPX/spot-exposures?date=<today>  (per-minute price + totals)

to DATA_ROOT/live/YYYY-MM-DD/HHMM_<name>.json. Response bodies are written byte for
byte as received. Every request (success or failure) is appended to
DATA_ROOT/live/YYYY-MM-DD/_requests.csv. Nothing is ever overwritten or deleted:
if a file already exists the collector writes nothing for that slot.

Standard library only, so it runs on any Python 3.9+ (Windows needs `pip install
tzdata` for the time zone database; without it a built-in US DST rule is used).

Usage:
  python collect.py               run the current 5-minute slot (what the scheduler calls)
  python collect.py --force       collect now, even outside market hours, into
                                  DATA_ROOT/live/_test/ (setup test; never mixed with live data)
  python collect.py --check [DATE ...]   gap report for the given dates (default: today)
  python collect.py --check-all   gap report for every collected date
  python collect.py --selftest    offline checks, no API calls
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API_BASE = "https://api.unusualwhales.com/api"
USER_AGENT = "gamma-nodes-collector/1.0"
HTTP_TIMEOUT = 30
MAX_RETRIES = 3
PAGE_LIMIT = 500
MAX_PAGES = 10

FIRST_SLOT = (9, 35)
LAST_SLOT = (16, 0)
EARLY_CLOSE_LAST_SLOT = (13, 0)
SLOT_MINUTES = 5
SLOT_TOLERANCE_S = 90  # a run more than 90 s from a 5-minute mark is ignored

# NYSE full-day closures and 13:00 early closes, from
# https://www.nyse.com/markets/hours-calendars. Add each new year before it starts:
# the collector refuses to guess and logs an error for a year it does not know.
HOLIDAYS = {
    2025: "01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25",
    2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
    2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
}
EARLY_CLOSES = {
    2025: "07-03 11-28 12-24",
    2026: "11-27 12-24",
    2027: "11-26",
}

# Endpoints whose files must exist for a slot to count as complete. The price is
# complete if either spx_quote or spx_spot_1m succeeded.
REQUIRED = ("spx_expiry_strike", "xsp_expiry_strike", "spx_gex_levels_vol", "spx_gex_levels_oi")
PRICE_ANY_OF = ("spx_quote", "spx_spot_1m")

LOG_FIELDS = ("requested_at_utc", "slot", "name", "url", "http_status", "bytes",
              "sha256", "file", "note")


LOCAL_LOG = Path(__file__).resolve().parent / "collector.log"


def say(msg: str) -> None:
    """Print and append to collector/collector.log (local, so failures to reach
    DATA_ROOT are still recorded)."""
    print(msg)
    try:
        with open(LOCAL_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}\n")
    except OSError:
        pass


def notify(title: str, msg: str) -> None:
    """Best-effort desktop notification (macOS only); never raises."""
    if sys.platform == "darwin":
        try:
            import subprocess
            subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                           timeout=10, check=False)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# time zone and calendar
# ----------------------------------------------------------------------------

try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:  # Windows without the tzdata package
    EASTERN = None


def _us_dst(utc_dt: datetime) -> bool:
    """US daylight time (2007 rules): 2nd Sunday of March 07:00 UTC to 1st Sunday of
    November 06:00 UTC. Fallback only, used when no tz database is installed."""
    y = utc_dt.year
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    start = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7, hours=7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7, hours=6)
    return start <= utc_dt < end


def to_eastern(utc_dt: datetime) -> datetime:
    if EASTERN is not None:
        return utc_dt.astimezone(EASTERN)
    off = timedelta(hours=-4 if _us_dst(utc_dt) else -5)
    return utc_dt.astimezone(timezone(off))


def _table(src: dict[int, str], y: int) -> set[date]:
    if y not in src:
        raise RuntimeError(f"holiday table has no entry for {y}; add it from "
                           "https://www.nyse.com/markets/hours-calendars")
    return {date(y, int(md[:2]), int(md[3:])) for md in src[y].split()}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _table(HOLIDAYS, d.year)


def is_early_close(d: date) -> bool:
    return d in _table(EARLY_CLOSES, d.year)


def expected_slots(d: date) -> list[str]:
    """HHMM labels of every 5-minute slot the collector should fill on `d`."""
    if not is_trading_day(d):
        return []
    last = EARLY_CLOSE_LAST_SLOT if is_early_close(d) else LAST_SLOT
    h, m = FIRST_SLOT
    out = []
    while (h, m) <= last:
        out.append(f"{h:02d}{m:02d}")
        m += SLOT_MINUTES
        if m >= 60:
            h, m = h + 1, m - 60
    return out


def current_slot(now_et: datetime) -> str | None:
    """The 5-minute slot this run belongs to: the nearest 5-minute mark, if within
    SLOT_TOLERANCE_S of it and inside 09:35-16:00 (13:00 on early-close days)."""
    if not is_trading_day(now_et.date()):
        return None
    secs = now_et.hour * 3600 + now_et.minute * 60 + now_et.second
    step = SLOT_MINUTES * 60
    nearest = int(round(secs / step)) * step
    if abs(secs - nearest) > SLOT_TOLERANCE_S:
        return None
    label = f"{nearest // 3600:02d}{(nearest % 3600) // 60:02d}"
    return label if label in expected_slots(now_et.date()) else None


# ----------------------------------------------------------------------------
# configuration (.env)
# ----------------------------------------------------------------------------

def read_dotenv() -> dict[str, str]:
    """KEY=VALUE lines from the first .env found in the working directory, the
    script's directory, or any parent of the script's directory."""
    here = Path(__file__).resolve().parent
    candidates = [Path.cwd() / ".env", here / ".env", *[p / ".env" for p in here.parents]]
    for p in candidates:
        if p.is_file():
            out = {}
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
            return out
    return {}


def fail(msg: str) -> None:
    say(msg)
    sys.exit(1)


def config() -> tuple[str, Path]:
    env = read_dotenv()
    key = os.environ.get("UW_API_KEY") or env.get("UW_API_KEY")
    root = os.environ.get("DATA_ROOT") or env.get("DATA_ROOT")
    if not key:
        fail("error: UW_API_KEY is not set (put UW_API_KEY=... in gamma_nodes/.env)")
    if not root:
        fail("error: DATA_ROOT is not set (put DATA_ROOT=... in gamma_nodes/.env)")
    root_p = Path(os.path.expandvars(os.path.expanduser(root)))
    if not root_p.is_dir():
        fail(f"error: DATA_ROOT {root_p} does not exist or is not a folder. Is "
                 "Google Drive for desktop running and signed in?")
    return key, root_p


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

def http_get(url: str, key: str) -> tuple[int, bytes, str]:
    """GET with retries on 429/5xx/network errors. Returns (status, body, note)."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    note = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                return r.status, r.read(), note
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                wait = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait_s = min(float(wait), 20.0) if wait else 2.0 * (attempt + 1)
                except ValueError:
                    wait_s = 2.0 * (attempt + 1)
                note += f"retry{attempt + 1}:http{e.code};"
                time.sleep(wait_s)
                continue
            return e.code, body, note
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if attempt < MAX_RETRIES:
                note += f"retry{attempt + 1}:{type(e).__name__};"
                time.sleep(2.0 * (attempt + 1))
                continue
            return 0, str(e).encode(), note + f"failed:{type(e).__name__}"
    return 0, b"", note + "exhausted"


def page_is_empty(body: bytes) -> bool:
    try:
        obj = json.loads(body)
    except ValueError:
        return False
    data = obj.get("data") if isinstance(obj, dict) else obj
    return isinstance(data, list) and len(data) == 0


def requests_for(d: date) -> list[tuple[str, str, bool]]:
    """(name, url, paged) for one slot."""
    ds = d.isoformat()
    q = urllib.parse.urlencode
    out = []
    for tk in ("SPX", "XSP"):
        out.append((f"{tk.lower()}_expiry_strike",
                    f"{API_BASE}/stock/{tk}/spot-exposures/expiry-strike?"
                    + q({"expirations[]": ds, "limit": PAGE_LIMIT}), True))
    out.append(("spx_gex_levels_vol", f"{API_BASE}/stock/SPX/gex-levels?" + q({"source": "vol"}), False))
    out.append(("spx_gex_levels_oi", f"{API_BASE}/stock/SPX/gex-levels?" + q({"source": "oi"}), False))
    out.append(("spx_quote", f"{API_BASE}/stock/SPX/quote", False))
    out.append(("spx_spot_1m", f"{API_BASE}/stock/SPX/spot-exposures?" + q({"date": ds}), False))
    return out


# ----------------------------------------------------------------------------
# append-only storage
# ----------------------------------------------------------------------------

def write_new(path: Path, body: bytes) -> bool:
    """Write `body` to `path` only if `path` does not exist. Returns True if written."""
    if path.exists():
        return False
    tmp = path.with_name(path.name + ".partial")
    with open(tmp, "wb") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)  # fails if path appeared meanwhile: never overwrite
        os.remove(tmp)
    except (OSError, NotImplementedError):
        if path.exists():
            os.remove(tmp)
            return False
        os.replace(tmp, path)
    return True


def append_log(day_dir: Path, row: dict) -> None:
    log = day_dir / "_requests.csv"
    new = not log.exists()
    with open(log, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def collect_slot(key: str, root: Path, d: date, slot: str, test: bool = False) -> int:
    day_dir = root / "live" / ("_test" if test else "") / d.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    if any(day_dir.glob(f"{slot}_*.json")):
        say(f"{d} {slot}: already collected, nothing to do")
        return 0
    failures = 0
    for name, url, paged in requests_for(d):
        pages = range(MAX_PAGES) if paged else [None]
        for page in pages:
            u = url + (f"&page={page}" if page is not None else "")
            fname = f"{slot}_{name}" + (f"_p{page}" if page is not None else "") + ".json"
            t0 = datetime.now(timezone.utc)
            status, body, note = http_get(u, key)
            ok = status == 200
            written = ""
            if ok:
                if write_new(day_dir / fname, body):
                    written = fname
                else:
                    note += "exists;"
            else:
                failures += 1
            append_log(day_dir, {
                "requested_at_utc": t0.isoformat(timespec="milliseconds"),
                "slot": slot, "name": name, "url": u, "http_status": status,
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "file": written, "note": note + ("" if ok else body[:200].decode("utf-8", "replace").replace("\n", " ")),
            })
            if not ok or page is None or page_is_empty(body):
                break
    say(f"{d} {slot}: done, {failures} failed request(s)")
    return failures


# ----------------------------------------------------------------------------
# gap check
# ----------------------------------------------------------------------------

def slot_status(day_dir: Path, slot: str) -> list[str]:
    """Names of required pieces missing for one slot (empty list = complete)."""
    missing = []
    for name in REQUIRED:
        if not (day_dir / f"{slot}_{name}_p0.json").exists() and \
           not (day_dir / f"{slot}_{name}.json").exists():
            missing.append(name)
    if not any((day_dir / f"{slot}_{n}.json").exists() for n in PRICE_ANY_OF):
        missing.append("spx_price")
    return missing


def check_day(root: Path, d: date) -> tuple[int, int, list[str]]:
    slots = expected_slots(d)
    day_dir = root / "live" / d.isoformat()
    lines = []
    complete = 0
    for s in slots:
        miss = slot_status(day_dir, s) if day_dir.is_dir() else ["all"]
        if miss:
            lines.append(f"  {s} missing: {', '.join(miss)}")
        else:
            complete += 1
    return complete, len(slots), lines


def gap_report(root: Path, days: list[date]) -> int:
    bad = 0
    for d in days:
        if not is_trading_day(d):
            print(f"{d}: not a trading day")
            continue
        ok, n, lines = check_day(root, d)
        status = "OK" if ok == n else "GAPS"
        print(f"{d}: {status} {ok}/{n} slots complete")
        for ln in lines:
            print(ln)
        if ok < n:
            bad += 1
            say(f"WARNING {d}: {n - ok} of {n} live slots incomplete")
            notify("UW gamma collector", f"{d}: {n - ok} of {n} slots incomplete")
            day_dir = root / "live" / d.isoformat()
            if day_dir.is_dir():
                write_new(day_dir / f"_GAPS_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.txt",
                          ("\n".join([f"{d}: {ok}/{n} slots complete"] + lines) + "\n").encode())
    return 1 if bad else 0


# ----------------------------------------------------------------------------
# selftest (no network)
# ----------------------------------------------------------------------------

def selftest() -> int:
    import tempfile
    checks = []

    def ok(cond, label):
        checks.append((bool(cond), label))

    ok(len(expected_slots(date(2026, 10, 2))) == 78, "78 slots on a normal day")
    ok(expected_slots(date(2026, 10, 2))[0] == "0935", "first slot 09:35")
    ok(expected_slots(date(2026, 10, 2))[-1] == "1600", "last slot 16:00")
    ok(expected_slots(date(2026, 11, 27))[-1] == "1300", "early close ends 13:00")
    ok(expected_slots(date(2026, 11, 26)) == [], "Thanksgiving has no slots")
    ok(expected_slots(date(2026, 10, 3)) == [], "Saturday has no slots")
    et = lambda h, m, s=0: to_eastern(datetime(2026, 10, 2, h + 4, m, s, tzinfo=timezone.utc))
    ok(current_slot(et(9, 35, 3)) == "0935", "09:35:03 -> 0935")
    ok(current_slot(et(9, 34, 58)) == "0935", "09:34:58 -> 0935")
    ok(current_slot(et(9, 30, 0)) is None, "09:30 is before the window")
    ok(current_slot(et(9, 37, 40)) is None, "09:37:40 is off-slot")
    ok(current_slot(et(16, 0, 10)) == "1600", "16:00:10 -> 1600")
    ok(current_slot(et(16, 5, 0)) is None, "16:05 is after the window")
    # DST fallback rule agrees with zoneinfo on the 2026 transition instants
    ok(_us_dst(datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)), "DST starts 2026-03-08 07:00Z")
    ok(not _us_dst(datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc)), "not DST 2026-03-08 06:59Z")
    ok(not _us_dst(datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)), "DST ends 2026-11-01 06:00Z")
    ok(_us_dst(datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc)), "DST 2026-11-01 05:59Z")
    ok(page_is_empty(b'{"data": []}') and not page_is_empty(b'{"data": [{"strike": "1"}]}'),
       "empty-page detection")
    urls = dict((n, u) for n, u, _ in requests_for(date(2026, 10, 2)))
    ok("expirations%5B%5D=2026-10-02" in urls["spx_expiry_strike"], "expiry param encoded")
    ok(urls["xsp_expiry_strike"].startswith(f"{API_BASE}/stock/XSP/"), "XSP url")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "a.json"
        ok(write_new(p, b"1") and not write_new(p, b"2") and p.read_bytes() == b"1",
           "write_new never overwrites")
        root = Path(tmp)
        dd = root / "live" / "2026-10-02"
        dd.mkdir(parents=True)
        for n in REQUIRED:
            write_new(dd / f"0935_{n}_p0.json", b"{}")
        ok(slot_status(dd, "0935") == ["spx_price"], "price missing detected")
        write_new(dd / "0935_spx_spot_1m.json", b"{}")
        ok(slot_status(dd, "0935") == [], "complete slot detected")
        c, n, _ = check_day(root, date(2026, 10, 2))
        ok((c, n) == (1, 78), "gap count 1/78")
    for good, label in checks:
        print(("PASS " if good else "FAIL ") + label)
    failed = sum(1 for g, _ in checks if not g)
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--check" in argv or "--check-all" in argv:
        _, root = config()
        if "--check-all" in argv:
            days = sorted(date.fromisoformat(p.name) for p in (root / "live").iterdir()
                          if p.is_dir() and len(p.name) == 10)
        else:
            args = [a for a in argv if not a.startswith("--")]
            days = [date.fromisoformat(a) for a in args] or [to_eastern(datetime.now(timezone.utc)).date()]
        return gap_report(root, days)
    now_et = to_eastern(datetime.now(timezone.utc))
    if "--force" in argv:
        key, root = config()
        slot = f"{now_et:%H%M}"
        say(f"forced collection at {now_et:%Y-%m-%d %H:%M:%S %Z} (slot {slot})")
        return 1 if collect_slot(key, root, now_et.date(), slot, test=True) else 0
    try:
        slot = current_slot(now_et)
    except RuntimeError as e:
        say(f"error: {e}")
        return 1
    if slot is None:
        print(f"{now_et:%Y-%m-%d %H:%M:%S} ET is not a collection slot; nothing to do")
        return 0
    key, root = config()
    failures = collect_slot(key, root, now_et.date(), slot)
    last = expected_slots(now_et.date())[-1]
    if slot == last:
        gap_report(root, [now_et.date()])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
