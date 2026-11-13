"""Command-line interface for supersonic-inlet-designer.

Thin argparse layer over the existing library: no shock-relation or
optimization formulas live here.
"""
import argparse
import csv
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from . import inlet as _inlet
from .cfd_domain import export_cfd_domain_dxf, export_offdesign_domain_dxf
from .export import export_dxf
from .geometry import design_inlet
from .offdesign import off_design
from .optimize import optimize_equal_strength
from .plotting import _BG_COLOR, _RAMP_COLOR, save_inlet_plot


class CliError(Exception):
    """Raised for invalid user input; caught once in main() for a clean exit."""


def _package_version():
    try:
        return version("supersonic-inlet-designer")
    except PackageNotFoundError:            # running from a source tree that is not installed
        return "unknown"


def _cumulative_angles(ramp_angles_deg):
    phis = [0.0]
    for theta in ramp_angles_deg:
        phis.append(phis[-1] + theta)
    return phis[1:]


def _handle_design(args):
    if args.mach <= 1:
        raise CliError("mach must be > 1")
    if args.ramps < 0:
        raise CliError("ramps must be >= 0")

    geom = design_inlet(args.mach, args.ramps, capture_height=args.capture_height)
    states = _inlet.compress(args.mach, geom.ramp_angles_deg)
    cumulative = _cumulative_angles(geom.ramp_angles_deg)

    machs = [args.mach] + [s.M for s in states]
    p0_ratios = [1.0] + [s.p0_ratio for s in states]
    recovery = states[-1].p0_ratio if states else 1.0

    print(f"Design: M_inf={args.mach:.3f}  ramps={args.ramps}")
    print(f"{'ramp':>6} {'incr (°)':>10} {'cumul (°)':>10} {'beta (°)':>10}")
    for i in range(args.ramps):
        beta = geom.betas_deg[i]
        print(
            f"{i + 1:>6} {geom.ramp_angles_deg[i]:>10.4f} {cumulative[i]:>10.4f} {beta:>10.4f}"
        )
    print()
    print(f"{'region':>8} {'Mach':>10} {'p0/p0_inf':>12}")
    print(f"{'inf':>8} {machs[0]:>10.4f} {p0_ratios[0]:>12.4f}")
    for i in range(1, len(machs)):
        label = f"shock{i}" if i < len(machs) - 1 else "terminal"
        print(f"{label:>8} {machs[i]:>10.4f} {p0_ratios[i]:>12.4f}")
    print()
    print(f"total recovery (pi_d): {recovery:.4f}")
    print(f"capture height: {geom.capture_height:.4f}")
    print(f"throat height:  {geom.throat_height:.4f}")
    print(f"lip position:   ({geom.lip[0]:.4f}, {geom.lip[1]:.4f})")

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    png_path = f"{args.out}.png"
    dxf_path = f"{args.out}.dxf"
    json_path = f"{args.out}.json"

    save_inlet_plot(geom, png_path, units=args.units)
    export_dxf(geom, dxf_path, include_shocks=not args.no_shocks_in_dxf)

    result = {
        "inputs": {
            "mach": args.mach,
            "ramps": args.ramps,
            "capture_height": args.capture_height,
            "units": args.units,
        },
        "ramp_angles_deg": geom.ramp_angles_deg,
        "cumulative_angles_deg": cumulative,
        "beta_angles_deg": geom.betas_deg,
        "region_mach": machs,
        "region_p0_ratio": p0_ratios,
        "recovery": recovery,
        "capture_height": geom.capture_height,
        "throat_height": geom.throat_height,
        "lip": list(geom.lip),
        "package_version": _package_version(),
    }
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)

    return 0


