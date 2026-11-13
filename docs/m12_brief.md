# M12 brief — finish Busemann and make it installable

Read docs/busemann_spec_v1_addendum.md (sections A, H, K) and tools/brand/README.md first. Work in the order below and report after each PART. Do not commit.

## PART 0 — Sources (final state for release)
1. CONFIRMED (reviewer checked the scan in references/): Oswatitsch, K., "Pressure Recovery for Missiles with Reaction Propulsion at High Supersonic Speeds (The Efficiency of Shock Diffusers)", NACA TM 1140 (1947), translation of Forschungen und Entwicklungen des Heereswaffenamtes, Bericht Nr. 1005, Göttingen, January 1944. Equal-strength condition: eq. (17), p. 13 (Ma₀ sin γ₀ = Ma₁ sin γ₁ = … ; "the total-pressure ratios as well as the pressure ratios themselves for all oblique compression shocks are equal"); problem statement p. 6. Note in the citation: TM 1140 writes γ for the shock angle (our β) and k for the ratio of specific heats (our γ); its n counts the terminal normal shock. Remove "pending" everywhere for this source (Explain, Verification, notes, code comments).
2. Add a documented consistency check (comment + docs, not a hard test): Busemann's maximum recovery at M3 for 1–4 shocks (0.328, 0.581, 0.744, 0.836) agrees with TM 1140 Fig. 1, p. 43, read off the printed graph.
3. Korkegi (AIAA J. 13(4), 1975) and Seddon & Goldsmith (Intake Aerodynamics, 2nd ed., 1999): the originals could not be obtained. Replace "pending" with "(original not consulted; widely cited correlation)" in every user-facing place and in verification_notes.md. Keep the criteria, their "approximate — verify with CFD" wording and the validation-CFD agreement note. Add a test that no user-facing string contains "pending".

## PART 1 — Brand assets (all files already in src/busemann/resources/brand/)
1. Window/taskbar icon: QIcon built from brand/app_icon_16/24/32/48/64/128/256.png, set on QApplication and every top-level window (main, welcome, About, isentropic window, dialogs). Remove the tinted icons/busemann.svg and its theme.icon() use if nothing else needs it.
2. Welcome window: header = brand/logo_lockup.svg at 34 px height (fall back to logo_lockup_2x.png if the outlined SVG renders soft), replacing the separate title/tagline text; version line under it. Replace images/inlet_3d.png with brand/welcome_hero.png shown at 260×165 with devicePixelRatio 2, rounded 6 px corners, and a muted 10 px caption: "Concorde-style intake at Mach 2.02 — temperature field computed with Busemann". Delete images/inlet_3d.png, tools/render_inlet_3d.py and every reference/test to them.
3. About: brand/logo_lockup.svg at 40 px height replaces the "Busemann 0.1.0" heading; version as a muted line under it.
4. Tests: icon has all sizes; hero loads at DPR 2; no reference to inlet_3d remains.

## PART 2 — Remaining fixes
1. Isentropic window, wrong value: the "Engine-face (MIL-E-5008B)" row shows η_MIL. Show two rows: "Engine face ≈ η × diffuser recovery" (0.854 at M3, δ 33.789°) and "MIL-E-5008B" (0.809). Test both values.
2. Isentropic window, finish the styling to match the main window: token stylesheet (no grey default), results as cards like the Results panel, real subscripts (M_f → M<sub>f</sub>, h_c → h<sub>c</sub>), show duct entry height h<sub>t</sub> (30.26 mm at M3/δ 33.789°, h_c 100 mm) as a result, a p/p∞ legend for the field, the hatched wall and the cowl drawn like the main canvas, the "coalesce into a shock" label not clipped, and the drawing framed to fill the view (ramp, fan, lip and duct entry). Extend the text audit to this window.
3. Export errors: export_controller has no error handling. Wrap every export in try/except (OSError, ValueError, ezdxf errors) and show a clear token-styled message ("Could not write <file>: <reason>. Is it open in another program?"). Never crash or fail silently. Test with a read-only target and a locked file.
4. Remove the expired M_duct deprecated alias and its test (it said "removed after M6").
5. Version: single source of truth src/busemann/__init__.py __version__ = "1.0.0"; pyproject reads it (dynamic version) or matches it, with a test that they agree. About, welcome window, export metadata and the installer all use it.

