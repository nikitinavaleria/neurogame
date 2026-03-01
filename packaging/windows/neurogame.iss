[Setup]
AppName=NeuroGame
AppVersion=1.0.0
DefaultDirName={autopf}\NeuroGame
DefaultGroupName=NeuroGame
OutputDir=..\..\dist
OutputBaseFilename=NeuroGameSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\NeuroGame\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NeuroGame"; Filename: "{app}\NeuroGame.exe"
Name: "{autodesktop}\NeuroGame"; Filename: "{app}\NeuroGame.exe"

[Run]
Filename: "{app}\NeuroGame.exe"; Description: "Launch NeuroGame"; Flags: nowait postinstall skipifsilent
