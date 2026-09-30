"""ES parameters transcribed from docs_scalpel_v37.pine (Matryoshka Engine).
For other assets, parse the ternary lookup tables in the .pine file."""
ES = {
    "D": dict(vol=18.54, bias=0.481, periods=252,
              wrh=0.624, wth1=1.248, wth2=1.562, gbtop=1.819,
              wrl=0.530, tl1=1.224, tl2=1.515, rbbot=1.796,
              inner_top=1.098, inner_bot=1.053, rng_top=0.084, rng_bot=0.096),
    "W": dict(vol=18.54, bias=0.481, periods=52,
              wrh=0.550, wth1=1.202, wth2=1.654, gbtop=1.826,
              wrl=0.551, tl1=1.171, tl2=1.638, rbbot=1.704,
              inner_top=1.0, inner_bot=1.0, rng_top=0.078, rng_bot=0.078),
    "M": dict(vol=17.37, bias=0.531, periods=12,
              wrh=0.511, wth1=1.013, wth2=1.197, gbtop=1.217,
              wrl=0.491, tl1=1.127, tl2=1.539, rbbot=1.598,
              inner_top=1.0, inner_bot=1.0, rng_top=0.138, rng_bot=0.078),
}
GP_OUTER, GP_INNER = 0.618, 0.650
