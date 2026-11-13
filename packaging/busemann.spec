# PyInstaller spec: one-folder, windowed Windows build of Busemann (M12 PART 4).
#
#     pyinstaller packaging/busemann.spec --distpath dist --workpath build/pyinstaller
#
# Run from the repository root in an environment with `pip install ".[app]" pyinstaller`
# (PySide6-Essentials only). tools/build_release.ps1 does that in a clean venv.
#
# - datas: the whole src/busemann/resources tree and the QSS template; matplotlib's own
#   data (mathtext fonts) comes from PyInstaller's matplotlib hook; package metadata for the
#   About dialog's licence list (importlib.metadata) is copied explicitly.
# - Qt: only QtCore, QtGui, QtWidgets, QtSvg are imported, so only those (plus the plugins
#   they need) are collected; the Addons modules are excluded by name as a guard.
# - The spawn-based equation warm-up process re-launches this exe; busemann_entry.py calls
#   multiprocessing.freeze_support() first (busemann --self-test proves it works).
# - Version resource from busemann.__version__ (single source).
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parent            # noqa: F821 - defined by PyInstaller
SRC = ROOT / "src"
PKG = SRC / "busemann"
sys.path.insert(0, str(SRC))

VERSION = re.search(r'__version__\s*=\s*"([^"]+)"',
                    (PKG / "__init__.py").read_text(encoding="utf-8")).group(1)
NUMS = tuple(int(x) for x in VERSION.split(".")) + (0,)
COMPANY = "Pablo Goulet Valenti"
PRODUCT = "Busemann"

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS, mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", COMPANY),
            StringStruct("FileDescription", "Busemann - supersonic inlet design"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", PRODUCT),
            StringStruct("LegalCopyright", f"Copyright (c) 2026 {COMPANY}. MIT License."),
            StringStruct("OriginalFilename", "Busemann.exe"),
            StringStruct("ProductName", PRODUCT),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

datas = [
    (str(PKG / "resources"), "busemann/resources"),
    (str(PKG / "theme" / "style.qss.tmpl"), "busemann/theme"),
]                     # LICENSE and THIRD-PARTY-NOTICES.txt: install root (build_release.ps1)
for dist in ("PySide6-Essentials", "shiboken6", "pyqtgraph", "numpy", "scipy", "matplotlib",
             "ezdxf", "supersonic-inlet-designer"):
    datas += copy_metadata(dist)

EXCLUDES = [
    # Qt Addons and other bindings (PySide6-Essentials only)
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtQuickControls2",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTextToSpeech",
    "PyQt5", "PyQt6", "PySide2",
    # not used by the app
    "tkinter", "_tkinter", "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_qt",
    "pyqtgraph.examples", "pyqtgraph.opengl", "OpenGL",
    "IPython", "jupyter_client", "ipykernel", "notebook",
    "pytest", "pytestqt", "_pytest", "tests", "setuptools", "pip",
]

a = Analysis(                                      # noqa: F821
    [str(Path(SPECPATH) / "busemann_entry.py")],  # noqa: F821
    pathex=[str(SRC)],
    datas=datas,
    # matplotlib picks backends by name at run time: mathtext.math_to_image(format="svg")
    # in the equation render process needs backend_svg (found by the frozen self-test)
    hiddenimports=["busemann.selftest", "busemann.screenshots",
                   "matplotlib.backends.backend_svg",
                   "matplotlib.backends.backend_agg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)                                  # noqa: F821

exe = EXE(                                         # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Busemann",
    console=False,
    icon=str(PKG / "resources" / "brand" / "busemann.ico"),
    version=version_info,
    upx=False,
)
coll = COLLECT(                                    # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="Busemann",
    upx=False,
)
