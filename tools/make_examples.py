"""Write the bundled example designs as Busemann DXFs (src/busemann/resources/examples/).

    python tools/make_examples.py

Each example is a set of inputs saved with busemann.project.save, so it reopens exactly.
"""
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from busemann import project as P  # noqa: E402
from busemann.inputs import Inputs, preset_changes  # noqa: E402

OUT = ROOT / "src" / "busemann" / "resources" / "examples"

EXAMPLES = {
    # the Phase 3 CFD freestream (M 3, 10 kPa, 220 K), Oswatitsch 2 ramps
    "validation_case": dataclasses.replace(Inputs(), **preset_changes("Validation case")),
    # X-15 record conditions with 4 ramps: shows the real-gas warning
    "x15_four_ramp": dataclasses.replace(Inputs(), **preset_changes("X-15 record"), n_ramps=4),
    # M 3, 3 ramps, the Oswatitsch optimum limited to a 30° cowl angle
    "m3_cowl_constrained": Inputs(n_ramps=3, max_cowl_enabled=True),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, inputs in EXAMPLES.items():
        path = P.save(OUT / f"{name}.dxf", inputs)
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
