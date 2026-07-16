import os
import sys
import subprocess
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTime, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QRadioButton, QCheckBox,
    QGroupBox, QMessageBox, QProgressBar, QDialog, QTextEdit,
    QSizePolicy
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QSize, QEvent
import qtawesome as qta
from timeline_slider import TimelineSlider

if "__compiled__" in globals():
    # Nuitka
    APP_DIR = Path(__compiled__.containing_dir)
else:
    # Python実行（開発・テスト）
    APP_DIR = Path(__file__).resolve().parent

# FFmpegのパス
ffmpeg = shutil.which("ffmpeg")
if ffmpeg:
    # 環境変数に登録されているのでそれを採用する
    FFMPEG = Path(ffmpeg)
else:
    # 環境変数に無い…
    FFMPEG = APP_DIR / "ffmpeg" / "ffmpeg.exe"


def ms_to_text(ms: int) -> str:
    """ミリ秒を hh:mm:ss.zzz 形式の文字列へ変換する。"""
    t = QTime(0, 0).addMSecs(max(0, ms))
    return t.toString("hh:mm:ss.zzz")


def time_str_to_ms(time_str: str) -> float:
    """time=00:00:00.00 形式の文字列をミリ秒に変換する。"""
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600000 + int(m) * 60000 + float(s) * 1000
    except Exception:
        return 0.0


