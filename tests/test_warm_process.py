"""Equation warm-up in a separate render process (no Qt): files appear in the cache and this
process renders nothing."""
import concurrent.futures as cf

from busemann.explain import mathsvg, warm
from inletdesign import api


def test_render_process_fills_the_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BUSEMANN_CACHE_DIR", str(tmp_path))
    mathsvg.clear_memory()
    d = api.design(3.0, 2)
    texs = warm.equations(d, api.off_design_point(d, 2.5), api.freestream(3.0, altitude_m=2e4))[:8]
    before = mathsvg.render_count
    try:
        futures = warm.start(texs, "#111827")
        done = [f.result(timeout=120) for f in cf.as_completed(futures, timeout=120)]
    finally:
        warm.shutdown()
    assert sum(n for n, _ in done) == len(texs)
    assert mathsvg.render_count == before                  # rendered in the other process
    for tex in texs:
        assert mathsvg.cache_path(tex, "#111827").exists()
        assert mathsvg.cached(tex, "#111827").startswith(b"<?xml")
    assert mathsvg.render_count == before                  # loading files renders nothing
    assert warm.start(texs, "#111827") == []               # nothing missing: no jobs
    warm.shutdown()


def test_cache_key_covers_colour_and_size(tmp_path):
    a = mathsvg.cache_path("x^2", "#111827", 11.0, tmp_path)
    assert a != mathsvg.cache_path("x^2", "#000000", 11.0, tmp_path)
    assert a != mathsvg.cache_path("x^2", "#111827", 12.0, tmp_path)
    assert a != mathsvg.cache_path("x^3", "#111827", 11.0, tmp_path)
    assert a.parent == tmp_path and a.suffix == ".svg"


def test_tex_to_svg_stores_and_reuses_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BUSEMANN_CACHE_DIR", str(tmp_path))
    mathsvg.clear_memory()
    n = mathsvg.render_count
    svg = mathsvg.tex_to_svg(r"M_{n1} = M_1 \sin\beta")
    assert mathsvg.render_count == n + 1 and list(tmp_path.rglob("*.svg"))
    mathsvg.clear_memory()
    assert mathsvg.tex_to_svg(r"M_{n1} = M_1 \sin\beta") == svg
    assert mathsvg.render_count == n + 1                   # second time from disk
