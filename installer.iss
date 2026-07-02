; Script Inno Setup pour IntermitDoc
; Compiler : "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; Prérequis : avoir généré dist\IntermitDoc\ via PyInstaller au préalable.

#define MyAppName "IntermitDoc"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "IntermitDoc"
#define MyAppURL "https://github.com/ethilbalde/IntermitDoc"
#define MyAppExeName "IntermitDoc.exe"

[Setup]
AppId={{6F8C8B2E-3E7A-4C5B-9D1F-7A2E4B9C1D3A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Pas besoin de droits admin : installation dans AppData\Local par défaut si l'utilisateur préfère,
; mais Program Files reste l'usage standard — on autorise le choix.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=IntermitDoc-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=
SetupLogging=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\IntermitDoc\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ne supprime PAS %APPDATA%\IntermitDoc (données utilisateur : clés API, employeurs,
; contrats, prévisionnels) — l'utilisateur les retrouve intactes en cas de réinstallation.
