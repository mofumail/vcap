import os

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QKeySequence, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QProgressBar,
    QStatusBar,
    QMenuBar,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
)

from vidcapt.player import MpvPlayer
from vidcapt.timeline import Timeline
from vidcapt.exporter import Exporter, format_time, ffmpeg_available


VIDEO_FILTERS = "Video Files (*.mkv *.mp4 *.avi *.webm *.mov *.flv *.wmv);;All Files (*)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VidCapt")
        self.setMinimumSize(800, 600)
        self.resize(1024, 720)
        self.setAcceptDrops(True)

        self._source_path = ""

        # Components
        self._player = MpvPlayer()
        self._timeline = Timeline()
        self._exporter = Exporter(self)

        self._build_ui()
        self._build_menu()
        self._build_shortcuts()
        self._connect_signals()

        # Position polling timer (mpv property observers fire on the mpv thread,
        # so we poll from the Qt side to keep UI updates safe)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_position)

    # ── UI Construction ─────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Video area
        self._player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._player, stretch=1)

        # Transport controls
        transport = QHBoxLayout()
        transport.setSpacing(6)

        self._btn_prev_frame = QPushButton("|◀")
        self._btn_prev_frame.setFixedWidth(40)
        self._btn_prev_frame.setToolTip("Previous frame (,)")
        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(40)
        self._btn_play.setToolTip("Play / Pause (Space)")
        self._btn_next_frame = QPushButton("▶|")
        self._btn_next_frame.setFixedWidth(40)
        self._btn_next_frame.setToolTip("Next frame (.)")
        self._btn_seek_back = QPushButton("◀◀")
        self._btn_seek_back.setFixedWidth(40)
        self._btn_seek_back.setToolTip("Seek -5s (Left)")
        self._btn_seek_fwd = QPushButton("▶▶")
        self._btn_seek_fwd.setFixedWidth(40)
        self._btn_seek_fwd.setToolTip("Seek +5s (Right)")

        self._lbl_time = QLabel("00:00:00.000 / 00:00:00.000")
        self._lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        for btn in (self._btn_prev_frame, self._btn_play, self._btn_next_frame,
                     self._btn_seek_back, self._btn_seek_fwd):
            transport.addWidget(btn)
        transport.addStretch()
        transport.addWidget(self._lbl_time)
        layout.addLayout(transport)

        # Timeline
        layout.addWidget(self._timeline)

        # Clip controls
        clip_layout = QHBoxLayout()
        clip_layout.setSpacing(8)

        self._lbl_start = QLabel("Start:")
        self._edit_start = QLineEdit("00:00:00.000")
        self._edit_start.setFixedWidth(120)
        self._edit_start.setReadOnly(True)

        self._lbl_end = QLabel("End:")
        self._edit_end = QLineEdit("00:00:00.000")
        self._edit_end.setFixedWidth(120)
        self._edit_end.setReadOnly(True)

        self._lbl_duration = QLabel("Duration: 00:00:00.000")

        clip_layout.addWidget(self._lbl_start)
        clip_layout.addWidget(self._edit_start)
        clip_layout.addWidget(self._lbl_end)
        clip_layout.addWidget(self._edit_end)
        clip_layout.addWidget(self._lbl_duration)
        clip_layout.addStretch()
        layout.addLayout(clip_layout)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._btn_set_in = QPushButton("Set Start (I)")
        self._btn_set_out = QPushButton("Set End (O)")
        self._btn_preview = QPushButton("Preview Selection")

        btn_layout.addWidget(self._btn_set_in)
        btn_layout.addWidget(self._btn_set_out)
        btn_layout.addWidget(self._btn_preview)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Export row
        export_layout = QHBoxLayout()
        export_layout.setSpacing(8)

        export_layout.addWidget(QLabel("Format:"))
        self._combo_format = QComboBox()
        self._combo_format.addItems(["mp4", "webm"])
        export_layout.addWidget(self._combo_format)

        export_layout.addWidget(QLabel("Quality:"))
        self._combo_quality = QComboBox()
        self._combo_quality.addItems(["High", "Medium", "Low"])
        export_layout.addWidget(self._combo_quality)

        self._btn_export = QPushButton("Export Clip...")
        self._btn_export.setEnabled(False)
        export_layout.addWidget(self._btn_export)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedWidth(200)
        self._progress.setVisible(False)
        export_layout.addWidget(self._progress)

        export_layout.addStretch()
        layout.addLayout(export_layout)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready. Open a video file to begin.")

    def _build_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open File...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)

        export_action = QAction("&Export Clip...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_clip)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _build_shortcuts(self):
        """Set up keyboard shortcuts that aren't already on menu actions."""
        # These use lambda so they don't need dedicated slots
        shortcuts = {
            Qt.Key_Space: self._toggle_play,
            Qt.Key_I: self._set_in_point,
            Qt.Key_O: self._set_out_point,
            Qt.Key_Left: lambda: self._player.seek(-5),
            Qt.Key_Right: lambda: self._player.seek(5),
            Qt.Key_Comma: self._player.frame_back_step,
            Qt.Key_Period: self._player.frame_step,
            Qt.Key_BracketLeft: lambda: self._jump_to(self._timeline.in_point),
            Qt.Key_BracketRight: lambda: self._jump_to(self._timeline.out_point),
        }

        from PySide6.QtGui import QShortcut

        for key, callback in shortcuts.items():
            sc = QShortcut(key, self)
            sc.activated.connect(callback)

        # Shift+Arrow for fine seeking
        sc_left = QShortcut(QKeySequence("Shift+Left"), self)
        sc_left.activated.connect(lambda: self._player.seek(-1))
        sc_right = QShortcut(QKeySequence("Shift+Right"), self)
        sc_right.activated.connect(lambda: self._player.seek(1))

    def _connect_signals(self):
        # Transport buttons
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_prev_frame.clicked.connect(self._player.frame_back_step)
        self._btn_next_frame.clicked.connect(self._player.frame_step)
        self._btn_seek_back.clicked.connect(lambda: self._player.seek(-5))
        self._btn_seek_fwd.clicked.connect(lambda: self._player.seek(5))

        # Clip buttons
        self._btn_set_in.clicked.connect(self._set_in_point)
        self._btn_set_out.clicked.connect(self._set_out_point)
        self._btn_preview.clicked.connect(self._preview_selection)
        self._btn_export.clicked.connect(self._export_clip)

        # Player signals
        self._player.duration_changed.connect(self._on_duration_changed)
        self._player.file_loaded.connect(self._on_file_loaded)

        # Timeline signals
        self._timeline.seek_requested.connect(self._on_seek_requested)
        self._timeline.in_point_changed.connect(self._on_in_point_changed)
        self._timeline.out_point_changed.connect(self._on_out_point_changed)

        # Exporter signals
        self._exporter.progress.connect(self._on_export_progress)
        self._exporter.finished.connect(self._on_export_finished)
        self._exporter.error.connect(self._on_export_error)

    # ── Slots ───────────────────────────────────────────────────────

    def _poll_position(self):
        """Poll mpv position and update UI."""
        pos = self._player.position
        dur = self._player.duration
        self._timeline.position = pos
        self._lbl_time.setText(f"{format_time(pos)} / {format_time(dur)}")

        # Update play button text
        self._btn_play.setText("❚❚" if not self._player.paused else "▶")

    def _toggle_play(self):
        self._player.toggle_pause()

    def _jump_to(self, t: float):
        self._player.seek(t, "absolute")

    @Slot()
    def _set_in_point(self):
        t = self._player.position
        self._timeline.in_point = t
        self._edit_start.setText(format_time(t))
        self._update_clip_duration()

    @Slot()
    def _set_out_point(self):
        t = self._player.position
        self._timeline.out_point = t
        self._edit_end.setText(format_time(t))
        self._update_clip_duration()

    def _update_clip_duration(self):
        dur = self._timeline.out_point - self._timeline.in_point
        self._lbl_duration.setText(f"Duration: {format_time(max(0, dur))}")

    @Slot(float)
    def _on_duration_changed(self, duration: float):
        self._timeline.duration = duration
        self._timeline.out_point = duration
        self._edit_end.setText(format_time(duration))
        self._update_clip_duration()

    @Slot()
    def _on_file_loaded(self):
        self._btn_export.setEnabled(True)
        self._poll_timer.start()
        self._status.showMessage(f"Loaded: {os.path.basename(self._source_path)}")

    @Slot(float)
    def _on_seek_requested(self, t: float):
        self._player.seek(t, "absolute")

    @Slot(float)
    def _on_in_point_changed(self, t: float):
        self._edit_start.setText(format_time(t))
        self._update_clip_duration()

    @Slot(float)
    def _on_out_point_changed(self, t: float):
        self._edit_end.setText(format_time(t))
        self._update_clip_duration()

    @Slot()
    def _preview_selection(self):
        """Seek to in-point and play to out-point."""
        self._player.seek(self._timeline.in_point, "absolute")
        self._player.play()

    # ── Export ──────────────────────────────────────────────────────

    @Slot()
    def _export_clip(self):
        if not self._source_path:
            self._status.showMessage("No file loaded.")
            return

        if not ffmpeg_available():
            QMessageBox.warning(
                self, "ffmpeg not found",
                "ffmpeg was not found on PATH. Please install ffmpeg to export clips."
            )
            return

        fmt = self._combo_format.currentText()
        quality = self._combo_quality.currentText()

        base = os.path.splitext(os.path.basename(self._source_path))[0]
        default_name = f"{base}_clip.{fmt}"

        if fmt == "mp4":
            file_filter = "MP4 Files (*.mp4)"
        else:
            file_filter = "WebM Files (*.webm)"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Clip", default_name, file_filter
        )
        if not path:
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_export.setEnabled(False)
        self._status.showMessage("Exporting...")

        self._exporter.export(
            source=self._source_path,
            start=self._timeline.in_point,
            end=self._timeline.out_point,
            output_path=path,
            fmt=fmt,
            quality=quality,
        )

    @Slot(int)
    def _on_export_progress(self, pct: int):
        self._progress.setValue(pct)

    @Slot(str)
    def _on_export_finished(self, path: str):
        self._progress.setVisible(False)
        self._btn_export.setEnabled(True)
        self._status.showMessage(f"Export complete: {path}")

    @Slot(str)
    def _on_export_error(self, msg: str):
        self._progress.setVisible(False)
        self._btn_export.setEnabled(True)
        self._status.showMessage(f"Export failed: {msg}")
        QMessageBox.critical(self, "Export Error", msg)

    # ── File Loading ───────────────────────────────────────────────

    @Slot()
    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", VIDEO_FILTERS)
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        self._source_path = path
        self._player.load(path)
        self._timeline.in_point = 0.0
        self._edit_start.setText(format_time(0))
        self._status.showMessage(f"Loading: {os.path.basename(path)}")

    # ── Drag & Drop ────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._load_file(path)

    # ── Close ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._poll_timer.stop()
        if self._exporter.is_running:
            self._exporter.cancel()
        self._player.closeEvent(event)
        super().closeEvent(event)