## PART 3 — Frozen-app self-test
Add `busemann --self-test`: loads every resource (fonts, icons, brand, explain .md, tooltips.json, examples, validation.json, licences), computes the validation design (recovery 0.7437), one off-design point, the isentropic case, renders one Explain equation through the warm-up process (spawn), writes and re-reads a DXF in a temp folder, prints a one-line summary and exits 0 (non-zero naming the failing item otherwise). No window shown. Test it in pytest (source mode).

## PART 4 — Windows build (one-folder, LGPL-compliant)
1. packaging/busemann.spec (PyInstaller, one-folder, windowed, name "Busemann", icon src/busemann/resources/brand/busemann.ico):
   - datas: the whole src/busemann/resources tree; matplotlib data needed for mathtext;
   - PySide6-Essentials only (QtCore, QtGui, QtWidgets, QtSvg); exclude QtWebEngine, Qt3D, QtMultimedia, QtQuick/QML, tkinter, tests, IPython, pytest;
   - verify the spawn-based warm-up process works frozen (freeze_support is already in main());
   - Windows version info (company "Pablo Goulet Valenti", product "Busemann", version from __version__).
2. packaging/busemann.iss (Inno Setup 6):
   - per-user install by default (no admin) to {localappdata}\Programs\Busemann, with an all-users option;
   - Start-menu shortcut, optional desktop shortcut, uninstaller, SetupIconFile = busemann.ico, WizardStyle modern, a fixed AppId GUID (generate once and keep it);
   - license page showing LICENSE; no file associations (do not take over .dxf);
   - output dist/Busemann-Setup-<version>.exe.
3. tools/build_release.ps1: clean venv in build/venv → pip install ".[app]" pyinstaller → pyinstaller packaging/busemann.spec → run dist/Busemann/Busemann.exe --self-test (fail the build if non-zero) → ISCC packaging/busemann.iss → zip the one-folder build as dist/Busemann-<version>-portable.zip → write dist/SHA256SUMS.txt. Print final sizes.
4. Licences in the build: resources/licenses/ plus THIRD-PARTY-NOTICES.txt at the install root listing each bundled component, its licence and source URL (PySide6/Qt LGPLv3 with a note that the Qt DLLs are replaceable in the install folder; numpy/scipy incl. OpenBLAS and the GCC runtime notice; matplotlib; pyqtgraph; ezdxf; Inter; JetBrains Mono).
5. Add build/ and dist/ to .gitignore. Report installed size, exe start-up time to the welcome window, and the self-test output.

## PART 5 — Release automation (GitHub)
- .github/workflows/release.yml: on push of tags v*, windows-2022 runner: Python 3.11, Inno Setup (choco install innosetup), run tools/build_release.ps1, upload the installer, the portable zip and SHA256SUMS.txt to a GitHub Release named "Busemann <version>", body from the CHANGELOG section for that version.
- Existing tests.yml unchanged.

## PART 6 — Repository front door
1. LICENSE: MIT, "Copyright (c) 2026 Pablo Goulet Valenti".
2. CHANGELOG.md: "1.0.0 — first release", grouped (Design, Off-design, Analytics, Compare, Isentropic ramp, Explain/Verification, Files/Export, Validation, Engineering), plus a "History notes" line: commit 159efb5 also contains the MainWindow leak fix despite its M10 message.
3. README.md rewrite:
   - stacked logo (brand/logo_lockup_stacked_2x.png, width 220), a one-sentence pitch, the welcome hero image;
   - Download (link to the latest release) with: "The installer is not code-signed, so Windows SmartScreen may warn on first run: choose More info → Run anyway";
   - Features (short bullets with 3–4 screenshots from docs/screenshots);
   - How it works (one paragraph, citing Oswatitsch NACA TM 1140 and NACA Report 1135);
   - Validation summary (the About paragraph, no internal phase names) plus one line: "Maximum recoveries agree with Oswatitsch's 1944 results (NACA TM 1140, Fig. 1)";
   - Build from source, Running tests (keep the existing section), Licence.
4. Refresh the README screenshots in docs/screenshots from the final build.

## PART 7 — Final verification
- Plain pytest and pytest -m "not perf", plugged in, with counts and times.
- Run tools/build_release.ps1 locally and report the self-test line and sizes.
- List anything you could not do (the GitHub Release only runs after the tag is pushed).
