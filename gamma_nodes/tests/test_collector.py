"""Collector end-to-end against a local fake API (no network)."""
import csv
import http.server
import json
import sys
import threading
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
import collect  # noqa: E402


class FakeUW(http.server.BaseHTTPRequestHandler):
    calls: list[str] = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        FakeUW.calls.append(self.path)
        if "expiry-strike" in self.path:
            page = int(self.path.split("page=")[1]) if "page=" in self.path else 0
            data = [{"strike": "7680"}] if page == 0 else []
            body = json.dumps({"data": data}).encode()
        elif "/quote" in self.path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        else:
            body = b'{"data": {"x": 1}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def test_collect_slot_end_to_end(tmp_path, monkeypatch):
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeUW)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(collect, "API_BASE", f"http://127.0.0.1:{srv.server_port}/api")
    monkeypatch.setattr(collect, "MAX_RETRIES", 0)
    d = date(2026, 10, 2)
    fails = collect.collect_slot("k", tmp_path, d, "0935")
    srv.shutdown()
    day = tmp_path / "live" / "2026-10-02"
    names = sorted(p.name for p in day.glob("0935_*.json"))
    assert "0935_spx_expiry_strike_p0.json" in names
    assert "0935_spx_expiry_strike_p1.json" in names  # the empty page that ends the walk
    assert "0935_spx_expiry_strike_p2.json" not in names
    assert "0935_spx_quote.json" not in names  # 404 is logged, not saved
    assert fails == 1
    rows = list(csv.DictReader(open(day / "_requests.csv")))
    assert len(rows) == 8 and {r["http_status"] for r in rows} == {"200", "404"}
    # the raw body is stored byte for byte
    assert json.loads((day / "0935_spx_expiry_strike_p0.json").read_bytes()) == {"data": [{"strike": "7680"}]}
    # price is satisfied by spx_spot_1m even though the quote failed
    assert collect.slot_status(day, "0935") == []
    # re-running the same slot writes nothing new
    n_before = len(list(day.iterdir()))
    assert collect.collect_slot("k", tmp_path, d, "0935") == 0
    assert len(list(day.iterdir())) == n_before


def test_holiday_tables_match_pipeline_calendar():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import gn_calendar
    for y, mds in collect.HOLIDAYS.items():
        assert gn_calendar.HOLIDAYS[y] == mds
    for y, mds in collect.EARLY_CLOSES.items():
        assert gn_calendar.EARLY_CLOSES[y] == mds