def _handle_curve(args):
    for n in args.ramps:
        if n < 0:
            raise CliError("ramps must be >= 0")
    if args.mach_min >= args.mach_max:
        raise CliError("mach-min must be < mach-max")
    if args.step <= 0:
        raise CliError("step must be > 0")

    mach_values = np.arange(args.mach_min, args.mach_max + args.step / 2.0, args.step)

    rows = []
    skipped = 0
    for n_ramps in args.ramps:
        for M in mach_values:
            try:
                result = optimize_equal_strength(float(M), n_ramps)
            except ValueError:
                skipped += 1
                continue
            rows.append((float(M), n_ramps, result["recovery"], result["ramps"]))

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    csv_path = f"{args.out}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["M_inf", "n_ramps", "recovery", "ramp_angles_deg"])
        for M, n_ramps, recovery, ramps in rows:
            ramps_str = ";".join(f"{a:.6f}" for a in ramps)
            writer.writerow([f"{M:.6f}", n_ramps, f"{recovery:.6f}", ramps_str])

    fig, ax = plt.subplots()
    fig.patch.set_facecolor(_BG_COLOR)
    ax.set_facecolor(_BG_COLOR)
    for n_ramps in args.ramps:
        xs = [r[0] for r in rows if r[1] == n_ramps]
        ys = [r[2] for r in rows if r[1] == n_ramps]
        ax.plot(xs, ys, label=f"{n_ramps} ramps", linewidth=1.2)
    ax.set_xlabel("M∞")
    ax.set_ylabel("$\\pi_d$ = p02/p01")
    ax.grid(True, alpha=0.3)
    ax.legend()
    png_path = f"{args.out}.png"
    fig.savefig(png_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    print(f"skipped {skipped} infeasible combinations", file=sys.stderr)

    return 0


def _handle_cfd_domain(args):
    if args.mach <= 1:
        raise CliError("mach must be > 1")
    if args.ramps < 0:
        raise CliError("ramps must be >= 0")

    geom = design_inlet(args.mach, args.ramps, capture_height=args.capture_height)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    dxf_path = f"{args.out}.dxf"
    export_cfd_domain_dxf(geom, dxf_path)
    print(f"wrote {dxf_path}")

    if args.offdesign:
        offdesign_path = f"{args.out}_offdesign.dxf"
        export_offdesign_domain_dxf(
            geom,
            offdesign_path,
            top_height_factor=args.top_height_factor,
            ext_outlet=args.ext_outlet,
        )
        print(f"wrote {offdesign_path}")

    return 0


def _handle_offdesign(args):
    if args.design_mach <= 1:
        raise CliError("design-mach must be > 1")
    if args.ramps < 0:
        raise CliError("ramps must be >= 0")
    for M in args.mach:
        if M <= 1:
            raise CliError("mach must be > 1")

    geom = design_inlet(args.design_mach, args.ramps, capture_height=args.capture_height)

    results = []
    for M in args.mach:
        try:
            results.append(off_design(geom, M))
        except ValueError as exc:
            print(f"M={M}: detached, skipped ({exc})", file=sys.stderr)

    header = (
        f"{'M_inf':>8} {'regime':>14} {'dx/h_c':>24} {'A0/Ac':>10} "
        f"{'rec_obl':>10} {'M_pre_term':>11} {'M_post_term':>11} {'rec_tot':>10}  warnings"
    )
    print(header)
    for r in results:
        dx_str = ",".join(f"{d:.4f}" for d in r.dx_over_hc)
        warn_str = "; ".join(r.warnings)
        print(
            f"{r.M_inf:>8.3f} {r.regime:>14} {dx_str:>24} {r.mass_capture_ratio:>10.4f} "
            f"{r.recovery_oblique:>10.4f} {r.M_pre_terminal:>11.4f} {r.M_post_terminal:>11.4f} "
            f"{r.recovery_total:>10.4f}  {warn_str}"
        )

    if args.json:
        out_dir = os.path.dirname(args.json)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        data = [
            {
                "M_inf": r.M_inf,
                "regime": r.regime,
                "dx_over_hc": r.dx_over_hc,
                "mass_capture_ratio": r.mass_capture_ratio,
                "recovery_oblique": r.recovery_oblique,
                "M_pre_terminal": r.M_pre_terminal,
                "M_post_terminal": r.M_post_terminal,
                "recovery_total": r.recovery_total,
                "warnings": r.warnings,
            }
            for r in results
        ]
        with open(args.json, "w") as f:
            json.dump(data, f, indent=2)

    if args.plot:
        out_dir = os.path.dirname(args.plot)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
        fig.patch.set_facecolor(_BG_COLOR)

        machs = [r.M_inf for r in results]
        capture = [r.mass_capture_ratio for r in results]
        rec_obl = [r.recovery_oblique for r in results]
        rec_tot = [r.recovery_total for r in results]

        ax1.set_facecolor(_BG_COLOR)
        ax1.plot(machs, capture, color=_RAMP_COLOR, linewidth=1.2, marker="o")
        ax1.axvline(args.design_mach, color="grey", linestyle="--", linewidth=0.8)
        ax1.set_ylabel("A0/Ac")
        ax1.grid(True, alpha=0.3)

        ax2.set_facecolor(_BG_COLOR)
        ax2.plot(machs, rec_obl, linewidth=1.2, marker="o", label="oblique only")
        ax2.plot(machs, rec_tot, linewidth=1.2, marker="o", label="total")
        ax2.axvline(args.design_mach, color="grey", linestyle="--", linewidth=0.8)
        ax2.set_xlabel("M∞")
        ax2.set_ylabel("$\\pi_d$ = p02/p01")
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        fig.savefig(args.plot, dpi=200, facecolor=fig.get_facecolor())
        plt.close(fig)

    return 0


def _handle_gui(args):
    # Lazy import: the core install has no Qt; the app is an optional extra.
    try:
        from busemann.app import main as gui_main
    except ImportError as exc:
        raise CliError(
            f"the Busemann GUI is not installed ({exc}); install it with: pip install -e .[app]"
        ) from exc
    return gui_main([])


def build_parser():
    parser = argparse.ArgumentParser(prog="inletdesign")
    subparsers = parser.add_subparsers(dest="command", required=True)

    design_parser = subparsers.add_parser("design", help="design a single inlet")
    design_parser.add_argument("--mach", type=float, required=True)
    design_parser.add_argument("--ramps", type=int, required=True)
    design_parser.add_argument("--capture-height", type=float, default=1.0)
    design_parser.add_argument("--out", type=str, default="results/design")
    design_parser.add_argument("--units", choices=["hc", "m", "mm"], default="hc")
    design_parser.add_argument("--no-shocks-in-dxf", action="store_true")
    design_parser.set_defaults(handler=_handle_design)

    curve_parser = subparsers.add_parser("curve", help="sweep recovery vs Mach")
    curve_parser.add_argument("--ramps", type=int, nargs="+", required=True)
    curve_parser.add_argument("--mach-min", type=float, required=True)
    curve_parser.add_argument("--mach-max", type=float, required=True)
    curve_parser.add_argument("--step", type=float, required=True)
    curve_parser.add_argument("--out", type=str, default="results/curve")
    curve_parser.set_defaults(handler=_handle_curve)

    cfd_domain_parser = subparsers.add_parser(
        "cfd-domain", help="export a closed CFD fluid-domain outline (DXF)"
    )
    cfd_domain_parser.add_argument("--mach", type=float, required=True)
    cfd_domain_parser.add_argument("--ramps", type=int, required=True)
    cfd_domain_parser.add_argument("--capture-height", type=float, default=1.0)
    cfd_domain_parser.add_argument("--out", type=str, default="results/cfd_domain")
    cfd_domain_parser.add_argument("--offdesign", action="store_true")
    cfd_domain_parser.add_argument("--top-height-factor", type=float, default=2.0)
    cfd_domain_parser.add_argument(
        "--ext-outlet", choices=["normal", "vertical"], default="normal"
    )
    cfd_domain_parser.set_defaults(handler=_handle_cfd_domain)

    offdesign_parser = subparsers.add_parser(
        "offdesign", help="evaluate a fixed inlet geometry at other freestream Mach numbers"
    )
    offdesign_parser.add_argument("--design-mach", type=float, required=True)
    offdesign_parser.add_argument("--ramps", type=int, required=True)
    offdesign_parser.add_argument("--capture-height", type=float, default=1.0)
    offdesign_parser.add_argument("--mach", type=float, nargs="+", required=True)
    offdesign_parser.add_argument("--json", type=str, default=None)
    offdesign_parser.add_argument("--plot", type=str, default=None)
    offdesign_parser.set_defaults(handler=_handle_offdesign)

    gui_parser = subparsers.add_parser("gui", help="open the Busemann desktop app")
    gui_parser.set_defaults(handler=_handle_gui)

    return parser


def main(argv=None):
    # Warnings contain θ/∞; a piped cp1252 stdout on Windows must not crash on them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
