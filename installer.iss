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
; 右クリックメニューを追加
Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim"; \
    ValueType: string; ValueData: "Clip2Animで開く"

Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim"; \
    ValueName: "Icon"; ValueType: string; ValueData: "{app}\clip2anim.exe"

Root: HKCU; Subkey: "Software\Classes\*\shell\Clip2Anim\command"; \
    ValueType: string; \
    ValueData: """{app}\clip2anim.exe"" ""%1"""