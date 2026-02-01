import re
import shutil

from PySide6.QtCore import QObject, Signal, QProcess


# Quality presets: (format, quality_name) -> crf value
QUALITY_PRESETS = {
    ("mp4", "High"): 18,
    ("mp4", "Medium"): 23,
    ("mp4", "Low"): 28,
    ("webm", "High"): 24,
    ("webm", "Medium"): 30,
    ("webm", "Low"): 36,
}


def ffmpeg_available() -> bool:
    """Check if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS.mmm string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


class Exporter(QObject):
    """Runs ffmpeg to export a clip from a video file."""

    progress = Signal(int)  # percent 0-100
    finished = Signal(str)  # output path
    error = Signal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._total_duration = 0.0
        self._output_path = ""

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() == QProcess.Running

    def export(
        self,
        source: str,
        start: float,
        end: float,
        output_path: str,
        fmt: str = "mp4",
        quality: str = "High",
    ):
        """Start exporting a clip.

        Args:
            source: Path to the source video file.
            start: Start time in seconds.
            end: End time in seconds.
            output_path: Path for the output file.
            fmt: 'mp4' or 'webm'.
            quality: 'High', 'Medium', or 'Low'.
        """
        if self.is_running:
            self.error.emit("Export already in progress.")
            return

        self._total_duration = end - start
        self._output_path = output_path

        crf = QUALITY_PRESETS.get((fmt, quality), 23)

        duration = end - start

        args = [
            "-y",
            "-ss", format_time(start),
            "-accurate_seek",
            "-i", source,
            "-t", format_time(duration),
        ]

        if fmt == "mp4":
            args += [
                "-c:v", "libx264",
                "-crf", str(crf),
                "-c:a", "aac",
                "-b:a", "192k",
            ]
        elif fmt == "webm":
            args += [
                "-c:v", "libvpx-vp9",
                "-crf", str(crf),
                "-b:v", "0",
                "-c:a", "libopus",
                "-b:a", "128k",
            ]

        args.append(output_path)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self._process.start("ffmpeg", args)

    def cancel(self):
        """Cancel the running export."""
        if self._process and self._process.state() == QProcess.Running:
            self._process.kill()

    def _on_output(self):
        """Parse ffmpeg output for progress."""
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        # Look for time= in ffmpeg output
        match = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", data)
        if match and self._total_duration > 0:
            h, m, s, ms = match.groups()
            current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
            pct = min(100, int(current / self._total_duration * 100))
            self.progress.emit(pct)

    def _on_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self.progress.emit(100)
            self.finished.emit(self._output_path)
        else:
            self.error.emit(f"ffmpeg exited with code {exit_code}")
        self._process = None

    def _on_error(self, error):
        error_map = {
            QProcess.FailedToStart: "ffmpeg failed to start. Is it installed and on PATH?",
            QProcess.Crashed: "ffmpeg crashed.",
            QProcess.Timedout: "ffmpeg timed out.",
        }
        msg = error_map.get(error, f"ffmpeg error: {error}")
        self.error.emit(msg)
        self._process = None
