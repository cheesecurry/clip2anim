from PySide6.QtCore import Qt, QSize, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QMouseEvent
from PySide6.QtWidgets import QWidget

class TimelineSlider(QWidget):
    """
    カット範囲（開始・終了）と再生位置を同時に表示・操作できるカスタムタイムラインスライダー。
    """
    positionChanged = Signal(int)
    startChanged = Signal(int)
    endChanged = Signal(int)
    draggingChanged = Signal(bool)  # ドラッグ中の状態を通知

    DRAG_NONE, DRAG_START, DRAG_END, DRAG_PLAYHEAD = range(4)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(48)
        self._duration = 0
        self._start = 0
        self._end = 0
        self._position = 0
        self._dragging = self.DRAG_NONE
        
        self._hit_radius = 14       # 操作判定の半径（ピクセル）
        self._min_gap = 100         # 開始と終了の最小ギャップ（ms）
        self._margin = 16
        self._handle_w = 6
        self._handle_h = 24
        self._track_h = 4
        
        self._colors = {
            "track": QColor(70, 70, 70),
            "range": QColor(60, 140, 255, 160),
            "handle_start": QColor(30, 90, 220),
            "handle_end": QColor(30, 90, 220),
            "playhead": QColor(220, 40, 40),
        }
        
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self.draggingChanged.emit(False)

    def sizeHint(self):
        # レイアウトが十分な幅を確保できるよう推奨サイズを返す
        return QSize(800, self.minimumHeight())

    def set_duration(self, ms):
        if ms <= 0: return
        self._duration = ms
        # 範囲外の値を自動的に調整
        if self._start >= self._end:
            self._start = max(0, self._end - self._min_gap)
        if self._end > ms:
            self._end = ms
        if self._position > ms:
            self._position = ms
        self.update()

    def set_start(self, ms):
        """開始位置を設定（ミリ秒）"""
        new_start = max(0, min(ms, self._end - self._min_gap))
        if new_start != self._start:
            self._start = new_start
            self.startChanged.emit(self._start)
            self.update()

    def set_end(self, ms):
        """終了位置を設定（ミリ秒）"""
        new_end = min(self._duration, max(ms, self._start + self._min_gap))
        if new_end != self._end:
            self._end = new_end
            self.endChanged.emit(self._end)
            self.update()

    def set_position(self, ms):
        """再生位置を設定（ミリ秒・外部更新用）"""
        new_pos = max(0, min(ms, self._duration))
        if new_pos != self._position:
            self._position = new_pos
            self.update()

    def _ms_to_x(self, ms):
        """ミリ秒 -> X座標"""
        w = self.width() - self._margin * 2
        if w <= 0: return self._margin
        return self._margin + (ms / self._duration) * w

    def _x_to_ms(self, x):
        """X座標 -> ミリ秒"""
        w = self.width() - self._margin * 2
        if w <= 0: return 0
        v = (x - self._margin) / w
        return int(max(0.0, min(1.0, v)) * self._duration)

    def _get_handle_rects(self):
        cy = self.height() / 2.0
        return {
            "start": QRectF(self._ms_to_x(self._start) - self._handle_w/2, cy - self._handle_h/2, self._handle_w, self._handle_h),
            "end": QRectF(self._ms_to_x(self._end) - self._handle_w/2, cy - self._handle_h/2, self._handle_w, self._handle_h),
            "playhead": QRectF(self._ms_to_x(self._position) - self._handle_w/2, cy - self._handle_h/2, self._handle_w, self._handle_h)
        }

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy = self.height() / 2.0

        # 背景トラック
        p.setPen(Qt.NoPen)
        p.setBrush(self._colors["track"])
        track_rect = QRectF(self._margin, cy - self._track_h/2, self.width() - self._margin*2, self._track_h)
        p.drawRoundedRect(track_rect, self._track_h/2, self._track_h/2)

        # 選択範囲（カット領域）
        sx = self._ms_to_x(self._start)
        ex = self._ms_to_x(self._end)
        p.setBrush(self._colors["range"])
        p.drawRect(sx, cy - 8, ex - sx, 16)

        # ハンドル描画ヘルパー
        def draw_handle(rect, color):
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(QPen(color.darker(130), 2))
            p.drawLine(rect.center().x(), rect.top() + 4, rect.center().x(), rect.bottom() - 4)

        handles = self._get_handle_rects()
        draw_handle(handles["start"], self._colors["handle_start"])
        draw_handle(handles["end"], self._colors["handle_end"])
        draw_handle(handles["playhead"], self._colors["playhead"])

    def mousePressEvent(self, event):
        if self._duration <= 0: return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        cy = self.height() / 2.0
        handles = self._get_handle_rects()
        hit = self._hit_radius

        if handles["start"].contains(x, cy) or abs(x - handles["start"].center().x()) < hit:
            self._dragging = self.DRAG_START
        elif handles["end"].contains(x, cy) or abs(x - handles["end"].center().x()) < hit:
            self._dragging = self.DRAG_END
        elif handles["playhead"].contains(x, cy) or abs(x - handles["playhead"].center().x()) < hit:
            self._dragging = self.DRAG_PLAYHEAD
        else:
            ms = self._x_to_ms(x)
            self._position = ms
            self.positionChanged.emit(ms)
            self.update()
            self._dragging = self.DRAG_PLAYHEAD
            
        self.draggingChanged.emit(True)  # ドラッグ開始を通知

    def mouseMoveEvent(self, event):
        if self._duration <= 0: return
        if self._dragging == self.DRAG_NONE:
            # カーソル変更のみ（既存のロジックそのまま）
            x = event.position().x()
            cy = self.height() / 2.0
            handles = self._get_handle_rects()
            hit = self._hit_radius
            if handles["start"].contains(x, cy) or handles["end"].contains(x, cy):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif handles["playhead"].contains(x, cy):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        ms = self._x_to_ms(event.position().x())
        if self._dragging == self.DRAG_START:
            self.set_start(ms)
        elif self._dragging == self.DRAG_END:
            self.set_end(ms)
        elif self._dragging == self.DRAG_PLAYHEAD:
            if ms != self._position:
                self._position = ms
                self.positionChanged.emit(ms)
                self.update()

    def mouseReleaseEvent(self, event):
        if self._duration <= 0: return
        self._dragging = self.DRAG_NONE
        self.draggingChanged.emit(False)  # ドラッグ終了を通知
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()