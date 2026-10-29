"""Syntax-highlighted Solidity PoC and Unified Git Diff Code Viewer."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class SoliditySyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Solidity smart contracts and Foundry (`vm.*`) test harnesses."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: List[Tuple[re.Pattern[str], QTextCharFormat]] = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#ff7b72"))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "pragma", "solidity", "import", "contract", "interface", "library", "is",
            "function", "returns", "return", "public", "external", "internal", "private",
            "view", "pure", "payable", "constant", "immutable", "memory", "storage",
            "calldata", "if", "else", "for", "while", "require", "assert", "revert",
            "new", "emit", "event", "struct", "mapping", "modifier", "unchecked",
        ]
        for kw in keywords:
            self._rules.append((re.compile(rf"\b{kw}\b"), kw_fmt))

        type_fmt = QTextCharFormat()
        type_fmt.setForeground(QColor("#79c0ff"))
        types = [
            "uint256", "uint128", "uint64", "uint32", "uint8", "uint",
            "int256", "int128", "address", "bool", "bytes32", "bytes", "string",
            "ether", "wei", "days", "hours", "seconds",
        ]
        for t in types:
            self._rules.append((re.compile(rf"\b{t}\b"), type_fmt))

        foundry_fmt = QTextCharFormat()
        foundry_fmt.setForeground(QColor("#d2a8ff"))
        foundry_fmt.setFontWeight(QFont.Weight.Bold)
        self._rules.append(
            (
                re.compile(r"\b(?:vm\.[a-zA-Z0-9_]+|assertEq|assertGt|assertLt|assertGe|assertLe|deal)\b"),
                foundry_fmt,
            )
        )

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#a5d6ff"))
        self._rules.append((re.compile(r"\b(?:0x[a-fA-F0-9]+|\d[\d_]*)\b"), num_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#a5d6ff"))
        self._rules.append((re.compile(r'"[^"]*"|\'[^\']*\''), str_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#8b949e"))
        self._rules.append((re.compile(r"//[^\n]*"), comment_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


class UnifiedDiffHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Unified Git Diff remediation patches."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._add_fmt = QTextCharFormat()
        self._add_fmt.setForeground(QColor("#3fb950"))
        self._add_fmt.setBackground(QColor("#0f2419"))

        self._del_fmt = QTextCharFormat()
        self._del_fmt.setForeground(QColor("#f85149"))
        self._del_fmt.setBackground(QColor("#2d1215"))

        self._hunk_fmt = QTextCharFormat()
        self._hunk_fmt.setForeground(QColor("#79c0ff"))
        self._hunk_fmt.setFontWeight(QFont.Weight.Bold)

        self._header_fmt = QTextCharFormat()
        self._header_fmt.setForeground(QColor("#d2a8ff"))
        self._header_fmt.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str) -> None:
        if text.startswith("+++") or text.startswith("---"):
            self.setFormat(0, len(text), self._header_fmt)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk_fmt)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._add_fmt)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._del_fmt)


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditorWidget) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._editor.line_number_area_paint_event(event)


class CodeEditorWidget(QPlainTextEdit):
    """Native code viewer/editor with line numbers and Solidity or Diff syntax highlighting."""

    def __init__(self, mode: str = "solidity", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self._line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)

        if mode == "diff":
            self._highlighter: QSyntaxHighlighter = UnifiedDiffHighlighter(self.document())
        else:
            self._highlighter = SoliditySyntaxHighlighter(self.document())

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#0d1117"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        painter.setPen(QColor("#484f58"))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
