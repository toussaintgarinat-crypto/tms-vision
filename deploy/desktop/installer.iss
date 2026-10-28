; Installateur Windows (Inno Setup), fabriqué par .github/workflows/desktop.yml :
;   iscc /DAppVersion=1.0.0 deploy\desktop\installer.iss
; Installation « pour l'utilisateur » (sans droits administrateur), dans %LOCALAPPDATA%\Programs.
; Les données (analyses, vidéos) sont dans %APPDATA%\TMS Vision : une mise à jour ou une
; désinstallation n'y touche pas.
; La mise à jour en un clic de l'application lance cet installateur en mode silencieux
; (/SILENT) : l'application doit donc se relancer toute seule à la fin (pas de skipifsilent).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E2D6F0A-5B1C-4E55-9C0B-7F3A2D1E8B41}
AppName=TMS Vision
AppVersion={#AppVersion}
AppPublisher=TMS Vision
DefaultDirName={localappdata}\Programs\TMS Vision
DefaultGroupName=TMS Vision
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=TMS-Vision-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\TMS Vision.exe

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\..\dist\TMS Vision\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\TMS Vision"; Filename: "{app}\TMS Vision.exe"
Name: "{autodesktop}\TMS Vision"; Filename: "{app}\TMS Vision.exe"

[Run]
Filename: "{app}\TMS Vision.exe"; Description: "Lancer TMS Vision"; Flags: nowait postinstall
