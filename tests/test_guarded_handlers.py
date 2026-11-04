"""Every overridden Qt event handler is wrapped in crashlog.guarded (no Qt needed).

An exception escaping an overridden handler hangs PySide6 6.12's event loop (M8.2 bug 1), so a
new override without the guard fails this test.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "busemann"
HANDLER = re.compile(r"^    def ([a-zA-Z]+Event|paint|eventFilter)\(self", re.M)


def test_every_event_handler_override_is_guarded():
    missing = []
    for path in SRC.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            m = HANDLER.match(line)
            if m and not lines[i - 1].strip().startswith("@guarded"):
                missing.append(f"{path.relative_to(SRC)}:{i + 1} {m.group(1)}")
    assert missing == []
