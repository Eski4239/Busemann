<#
.SYNOPSIS
  Build the Busemann Windows release (M12 PART 4): one-folder PyInstaller build, frozen
  self-test, Inno Setup installer, portable zip, SHA256SUMS.txt.

.DESCRIPTION
  From the repository root (any current folder works):
    1. clean build\venv, build\pyinstaller and the previous dist\ outputs;
    2. a clean venv in build\venv: pip install -r packaging\requirements-build.txt (exact
       versions: PySide6-Essentials only, PyInstaller), then pip install --no-deps .;
    3. pyinstaller packaging\busemann.spec -> dist\Busemann\ (+ LICENSE, THIRD-PARTY-NOTICES.txt);
    4. dist\Busemann\Busemann.exe --self-test --self-test-log <SelfTestLog>: the build fails unless
       the exe exits 0 within the timeout AND the log exists AND contains "self-test: OK";
    5. start-up time to the welcome window (informational, isolated settings);
    6. ISCC packaging\busemann.iss -> dist\Busemann-Setup-<version>.exe;
    7. dist\Busemann-<version>-portable.zip and dist\SHA256SUMS.txt; sizes printed.
  Works in Windows PowerShell 5.1 and PowerShell 7. This file is ASCII only on purpose.

.PARAMETER Python
  Interpreter used to create the build venv (default: python on PATH).
.PARAMETER Iscc
  ISCC.exe to use; default: ISCC.exe on PATH, then Program Files (x86)\Inno Setup 6, then
  %LOCALAPPDATA%\Programs\Inno Setup 6 (a per-user Inno Setup install).
.PARAMETER SkipInstaller
  Build, self-test and zip, without the Inno Setup step.
.PARAMETER SelfTestTimeout
  Seconds the frozen self-test may take (default 120; the release workflow passes 300).
.PARAMETER SelfTestLog
  Where the frozen self-test writes its log (default build\selftest.log). It is kept after the
  build; when the exe writes none, this file says so (the release workflow uploads it).
#>
param(
    [string]$Python = "python",
    [string]$Iscc = "",
    [switch]$SkipInstaller,
    [int]$SelfTestTimeout = 120,
    [string]$SelfTestLog = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$EmDash = [string][char]0x2014

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Invoke-Native {
    # run a native command; stop the build on a non-zero exit code
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

function Get-FolderBytes($path) {
    (Get-ChildItem -LiteralPath $path -Recurse -File | Measure-Object -Property Length -Sum).Sum
}

function Format-MB($bytes) { "{0:N1} MB" -f ($bytes / 1MB) }

function Stop-Tree($id) {
    # kill a process and its children (the equation render process); output discarded, no
    # stderr redirection (a redirected native stderr line is fatal in Windows PowerShell 5.1)
    Start-Process -FilePath "taskkill.exe" -ArgumentList "/PID $id /T /F" -NoNewWindow -Wait `
        -RedirectStandardOutput ([System.IO.Path]::GetTempFileName()) `
        -RedirectStandardError ([System.IO.Path]::GetTempFileName()) | Out-Null
}

function Find-Iscc {
    param([string]$Explicit)
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    $onPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    $candidates += "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe") }
    foreach ($c in $candidates) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }
    return $null
}

# --- version (busemann.__version__ is the single source) -------------------------------------
$init = Get-Content -Raw -LiteralPath (Join-Path $Root "src\busemann\__init__.py")
if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { throw "no __version__ in src\busemann\__init__.py" }
$Version = $Matches[1]
Write-Host "Busemann $Version release build"

$Dist = Join-Path $Root "dist"
$App = Join-Path $Dist "Busemann"
$Exe = Join-Path $App "Busemann.exe"
$Venv = Join-Path $Root "build\venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
$Setup = Join-Path $Dist "Busemann-Setup-$Version.exe"
$Zip = Join-Path $Dist "Busemann-$Version-portable.zip"
$Sums = Join-Path $Dist "SHA256SUMS.txt"
if (-not $SelfTestLog) { $SelfTestLog = Join-Path $Root "build\selftest.log" }
$SelfTestLog = [System.IO.Path]::GetFullPath($SelfTestLog)

