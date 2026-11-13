; Inno Setup 6 script: Busemann installer (M12 PART 4).
;
;     ISCC.exe /DAppVersion=1.0.0 packaging\busemann.iss
;
; Input: the one-folder build in dist\Busemann (tools\build_release.ps1 makes it, with
; LICENSE and THIRD-PARTY-NOTICES.txt at its root). Output: dist\Busemann-Setup-<version>.exe.
; Per-user install by default (no admin) to {localappdata}\Programs\Busemann; the first page
; offers an all-users install (Program Files, needs admin). No file associations: Busemann
; does not take over .dxf. The version comes from busemann.__version__ via /DAppVersion.

#ifndef AppVersion
  #error AppVersion is not defined: run ISCC with /DAppVersion=<busemann.__version__>
#endif

#define AppName "Busemann"
#define AppPublisher "Pablo Goulet Valenti"
#define AppExe "Busemann.exe"
; must equal busemann.app.APP_USER_MODEL_ID (tests/test_packaging.py): a pinned shortcut then
; groups with the running app on the taskbar instead of showing a second icon
#define AppUserModelID "PabloGouletValenti.Busemann"

[Setup]
; fixed for every release: identifies the installed app for upgrades and uninstall
AppId={{67786B54-1C47-43B9-8C2E-720A6927FD91}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/Eski4239/Busemann
AppSupportURL=https://github.com/Eski4239/Busemann/issues
AppUpdatesURL=https://github.com/Eski4239/Busemann/releases
AppCopyright=Copyright (c) 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
; per-user by default; the dialog offers "install for all users"
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; {autopf} is {localappdata}\Programs for a per-user install, Program Files for all users
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupIconFile=..\src\busemann\resources\brand\busemann.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
OutputDir=..\dist
OutputBaseFilename=Busemann-Setup-{#AppVersion}
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Busemann\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
