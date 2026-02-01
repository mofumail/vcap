import os
import sys

# Ensure libmpv DLL can be found when placed next to this script
os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

from PySide6.QtWidgets import QApplication, QMessageBox

from vidcapt.exporter import ffmpeg_available
from vidcapt.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VidCapt")

    window = MainWindow()
    window.show()

    if not ffmpeg_available():
        QMessageBox.warning(
            window,
            "ffmpeg not found",
            "ffmpeg was not found on PATH.\n\n"
            "Video export will not work until ffmpeg is installed and available on your system PATH.",
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
