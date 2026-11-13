"""Entry point of the frozen Windows build (packaging/busemann.spec).

freeze_support() runs first, before the app and Qt are imported: the equation warm-up process
(explain.warm, multiprocessing "spawn") starts this same exe as its child, and the child must
turn into a worker here without loading the GUI. app.main() calls it again (harmless).
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from busemann.app import main

    sys.exit(main())
