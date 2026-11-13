"""Windows packaging files (M12 PART 4, no Qt): the installer script, the PyInstaller spec,
the third-party notices, the build script and the licence agree with the app and with each
other. The build itself is run by tools/build_release.ps1 (and the release workflow)."""
import importlib.util
import json
import re
from pathlib import Path

from busemann import __version__

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / "packaging" / "busemann.iss").read_text(encoding="utf-8")
SPEC = (ROOT / "packaging" / "busemann.spec").read_text(encoding="utf-8")
PS1 = (ROOT / "tools" / "build_release.ps1").read_text(encoding="utf-8")
APP_PY = (ROOT / "src" / "busemann" / "app.py").read_text(encoding="utf-8")
APP_ID_GUID = "67786B54-1C47-43B9-8C2E-720A6927FD91"     # fixed once (M12): never change it


def _iss_setting(name):
    m = re.search(rf"^{name}=(.*)$", ISS, re.M)
    assert m, name
    return m.group(1).strip()


def _make_notices():
    spec = importlib.util.spec_from_file_location("make_notices", ROOT / "tools" / "make_notices.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- taskbar identity: installer shortcuts == the running app ---------------------------------
def test_shortcut_app_user_model_id_matches_the_app():
    app_id = re.search(r'^APP_USER_MODEL_ID = "([^"]+)"', APP_PY, re.M).group(1)
    iss_id = re.search(r'^#define AppUserModelID "([^"]+)"', ISS, re.M).group(1)
    assert app_id == iss_id == "PabloGouletValenti.Busemann"
    icons = ISS.split("[Icons]")[1].split("\n[")[0]
    shortcuts = [ln for ln in icons.splitlines() if ln.startswith("Name:")]
    assert len(shortcuts) == 2                                     # Start menu + desktop
    for line in shortcuts:
        assert 'AppUserModelID: "{#AppUserModelID}"' in line, line
    assert any("{autoprograms}" in ln for ln in shortcuts)
    assert any("{autodesktop}" in ln and "Tasks: desktopicon" in ln for ln in shortcuts)


# --- installer --------------------------------------------------------------------------------
def test_installer_is_per_user_with_an_all_users_option():
    assert _iss_setting("PrivilegesRequired") == "lowest"
    assert _iss_setting("PrivilegesRequiredOverridesAllowed") == "dialog"
    assert _iss_setting("DefaultDirName") == r"{autopf}\{#AppName}"   # {localappdata}\Programs


def test_installer_settings():
    assert _iss_setting("AppId") == "{{" + APP_ID_GUID + "}"
    assert _iss_setting("WizardStyle") == "modern"
    assert _iss_setting("OutputDir") == r"..\dist"
    assert _iss_setting("OutputBaseFilename") == "Busemann-Setup-{#AppVersion}"
    assert _iss_setting("AppVersion") == "{#AppVersion}"            # from /DAppVersion only
    for key in ("LicenseFile", "SetupIconFile"):
        assert (ROOT / "packaging" / _iss_setting(key)).is_file(), key
    assert _iss_setting("LicenseFile") == r"..\LICENSE"
    assert _iss_setting("SetupIconFile").endswith(r"brand\busemann.ico")
    assert "#error AppVersion is not defined" in ISS


def test_installer_takes_no_file_associations():
    assert _iss_setting("ChangesAssociations") == "no"
    assert "[Registry]" not in ISS
    code = [ln for ln in ISS.splitlines() if not ln.lstrip().startswith(";")]   # no comments
    assert not [ln for ln in code if ".dxf" in ln.lower()]


# --- PyInstaller spec --------------------------------------------------------------------------
def test_spec_builds_the_windowed_one_folder_app():
    assert 'name="Busemann"' in SPEC and "console=False" in SPEC
    assert "exclude_binaries=True" in SPEC and "COLLECT(" in SPEC        # one-folder
    assert 'PKG / "resources" / "brand" / "busemann.ico"' in SPEC
    assert '(str(PKG / "resources"), "busemann/resources")' in SPEC
    assert '"busemann/theme"' in SPEC
    assert 'COMPANY = "Pablo Goulet Valenti"' in SPEC and 'PRODUCT = "Busemann"' in SPEC
    assert "__version__" in SPEC                                       # version from the app


def test_spec_keeps_qt_to_essentials_and_drops_dev_packages():
    for name in ("PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
                 "PySide6.QtQuick", "PySide6.QtQml", "tkinter", "IPython", "pytest"):
        assert f'"{name}"' in SPEC, name


def test_spec_bundles_the_matplotlib_svg_backend():
    """The frozen self-test found it missing (mathtext SVG in the render process)."""
    assert '"matplotlib.backends.backend_svg"' in SPEC


def test_entry_point_calls_freeze_support_before_importing_the_app():
    entry = (ROOT / "packaging" / "busemann_entry.py").read_text(encoding="utf-8")
    assert entry.index("multiprocessing.freeze_support()") < entry.index("from busemann.app")


def test_app_extra_is_pyside6_essentials_only():
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    app = data["project"]["optional-dependencies"]["app"]
    assert any(d.startswith("PySide6-Essentials") for d in app)
    assert not any(re.match(r"PySide6(?!-Essentials)\b", d) for d in app)


# --- notices and licence -----------------------------------------------------------------------
def test_third_party_notices_list_every_component():
    mn = _make_notices()
    comps = mn.components()
    text = mn.render(comps, __version__, versions={})
    assert text.startswith(f"Busemann {__version__} - third-party notices")
    for comp in comps:
        assert comp["name"] in text and comp["license"] in text and comp["url"] in text
        for f in comp["files"]:
            assert f"_internal\\busemann\\resources\\licenses\\{f}" in text
    for must in ("LGPL", "replace them", r"_internal\PySide6", "OpenBLAS",
                 "GCC-exception-3.1", "MIT License"):
        assert must in text, must
    names = {c["name"] for c in comps}
    assert {"PySide6 / Qt", "NumPy", "SciPy", "Matplotlib", "pyqtgraph", "ezdxf",
            "Inter (font)", "JetBrains Mono (font)", "Python",
            "PyInstaller bootloader"} <= names


def test_every_component_has_a_source_url_and_licence_text():
    comps = json.loads((ROOT / "src/busemann/resources/licenses/components.json")
                       .read_text(encoding="utf-8"))["components"]
    for comp in comps:
        assert comp["url"].startswith("https://"), comp["name"]
        for f in comp["files"]:
            assert (ROOT / "src/busemann/resources/licenses" / f).stat().st_size > 1000, f
    assert "Bootloader Exception" in (ROOT / "src/busemann/resources/licenses/"
                                      "PyInstaller-COPYING.txt").read_text(encoding="utf-8")
    assert "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2" in (ROOT / "src/busemann/resources/licenses/"
                                       "Python-LICENSE.txt").read_text(encoding="utf-8")


def test_licence_is_mit_with_the_copyright_line():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n\nCopyright (c) 2026 Pablo Goulet Valenti\n")
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in text


# --- build script ------------------------------------------------------------------------------
def test_build_script_is_ascii_for_windows_powershell():
    PS1.encode("ascii")                       # PowerShell 5.1 reads BOM-less files as ANSI


def test_build_script_finds_iscc_in_the_agreed_order():
    """-Iscc, then PATH, then Program Files (x86), then %LOCALAPPDATA% (per-user install)."""
    find = PS1[PS1.index("function Find-Iscc"):]
    find = find[:find.index("\n}\n")]
    order = [find.index(s) for s in (
        "if ($Explicit)",
        'Get-Command "ISCC.exe"',
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r'Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"')]
    assert order == sorted(order)


def test_build_script_has_no_personal_paths():
    assert not re.search(r"[A-Z]:\\Users\\", PS1, re.I)
    assert "Usuario" not in PS1


def test_build_script_self_test_rules():
    assert "[int]$SelfTestTimeout = 120" in PS1
    assert '[string]$SelfTestLog = ""' in PS1
    assert r'Join-Path $Root "build\selftest.log"' in PS1            # kept for the artifact
    assert "no log written $EmDash the exe crashed" in PS1
    assert "--self-test --self-test-log" in PS1
    assert '$code -eq 0' in PS1 and 'Contains("self-test: OK")' in PS1
    assert "the exe crashed before the self-test started" in PS1
    assert 'throw "frozen self-test failed"' in PS1


def test_build_script_outputs():
    for piece in ("Busemann-Setup-$Version.exe", "Busemann-$Version-portable.zip",
                  "SHA256SUMS.txt", "THIRD-PARTY-NOTICES.txt", '"/DAppVersion=$Version"',
                  r'build\venv', '".[app]", "pyinstaller"', "PySide6-Addons"):
        assert piece in PS1, piece


def test_build_and_dist_are_ignored():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "build/" in lines and "dist/" in lines
