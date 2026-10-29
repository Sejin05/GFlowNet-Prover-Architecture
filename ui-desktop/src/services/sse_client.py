"""Non-blocking QtNetwork Server-Sent Events (SSE) and REST Client for `gfn-forge serve`."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class NativeSseClient(QObject):
    """Non-blocking REST + Server-Sent Events (SSE) client on `127.0.0.1:8080`."""

    health_status_changed = Signal(bool, str)  # healthy, version_or_msg
    audit_submitted = Signal(str, dict)  # audit_id, full_response
    audit_status_updated = Signal(str, str, dict)  # audit_id, status_str, payload
    finding_discovered = Signal(dict)  # VerifiedFindingDto dict
    invariant_updated = Signal(dict)  # SynthesizedInvariantDto dict
    sse_event_received = Signal(str, dict)  # event_type, data_dict
    connection_error = Signal(str)

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self._nam = QNetworkAccessManager(self)
        self._sse_reply: Optional[QNetworkReply] = None
        self._active_audit_id: Optional[str] = None
        self._sse_buffer: str = ""
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 5

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._attempt_reconnect)

    def check_health(self) -> None:
        """Issue non-blocking `GET /health` liveness check."""
        url = QUrl(f"{self.base_url}/health")
        req = QNetworkRequest(url)
        req.setTransferTimeout(2000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_health_reply(reply))

    def _on_health_reply(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                raw = reply.readAll().data().decode("utf-8", errors="replace")
                data = json.loads(raw)
                status = str(data.get("status", "")).upper()
                version = str(data.get("version", "0.1.0"))
                self.health_status_changed.emit(status == "HEALTHY", version)
            else:
                self.health_status_changed.emit(False, reply.errorString())
        except Exception as exc:
            self.health_status_changed.emit(False, str(exc))
        finally:
            reply.deleteLater()

    def submit_audit(self, payload: Dict[str, Any]) -> None:
        """Submit `POST /v1/audits` asynchronously."""
        url = QUrl(f"{self.base_url}/v1/audits")
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = QByteArray(json.dumps(payload).encode("utf-8"))
        reply = self._nam.post(req, body)
        reply.finished.connect(lambda: self._on_submit_reply(reply))

    def _on_submit_reply(self, reply: QNetworkReply) -> None:
        try:
            raw = reply.readAll().data().decode("utf-8", errors="replace")
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = json.loads(raw)
                audit_id = str(data.get("audit_id", ""))
                self.audit_submitted.emit(audit_id, data)
                if audit_id:
                    self.connect_stream(audit_id)
            else:
                self.connection_error.emit(f"Audit submission failed: {reply.errorString()} ({raw})")
        except Exception as exc:
            self.connection_error.emit(f"Failed parsing audit response: {exc}")
        finally:
            reply.deleteLater()

    def fetch_audit_status(self, audit_id: str) -> None:
        """Poll `GET /v1/audits/:id` asynchronously."""
        url = QUrl(f"{self.base_url}/v1/audits/{audit_id}")
        req = QNetworkRequest(url)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_status_reply(audit_id, reply))

    def _on_status_reply(self, audit_id: str, reply: QNetworkReply) -> None:
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                raw = reply.readAll().data().decode("utf-8", errors="replace")
                data = json.loads(raw)
                status = str(data.get("status", "UNKNOWN"))
                self.audit_status_updated.emit(audit_id, status, data)
                for inv in data.get("synthesized_invariants", []):
                    self.invariant_updated.emit(inv)
                for finding in data.get("verified_findings", []):
                    self.finding_discovered.emit(finding)
                if "telemetry" in data and isinstance(data["telemetry"], dict):
                    self.sse_event_received.emit("telemetry_tick", data["telemetry"])
        except Exception as exc:
            self.connection_error.emit(f"Status poll error: {exc}")
        finally:
            reply.deleteLater()

    def connect_stream(self, audit_id: str) -> None:
        """Open continuous SSE connection `GET /v1/audits/:id/stream`."""
        self.disconnect_stream()
        self._active_audit_id = audit_id
        self._sse_buffer = ""

        url = QUrl(f"{self.base_url}/v1/audits/{audit_id}/stream")
        req = QNetworkRequest(url)
        req.setRawHeader(b"Accept", b"text/event-stream")
        req.setRawHeader(b"Cache-Control", b"no-cache")

        self._sse_reply = self._nam.get(req)
        self._sse_reply.readyRead.connect(self._on_sse_ready_read)
        self._sse_reply.finished.connect(self._on_sse_finished)

    def disconnect_stream(self) -> None:
        self._reconnect_timer.stop()
        if self._sse_reply is not None:
            try:
                self._sse_reply.readyRead.disconnect(self._on_sse_ready_read)
                self._sse_reply.finished.disconnect(self._on_sse_finished)
            except Exception:
                pass
            self._sse_reply.abort()
            self._sse_reply.deleteLater()
            self._sse_reply = None

    def _on_sse_ready_read(self) -> None:
        if self._sse_reply is None:
            return
        chunk = self._sse_reply.readAll().data().decode("utf-8", errors="replace")
        self._reconnect_attempts = 0
        self.feed_sse_chunk(chunk)

    def feed_sse_chunk(self, chunk: str) -> None:
        """Parse SSE stream frames (`event:` and `data:`) and emit signals."""
        self._sse_buffer += chunk.replace("\r\n", "\n")
        while "\n\n" in self._sse_buffer:
            frame, self._sse_buffer = self._sse_buffer.split("\n\n", 1)
            event_name = "message"
            data_lines = []
            for line in frame.split("\n"):
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())
            if not data_lines:
                continue
            raw_data = "\n".join(data_lines)
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                payload = {"raw": raw_data}

            # Unwrap envelope if nested {"event": ..., "data": ...}
            if isinstance(payload, dict) and "event" in payload and "data" in payload:
                event_name = str(payload["event"])
                payload = payload["data"] if isinstance(payload["data"], dict) else {"value": payload["data"]}

            self.sse_event_received.emit(event_name, payload)

            # Dispatch specialized signals
            if event_name == "finding_discovered" or "finding_id" in payload:
                self.finding_discovered.emit(payload)
            elif event_name in ("invariant_synthesized", "invariant_updated") or "invariant_id" in payload:
                self.invariant_updated.emit(payload)
            elif event_name == "status_change" or "stage" in payload or "status" in payload:
                status = str(payload.get("status") or payload.get("stage") or "EXPLORING_GFLOWNET")
                self.audit_status_updated.emit(self._active_audit_id or "", status, payload)
                if status in ("COMPLETED", "FAILED"):
                    if self._active_audit_id:
                        self.fetch_audit_status(self._active_audit_id)
                    self.disconnect_stream()

    def _on_sse_finished(self) -> None:
        if self._sse_reply is None:
            return
        err = self._sse_reply.error()
        if err != QNetworkReply.NetworkError.NoError and err != QNetworkReply.NetworkError.OperationCanceledError:
            if self._reconnect_attempts < self._max_reconnect_attempts and self._active_audit_id:
                self._reconnect_attempts += 1
                backoff_ms = min(500 * (2 ** (self._reconnect_attempts - 1)), 8000)
                self._reconnect_timer.start(backoff_ms)
            else:
                self.connection_error.emit(f"SSE stream disconnected: {self._sse_reply.errorString()}")

    def _attempt_reconnect(self) -> None:
        if self._active_audit_id:
            self.connect_stream(self._active_audit_id)
