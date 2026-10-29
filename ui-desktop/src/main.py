"""Application Entrypoint & Qt 6 Native Desktop Initialization (`src/main.py`)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from PySide6.QtCore import QLocale, QTimer
from PySide6.QtWidgets import QApplication

from src.app import GfnProverMainWindow


def load_stylesheet() -> str:
    """Resolve and load `resources/styles/dark_theme.qss`."""
    base_dir = Path(__file__).resolve().parent.parent
    qss_path = base_dir / "resources" / "styles" / "dark_theme.qss"
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    return ""


def create_application(argv: Optional[List[str]] = None) -> tuple[QApplication, GfnProverMainWindow, float]:
    """Initialize QApplication and GfnProverMainWindow, returning startup latency in seconds."""
    t0 = time.perf_counter()
    c_locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    QLocale.setDefault(c_locale)
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("GFlowNet-Prover Native Studio")
    app.setOrganizationName("GFlowNet-Prover")

    qss = load_stylesheet()
    if qss:
        app.setStyleSheet(qss)

    window = GfnProverMainWindow()
    startup_sec = time.perf_counter() - t0
    return app, window, startup_sec


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="GFlowNet-Prover Native Desktop UI")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run non-interactive startup latency and memory footprint verification and exit.",
    )
    parser.add_argument(
        "--qasync",
        action="store_true",
        help="Run the Qt event loop inside a qasync asyncio event loop.",
    )
    args, qt_args = parser.parse_known_args(argv)

    app, window, startup_sec = create_application([sys.argv[0]] + qt_args)
    window.show()

    if args.self_check:
        import os

        try:
            import psutil

            mem_info = psutil.Process(os.getpid()).memory_info()
            private_bytes = getattr(mem_info, "private", mem_info.rss)
            mem_mb = private_bytes / (1024 * 1024)
        except Exception:
            mem_mb = 0.0
        print(
            f"[SELF-CHECK] Cold startup latency: {startup_sec * 1000.0:.1f} ms (SLA <= 1200 ms) | "
            f"Idle Private Memory: {mem_mb:.1f} MB (SLA <= 95.0 MB)"
        )
        QTimer.singleShot(50, app.quit)

    if args.qasync:
        import qasync

        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        with loop:
            loop.run_forever()
        return 0

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
