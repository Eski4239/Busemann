# Changelog

## 1.0.0 — first release

Busemann is a desktop design lab for two-dimensional external-compression supersonic inlets.
Give it a flight Mach number and the air the aircraft flies in, and it finds the ramp angles
for the best total-pressure recovery (or takes yours), draws the shock system, and shows the
recovery, the mass capture and the flow in every region. It then tells you how that fixed
inlet behaves at other Mach numbers, where its boundary layer is likely to separate (and what
that means for buzz), and what to check with CFD. Windows 10/11 64-bit: installer or portable
zip.

### Design
- Oswatitsch equal-strength optimum (maximum recovery for 1–4 ramps) or your own ramp angles;
  optional limit on the cowl angle.
- Flight conditions from altitude (standard atmosphere) or pressure and temperature, in SI or
  imperial units; every field accepts a value with a unit ("65000 ft", "-56.5 C").
- Capture height set directly or sized to an engine's mass flow and inlet width.
- Canvas with shocks, coloured flow regions, dimensions and a grid; drag the ramp corners
  (custom angles) with a live no-go zone at the detachment limit.
- Results: total recovery, engine-face estimate against MIL-E-5008B, mass capture, captured
  mass flow, Mach after the terminal shock and cowl margin; gap to the optimum for custom
  angles; full undo/redo and keyboard shortcuts.
- Presets: Concorde cruise, XB-70, SR-71, X-15 record and the validation case.

### Off-design
- The fixed inlet at any flight Mach number: spillage, shock-in-duct above the design Mach,
  cowl-shock attachment, supplied versus demanded mass flow.
- Charts of recovery, capture and cowl margin against Mach, with a play button that sweeps
  the Mach number.

### Analytics
- Trade studies: recovery against total turning and against design Mach for 0–4 ramps, the
  isentropic limit and the MIL-E-5008B line; pick a point and apply it as the design.
- Drag (inviscid estimate): additive drag and cowl pressure drag against Mach.

### Compare
- Pin a design and compare it with the live one: side-by-side or overlaid drawings, a table
  of every input and result with differences, and off-design curves of both.

### Isentropic ramp
- Tools ▸ Isentropic ramp: the centred Prandtl–Meyer compression surface for a chosen turning
  or final Mach number, with its exact pressure field, duct entry height and a comparison with
  the multi-ramp optimum; exports as DXF or Gmsh geometry.

### Explain and Verification
- Explain: every shock, region and the method explained with its relations, this case's
  numbers, plain words and assumptions; every relation cites its source (NACA Report 1135,
  Oswatitsch NACA TM 1140, …).
- Verification: every approximation and warning (separation, buzz, cowl detachment, real gas,
  upper-bound recovery, drag estimates) with its criterion, source and "verify with CFD".

### Files and export
- Designs are saved as DXF drawings that reopen exactly; any other DXF with a ramp and a cowl
  line imports as a custom design.
- Exports: geometry DXF, CFD domain DXFs (design and off-design), Gmsh .geo, results JSON and
  CSV, each geometry export with a `verification_notes.md` beside it.

### Validation
- Every relation follows NACA Report 1135; maximum recoveries agree with Oswatitsch's 1944
  results (NACA TM 1140, Fig. 1); over 1,000 automated tests.
- Ansys Fluent 2D CFD: design-point recovery within 0.35 %, below the design Mach within 0.1 %
  (capture within 0.4 %); above it the model is an upper bound (CFD 4.9 % lower at Mach 3.25).

### Engineering
- Windows installer (per-user, no admin rights needed) and portable zip; `Busemann.exe
  --self-test` checks an installation without opening a window.
- The installer and the zip are not code-signed: Windows SmartScreen may warn on first run
  (More info → Run anyway), and the first launch can take up to a minute while Windows scans
  the new files.
- Open source under the MIT License; third-party licences in `THIRD-PARTY-NOTICES.txt` and
  under Help ▸ About.

## Development notes

Not part of any release text (tools/changelog_section.py stops at this heading).

- Commit 159efb5 also contains the MainWindow memory-leak fix, despite its M10 (Compare) commit
  message.
