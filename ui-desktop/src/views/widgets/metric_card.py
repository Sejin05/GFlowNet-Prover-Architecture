"""Reusable Metric Card Badge Widget (`MetricCardWidget`)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class MetricCardWidget(QFrame):
    """Compact high-contrast telemetry card for displaying real-time KPIs and SLA states."""

    def __init__(
        self,
        title: str,
        initial_value: str = "--",
        subtitle: str = "",
        accent_color: str = "#58a6ff",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self._accent_color = accent_color
        self.setStyleSheet(
            f"QFrame#CardFrame {{ background-color: #141b26; border: 1px solid #263042; "
            f"border-left: 3px solid {accent_color}; border-radius: 7px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "color: #9ecbff; font-size: 11px; font-weight: 700; letter-spacing: 0.3px;"
        )
        self.badge_label = QLabel("")
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.badge_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;"
        )
        self.badge_label.hide()
        top_row.addWidget(self.title_label)
        top_row.addStretch()
        top_row.addWidget(self.badge_label)

        self.value_label = QLabel(initial_value)
        self.value_label.setStyleSheet(
            f"color: {accent_color}; font-size: 18px; font-weight: 800; "
            "font-family: 'Cascadia Code', 'Consolas', monospace;"
        )

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 500;")

        layout.addLayout(top_row)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_value(self, value: str, subtitle: Optional[str] = None) -> None:
        self.value_label.setText(value)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)

    def set_status_badge(self, text: str, state: str = "normal") -> None:
        """Set badge state: 'normal', 'ok', 'warn', or 'alert'."""
        if not text:
            self.badge_label.hide()
            return
        self.badge_label.setText(text)
        self.badge_label.show()
        if state == "ok":
            self.badge_label.setStyleSheet(
                "background-color: #112a1d; color: #3fb950; border: 1px solid #2ea043; "
                "font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;"
            )
            self.value_label.setStyleSheet(
                f"color: {self._accent_color}; font-size: 18px; font-weight: 800; "
                "font-family: 'Cascadia Code', 'Consolas', monospace;"
            )
        elif state == "warn":
            self.badge_label.setStyleSheet(
                "background-color: #342209; color: #d29922; border: 1px solid #bb8009; "
                "font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;"
            )
            self.value_label.setStyleSheet(
                "color: #d29922; font-size: 18px; font-weight: 800; "
                "font-family: 'Cascadia Code', 'Consolas', monospace;"
            )
        elif state == "alert":
            self.badge_label.setStyleSheet(
                "background-color: #3d1316; color: #f85149; border: 1px solid #f85149; "
                "font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;"
            )
            self.value_label.setStyleSheet(
                "color: #f85149; font-size: 18px; font-weight: 800; "
                "font-family: 'Cascadia Code', 'Consolas', monospace;"
            )
        else:
            self.badge_label.setStyleSheet(
                "background-color: #1a2536; color: #79c0ff; border: 1px solid #30363d; "
                "font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;"
            )
            self.value_label.setStyleSheet(
                f"color: {self._accent_color}; font-size: 18px; font-weight: 800; "
                "font-family: 'Cascadia Code', 'Consolas', monospace;"
            )
