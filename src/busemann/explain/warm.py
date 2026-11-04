"""Every equation the Explain drawer can show for the current results (no Qt), so the cache
can be filled in the background before the drawer is first opened."""
from . import content as C
from .mathsvg import render_to_files, tex_to_svg
from .select import build_context, topic_context


def _items(result):
    return ([("region", i) for i in range(len(result.regions))]
            + [("shock", i) for i in range(len(result.shock_states))] + [("cowl", 0), (None, None)])


def equations(design, off=None, fs=None, off_fs=None):
    """TeX of every equation (relations and this case's numbers) for every selectable item,
    on both views, plus the topic entries. Entries that cannot render here are skipped."""
    texs = []
    contexts = []
    for view, result in (("design", design), ("offdesign", off)):
        if result is None:
            continue
        for kind, index in _items(result):
            contexts.append(build_context(design, off, fs, off_fs, view, kind, index))
    for topic in ("method", "offdesign"):
        if topic == "offdesign" and off is None:
            continue
        contexts.append(topic_context(topic, design, off, fs, off_fs))
    for name, ctx in contexts:
        try:
            rendered = C.render(C.load(name), ctx)
        except C.TemplateError:
            continue
        for lines in rendered.sections.values():
            texs.extend(ln.text for ln in lines if ln.kind == "equation")
    return list(dict.fromkeys(texs))            # unique, in order


# --- render process ----------------------------------------------------------------------
# mathtext holds the GIL for long stretches (up to ~0.25 s per equation), so the warm-up runs
# in a separate process (spawn, one worker) that writes SVG files into the disk cache; the GUI
# process only reads finished files.
CHUNK = 6                   # equations per job: pending jobs can be cancelled in between
_executor = None
_futures = []


def _pool():
    global _executor
    if _executor is None:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        _executor = ProcessPoolExecutor(max_workers=1,
                                        mp_context=multiprocessing.get_context("spawn"))
    return _executor


def start(texs, color, size_pt=None):
    """Queue the missing equations for the render process (previous queue cancelled).
    Returns the futures (each gives (rendered, longest ms))."""
    from .mathsvg import EQUATION_PT, cache_dir, cache_path

    cancel()
    size_pt = EQUATION_PT if size_pt is None else size_pt
    directory = cache_dir()
    missing = [t for t in texs if not cache_path(t, color, size_pt, directory).exists()]
    pool = _pool()
    for k in range(0, len(missing), CHUNK):
        _futures.append(pool.submit(render_to_files, missing[k:k + CHUNK], color, size_pt,
                                    str(directory)))
    return list(_futures)


def cancel():
    """Drop queued jobs (a job already running finishes its few equations)."""
    for f in _futures:
        f.cancel()
    _futures.clear()


def join(timeout=10.0):
    """Cancel queued jobs and wait for the one already running (measurements, tests).
    True when nothing is left running."""
    from concurrent.futures import wait

    running = [f for f in _futures if not f.cancel()]
    _futures.clear()
    if running:
        wait(running, timeout)
    return all(f.done() for f in running)


def shutdown():
    global _executor
    cancel()
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def warm_in_process(texs, color, should_stop=lambda: False):
    """Render into the cache from this process (tools and tests only, never the GUI)."""
    n = 0
    for tex in texs:
        if should_stop():
            break
        tex_to_svg(tex, color)
        n += 1
    return n
