#define MyAppName "Productivity Timer"
#define MyAppExeName "ProductivityTimer.exe"
#define MyAppVersion GetFileVersion("..\dist\ProductivityTimer.exe")

[Setup]
AppId={{77E48FDA-70E8-4CA0-AD24-7367F767F324}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Productivity Timer
AppPublisherURL=https://github.com/chieaid24/break-timer-app
AppSupportURL=https://github.com/chieaid24/break-timer-app/issues
AppUpdatesURL=https://github.com/chieaid24/break-timer-app/releases
DefaultDirName={localappdata}\Programs\ProductivityTimer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=ProductivityTimer-Setup
SetupIconFile=..\.build-assets\ProductivityTimer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ProductivityTimer"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start {#MyAppName}"; Flags: nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\ProductivityTimer"

[Code]
procedure StopRunningApp();
var
  ResultCode: Integer;
begin
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /IM ProductivityTimer.exe',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopRunningApp();
end;
