; VideoCheck.iss — Inno Setup script.
;
; This is what turns "a compiled Python exe" into a real Windows installer:
; Welcome screen -> progress -> Finish screen with a "Launch VideoCheck now"
; checkbox, a Start Menu entry, an optional Desktop icon, and a proper
; uninstaller that shows up in "Add or Remove Programs".
;
; ONE-TIME PREREQUISITE (on the machine that BUILDS the installer):
;   Install Inno Setup — free, ~5MB — from https://jrsoftware.org/isdl.php
;
; BUILD:
;   1. First run build_windows.bat — it builds dist\VideoCheckInstallerCore.exe
;      (the actual Python/dependency installer, with its own progress window).
;   2. Then either:
;        - Open this file in the Inno Setup Compiler and click "Compile", or
;        - From a terminal: iscc VideoCheck.iss
;      (build_windows.bat does step 2 automatically if it finds iscc.exe on PATH.)
;
; OUTPUT: installer\dist\VideoCheck-Setup.exe — this is the single file you
; give to end users. Double-click, Next, Next, Finish. Nothing else needed.

#define MyAppName "VideoCheck"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "Nincha"
#define CoreExeName "VideoCheckInstallerCore.exe"

[Setup]
AppId={{4F1B9B2E-6B7A-4C9E-9E19-3A0C7F2B7E10}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Per-user install under AppData\Local — no admin rights required, which
; matters for "usuario normal que no sabe nada de sistemas": no UAC prompt.
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=VideoCheck-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
; Once you have an icon file, uncomment these two lines:
; SetupIconFile=videocheck.ico
; UninstallDisplayIcon={app}\videocheck.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The real work (find/install Python, venv, hardware detection, pip
; install) is delegated to this exe, built separately by build_windows.bat.
; It's extracted to a temp folder and run once during setup — see [Run].
Source: "dist\{#CoreExeName}"; DestDir: "{tmp}"; Flags: dontcopy

[Run]
; Step 1 (during install): run the core installer against Inno's chosen
; {app} folder. --no-shortcut because Inno's own [Icons] section below
; already creates a proper Start Menu / Desktop shortcut.
Filename: "{tmp}\{#CoreExeName}"; \
    Parameters: "--install-dir ""{app}"" --no-shortcut"; \
    StatusMsg: "Instalando VideoCheck y sus dependencias..."; \
    Flags: waituntilterminated

; Step 2 (Finish page): standard "Launch the app now" checkbox.
Filename: "{app}\run_videocheck.bat"; \
    Description: "Abrir {#MyAppName} ahora"; \
    Flags: postinstall skipifsilent nowait shellexec

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\run_videocheck.bat"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\run_videocheck.bat"; \
    WorkingDir: "{app}"; Tasks: desktopicon

[UninstallDelete]
; run_install() puts the venv, downloaded model, and everything else under
; {app} — deleting that folder on uninstall is a complete, clean removal.
Type: filesandordirs; Name: "{app}"
