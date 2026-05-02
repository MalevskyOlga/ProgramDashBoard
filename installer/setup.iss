; ============================================================
;  Overall Programs Dashboard — Inno Setup script
;  Build:  iscc setup.iss   (from the installer\ folder)
;  Output: installer\Output\OverallDashboardSetup_x.y.z.exe
; ============================================================

#define AppName        "Overall Programs Dashboard"
#define AppVersion     "1.1.0"
#define AppPublisher   "Emerson"
#define ServiceName    "OverallDashboard"
#define DefaultPort    "8092"
#define AppDir         "{autopf}\OverallDashboard"
#define DataDir        "{commonappdata}\OverallDashboard"
#define SrcRoot        ".."    ; root of the repo relative to installer\

[Setup]
AppId               = {{A3F2C1D0-9B4E-4F7A-8C3D-1E2F5A6B7C8D}
AppName             = {#AppName}
AppVersion          = {#AppVersion}
AppPublisher        = {#AppPublisher}
AppPublisherURL     = http://localhost:{#DefaultPort}
DefaultDirName      = {#AppDir}
DefaultGroupName    = {#AppName}
DisableProgramGroupPage = yes
OutputDir           = Output
OutputBaseFilename  = OverallDashboardSetup_{#AppVersion}
Compression         = lzma2/ultra64
SolidCompression    = yes
PrivilegesRequired  = admin
ArchitecturesInstallIn64BitMode = x64compatible
; Keep data dir on uninstall — never delete C:\ProgramData\OverallDashboard
UninstallFilesDir   = {app}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Custom wizard page variables ──────────────────────────────────────────────
[Code]
var
  PortPage:   TInputQueryWizardPage;
  DbPage:     TInputOptionWizardPage;
  PortNumber: String;
  DbExists:   Boolean;

procedure InitializeWizard;
begin
  PortPage := CreateInputQueryPage(
    wpSelectDir,
    'Network Port',
    'Choose the port the dashboard will listen on.',
    '');
  PortPage.Add('Port number (users will access http://server-name:<port>):', False);
  PortPage.Values[0] := '{#DefaultPort}';

  DbExists := FileExists(ExpandConstant('{commonappdata}\OverallDashboard\dashboards.db'));
  DbPage := CreateInputOptionPage(
    PortPage.ID,
    'Database',
    'An existing database was found on this machine.',
    'How would you like to handle the database?',
    True, False);
  DbPage.Add('Keep production database — preserve live data (schema migrations applied automatically)');
  DbPage.Add('Replace with bundled database — start fresh (timestamped backup created first)');
  DbPage.Values[0] := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = DbPage.ID then
    Result := not DbExists;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  p: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then begin
    p := StrToIntDef(PortPage.Values[0], 0);
    if (p < 1024) or (p > 65535) then begin
      MsgBox('Please enter a valid port number between 1024 and 65535.', mbError, MB_OK);
      Result := False;
    end else
      PortNumber := PortPage.Values[0];
  end;
end;

function GetPort(Param: String): String;
begin
  Result := PortNumber;
  if Result = '' then Result := '{#DefaultPort}';
end;

function GetDbAction(Param: String): String;
begin
  if not DbExists then begin
    Result := 'replace';
    Exit;
  end;
  if DbPage.Values[1] then
    Result := 'replace'
  else
    Result := 'keep';
end;

procedure RunPowerShell(Script: String; Args: String);
var
  Cmd, Params, LogFile: String;
  ResultCode: Integer;
begin
  LogFile := ExpandConstant('{commonappdata}\OverallDashboard\logs\install-ps.log');
  // Use cmd /c to redirect stdout+stderr so we always get a log even if PS crashes early
  Cmd    := ExpandConstant('{sys}\cmd.exe');
  Params := '/c "md "' + ExpandConstant('{commonappdata}\OverallDashboard\logs') + '" 2>nul & ' +
            'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + Script + '" ' + Args +
            ' >> "' + LogFile + '" 2>&1"';
  if not Exec(Cmd, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    MsgBox('cmd.exe could not be launched. Exit code: ' + IntToStr(ResultCode), mbError, MB_OK);
  if ResultCode <> 0 then
    MsgBox('Post-install step failed (exit ' + IntToStr(ResultCode) + '). ' +
           'Check log: ' + LogFile, mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Args: String;
begin
  if CurStep = ssPostInstall then begin
    Args := '-InstallDir "' + ExpandConstant('{app}') + '"' +
            ' -DataDir "'    + ExpandConstant('{commonappdata}\OverallDashboard') + '"' +
            ' -Port '        + GetPort('') +
            ' -ServiceName ' + '{#ServiceName}' +
            ' -DbAction '    + GetDbAction('');
    RunPowerShell(ExpandConstant('{app}\installer\post_install.ps1'), Args);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Args: String;
begin
  if CurUninstallStep = usUninstall then begin
    Args := '-ServiceName {#ServiceName} -Port ' + GetPort('');
    RunPowerShell(ExpandConstant('{app}\installer\pre_uninstall.ps1'), Args);
  end;
end;

// ── End of [Code] section ──

[Files]
; Application source
Source: "{#SrcRoot}\server.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\config.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\database_manager.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\excel_parser.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\excel_exporter.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\ppt_exporter.py";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\risk_ppt_exporter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\gantt_ppt_exporter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\db_migrate.py";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\aggregate_server.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\aggregate_app.py";     DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\aggregate_db.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\aggregate_repository.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\aggregate_config.py";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\requirements.txt";     DestDir: "{app}"; Flags: ignoreversion

; Templates & static assets
Source: "{#SrcRoot}\templates\*";          DestDir: "{app}\templates";           Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcRoot}\aggregate_templates\*"; DestDir: "{app}\aggregate_templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcRoot}\aggregate_frontend\*"; DestDir: "{app}\aggregate_frontend";  Flags: ignoreversion recursesubdirs createallsubdirs

; Migration scripts
Source: "{#SrcRoot}\migrations\*";         DestDir: "{app}\migrations";          Flags: ignoreversion recursesubdirs createallsubdirs

; Bundled Python installer (run silently during post-install to create local venv)
Source: "python-installer.exe";            DestDir: "{app}\installer";           Flags: ignoreversion

; WinSW service wrapper (bundled — no external dependency)
Source: "nssm\WinSW.exe";                  DestDir: "{app}\nssm";                Flags: ignoreversion

; Installer helper scripts
Source: "post_install.ps1";                DestDir: "{app}\installer";           Flags: ignoreversion
Source: "pre_uninstall.ps1";               DestDir: "{app}\installer";           Flags: ignoreversion
Source: "backup_db.ps1";                   DestDir: "{app}\installer";           Flags: ignoreversion

; Offline pip wheels — allows install on intranet servers with no internet
Source: "wheels\*";                        DestDir: "{app}\installer\wheels";    Flags: ignoreversion recursesubdirs

; Bundled database — staged to installer folder; post_install.ps1 decides whether to deploy it
Source: "{#SrcRoot}\database\dashboards.db"; DestDir: "{app}\installer"; DestName: "dashboards_bundled.db"; Flags: ignoreversion

; ── Start Menu shortcut ───────────────────────────────────────────────────────
[Icons]
Name: "{group}\Open Dashboard";     Filename: "{app}\open_dashboard.bat"
Name: "{group}\Stop Service";       Filename: "{app}\installer\pre_uninstall.ps1"
Name: "{group}\Uninstall";          Filename: "{uninstallexe}"

; ── Create a one-click "open in browser" batch file ──────────────────────────
[INI]
; Nothing here — browser launcher written in [Run] below

[Run]
; Open browser after install (optional, skippable by user)
Filename: "http://localhost:{code:GetPort}"; \
  Description: "Open dashboard in browser now"; \
  Flags: postinstall shellexec skipifsilent unchecked

; ── Ensure exports folder exists in data dir (created by config.py too, belt+braces)
[Dirs]
Name: "{commonappdata}\OverallDashboard"
Name: "{commonappdata}\OverallDashboard\exports"
Name: "{commonappdata}\OverallDashboard\logs"
