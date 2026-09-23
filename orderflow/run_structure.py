"""Build the hourly day/week structure frame for every coin -> data/binance/parquet/structure/{SYM}.parquet

    python orderflow/run_structure.py [SYM ...]
"""
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from of import load, structure            # noqa: E402
from of.config import DEV, HOLDOUT, PQ     # noqa: E402


def one(sym):
    out = PQ / "structure" / f"{sym}.parquet"
    if out.exists():
        return sym, "cached"
    t0 = time.time()
    try:
        X = structure.build(load.klines_1m(sym), load.hourly(sym), load.funding(sym))
        bad = [c for c in X.columns if X[c].dtype == object or X[c].isna().all()]
        if bad:
            raise ValueError(f"empty/object columns {bad}")
        out.parent.mkdir(parents=True, exist_ok=True)
        X.to_parquet(out)
        return sym, f"{len(X)} rows {time.time() - t0:.0f}s"
    except Exception:
        return sym, "FAILED\n" + traceback.format_exc()


if __name__ == "__main__":
    syms = sys.argv[1:] or DEV + HOLDOUT
    with ProcessPoolExecutor(3) as ex:
        for f in as_completed([ex.submit(one, s) for s in syms]):
            print(*f.result(), flush=True)
