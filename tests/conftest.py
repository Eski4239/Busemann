import os
import tempfile

# Equation SVG cache (explain.mathsvg) goes to a temporary folder for the whole session, so
# tests never write into the user's cache. Set before any test imports busemann.
os.environ.setdefault("BUSEMANN_CACHE_DIR", tempfile.mkdtemp(prefix="busemann_eqcache_"))
# Crash log (busemann.crashlog) likewise, when a test runs main().
os.environ.setdefault("BUSEMANN_CRASH_DIR", tempfile.mkdtemp(prefix="busemann_crash_"))
