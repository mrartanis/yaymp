#define MyAppName "YAYMP"
#define MyAppPublisher "yaymp"
#define MyAppId "yaymp.YAYMP"

#ifndef MyAppVersion
  #error MyAppVersion is required
#endif
#ifndef MyReleaseTag
  #error MyReleaseTag is required
#endif
#ifndef MySourceDir
  #error MySourceDir is required
#endif
#ifndef MyOutputDir
  #error MyOutputDir is required
#endif
#ifndef MySetupIconFile
  #error MySetupIconFile is required
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/mrartanis/yaymp
AppSupportURL=https://github.com/mrartanis/yaymp/issues
AppUpdatesURL=https://github.com/mrartanis/yaymp/releases
DefaultDirName={localappdata}\Programs\YAYMP
DefaultGroupName=YAYMP
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\YaYmp.exe
SetupIconFile={#MySetupIconFile}
OutputDir={#MyOutputDir}
OutputBaseFilename=YAYMP-{#MyReleaseTag}-windows-x86_64-setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\YAYMP"; Filename: "{app}\YaYmp.exe"; WorkingDir: "{app}"; IconFilename: "{app}\YaYmp.exe"
Name: "{autodesktop}\YAYMP"; Filename: "{app}\YaYmp.exe"; WorkingDir: "{app}"; IconFilename: "{app}\YaYmp.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\YaYmp.exe"; Description: "Launch YAYMP"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\yaymp\YAYMP"
