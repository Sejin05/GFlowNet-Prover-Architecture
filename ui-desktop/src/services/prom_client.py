"""Non-blocking Prometheus Telemetry Scraper (`127.0.0.1:9090/metrics` at 1 Hz)."""

from __future__ import annotations

import re
from typing import Dict, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

_METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]?Inf)$"
)


class PrometheusScraper(QObject):
    """Scrapes Prometheus metrics from `http://127.0.0.1:9090/metrics` at 1 Hz."""

    metrics_updated = Signal(dict)  # dict[metric_name, float]
    scrape_error = Signal(str)

    def __init__(
        self,
        metrics_url: str = "http://127.0.0.1:9090/metrics",
        interval_ms: int = 1000,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.metrics_url = metrics_url
        self._nam = QNetworkAccessManager(self)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.scrape_once)
        self._in_flight: bool = False

    def start_polling(self, interval_ms: Optional[int] = None) -> None:
        if interval_ms is not None:
            self._timer.setInterval(interval_ms)
        if not self._timer.isActive():
            self._timer.start()
            self.scrape_once()

    def stop_polling(self) -> None:
        self._timer.stop()

    def is_polling(self) -> bool:
        return self._timer.isActive()

    def scrape_once(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        req = QNetworkRequest(QUrl(self.metrics_url))
        req.setTransferTimeout(900)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply: QNetworkReply) -> None:
        self._in_flight = False
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                raw = reply.readAll().data().decode("utf-8", errors="replace")
                parsed = self.parse_prometheus_text(raw)
                self.metrics_updated.emit(parsed)
            else:
                self.scrape_error.emit(reply.errorString())
        except Exception as exc:
            self.scrape_error.emit(str(exc))
        finally:
            reply.deleteLater()

    @staticmethod
    def parse_prometheus_text(text: str) -> Dict[str, float]:
        """Parse standard Prometheus text exposition format into a float dictionary."""
        metrics: Dict[str, float] = {}
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = _METRIC_LINE_RE.match(s)
            if m:
                name, val_str = m.group(1), m.group(2)
                try:
                    val = float(val_str)
                    metrics[name] = val
                except ValueError:
                    continue
        return metrics
