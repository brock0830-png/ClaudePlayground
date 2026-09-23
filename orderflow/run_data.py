"""Download and cache 1m klines, OI metrics and funding for all 35 coins; build the hourly panels.

    python orderflow/run_data.py [SYM ...]
"""
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from of import load                      # noqa: E402
from of.config import DEV, HOLDOUT        # noqa: E402


def one(sym):
    t0 = time.time()
    try:
        load.klines_1m(sym)
        load.oi_5m(sym)
        load.funding(sym)
        h = load.hourly(sym)
        return sym, f"ok {len(h)} hours {h.index[0]:%Y-%m-%d}..{h.index[-1]:%Y-%m-%d} " \
                    f"oi missing {h.oi_usd.isna().mean():.1%} {time.time() - t0:.0f}s"
    except Exception:
        return sym, "FAILED\n" + traceback.format_exc()


if __name__ == "__main__":
    syms = sys.argv[1:] or DEV + HOLDOUT
    with ProcessPoolExecutor(3) as ex:
        futs = [ex.submit(one, s) for s in syms]
        for f in as_completed(futs):
            s, msg = f.result()
            print(s, msg, flush=True)
