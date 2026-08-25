; Script Inno Setup pour IntermitDoc
; Compiler : "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; Prérequis :
;   1. Avoir généré dist\IntermitDoc\ via PyInstaller au préalable.
;   2. Avoir récupéré l'installeur Tesseract OCR (non versionné, trop lourd) :
;      powershell -File installer_assets\telecharger_tesseract.ps1

#define MyAppName "IntermitDoc"
#define MyAppVersion "1.4.0"
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
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=
SetupLogging=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "installtesseract"; Description: "Installer Tesseract OCR (recommandé — nécessaire uniquement pour analyser des PDF scannés / images)"; Check: not TesseractDejaInstalle

[Files]
Source: "dist\IntermitDoc\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "installer_assets\tesseract-ocr-w64-setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Tasks: installtesseract

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\tesseract-ocr-w64-setup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; StatusMsg: "Installation de Tesseract OCR..."; Tasks: installtesseract; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ne supprime PAS %APPDATA%\IntermitDoc (données utilisateur : clés API, employeurs,
; contrats, prévisionnels) — l'utilisateur les retrouve intactes en cas de réinstallation.
; Ne désinstalle pas non plus Tesseract OCR (programme tiers indépendant, peut être
; utilisé par d'autres logiciels).

[Code]
function TesseractDejaInstalle(): Boolean;
begin
  Result := FileExists(ExpandConstant('{pf}\Tesseract-OCR\tesseract.exe'))
         or FileExists(ExpandConstant('{pf32}\Tesseract-OCR\tesseract.exe'));
end;
