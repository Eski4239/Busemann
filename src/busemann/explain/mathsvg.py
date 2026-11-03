"""LaTeX (matplotlib mathtext subset) -> SVG bytes, cached in memory and on disk. No Qt.

The equation warm-up runs in a separate process (explain.warm) that writes finished SVG
files into the cache directory; the GUI only reads files. tex_to_svg() renders in the calling
process only on a cache miss.
"""
import hashlib
import io
import os
import sys
import threading
import time
from pathlib import Path

EQUATION_PT = 11.0      # font size of rendered equations, points (SVG units are pt)
PT_TO_PX = 4.0 / 3.0    # 1 pt = 1/72 in, 1 px = 1/96 in
CACHE_VERSION = "1"     # bump to invalidate every cached file

# mathtext is not thread-safe: calls in this process take turns.
_LOCK = threading.Lock()
render_count = 0        # mathtext renders done in this process (tests use it)


def cache_dir():
    """Equation cache directory: $BUSEMANN_CACHE_DIR, else the user cache folder."""
    env = os.environ.get("BUSEMANN_CACHE_DIR")
    if env:
        base = Path(env)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / \
            "Busemann" / "cache"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "busemann"
    return base / "equations"


def cache_path(tex, color, size_pt=EQUATION_PT, directory=None):
    """File of one equation: the name hashes the cache version, matplotlib version, colour,
    size and TeX, so a change in any of them is a different file."""
    import matplotlib

    key = "\n".join((CACHE_VERSION, matplotlib.__version__, color, repr(size_pt), tex))
    name = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".svg"
    return Path(directory or cache_dir()) / name


def render(tex, color="#111827", size_pt=EQUATION_PT):
    """Render with mathtext now (no cache). ValueError if mathtext cannot parse it."""
    global render_count
    from matplotlib import mathtext
    from matplotlib.font_manager import FontProperties

    with _LOCK:
        render_count += 1
        buf = io.BytesIO()
        mathtext.math_to_image(f"${tex}$", buf, prop=FontProperties(size=size_pt),
                               format="svg", color=color)
        return buf.getvalue()


class _Memory(dict):
    """Bounded in-memory cache (oldest entry dropped first)."""
    LIMIT = 2048

    def __setitem__(self, key, value):
        if key not in self and len(self) >= self.LIMIT:
            self.pop(next(iter(self)))
        super().__setitem__(key, value)


_memory = _Memory()


def cached(tex, color="#111827", size_pt=EQUATION_PT):
    """SVG bytes if already cached (memory or disk), else None. Never renders."""
    key = (tex, color, size_pt)
    hit = _memory.get(key)
    if hit is not None:
        return hit
    try:
        data = cache_path(tex, color, size_pt).read_bytes()
    except OSError:
        return None
    _memory[key] = data
    return data


def tex_to_svg(tex, color="#111827", size_pt=EQUATION_PT):
    """SVG bytes of `$tex$`: from the cache, else rendered here and stored."""
    data = cached(tex, color, size_pt)
    if data is None:
        data = render(tex, color, size_pt)
        _memory[(tex, color, size_pt)] = data
        _write(cache_path(tex, color, size_pt), data)
    return data


def _write(path, data):
    """Atomic write (temp file + replace): a reader never sees half a file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError:
        pass                                   # the cache is an optimisation only


def render_to_files(texs, color, size_pt, directory):
    """Warm-up worker entry point (runs in the render process): render every equation that
    is not yet in `directory`. Returns (rendered count, longest single render in ms)."""
    rendered, longest = 0, 0.0
    for tex in texs:
        path = cache_path(tex, color, size_pt, directory)
        if path.exists():
            continue
        t0 = time.perf_counter()
        try:
            data = render(tex, color, size_pt)
        except ValueError:
            continue
        longest = max(longest, (time.perf_counter() - t0) * 1000.0)
        _write(path, data)
        rendered += 1
    return rendered, longest


CACHE_MAX_AGE_DAYS = 60
CACHE_MAX_BYTES = 50 * 2**20


def prune_cache(directory=None, max_age_days=CACHE_MAX_AGE_DAYS, max_bytes=CACHE_MAX_BYTES,
                now=None):
    """Start-up housekeeping: delete cache files older than max_age_days, then the oldest
    files until the folder is at most max_bytes. Returns the number of files removed.
    Errors are ignored (the cache is an optimisation)."""
    directory = Path(directory or cache_dir())
    now = time.time() if now is None else now
    try:
        files = []
        for p in directory.iterdir():
            if p.suffix in (".svg", ".tmp") and p.is_file():
                st = p.stat()
                files.append((st.st_mtime, st.st_size, p))
    except OSError:
        return 0
    removed = 0
    keep = []
    for mtime, size, p in files:
        if now - mtime > max_age_days * 86400.0:
            removed += _unlink(p)
        else:
            keep.append((mtime, size, p))
    keep.sort()                                   # oldest first
    total = sum(size for _, size, _ in keep)
    for mtime, size, p in keep:
        if total <= max_bytes:
            break
        if _unlink(p):
            removed += 1
            total -= size
    return removed


def _unlink(path):
    try:
        path.unlink()
        return 1
    except OSError:
        return 0


def clear_memory():
    _memory.clear()


def cache_info():
    return {"memory": len(_memory), "renders_here": render_count}