# find ISCC before the long build, so a missing Inno Setup fails at once
$IsccExe = $null
if (-not $SkipInstaller) {
    $IsccExe = Find-Iscc $Iscc
    if (-not $IsccExe) {
        throw ("ISCC.exe (Inno Setup 6) not found: pass -Iscc <path>, add it to PATH or install " +
               "it (winget install JRSoftware.InnoSetup / choco install innosetup); " +
               "-SkipInstaller builds without the installer")
    }
    Write-Host "Inno Setup: $IsccExe"
}

# --- 1. clean ------------------------------------------------------------------------------
Step "Cleaning build\venv, build\pyinstaller and dist outputs"
foreach ($p in @($Venv, (Join-Path $Root "build\pyinstaller"), $App, $Setup, $Zip, $Sums)) {
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

# --- 2. clean venv -------------------------------------------------------------------------
Step "Creating build\venv with $Python"
Invoke-Native $Python @("-m", "venv", $Venv)
Invoke-Native $VPy @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
# pinned: the exact versions of the build whose frozen self-test passed
Invoke-Native $VPy @("-m", "pip", "install", "--quiet", "-r", "packaging\requirements-build.txt")
Invoke-Native $VPy @("-m", "pip", "install", "--quiet", "--no-deps", ".")
# (checked in Python: in PowerShell 5.1 a redirected native stderr line is a terminating error)
Invoke-Native $VPy @("-c", "import importlib.util as u, sys; sys.exit('PySide6-Addons is installed in the build venv (PySide6-Essentials only)' if u.find_spec('PySide6.QtWebEngineCore') or u.find_spec('PySide6.Qt3DCore') else 0)")
Invoke-Native $VPy @("-c", "import sys, PySide6, PyInstaller; print('Python', sys.version.split()[0], '| PySide6', PySide6.__version__, '| PyInstaller', PyInstaller.__version__)")

# --- 3. PyInstaller ------------------------------------------------------------------------
Step "PyInstaller (one-folder, windowed)"
Invoke-Native $VPy @("-m", "PyInstaller", "packaging\busemann.spec", "--noconfirm", "--clean",
                     "--distpath", $Dist, "--workpath", (Join-Path $Root "build\pyinstaller"))
if (-not (Test-Path -LiteralPath $Exe)) { throw "PyInstaller did not produce $Exe" }
Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination $App
Invoke-Native $VPy @("tools\make_notices.py", (Join-Path $App "THIRD-PARTY-NOTICES.txt"))

# --- 4. frozen self-test -------------------------------------------------------------------
Step "Self-test of the frozen exe (timeout $SelfTestTimeout s)"
$log = $SelfTestLog
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null
$info = New-Object System.Diagnostics.ProcessStartInfo
$info.FileName = $Exe
$info.Arguments = "--self-test --self-test-log `"$log`""
$info.UseShellExecute = $false
$info.WorkingDirectory = $App
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$proc = [System.Diagnostics.Process]::Start($info)
$finished = $proc.WaitForExit($SelfTestTimeout * 1000)
$timer.Stop()
if (-not $finished) {
    Stop-Tree $proc.Id
    $code = "timeout"
} else {
    $proc.WaitForExit()
    $code = $proc.ExitCode
}
$logText = if (Test-Path -LiteralPath $log) { Get-Content -Raw -LiteralPath $log -Encoding UTF8 } else { $null }
$passed = ($finished -and $code -eq 0 -and $logText -and $logText.Contains("self-test: OK"))
$status = "exit code: $code, after $([int]$timer.Elapsed.TotalSeconds) s (timeout $SelfTestTimeout s)"
if (-not $passed) {
    Write-Host "Self-test FAILED ($status)" -ForegroundColor Red
    if ($logText) {
        Write-Host $logText
        Add-Content -LiteralPath $log -Value "build_release.ps1: FAILED ($status)" -Encoding UTF8
    } else {
        $missing = "no log written $EmDash the exe crashed before the self-test started"
        Write-Host $missing
        # the uploaded artifact still says what happened
        [System.IO.File]::WriteAllText($log, "$missing`nbuild_release.ps1: FAILED ($status)`n",
                                       (New-Object System.Text.UTF8Encoding($false)))
    }
    throw "frozen self-test failed"
}
$SelfTestLine = ($logText -split "`r?`n")[0]
Write-Host $SelfTestLine -ForegroundColor Green
Write-Host ("  (process wall time {0:N1} s; log kept at {1})" -f $timer.Elapsed.TotalSeconds, $log)
Add-Content -LiteralPath $log -Value "build_release.ps1: passed ($status)" -Encoding UTF8

# --- 5. start-up time to the welcome window (informational) --------------------------------
Step "Start-up time to the welcome window"
$StartupText = "not measured"
$settings = Join-Path ([System.IO.Path]::GetTempPath()) ("busemann-startup-" + [guid]::NewGuid().ToString("N") + ".ini")
$info = New-Object System.Diagnostics.ProcessStartInfo
$info.FileName = $Exe
$info.UseShellExecute = $false
$info.EnvironmentVariables["BUSEMANN_SETTINGS_FILE"] = $settings   # never the user's settings
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$proc = [System.Diagnostics.Process]::Start($info)
while ($timer.Elapsed.TotalSeconds -lt 60 -and -not $proc.HasExited) {
    $proc.Refresh()
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero -and $proc.MainWindowTitle -eq "Busemann") { break }
    Start-Sleep -Milliseconds 50
}
$timer.Stop()
if (-not $proc.HasExited -and $proc.MainWindowHandle -ne [IntPtr]::Zero) {
    $StartupText = "{0:N1} s" -f $timer.Elapsed.TotalSeconds
} else {
    Write-Warning "no welcome window within 60 s (headless session?)"
}
if (-not $proc.HasExited) { Stop-Tree $proc.Id }
if (Test-Path -LiteralPath $settings) { Remove-Item -LiteralPath $settings -Force }
Write-Host "Welcome window after $StartupText"

# --- 6. installer --------------------------------------------------------------------------
if (-not $SkipInstaller) {
    Step "Inno Setup installer"
    Invoke-Native $IsccExe @("/Qp", "/DAppVersion=$Version", "packaging\busemann.iss")
    if (-not (Test-Path -LiteralPath $Setup)) { throw "ISCC did not produce $Setup" }
}

# --- 7. portable zip, checksums, sizes -----------------------------------------------------
Step "Portable zip and SHA256SUMS.txt"
Invoke-Native $VPy @("-c", "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], 'Busemann')",
                     ($Zip -replace '\.zip$', ''), $Dist)
$lines = @()
foreach ($f in @($Setup, $Zip)) {
    if (Test-Path -LiteralPath $f) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant()
        $lines += "$hash  $(Split-Path -Leaf $f)"
    }
}
[System.IO.File]::WriteAllText($Sums, (($lines -join "`n") + "`n"))
Get-Content -LiteralPath $Sums

Step "Summary"
Write-Host ("Installed size (dist\Busemann): " + (Format-MB (Get-FolderBytes $App)))
Write-Host ("Portable zip:                  " + (Format-MB (Get-Item -LiteralPath $Zip).Length) + "  $(Split-Path -Leaf $Zip)")
if (Test-Path -LiteralPath $Setup) {
    Write-Host ("Installer:                     " + (Format-MB (Get-Item -LiteralPath $Setup).Length) + "  $(Split-Path -Leaf $Setup)")
}
Write-Host "Start-up to welcome window:    $StartupText"
Write-Host "Self-test:                     $SelfTestLine"
