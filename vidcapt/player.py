import sys
import locale

import mpv
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget


class MpvPlayer(QWidget):
    """Embeds an mpv player into a Qt widget."""

    position_changed = Signal(float)
    duration_changed = Signal(float)
    file_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: black;")

        self._duration = 0.0
        self._position = 0.0
        self._creating_player = False
        self._mpv = None

    def init_mpv(self):
        """Initialize mpv after the widget has a valid window handle."""
        if self._mpv is not None or self._creating_player:
            return
        self._creating_player = True

        wid = int(self.winId())
        # Workaround: locale must be set for mpv on some systems
        locale.setlocale(locale.LC_NUMERIC, "C")

        self._mpv = mpv.MPV(
            wid=str(wid),
            vo="gpu",
            keep_open="yes",
            idle="yes",
            osc="no",
            input_default_bindings="no",
            input_vo_keyboard="no",
            log_handler=lambda *a: None,
        )

        @self._mpv.property_observer("time-pos")
        def on_time_pos(_name, value):
            if value is not None:
                self._position = value
                self.position_changed.emit(value)

        @self._mpv.property_observer("duration")
        def on_duration(_name, value):
            if value is not None:
                self._duration = value
                self.duration_changed.emit(value)

        @self._mpv.event_callback("file-loaded")
        def on_file_loaded(event):
            self.file_loaded.emit()

        self._creating_player = False

    def load(self, path: str):
        """Load a video file."""
        if self._mpv is None:
            self.init_mpv()
        self._mpv.play(path)

    def play(self):
        """Resume playback."""
        if self._mpv and self._mpv.pause:
            self._mpv.pause = False

    def pause(self):
        """Pause playback."""
        if self._mpv and not self._mpv.pause:
            self._mpv.pause = True

    def toggle_pause(self):
        """Toggle play/pause."""
        if self._mpv:
            self._mpv.pause = not self._mpv.pause

    def seek(self, seconds: float, reference: str = "relative"):
        """Seek by a relative or absolute amount.

        Args:
            seconds: Time in seconds.
            reference: 'relative' for offset, 'absolute' for absolute position.
        """
        if self._mpv:
            self._mpv.seek(seconds, reference)

    def frame_step(self):
        """Advance one frame."""
        if self._mpv:
            self._mpv.frame_step()

    def frame_back_step(self):
        """Go back one frame."""
        if self._mpv:
            self._mpv.frame_back_step()

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def paused(self) -> bool:
        if self._mpv:
            return self._mpv.pause
        return True

    def get_tracks(self, track_type=None):
        """Return list of track dicts from mpv.

        Args:
            track_type: Optional filter — 'video', 'audio', or 'sub'.
        """
        if not self._mpv:
            return []
        tracks = self._mpv.track_list
        if track_type is not None:
            tracks = [t for t in tracks if t.get("type") == track_type]
        return tracks

    def set_video_track(self, track_id):
        if self._mpv:
            self._mpv.vid = track_id

    def set_audio_track(self, track_id):
        if self._mpv:
            self._mpv.aid = track_id

    def set_subtitle_track(self, track_id):
        """Set subtitle track. Pass 'no' to disable subtitles."""
        if self._mpv:
            self._mpv.sid = track_id

    def showEvent(self, event):
        super().showEvent(event)
        if self._mpv is None:
            self.init_mpv()

    def closeEvent(self, event):
        if self._mpv:
            self._mpv.terminate()
            self._mpv = None
        super().closeEvent(event)
