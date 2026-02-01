from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QWidget


class Timeline(QWidget):
    """Custom timeline widget with playhead and in/out markers."""

    seek_requested = Signal(float)
    in_point_changed = Signal(float)
    out_point_changed = Signal(float)

    TRACK_HEIGHT = 20
    HANDLE_WIDTH = 10
    HANDLE_HEIGHT = 30
    MARGIN_X = 12
    MARGIN_Y = 10

    COLOR_TRACK = QColor(60, 60, 60)
    COLOR_SELECTION = QColor(40, 120, 200, 120)
    COLOR_PLAYHEAD = QColor(255, 60, 60)
    COLOR_IN_HANDLE = QColor(30, 180, 60)
    COLOR_OUT_HANDLE = QColor(200, 60, 30)
    COLOR_HANDLE_HOVER = QColor(255, 255, 100)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.HANDLE_HEIGHT + self.MARGIN_Y * 2)
        self.setFixedHeight(self.HANDLE_HEIGHT + self.MARGIN_Y * 2 + 10)
        self.setCursor(Qt.PointingHandCursor)

        self._duration = 0.0
        self._position = 0.0
        self._in_point = 0.0
        self._out_point = 0.0

        self._dragging = None  # None, 'in', 'out', 'seek'
        self._hover = None  # None, 'in', 'out'

        self.setMouseTracking(True)

    @property
    def duration(self) -> float:
        return self._duration

    @duration.setter
    def duration(self, value: float):
        self._duration = max(0.0, value)
        self._out_point = self._duration
        self.update()

    @property
    def position(self) -> float:
        return self._position

    @position.setter
    def position(self, value: float):
        self._position = max(0.0, min(value, self._duration))
        self.update()

    @property
    def in_point(self) -> float:
        return self._in_point

    @in_point.setter
    def in_point(self, value: float):
        self._in_point = max(0.0, min(value, self._out_point))
        self.update()

    @property
    def out_point(self) -> float:
        return self._out_point

    @out_point.setter
    def out_point(self, value: float):
        self._out_point = max(self._in_point, min(value, self._duration))
        self.update()

    def _track_rect(self) -> QRectF:
        """Return the rectangle for the track bar."""
        y = (self.height() - self.TRACK_HEIGHT) / 2
        return QRectF(self.MARGIN_X, y, self.width() - 2 * self.MARGIN_X, self.TRACK_HEIGHT)

    def _time_to_x(self, t: float) -> float:
        """Convert a time value to an x pixel position."""
        track = self._track_rect()
        if self._duration <= 0:
            return track.left()
        ratio = t / self._duration
        return track.left() + ratio * track.width()

    def _x_to_time(self, x: float) -> float:
        """Convert an x pixel position to a time value."""
        track = self._track_rect()
        if track.width() <= 0:
            return 0.0
        ratio = (x - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        return ratio * self._duration

    def _in_handle_rect(self) -> QRectF:
        x = self._time_to_x(self._in_point)
        y = (self.height() - self.HANDLE_HEIGHT) / 2
        return QRectF(x - self.HANDLE_WIDTH, y, self.HANDLE_WIDTH, self.HANDLE_HEIGHT)

    def _out_handle_rect(self) -> QRectF:
        x = self._time_to_x(self._out_point)
        y = (self.height() - self.HANDLE_HEIGHT) / 2
        return QRectF(x, y, self.HANDLE_WIDTH, self.HANDLE_HEIGHT)

    def _hit_test(self, pos) -> str | None:
        """Return 'in', 'out', or None based on mouse position."""
        # Expand hit area slightly for easier grabbing
        expand = 4
        in_rect = self._in_handle_rect().adjusted(-expand, -expand, expand, expand)
        out_rect = self._out_handle_rect().adjusted(-expand, -expand, expand, expand)
        if in_rect.contains(pos):
            return "in"
        if out_rect.contains(pos):
            return "out"
        return None

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        # Draw track background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.COLOR_TRACK))
        painter.drawRoundedRect(track, 3, 3)

        # Draw selected region
        if self._duration > 0:
            x_in = self._time_to_x(self._in_point)
            x_out = self._time_to_x(self._out_point)
            sel_rect = QRectF(x_in, track.top(), x_out - x_in, track.height())
            painter.setBrush(QBrush(self.COLOR_SELECTION))
            painter.drawRect(sel_rect)

        # Draw in handle
        in_rect = self._in_handle_rect()
        color = self.COLOR_HANDLE_HOVER if self._hover == "in" else self.COLOR_IN_HANDLE
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        painter.drawRoundedRect(in_rect, 2, 2)

        # Draw out handle
        out_rect = self._out_handle_rect()
        color = self.COLOR_HANDLE_HOVER if self._hover == "out" else self.COLOR_OUT_HANDLE
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(out_rect, 2, 2)

        # Draw playhead
        if self._duration > 0:
            px = self._time_to_x(self._position)
            pen = QPen(self.COLOR_PLAYHEAD, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(int(px), int(track.top() - 4), int(px), int(track.bottom() + 4))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return

        hit = self._hit_test(event.position())
        if hit:
            self._dragging = hit
        else:
            self._dragging = "seek"
            t = self._x_to_time(event.position().x())
            self.seek_requested.emit(t)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._duration <= 0:
            return

        if self._dragging == "in":
            t = self._x_to_time(event.position().x())
            t = max(0.0, min(t, self._out_point))
            self._in_point = t
            self.in_point_changed.emit(t)
            self.update()
        elif self._dragging == "out":
            t = self._x_to_time(event.position().x())
            t = max(self._in_point, min(t, self._duration))
            self._out_point = t
            self.out_point_changed.emit(t)
            self.update()
        elif self._dragging == "seek":
            t = self._x_to_time(event.position().x())
            self.seek_requested.emit(t)
        else:
            # Hover detection
            hit = self._hit_test(event.position())
            if hit != self._hover:
                self._hover = hit
                self.setCursor(Qt.SizeHorCursor if hit else Qt.PointingHandCursor)
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = None
