; Seraphine Windows installer — Inno Setup 6
; Build: ISCC.exe Seraphine.iss /DMyAppVersion=1.2.0

#define MyAppName "Seraphine"
#define MyAppPublisher "Li-Qifeng"
#define MyAppURL "https://github.com/Li-Qifeng/Seraphine"
#define MyAppIcon "..\..\app\resource\images\logo.ico"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
SetupIconFile={#MyAppIcon}
OutputDir=.
OutputBaseFilename=SeraphineSetup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayIcon={app}\Seraphine.exe
PrivilegesRequired=lowest

[Files]
Source: "..\..\dist\Seraphine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\Seraphine.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Seraphine.exe"

[Run]
Filename: "{app}\Seraphine.exe"; Description: "Launch Seraphine"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; remove tufup cached targets so fresh install doesn't mix old caches with new binary
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{localappdata}\{#MyAppName}\tufup_targets"""; Flags: runhidden

[InstallDelete]
; cleanup any leftover from old 7z portable extract
Type: filesandordirs; Name: "{app}\tufup_targets"
Type: filesandordirs; Name: "{app}\tufup_extract"