class ExportWorker(QThread):
    """FFmpegを実行し、進捗とログを報告するスレッド"""
    progress_updated = Signal(int)
    log_updated = Signal(str)
    error = Signal(str)
    finished_with_path = Signal(Path)

    def __init__(self, cmd, start_ms, end_ms, out_file):
        """スレッドの初期化。cmdは文字列のリストであること。"""
        super().__init__()
        self.cmd = cmd
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.out_file = out_file
        self._is_running = True
        self._stderr_log = []

    def run(self):
        """バックグラウンドでFFmpegプロセスを実行し、出力を解析する。"""
        self.log_updated.emit(f"Executing command:\n{' '.join(self.cmd)}\n")
        
        process = subprocess.Popen(
            self.cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        duration = self.end_ms - self.start_ms

        try:
            while True:
                line = process.stderr.readline()
                if line:
                    line = line.strip()

                    # ログはすべて保存・表示
                    self._stderr_log.append(line)
                    self.log_updated.emit(line)
                    
                    # progress情報だけ解析
                    if line.startswith("out_time_ms="):
                        try:
                            current_us = int(line.split("=", 1)[1])
                            current_ms = current_us // 1000

                            if duration > 0:
                                progress = int(current_ms * 100 / duration)
                                progress = max(0, min(progress, 100))
                                self.progress_updated.emit(progress)
                        except ValueError:
                            pass
                    elif line == "progress=end":
                        self.progress_updated.emit(100)
                        
                if process.poll() is not None:
                    break

                if not self._is_running:
                    process.terminate()
                    process.wait()
                    self.error.emit("ユーザーによって中断されました。")
                    return

            process.wait()
            if process.returncode == 0:
                self.finished_with_path.emit(self.out_file)
            else:
                error_msg = "\n".join(self._stderr_log[-10:])
                self.error.emit(f"FFmpeg Error (Exit Code: {process.returncode})\n\n{error_msg}")
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """実行中のプロセスを停止するためのフラグを立てる。"""
        self._is_running = False


class ExportProgressDialog(QDialog):
    """進捗表示・ログ出力・中断用のサブウィンドウ"""
    request_stop = Signal()

    def __init__(self, parent, command_text):
        """ダイアログの初期化。"""
        super().__init__(parent)
        self.setWindowTitle("エクスポート実行中")
        self.setModal(True)
        self.resize(600, 450)

        layout = QVBoxLayout(self)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: 'Consolas', 'Monaco', monospace; font-size: 10pt;")
        layout.addWidget(self.log_text)

        self.btn_cancel = QPushButton("中断")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self.btn_cancel.clicked.connect(self.request_stop.emit)
        layout.addWidget(self.btn_cancel)

        self.log_text.append(f"Command:\n{command_text}\n" + "-"*40)

    def update_progress(self, value):
        """プログレスバーの値を更新する。"""
        self.progress_bar.setValue(value)

    def append_log(self, text):
        """ログエリアに新しい行を追加する。"""
        self.log_text.append(text)
        self.log_text.ensureCursorVisible()

    def closeEvent(self, event):
        """ウィンドウが閉じられた場合に中断を要求する。"""
        self.request_stop.emit()
        event.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        """メインウィンドウを初期化する。"""
        super().__init__()
        self.setWindowTitle("Clip2Anim")
        self.resize(1400, 760)

        self.video_path = None
        self.start_ms = 0
        self.end_ms = 0
        self.is_dragging = False
        self.worker = None
        self.progress_dialog = None

        # --- Media Playerの設定 ---
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background:black;")
        self.video.setMinimumSize(640, 360)
        self.video.installEventFilter(self)
        self.player.setVideoOutput(self.video)
        
        # --- UI コンポーネント ---
        self.btn_open = QPushButton()
        self.btn_open.setIcon(qta.icon("mdi6.folder-open"))
        self.btn_open.setFixedSize(48, 48)
        self.btn_open.setIconSize(QSize(32, 32))
        self.btn_open.setToolTip("動画を開く Ctrl+O")
        
        self.btn_play = QPushButton()
        self.btn_play.setIcon(qta.icon("mdi6.play"))
        self.btn_play.setFixedSize(48, 48)
        self.btn_play.setIconSize(QSize(32, 32))
        self.btn_play.setToolTip("再生 Space")
        
        self.btn_prev_frame = QPushButton()
        self.btn_prev_frame.setIcon(qta.icon("mdi6.step-backward"))
        self.btn_prev_frame.setFixedSize(48, 48)
        self.btn_prev_frame.setIconSize(QSize(32, 32))
        self.btn_prev_frame.setToolTip("コマ戻し Ctrl+←")
        
        self.btn_next_frame = QPushButton()
        self.btn_next_frame.setIcon(qta.icon("mdi6.step-forward"))
        self.btn_next_frame.setFixedSize(48, 48)
        self.btn_next_frame.setIconSize(QSize(32, 32))
        self.btn_next_frame.setToolTip("コマ送り Ctrl+→")
        
        self.btn_prev_sec = QPushButton()
        self.btn_prev_sec.setIcon(qta.icon("mdi6.rewind"))
        self.btn_prev_sec.setFixedSize(48, 48)
        self.btn_prev_sec.setIconSize(QSize(32, 32))
        self.btn_prev_sec.setToolTip("1秒戻し ←")       
        
        self.btn_next_sec = QPushButton()
        self.btn_next_sec.setIcon(qta.icon("mdi6.fast-forward"))
        self.btn_next_sec.setFixedSize(48, 48)
        self.btn_next_sec.setIconSize(QSize(32, 32))
        self.btn_next_sec.setToolTip("1秒送り →")  

        self.btn_skip_start = QPushButton()
        self.btn_skip_start.setIcon(qta.icon("mdi6.skip-backward"))
        self.btn_skip_start.setFixedSize(48, 48)
        self.btn_skip_start.setIconSize(QSize(32, 32))
        self.btn_skip_start.setToolTip("最初へ") 

        self.btn_skip_end = QPushButton()
        self.btn_skip_end.setIcon(qta.icon("mdi6.skip-forward"))
        self.btn_skip_end.setFixedSize(48, 48)
        self.btn_skip_end.setIconSize(QSize(32, 32))
        self.btn_skip_end.setToolTip("最後へ") 

        self.btn_start = QPushButton()
        self.btn_start.setIcon(qta.icon("mdi6.map-marker-right"))
        self.btn_start.setFixedSize(48, 48)
        self.btn_start.setIconSize(QSize(32, 32))
        self.btn_start.setToolTip("開始設定 Ctrl+S")  

        self.btn_end = QPushButton()
        self.btn_end.setIcon(qta.icon("mdi6.map-marker-left"))
        self.btn_end.setFixedSize(48, 48)
        self.btn_end.setIconSize(QSize(32, 32))
        self.btn_end.setToolTip("終了設定 Ctrl+E")  
        self.lbl_start = QLabel("開始: 00:00:00.000")
        self.lbl_end = QLabel("終了: 00:00:00.000")

        self.slider = TimelineSlider()
        self.slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pos_label = QLabel("00:00:00.000")

        self.rb_aspect = QRadioButton("アスペクト比維持")
        self.rb_aspect.setToolTip("画面サイズのアスペクト比を維持します") 
        self.rb_square = QRadioButton("正方形")
        self.rb_square.setToolTip("画面サイズの横幅と縦幅のどちらか短い方に合わせて切り抜きます") 
        self.rb_aspect.setChecked(True)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(32, 4000)
        self.size_spin.setValue(500)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(24)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(90)
        self.privacy_crop = QCheckBox("個人情報保護クロップ")
        self.privacy_crop.setChecked(True)
        self.privacy_crop.setToolTip("画面下部3%を除去します") 

        self.btn_export = QPushButton("WebP")
        self.btn_export_gif = QPushButton("GIF")
        self.btn_export_avif = QPushButton("AVIF")
        self.btn_export.setMinimumHeight(50)
        self.btn_export_gif.setMinimumHeight(50)
        self.btn_export_avif.setMinimumHeight(50)
        
        self.btn_export.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")
        self.btn_export_gif.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        self.btn_export_avif.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")

        self.result_label = QLabel("未出力")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setWordWrap(True)

        # --- レイアウト ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(self.video, stretch=1)

        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)

        slider_row = QHBoxLayout()
        slider_row.addWidget(self.slider)
        slider_row.addWidget(self.pos_label)
        controls_layout.addLayout(slider_row)

        play_row = QHBoxLayout()
        play_row.addWidget(self.btn_open)
        play_row.addWidget(self.btn_play)
        play_row.addStretch()
        play_row.addWidget(self.lbl_start)
        play_row.addWidget(self.btn_start)
        play_row.addWidget(self.btn_skip_start)
        play_row.addWidget(self.btn_prev_frame)
        play_row.addWidget(self.btn_prev_sec)
        play_row.addWidget(self.btn_next_sec)
        play_row.addWidget(self.btn_next_frame)
        play_row.addWidget(self.btn_skip_end)
        play_row.addWidget(self.btn_end)
        play_row.addWidget(self.lbl_end)

        controls_layout.addLayout(play_row)
        
        left_layout.addWidget(controls_container)

        right_widget = QWidget()
        right_widget.setFixedWidth(300)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setAlignment(Qt.AlignTop)

        grp = QGroupBox("出力設定")
        g_layout = QVBoxLayout(grp)
        g_layout.addWidget(self.rb_aspect)
        g_layout.addWidget(self.rb_square)
        g_layout.addSpacing(10)
        g_layout.addWidget(QLabel("サイズ (px)"))
        g_layout.addWidget(self.size_spin)
        g_layout.addWidget(QLabel("FPS"))
        g_layout.addWidget(self.fps_spin)
        g_layout.addWidget(QLabel("品質 (0-100)"))
        g_layout.addWidget(self.quality_spin)
        g_layout.addWidget(self.privacy_crop)
        right_layout.addWidget(grp)

        right_layout.addSpacing(20)
        
        self.btn_group_widget = QWidget()
        self.btn_group_layout = QHBoxLayout(self.btn_group_widget)
        self.btn_group_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_group_layout.addWidget(self.btn_export)
        self.btn_group_layout.addWidget(self.btn_export_gif)
        self.btn_group_layout.addWidget(self.btn_export_avif)
        
        right_layout.addWidget(self.btn_group_widget)
        right_layout.addWidget(self.result_label)

        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(right_widget, stretch=0)

        # --- Connections ---
        self.btn_open.clicked.connect(self.open_file)
        self.btn_play.clicked.connect(self.toggle_play)
        self.slider.positionChanged.connect(self.on_slider_position_changed)
        self.slider.startChanged.connect(self.on_slider_start_changed)
        self.slider.endChanged.connect(self.on_slider_end_changed)
        self.slider.draggingChanged.connect(self.on_slider_dragging_changed)
        
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.btn_prev_frame.clicked.connect(lambda: self.seek_relative(-33))
        self.btn_next_frame.clicked.connect(lambda: self.seek_relative(33))
        self.btn_prev_sec.clicked.connect(lambda: self.seek_relative(-1000))
        self.btn_next_sec.clicked.connect(lambda: self.seek_relative(1000))
        self.btn_start.clicked.connect(self.set_start)
        self.btn_end.clicked.connect(self.set_end)
        self.btn_skip_start.clicked.connect(self.jump_to_start)
        self.btn_skip_end.clicked.connect(self.jump_to_end)
        self.btn_export.clicked.connect(self.start_export_webp)
        self.btn_export_gif.clicked.connect(self.start_export_gif)
        self.btn_export_avif.clicked.connect(self.start_export_avif)
        
        # フォーカス無効
        self.btn_open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev_frame.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next_frame.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev_sec.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next_sec.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_skip_start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_skip_end.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_end.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_export.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_export_gif.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_export_avif.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def keyPressEvent(self, event):
        """キーボードショートカットの制御"""
        modifiers = event.modifiers()
        is_ctrl = modifiers == Qt.KeyboardModifier.ControlModifier
        
        # --- 1. Ctrl + キー (ショートカット操作) ---
        if is_ctrl:
            if event.key() == Qt.Key.Key_O:
                self.open_file()             # Ctrl + O: ファイルを開く
            elif event.key() == Qt.Key.Key_S:
                self.set_start()             # Ctrl + S: 開始位置設定
            elif event.key() == Qt.Key.Key_E:
                self.set_end()               # Ctrl + E: 終了位置設定
            elif event.key() == Qt.Key.Key_G:
                self.start_export_gif()      # Ctrl + G: GIFエクスポート
            elif event.key() == Qt.Key.Key_W:
                self.start_export_webp()     # Ctrl + W: WebPエクスポート
            elif event.key() == Qt.Key.Key_A:
                self.start_export_avif()     # Ctrl + A: AVIFエクスポート
            elif event.key() == Qt.Key.Key_Left:
                self.seek_relative(-33)      # Ctrl + ←: コマ戻し
            elif event.key() == Qt.Key.Key_Right:
                self.seek_relative(33)       # Ctrl + →: コマ送り
            return # ショートカットを処理したら終了

        # --- 2. 単体キー (再生・シーク操作) ---
        # スペースキー (再生/一時停止)
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        
        # 矢印キー (1秒移動)
        elif event.key() == Qt.Key.Key_Left:
            self.seek_relative(-1000)        # ←: 1秒戻し
        elif event.key() == Qt.Key.Key_Right:
            self.seek_relative(1000)         # →: 1秒送り

        # 親クラスのイベント処理を呼び出す
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """映像表示エリア（VideoWidget）へのクリックイベントを検知"""
        if obj == self.video and event.type() == QEvent.Type.MouseButtonPress:
            self.toggle_play()
            return True
        return super().eventFilter(obj, event)

    def open_file(self):
        """動画ファイルを選択して読み込む。"""
        path, _ = QFileDialog.getOpenFileName(self, "動画を開く", "", "Video Files (*.mp4 *.mkv *.webm *.mov *.avi)")
        if not path: return
        self.video_path = path
        self.setWindowTitle(f"{path} - Clip2Anim")
        self.player.setSource(QUrl.fromLocalFile(path))
        self.setFocus() 

    def toggle_play(self):
        """動画の再生・一時停止を切り替える。"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.btn_play.setIcon(qta.icon("mdi6.play"))
            self.btn_play.setToolTip("再生")
        else:
            self.player.play()
            self.btn_play.setIcon(qta.icon("mdi6.pause"))
            self.btn_play.setToolTip("一時停止")
        self.setFocus() 

    def on_slider_dragging_changed(self, is_dragging: bool):
        """スライダー操作中のフラグ管理"""
        self.is_dragging = is_dragging

    def on_slider_position_changed(self, pos: int):
        """スライダーの再生位置が変更された時（ユーザー操作のみ）"""
        self.player.setPosition(pos)
        self.pos_label.setText(ms_to_text(pos))

    def on_slider_start_changed(self, start_ms: int):
        """スライダーの開始位置が変更された時"""
        self.start_ms = start_ms
        self.lbl_start.setText(f"開始: {ms_to_text(start_ms)}")

    def on_slider_end_changed(self, end_ms: int):
        """スライダーの終了位置が変更された時"""
        self.end_ms = end_ms
        self.lbl_end.setText(f"終了: {ms_to_text(end_ms)}")

    def on_media_status_changed(self, status):
        """メディアの状態（再生終了など）を検知してUIを更新する。"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.pause()
            self.btn_play.setIcon(qta.icon("mdi6.play"))
            self.btn_play.setToolTip("再生")

    def on_duration_changed(self, duration):
        """動画の長さに合わせてスライダーと終了位置を初期化する。"""
        if duration <= 0:
            return
        # スライダーの内部最大値を動画の長さに同期
        self.slider.set_duration(duration)
        self.slider.set_end(duration)
        
        self.end_ms = duration
        self.lbl_end.setText(f"終了: {ms_to_text(duration)}")
        
        
        # 初回読み込み時などに位置をリセット
        if self.slider._position == 0:
            self.slider.set_position(0)

    def on_position_changed(self, pos):
        """プレイヤーの再生位置に応じてスライダーと時刻表示を更新する。"""
        if not self.is_dragging:
            self.slider.set_position(pos)
        self.pos_label.setText(ms_to_text(pos))

    def on_slider_pressed(self):
        """スライダー操作中の判定を開始する。"""
        self.is_dragging = True

    def on_slider_released(self):
        """スライダー操作を終了し、再生位置を確定する。"""
        self.is_dragging = False
        self.player.setPosition(self.slider.value())

    def seek_relative(self, delta):
        """現在位置から指定ミリ秒だけ移動する。"""
        self.player.setPosition(max(0, self.player.position() + delta))

    def set_start(self):
        """現在の再生位置を開始位置として設定する。"""
        self.slider.set_start(self.player.position())
        self.lbl_start.setText(f"開始: {ms_to_text(self.start_ms)}")

    def set_end(self):
        """現在の再生位置を終了位置として設定する。"""
        self.slider.set_end(self.player.position())
        self.lbl_end.setText(f"終了: {ms_to_text(self.end_ms)}")

    def jump_to_start(self):
        """再生位置を動画の先頭(0ms)へ移動します。"""
        self.player.setPosition(0)

    def jump_to_end(self):
        """再生位置を動画の末尾(duration)へ移動します。"""
        duration = self.player.duration()
        if duration > 0:
            self.player.setPosition(duration)

    def prepare_export(self):
        """エクスポート開始前のバリデーションを行う。"""
        if not self.video_path:
            QMessageBox.warning(self, "エラー", "動画を開いてください")
            return False
        if self.end_ms <= self.start_ms:
            QMessageBox.warning(self, "エラー", "終了位置が開始位置以下です")
            return False
        return True

    # --- エクスポートプロセス ---

    def run_export_process(self, cmd, out_file):
        """エクスポートプロセスを開始し、専用ダイアログを起動する。"""
        if not self.prepare_export():
            return

        cmd_str = " ".join(cmd)
        self.progress_dialog = ExportProgressDialog(self, cmd_str)
        self.worker = ExportWorker(cmd, self.start_ms, self.end_ms, out_file)

        self.worker.progress_updated.connect(self.progress_dialog.update_progress)
        self.worker.log_updated.connect(self.progress_dialog.append_log)
        self.worker.error.connect(self.on_export_error)
        self.worker.finished_with_path.connect(self.on_export_finished)
        self.progress_dialog.request_stop.connect(self.cancel_export)

        self.progress_dialog.show()
        self.worker.start()

    def cancel_export(self):
        """エクスポートを中断する。"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.progress_dialog.append_log("\n[INFO] 中断リクエストを送信しました...")
        else:
            self.progress_dialog.accept()

    def on_export_finished(self, out_file: Path):
        """エクスポートが正常に終了した際の処理。"""
        size_bytes = out_file.stat().st_size
        self.result_label.setText(f"完了: {out_file.name[:20]}...\n({size_bytes/1024:.1f} KB)")
        self.progress_dialog.progress_bar.setValue(100)
        self.progress_dialog.btn_cancel.setText("完了")
        self.progress_dialog.btn_cancel.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold;")


    def on_export_error(self, error_msg):
        """エクスポート中にエラーが発生した際の処理。"""
        self.progress_dialog.append_log(error_msg)
        self.result_label.setText("エラーが発生しました")
        self.progress_dialog.btn_cancel.setText("閉じる")

    # --- FFmpegコマンドの作成 ---

    def build_base_args(self):
        """ベースとなるFFmpeg引数を構築する。"""
        src = Path(self.video_path)
        args = [
            str(FFMPEG),
            "-progress",
            "pipe:2",
            "-nostats",
            "-y",
            "-ss", str(self.start_ms / 1000.0),
            "-to", str(self.end_ms / 1000.0),
            "-i", str(src)
        ]
        return args, src

    def build_video_filters(self, force_format=None):
        """ビデオフィルタを構築する。"""
        vf = []
        if self.rb_square.isChecked():
            # 正方形にクリップする
            # 横幅、縦幅のどちらか短いほうに合わせてくり抜く
            vf.append("crop=min(iw\\,ih):min(iw\\,ih)")
            # 500:500
            vf.append(f"scale={self.size_spin.value()}:{self.size_spin.value()}")
        else:
            if self.privacy_crop.isChecked():
                # 個人情報保護。アスペクト比を維持するときだけ有効
                # 画面下部3%を除去する。具体的には原神の右下に表示されるUIDを削る機能
                # 2160pなら2110pに。1080pなら1055pに。解像度に柔軟に対応する
                vf.append("crop=iw:ih*0.976851851852:0:0")
            # 500:-1
            vf.append(f"scale={self.size_spin.value()}:-1")
        if force_format:
            # avifの場合、format=nv12を入れておく
            vf.append(f"format={force_format}")
        return vf

    def start_export_webp(self):
        """選択範囲をWebPとして出力する。"""
        args, src = self.build_base_args()
        vf = self.build_video_filters()
        vf.insert(0, f"fps={self.fps_spin.value()}")
        out_file = src.with_name(f"{src.stem}_webp_{self.size_spin.value()}.webp")
        cmd = args + ["-vf", ",".join(vf), "-c:v", "libwebp", "-lossless", "1", 
                       "-quality", str(self.quality_spin.value()), "-loop", "0", 
                       "-preset", "picture", "-an", "-vsync", "0", "-compression_level", "6", str(out_file)]
        self.run_export_process(cmd, out_file)

    def start_export_gif(self):
        """選択範囲をGIFとして出力する。"""
        args, src = self.build_base_args()
        vf = self.build_video_filters()
        vf.insert(0, f"[0:v] fps={self.fps_spin.value()}")
        vf.append("split [a][b];[a] palettegen=stats_mode=single [p];[b][p] paletteuse=new=1")
        out_file = src.with_name(f"{src.stem}_gif_{self.size_spin.value()}.gif")
        cmd = args + ["-filter_complex", ",".join(vf), "-c:v", "gif", "-f", "gif", str(out_file)]
        self.run_export_process(cmd, out_file)

    def start_export_avif(self):
        """選択範囲をアニメーションAVIFとして出力する。"""
        args, src = self.build_base_args()
        vf = self.build_video_filters(force_format="nv12")
        vf.insert(0, f"fps={self.fps_spin.value()}")
        out_file = src.with_name(f"{src.stem}_avif_{self.size_spin.value()}_{self.fps_spin.value()}fps_q{self.quality_spin.value()}.avif")
        quality_val = int(63 * (1 - self.quality_spin.value() / 100))
        cmd = args + [
            "-vf", ",".join(vf),
            "-c:v", "av1_nvenc",
            "-rc", "vbr",
            "-cq", str(quality_val),
            str(out_file)
        ]
        self.run_export_process(cmd, out_file)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        w.video_path = sys.argv[1]
        w.setWindowTitle(f"{sys.argv[1]} - Clip2Anim")
        w.player.setSource(QUrl.fromLocalFile(sys.argv[1]))
        w.player.play()
        w.btn_play.setIcon(qta.icon("mdi6.pause"))
        w.btn_play.setToolTip("一時停止")
    w.show()
    sys.exit(app.exec())
