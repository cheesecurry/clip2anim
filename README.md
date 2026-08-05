# clip2anim

**clip2anim**は、動画ファイルからGIF、WebP、Avifのアニメーション画像を作成するWindows向けツールです。  
動画の変換には[ffmpeg](https://ffmpeg.org)を使用しています。

## 機能
- 動画のプレビュー
- シークバーによる出力範囲の選択
- FFmpegによるGIF、WebP、Avifのアニメーション画像への書き出し

## ダウンロード
- [インストーラー版](https://github.com/cheesecurry/clip2anim/releases/latest/download/Clip2AnimSetup.exe)
- [ポータブル版](https://github.com/cheesecurry/clip2anim/releases/latest/download/Clip2Anim-portable.zip)

## インストール
インストーラーを用いてセットアップする方法と、zipを展開して配置する方法があります。

### インストーラー版を使用する場合
**Clip2AnimSetup.exe**を実行し、画面通りに進めると**clip2anim.exe**は`%localappdata%\Clip2Anim`の配下にインストールされます。  
**ffmpeg**も`%localappdata%\Clip2Anim\ffmpeg`にインストールされ、動画ファイルの右クリックメニューに「clip2animで開く」を追加されます。  
AVIFエンコーダーはなるべくハードウェアアクセラレーションが有効になるよう`av1_nvenc` or `av1_qsv` or `av1_amf`が使用されるよう設定されます。使用できない場合は`libaom-av1`が採用されます。

### ポータブル版を使用する場合
**Clip2Anim-portable.zip**を展開し、**clip2anim.exe**を任意のディレクトリに配置します。  
別途[ffmpeg](https://ffmpeg.org)をインストールする必要があります。環境変数にパスが通っていればどこにインストールされていても問題ありません。  
パスを通さない場合、**ffmpeg**を次の構成になるよう配置してください。
- `(任意のディレクトリ)\clip2anim.exe`
- `(任意のディレクトリ)\ffmpeg\ffmpeg.exe` ※Pathが通ってない場合
- `(任意のディレクトリ)\config.json` ※AVIFエンコーダーを指定する場合

AVIFエンコーダーはデフォルトだと`libaom-av1`が採用されます。AVIFのエンコーダーを変更したい場合、`clip2anim.exe`と同じディレクトリに`config.json`を作成し、中身は次のように記述します。
```av1_nvenc
{
    "av1_codec": "av1_nvenc"
}
```

## アンインストール
インストーラー版を使用した場合、[アンインストール手順](https://support.microsoft.com/ja-jp/windows/4b55f974-2cc6-2d2b-d092-5905080eaf98)でアンインストールしてください。  
右クリックメニューに「clip2animで開く」が残る場合、レジストリエディターで`HKEY_CLASSES_ROOT\*\shell\Clip2Anim`のキーを削除してください。

## ライセンス
- MIT License