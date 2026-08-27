#define AppVersion GetEnv("APP_VERSION")

[Setup]
AppName=Clip2Anim
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
DefaultDirName={localappdata}\Clip2Anim
OutputDir=Output
OutputBaseFilename=Clip2AnimSetup
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Files]
Source: "clip2anim.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffmpeg\bin\ffmpeg.exe"; DestDir: "{app}\ffmpeg"
Source: "ffmpeg\LICENSE"; DestDir: "{app}\ffmpeg"

[Registry]
Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim"; \
    ValueType: string; ValueData: "Clip2Animで開く"; \
    Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim"; \
    ValueName: "Icon"; ValueType: string; ValueData: "{app}\clip2anim.exe"
    
Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim"; \
    ValueName: "AppliesTo"; ValueType: string; \
    ValueData: "System.Kind:=video"

Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim\command"; \
    ValueType: string; \
    ValueData: """{app}\clip2anim.exe"" ""%1"""

[UninstallDelete]
Type: files; Name: "{app}\config.json"

[Code]

function TestEncoder(Encoder: String): Boolean;
var
  ResultCode: Integer;
  Params: String;
begin
  Params :=
    '-hide_banner ' +
    '-loglevel error ' +
    '-f lavfi ' +
    '-i testsrc2=size=256x256:rate=30 ' +
    '-t 1 ' +
    '-c:v ' + Encoder + ' ' +
    '-f null -';

  Result :=
    Exec(
      ExpandConstant('{app}\ffmpeg\ffmpeg.exe'),
      Params,
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    )
    and (ResultCode = 0);
end;


function DetectEncoder(): String;
begin
  if TestEncoder('av1_nvenc') then
    Result := 'av1_nvenc'
  else if TestEncoder('av1_qsv') then
    Result := 'av1_qsv'
  else if TestEncoder('av1_amf') then
    Result := 'av1_amf'
  else 
    Result := 'libaom-av1';
end;


procedure WriteConfigJson();
var
  Encoder: String;
  Json: String;
begin
  Encoder := DetectEncoder();

  Json :=
    '{' + #13#10 +
    '  "av1_codec": "' + Encoder + '"' + #13#10 +
    '}';

  SaveStringToFile(
    ExpandConstant('{app}\config.json'),
    Json,
    False
  );
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption :=
      '利用可能なAV1エンコーダーを確認しています...';

    WizardForm.ProgressGauge.Style := npbstMarquee;
    WriteConfigJson();
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
end;
