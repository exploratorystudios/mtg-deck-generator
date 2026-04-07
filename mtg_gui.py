#!/usr/bin/env python3
"""
MTG Commander Deck Generator — Professional GUI
Requires: PySide6 (.venv), deck_generator_commander.py, cards/commander/
Run:  .venv/bin/python mtg_gui.py
"""

from __future__ import annotations

import os
import re
import sys
import json
import math
import random
import socket
import traceback
import urllib.request as _urllib_req
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QTextEdit, QSplitter, QFrame, QScrollArea,
    QProgressBar, QTabWidget, QStatusBar, QMessageBox, QFileDialog,
    QSizePolicy, QGroupBox, QSlider, QFormLayout, QGraphicsDropShadowEffect,
    QButtonGroup, QAbstractButton, QToolButton, QStackedWidget, QCompleter,
    QMenu, QDialog, QTextBrowser,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QPropertyAnimation, QEasingCurve,
    QRect, QRectF, QSize, QPoint, QPointF, QObject, Slot, QEvent,
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QPainter, QBrush, QPen, QLinearGradient,
    QFontDatabase, QIcon, QPixmap, QClipboard, QKeySequence,
    QRadialGradient, QPainterPath, QFontMetrics, QCursor,
    QTextCursor, QTextCharFormat, QSyntaxHighlighter,
)

import deck_generator_commander as dgc


# ══════════════════════════════════════════════════════════════════════════════
# THEME / PALETTE
# ══════════════════════════════════════════════════════════════════════════════

C_BG          = QColor("#0d1117")
C_PANEL       = QColor("#161b22")
C_CARD        = QColor("#21262d")
C_BORDER      = QColor("#30363d")
C_TEXT        = QColor("#e6edf3")
C_TEXT_DIM    = QColor("#8b949e")
C_ACCENT      = QColor("#d4af37")      # gold
C_ACCENT2     = QColor("#1f6feb")      # blue
C_SUCCESS     = QColor("#3fb950")
C_ERROR       = QColor("#f85149")
C_WARNING     = QColor("#d29922")

MANA_DEFS = {
    "W": {"bg": QColor("#f5e6c8"), "fg": QColor("#1a1a1a"), "label": "W", "name": "White"},
    "U": {"bg": QColor("#0ea5e9"), "fg": QColor("#ffffff"), "label": "U", "name": "Blue"},
    "B": {"bg": QColor("#6b7280"), "fg": QColor("#f9fafb"), "label": "B", "name": "Black"},
    "R": {"bg": QColor("#dc2626"), "fg": QColor("#ffffff"), "label": "R", "name": "Red"},
    "G": {"bg": QColor("#16a34a"), "fg": QColor("#ffffff"), "label": "G", "name": "Green"},
}

# ── Predefined strategy keywords grouped by category ──────────────────────────
STRATEGY_OPTIONS: dict[str, list[str]] = {
    "Tribes": sorted([
        "angels", "birds", "cats", "clerics", "demons", "dinosaurs", "dragons",
        "elves", "faeries", "giants", "goblins", "humans", "insects", "knights",
        "merfolk", "monks", "ninjas", "pirates", "raccoons", "rogues", "samurai",
        "shamans", "snakes", "soldiers", "spirits", "vampires", "warriors",
        "wizards", "zombies",
    ]),
    "Mechanics": sorted([
        "artifacts", "enchantments", "equipment", "vehicles",
        "flashback", "escape", "unearth", "jump-start", "retrace",
        "tokens", "sacrifice", "graveyard", "reanimator",
        "spells", "prowess", "storm", "cascade",
        "counters", "proliferate", "energy", "stickers",
        "landfall", "cycling", "madness", "convoke", "improvise",
        "burn", "mill", "lifegain", "discard", "ramp",
    ]),
    "Synergies": sorted([
        "blink", "copy", "etb", "extra turns", "haste", "hexproof",
        "infinite", "looting", "protection", "recursion", "theft", "tempo",
    ]),
}

ARCHETYPE_COLORS = {
    "aggro":    QColor("#ef4444"),
    "midrange": QColor("#f59e0b"),
    "control":  QColor("#3b82f6"),
    "combo":    QColor("#a855f7"),
}

ARCHETYPE_DESCS = {
    "aggro":    "Fast, low-curve threats. Win by turn 4-5.",
    "midrange": "Value-oriented threats and interaction. Win turns 5-7.",
    "control":  "Counterspells, removal, and finishers. Win turns 8-12.",
    "combo":    "Card draw, tutors, and win conditions.",
}

RARITY_COLORS = {
    "common":   QColor("#c0c0c0"),
    "uncommon": QColor("#c0e0c0"),
    "rare":     QColor("#d4af37"),
    "mythic":   QColor("#e87c3e"),
}

ROLE_COLORS = {
    "threat":      QColor("#ef4444"),
    "removal":     QColor("#f97316"),
    "counterspell":QColor("#3b82f6"),
    "draw":        QColor("#06b6d4"),
    "disruption":  QColor("#8b5cf6"),
    "ramp":        QColor("#22c55e"),
    "tutor":       QColor("#d946ef"),
    "sweeper":     QColor("#f43f5e"),
    "utility":     QColor("#6b7280"),
    "wincon":      QColor("#fbbf24"),
}

STYLESHEET = """
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #161b22;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #484f58; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QComboBox {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e6edf3;
    selection-background-color: #1f6feb;
}
QComboBox:hover { border-color: #484f58; }
QComboBox:focus { border-color: #1f6feb; }
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8b949e;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    selection-background-color: #1f6feb;
    outline: none;
    padding: 4px;
}
QLineEdit {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e6edf3;
    selection-background-color: #1f6feb;
}
QLineEdit:hover { border-color: #484f58; }
QLineEdit:focus { border-color: #1f6feb; }
QSpinBox {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e6edf3;
}
QSpinBox:hover { border-color: #484f58; }
QSpinBox:focus { border-color: #1f6feb; }
QSpinBox::up-button, QSpinBox::down-button {
    background: #30363d;
    border-radius: 3px;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #484f58; }
QCheckBox {
    spacing: 8px;
    color: #e6edf3;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 4px;
    background: #21262d;
}
QCheckBox::indicator:hover { border-color: #484f58; }
QCheckBox::indicator:checked {
    background: #1f6feb;
    border-color: #1f6feb;
    image: none;
}
QTextEdit {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-family: "Cascadia Code", "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 12px;
    selection-background-color: #1f6feb;
    padding: 8px;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    border-radius: 6px;
    background: #161b22;
}
QTabBar::tab {
    background: #21262d;
    color: #8b949e;
    padding: 8px 18px;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: #161b22;
    color: #e6edf3;
    border-bottom: 2px solid #d4af37;
}
QTabBar::tab:hover:!selected { background: #30363d; color: #e6edf3; }
QGroupBox {
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
    color: #8b949e;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #8b949e;
    top: 4px;
    left: 12px;
}
QProgressBar {
    background: #21262d;
    border: none;
    border-radius: 4px;
    height: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #d4af37, stop:1 #f59e0b);
    border-radius: 4px;
}
QStatusBar {
    background: #161b22;
    border-top: 1px solid #30363d;
    color: #8b949e;
    font-size: 12px;
}
QSplitter::handle {
    background: #30363d;
    width: 1px;
}
QSplitter::handle:hover { background: #484f58; }
QToolTip {
    background: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
# HELPER WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet("background: #30363d; border: none;")


class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet("""
            color: #8b949e;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
            padding: 4px 0 2px 0;
        """)


class ManaButton(QPushButton):
    """Circular toggle button representing one MTG mana color."""

    SIZE = 40

    def __init__(self, color_code: str, parent=None):
        super().__init__(parent)
        self.color_code = color_code
        info = MANA_DEFS[color_code]
        self.bg_color = info["bg"]
        self.fg_color = info["fg"]
        self.label_text = info["label"]
        self.name = info["name"]

        self.setCheckable(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip(info["name"])
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()

        # Shadow / glow when checked
        if self.isChecked():
            glow = QRadialGradient(r.center(), r.width() * 0.6)
            glow_col = QColor(self.bg_color)
            glow_col.setAlpha(80)
            glow.setColorAt(0.6, glow_col)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(r, glow)

        # Circle
        pad = 4
        circle_r = r.adjusted(pad, pad, -pad, -pad)
        if self.isChecked():
            p.setBrush(QBrush(self.bg_color))
            p.setPen(QPen(self.bg_color.lighter(130), 2))
        elif self._hover:
            p.setBrush(QBrush(QColor("#30363d")))
            p.setPen(QPen(self.bg_color, 2))
        else:
            p.setBrush(QBrush(QColor("#21262d")))
            p.setPen(QPen(QColor("#30363d"), 1.5))

        p.drawEllipse(circle_r)

        # Label
        font = QFont("Beleren", 14, QFont.Bold)
        font.setBold(True)
        p.setFont(font)
        if self.isChecked():
            p.setPen(QPen(self.fg_color))
        elif self._hover:
            p.setPen(QPen(self.bg_color))
        else:
            p.setPen(QPen(QColor("#484f58")))
        p.drawText(circle_r, Qt.AlignCenter, self.label_text)


class StrategyChip(QWidget):
    """Removable keyword chip displayed inside the strategy tag area."""
    removed = Signal(str)

    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        self.keyword = keyword
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(4)

        lbl = QLabel(keyword)
        lbl.setStyleSheet("color: #d4af37; font-size: 11px; font-weight: 600;")
        layout.addWidget(lbl)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #8b949e; font-size: 14px; font-weight: 700;
                padding: 0; line-height: 14px;
            }
            QPushButton:hover { color: #f85149; }
        """)
        close_btn.clicked.connect(lambda: self.removed.emit(self.keyword))
        layout.addWidget(close_btn)

        self.setStyleSheet("""
            StrategyChip {
                background: #d4af3722;
                border: 1px solid #d4af3755;
                border-radius: 10px;
            }
        """)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setFixedHeight(24)


class StrategyWidget(QWidget):
    """
    Strategy keyword selector: dropdown of pre-defined options + custom entry,
    displayed as removable chips. Value exposed via get_strategy_string().
    """
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keywords: list[str] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Picker row ────────────────────────────────────────────────────
        picker = QHBoxLayout()
        picker.setSpacing(6)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.NoInsert)
        self._combo.lineEdit().setPlaceholderText("Pick or type a keyword…")
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Populate with grouped options
        self._combo.addItem("── Tribes ──")
        self._combo.model().item(0).setEnabled(False)
        self._combo.model().item(0).setForeground(QColor("#8b949e"))
        for kw in STRATEGY_OPTIONS["Tribes"]:
            self._combo.addItem(kw)

        self._combo.addItem("── Mechanics ──")
        idx = self._combo.count() - 1
        self._combo.model().item(idx).setEnabled(False)
        self._combo.model().item(idx).setForeground(QColor("#8b949e"))
        for kw in STRATEGY_OPTIONS["Mechanics"]:
            self._combo.addItem(kw)

        self._combo.addItem("── Synergies ──")
        idx = self._combo.count() - 1
        self._combo.model().item(idx).setEnabled(False)
        self._combo.model().item(idx).setForeground(QColor("#8b949e"))
        for kw in STRATEGY_OPTIONS["Synergies"]:
            self._combo.addItem(kw)

        self._combo.setCurrentIndex(-1)

        add_btn = QPushButton("Add")
        add_btn.setFixedSize(48, 28)
        add_btn.setCursor(QCursor(Qt.PointingHandCursor))
        add_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; border: 1px solid #d4af37;
                border-radius: 5px; color: #d4af37; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #2a2f37; }
            QPushButton:pressed { background: #1a1f27; }
        """)
        add_btn.clicked.connect(self._add_current)
        # Also add on Enter key in the combo's line edit
        self._combo.lineEdit().returnPressed.connect(self._add_current)

        picker.addWidget(self._combo)
        picker.addWidget(add_btn)
        root.addLayout(picker)

        # ── Chip area ─────────────────────────────────────────────────────
        chip_scroll = QScrollArea()
        chip_scroll.setFixedHeight(62)
        chip_scroll.setWidgetResizable(True)
        chip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_scroll.setFrameShape(QFrame.NoFrame)
        chip_scroll.setStyleSheet("""
            QScrollArea { background: #21262d; border: 1px solid #30363d; border-radius: 6px; }
        """)

        self._chip_inner = QWidget()
        self._chip_inner.setStyleSheet("background: transparent;")
        self._chip_layout = QHBoxLayout(self._chip_inner)
        self._chip_layout.setContentsMargins(6, 6, 6, 6)
        self._chip_layout.setSpacing(6)
        self._chip_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._empty_hint = QLabel("No keywords selected — deck will be general.")
        self._empty_hint.setStyleSheet("color: #484f58; font-size: 11px; font-style: italic;")
        self._chip_layout.addWidget(self._empty_hint)
        self._chip_layout.addStretch()

        chip_scroll.setWidget(self._chip_inner)
        root.addWidget(chip_scroll)

    def _add_current(self):
        text = self._combo.lineEdit().text().strip().lower()
        if not text or text.startswith("──"):
            return
        if text not in self._keywords:
            self._keywords.append(text)
            self._rebuild_chips()
            self.changed.emit(self.get_strategy_string())
        self._combo.setCurrentIndex(-1)
        self._combo.lineEdit().clear()

    def _remove(self, keyword: str):
        if keyword in self._keywords:
            self._keywords.remove(keyword)
            self._rebuild_chips()
            self.changed.emit(self.get_strategy_string())

    def _rebuild_chips(self):
        # Remove everything except the empty hint (which we recreate)
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._keywords:
            self._empty_hint = QLabel("No keywords selected — deck will be general.")
            self._empty_hint.setStyleSheet("color: #484f58; font-size: 11px; font-style: italic;")
            self._chip_layout.addWidget(self._empty_hint)
        else:
            for kw in self._keywords:
                chip = StrategyChip(kw)
                chip.removed.connect(self._remove)
                self._chip_layout.addWidget(chip)

        self._chip_layout.addStretch()

    def get_strategy_string(self) -> str:
        return " ".join(self._keywords)

    def clear(self):
        self._keywords.clear()
        self._rebuild_chips()


class SegmentedControl(QWidget):
    """Pill-style segmented control (like iOS UISegmentedControl)."""
    option_changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        """options: list of (label, value) pairs."""
        super().__init__(parent)
        self._options = options
        self._current = options[0][1] if options else ""
        self._buttons: dict[str, QPushButton] = {}
        self._build(options)

    def _build(self, options):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        container = QWidget()
        container.setFixedHeight(28)
        container.setStyleSheet("""
            QWidget {
                background: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
        """)
        cl = QHBoxLayout(container)
        cl.setContentsMargins(2, 2, 2, 2)
        cl.setSpacing(2)

        for i, (label, value) in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setChecked(i == 0)
            btn.setFixedHeight(22)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none;
                    color: #8b949e; font-size: 11px; font-weight: 600;
                    border-radius: 4px; padding: 0 10px;
                }
                QPushButton:checked {
                    background: #30363d; color: #e6edf3;
                }
                QPushButton:hover:!checked { color: #e6edf3; }
            """)
            v = value
            btn.clicked.connect(lambda _, v=v, b=btn: self._select(v, b))
            self._buttons[value] = btn
            cl.addWidget(btn)

        layout.addWidget(container)
        layout.addStretch()

    def _select(self, value: str, clicked_btn: QPushButton):
        self._current = value
        for v, btn in self._buttons.items():
            btn.setChecked(v == value)
        self.option_changed.emit(value)

    def current(self) -> str:
        return self._current


class GenerateButton(QPushButton):
    """Big animated generate button."""

    def __init__(self, parent=None):
        super().__init__("⚔  Generate Deck", parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(48)
        self._loading = False
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._update_style(False)

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def set_loading(self, val: bool):
        self._loading = val
        if val:
            self.setText("")
            self._timer.start(30)
            self._update_style(True)
        else:
            self._timer.stop()
            self.setText("⚔  Generate Deck")
            self._update_style(False)
        self.setEnabled(not val)

    def _update_style(self, loading: bool):
        if loading:
            self.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    border: 2px solid #d4af37;
                    border-radius: 8px;
                    color: #d4af37;
                    font-size: 14px;
                    font-weight: 700;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #b8960c, stop:0.5 #d4af37, stop:1 #b8960c);
                    border: none;
                    border-radius: 8px;
                    color: #1a1a1a;
                    font-size: 14px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #c8a01c, stop:0.5 #e4bf47, stop:1 #c8a01c);
                }
                QPushButton:pressed {
                    background: #a07c0a;
                    padding-top: 2px;
                }
                QPushButton:disabled {
                    background: #21262d;
                    color: #484f58;
                    border: 1px solid #30363d;
                }
            """)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._loading:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            cx = self.width() // 2
            cy = self.height() // 2
            r = 12
            p.translate(cx, cy)
            p.rotate(self._angle)
            pen = QPen(C_ACCENT, 3, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            # Draw spinning arc
            path = QPainterPath()
            path.arcMoveTo(-r, -r, 2 * r, 2 * r, 0)
            path.arcTo(-r, -r, 2 * r, 2 * r, 0, 270)
            p.drawPath(path)


class ActionButton(QPushButton):
    """Secondary action button (Copy, Save, etc.)."""

    def __init__(self, text, parent=None, primary=False):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(36)
        if primary:
            self.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    border: 1px solid #d4af37;
                    border-radius: 6px;
                    color: #d4af37;
                    font-weight: 600;
                    padding: 0 14px;
                }
                QPushButton:hover { background: #2a2f37; }
                QPushButton:pressed { background: #1a1f27; }
                QPushButton:disabled { color: #484f58; border-color: #30363d; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    color: #8b949e;
                    font-weight: 500;
                    padding: 0 14px;
                }
                QPushButton:hover { background: #2a2f37; color: #e6edf3; border-color: #484f58; }
                QPushButton:pressed { background: #1a1f27; }
                QPushButton:disabled { color: #484f58; }
            """)


# ══════════════════════════════════════════════════════════════════════════════
# MANA CURVE CHART
# ══════════════════════════════════════════════════════════════════════════════

class ManaCurveChart(QWidget):
    """Custom painted mana curve bar chart with optional ideal overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curve: dict[int, int] = {}
        self.ideal: dict[int, int] = {}
        self.archetype = "aggro"
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, curve: dict[int, int], archetype: str, curve_targets: dict | None = None):
        self.curve = curve
        raw = curve_targets if curve_targets is not None else dgc.ARCHETYPE_CONFIG[archetype]["curve_targets"]
        ideal_total = sum(raw.values())
        actual_total = max(sum(curve.values()), 1)
        self.ideal = {k: round(v / ideal_total * actual_total) for k, v in raw.items()}
        self.archetype = archetype
        self.update()

    def paintEvent(self, event):
        if not self.curve:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 16, 20, 32

        max_cmc = max(max(self.curve.keys(), default=0), 6)
        buckets = list(range(0, max_cmc + 1))
        max_count = max(max(self.curve.values(), default=1), 1)

        bar_area_w = w - pad_l - pad_r
        bar_area_h = h - pad_t - pad_b
        bar_w = bar_area_w / max(len(buckets), 1)
        bar_gap = max(bar_w * 0.18, 3)
        actual_bar_w = bar_w - bar_gap

        arch_col = ARCHETYPE_COLORS.get(self.archetype, C_ACCENT)

        # Background grid
        p.setPen(QPen(QColor("#21262d"), 1))
        for i in range(1, 5):
            y = pad_t + bar_area_h * (1 - i / 4)
            p.drawLine(int(pad_l), int(y), int(w - pad_r), int(y))

        # Y-axis label
        p.setPen(QPen(C_TEXT_DIM))
        font = QFont(); font.setPointSize(9)
        p.setFont(font)
        for i in range(1, 5):
            y = pad_t + bar_area_h * (1 - i / 4)
            label = str(round(max_count * i / 4))
            p.drawText(QRectF(0, y - 8, pad_l - 6, 16), Qt.AlignRight | Qt.AlignVCenter, label)

        # Ideal curve overlay (ghosted bars)
        if self.ideal:
            for i, cmc in enumerate(buckets):
                ideal_cnt = self.ideal.get(cmc, 0)
                if ideal_cnt == 0:
                    continue
                x = pad_l + i * bar_w + bar_gap / 2
                bar_h = (ideal_cnt / max_count) * bar_area_h
                y = pad_t + bar_area_h - bar_h
                ghost = QColor(arch_col)
                ghost.setAlpha(30)
                p.setBrush(QBrush(ghost))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x, y, actual_bar_w, bar_h), 3, 3)

        # Actual bars
        for i, cmc in enumerate(buckets):
            count = self.curve.get(cmc, 0)
            if count == 0:
                continue
            x = pad_l + i * bar_w + bar_gap / 2
            bar_h = (count / max_count) * bar_area_h
            y = pad_t + bar_area_h - bar_h

            grad = QLinearGradient(x, y, x, y + bar_h)
            col_light = QColor(arch_col).lighter(130)
            col_dark = QColor(arch_col)
            grad.setColorAt(0, col_light)
            grad.setColorAt(1, col_dark)

            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, actual_bar_w, bar_h), 3, 3)

            # Count label above bar
            p.setPen(QPen(C_TEXT))
            font2 = QFont(); font2.setPointSize(9); font2.setBold(True)
            p.setFont(font2)
            p.drawText(QRectF(x, y - 18, actual_bar_w, 16), Qt.AlignHCenter | Qt.AlignBottom, str(count))

        # X-axis labels
        p.setPen(QPen(C_TEXT_DIM))
        font3 = QFont(); font3.setPointSize(9)
        p.setFont(font3)
        for i, cmc in enumerate(buckets):
            x = pad_l + i * bar_w
            label = f"{cmc}+" if cmc >= 7 else str(cmc)
            p.drawText(QRectF(x, h - pad_b + 4, bar_w, pad_b - 4), Qt.AlignHCenter | Qt.AlignTop, label)

        # Baseline
        p.setPen(QPen(C_BORDER, 1))
        y_base = pad_t + bar_area_h
        p.drawLine(int(pad_l), int(y_base), int(w - pad_r), int(y_base))


# ══════════════════════════════════════════════════════════════════════════════
# ROLE BREAKDOWN BARS
# ══════════════════════════════════════════════════════════════════════════════

class RoleBreakdownWidget(QWidget):
    """Horizontal stacked bar showing role composition."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.roles: list[tuple[str, int]] = []
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Role distribution of nonland cards")

    def set_data(self, roles: dict[str, int]):
        total = sum(roles.values()) or 1
        self.roles = sorted(roles.items(), key=lambda x: -x[1])
        self.total = total
        self.update()

    def paintEvent(self, event):
        if not self.roles:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        total = self.total
        x = 0
        for role, count in self.roles:
            seg_w = count / total * w
            col = ROLE_COLORS.get(role, QColor("#6b7280"))
            p.setBrush(QBrush(col))
            p.setPen(Qt.NoPen)
            is_first = (x == 0)
            is_last = (x + seg_w >= w - 1)
            if is_first and is_last:
                p.drawRoundedRect(QRectF(x, 0, seg_w, h), 4, 4)
            elif is_first:
                path = QPainterPath()
                path.addRoundedRect(QRectF(x, 0, seg_w + 4, h), 4, 4)
                path.addRect(QRectF(x + seg_w - 4, 0, 4, h))
                p.drawPath(path.simplified())
            elif is_last:
                path = QPainterPath()
                path.addRoundedRect(QRectF(x - 4, 0, seg_w + 4, h), 4, 4)
                path.addRect(QRectF(x, 0, 4, h))
                p.drawPath(path.simplified())
            else:
                p.drawRect(QRectF(x, 0, seg_w, h))
            x += seg_w


# ══════════════════════════════════════════════════════════════════════════════
# STAT CARD WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class StatCard(QWidget):
    """Small card showing a label + value pair."""

    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        self._label = label
        self._value = value
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, value: str):
        self._value = value
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.setBrush(QBrush(C_CARD))
        p.setPen(QPen(C_BORDER, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        # Label
        p.setPen(QPen(C_TEXT_DIM))
        font_l = QFont(); font_l.setPointSize(9); font_l.setBold(True)
        p.setFont(font_l)
        p.drawText(QRectF(12, 8, w - 24, 18), Qt.AlignLeft | Qt.AlignVCenter, self._label.upper())

        # Value
        p.setPen(QPen(C_TEXT))
        font_v = QFont(); font_v.setPointSize(18); font_v.setBold(True)
        p.setFont(font_v)
        p.drawText(QRectF(12, 28, w - 24, 28), Qt.AlignLeft | Qt.AlignVCenter, self._value)


# ══════════════════════════════════════════════════════════════════════════════
# COLOR PIP WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class ColorPipWidget(QWidget):
    """Displays colored mana pips with percentage labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pips: dict[str, int] = {}
        self.setMinimumHeight(60)
        self.setMaximumHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, pips: dict[str, int]):
        self.pips = {c: v for c, v in pips.items() if v > 0}
        self.update()

    def paintEvent(self, event):
        if not self.pips:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        total = sum(self.pips.values()) or 1
        n = len(self.pips)
        pip_r = 18
        spacing = min(60, (w - 20) // max(n, 1))
        start_x = (w - spacing * n) // 2 + spacing // 2

        for i, (color, count) in enumerate(sorted(self.pips.items(), key=lambda x: -x[1])):
            cx = start_x + i * spacing
            cy = h // 2 - 4
            info = MANA_DEFS.get(color, {})
            bg = info.get("bg", QColor("#6b7280"))
            fg = info.get("fg", QColor("#ffffff"))

            # Outer glow
            glow = QRadialGradient(cx, cy, pip_r * 1.4)
            gc = QColor(bg)
            gc.setAlpha(40)
            glow.setColorAt(0, gc)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), pip_r * 1.4, pip_r * 1.4)

            # Circle
            p.setBrush(QBrush(bg))
            p.setPen(QPen(bg.lighter(140), 1.5))
            p.drawEllipse(QPointF(cx, cy), pip_r, pip_r)

            # Letter
            p.setPen(QPen(fg))
            font = QFont(); font.setPointSize(11); font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(cx - pip_r, cy - pip_r, pip_r * 2, pip_r * 2),
                       Qt.AlignCenter, color)

            # Percentage below
            pct = f"{count / total * 100:.0f}%"
            p.setPen(QPen(C_TEXT_DIM))
            font2 = QFont(); font2.setPointSize(8)
            p.setFont(font2)
            p.drawText(QRectF(cx - 20, cy + pip_r + 2, 40, 14), Qt.AlignCenter, pct)


# ══════════════════════════════════════════════════════════════════════════════
# DECK LIST SYNTAX HIGHLIGHTER
# ══════════════════════════════════════════════════════════════════════════════

class DeckHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor("#8b949e"))
        self._header_fmt = QTextCharFormat()
        self._header_fmt.setForeground(C_ACCENT)
        self._header_fmt.setFontWeight(QFont.Bold)
        self._count_fmt = QTextCharFormat()
        self._count_fmt.setForeground(C_ACCENT2)
        self._count_fmt.setFontWeight(QFont.Bold)

    def highlightBlock(self, text: str):
        stripped = text.strip()
        if stripped.startswith("//"):
            self.setFormat(0, len(text), self._comment_fmt)
        elif stripped in ("Deck", "Sideboard"):
            self.setFormat(0, len(text), self._header_fmt)
        elif stripped and stripped[0].isdigit():
            # Highlight the count number
            space = text.find(" ")
            if space > 0:
                self.setFormat(text.index(stripped[0]), space - text.index(stripped[0]), self._count_fmt)


# ══════════════════════════════════════════════════════════════════════════════
# MAGIC CARD RENDERER
# ══════════════════════════════════════════════════════════════════════════════

# (frame_border, art_grad_top, art_grad_bottom, textbox_bg)
_CARD_FRAME: dict[str, tuple] = {
    "W":         (QColor("#c8b89a"), QColor("#eedfc8"), QColor("#c8b080"), QColor("#f5f0e8")),
    "U":         (QColor("#2255aa"), QColor("#a0c8e8"), QColor("#5590cc"), QColor("#e4eef8")),
    "B":         (QColor("#555566"), QColor("#303040"), QColor("#181828"), QColor("#252535")),
    "R":         (QColor("#cc4422"), QColor("#f4c0a0"), QColor("#dc8048"), QColor("#f8eae0")),
    "G":         (QColor("#336633"), QColor("#b0d8a8"), QColor("#60a858"), QColor("#e4f0e0")),
    "MULTI":     (QColor("#c8a020"), QColor("#f8e480"), QColor("#c89818"), QColor("#f8f0c0")),
    "ARTIFACT":  (QColor("#8899aa"), QColor("#d0dde4"), QColor("#9ab0bc"), QColor("#e8ecf0")),
    "LAND":      (QColor("#887755"), QColor("#dcd0b8"), QColor("#a89870"), QColor("#f0ead8")),
    "COLORLESS": (QColor("#999999"), QColor("#d8d4cc"), QColor("#b4b0a8"), QColor("#ececea")),
}

_MANA_PIP: dict[str, tuple] = {
    "W": (QColor("#f5e6c8"), QColor("#2a2a2a")),
    "U": (QColor("#1a7ac4"), QColor("#ffffff")),
    "B": (QColor("#4a4a5e"), QColor("#f0f0f0")),
    "R": (QColor("#dc2626"), QColor("#ffffff")),
    "G": (QColor("#15803d"), QColor("#ffffff")),
    "C": (QColor("#c8c0b8"), QColor("#333333")),
    "S": (QColor("#a8d0e8"), QColor("#ffffff")),
}
_PIP_GENERIC = (QColor("#c8b484"), QColor("#2a2a2a"))


# ── Scryfall image support ─────────────────────────────────────────────────────

def _check_internet() -> bool:
    """Non-blocking check: try TCP connect to 8.8.8.8:53 (< 100 ms if online)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect(("8.8.8.8", 53))
        s.close()
        return True
    except OSError:
        return False


_HAS_INTERNET: bool = _check_internet()

# url → QPixmap, populated only from the main thread (via signal delivery)
_IMAGE_CACHE: dict[str, "QPixmap"] = {}
# url → waiting callbacks; prevents duplicate in-flight fetches
_FETCH_WAITERS: dict[str, list] = {}
# keep worker references alive until they finish
_ACTIVE_FETCH_WORKERS: list = []

# ── Scryfall keyword catalog (populated at startup when online) ───────────────
# Holds all official MTG keywords so oracle text can be auto-linked without
# relying solely on the local _KEYWORD_DEFS dict.
_KEYWORD_CATALOG: set[str] = set()


class _KWCatalogFetchWorker(QThread):
    """Fetch keyword-abilities, keyword-actions and ability-words from Scryfall."""
    done = Signal(set)

    _CATALOGS = ("keyword-abilities", "keyword-actions", "ability-words")

    def run(self):
        collected: set[str] = set()
        for cat in self._CATALOGS:
            try:
                url = f"https://api.scryfall.com/catalog/{cat}"
                req = _urllib_req.Request(url, headers={"User-Agent": "MTGDeckBuilder/1.0"})
                with _urllib_req.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                for kw in data.get("data", []):
                    collected.add(kw)          # keep original casing
            except Exception:
                pass
        self.done.emit(collected)


def _start_kw_catalog_fetch():
    """Launch catalog fetch worker if online; populates _KEYWORD_CATALOG on completion."""
    if not _HAS_INTERNET:
        return
    worker = _KWCatalogFetchWorker()
    _ACTIVE_FETCH_WORKERS.append(worker)

    def _on_done(kws: set):
        _KEYWORD_CATALOG.update(kws)
        try:
            _ACTIVE_FETCH_WORKERS.remove(worker)
        except ValueError:
            pass

    worker.done.connect(_on_done)
    worker.start()


def _get_image_uri(card: dict, size: str = "small", face_idx: int = 0) -> str | None:
    """Return a Scryfall image URL for the card at the requested size.
    face_idx selects which face for DFC cards (0=front, 1=back)."""
    uris = card.get("image_uris")
    if not uris and "card_faces" in card:
        faces = card.get("card_faces") or []
        if faces:
            face = faces[face_idx] if face_idx < len(faces) else faces[0]
            uris = face.get("image_uris")
    return (uris or {}).get(size)


def _get_card_face(card: dict, face_idx: int) -> dict:
    """Return a display dict for a specific face of a DFC card.
    Face-specific fields (name, oracle_text, type_line, mana_cost, image_uris,
    power, toughness, loyalty, colors) override the top-level card fields.
    For non-DFC cards, always returns the card itself."""
    faces = card.get("card_faces")
    if not faces or len(faces) <= face_idx:
        return card
    face = faces[face_idx]
    # Merge: top-level card provides defaults (color_identity, set, artist, …),
    # face-specific fields override where they exist and are non-None.
    merged = {**card}
    for k, v in face.items():
        if v is not None:
            merged[k] = v
    # Make sure image_uris points to this face's images (if face has them)
    if "image_uris" in face:
        merged["image_uris"] = face["image_uris"]
    return merged


def _is_dfc(card: dict) -> bool:
    """True if the card has a usable back face."""
    faces = card.get("card_faces")
    return bool(faces and len(faces) >= 2)


def _on_image_fetched(url: str, px: "QPixmap | None") -> None:
    """Called on the main thread when a fetch completes."""
    if px is not None and not px.isNull():
        _IMAGE_CACHE[url] = px
    for cb in _FETCH_WAITERS.pop(url, []):
        cb(px)


def request_image(url: str, callback) -> None:
    """Async image fetch. callback(QPixmap|None) is called on the main thread.
    If the image is already cached, callback is invoked immediately."""
    if url in _IMAGE_CACHE:
        callback(_IMAGE_CACHE[url])
        return
    if url in _FETCH_WAITERS:
        _FETCH_WAITERS[url].append(callback)
        return
    _FETCH_WAITERS[url] = [callback]
    w = _ImageFetchWorker(url)
    w.done.connect(_on_image_fetched)
    _ACTIVE_FETCH_WORKERS.append(w)
    w.finished.connect(lambda: _ACTIVE_FETCH_WORKERS.remove(w)
                       if w in _ACTIVE_FETCH_WORKERS else None)
    w.start()


class _ImageFetchWorker(QThread):
    """Fetch one Scryfall image URL in a background thread."""
    done = Signal(str, object)   # url, QPixmap or None

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            req = _urllib_req.Request(
                self._url,
                headers={"User-Agent": "MTGDeckBuilder/1.0 (personal tool)"}
            )
            with _urllib_req.urlopen(req, timeout=20) as resp:
                data = resp.read()
            px = QPixmap()
            px.loadFromData(data)
            self.done.emit(self._url, px if not px.isNull() else None)
        except Exception:
            self.done.emit(self._url, None)


def _card_frame_key(card: dict) -> str:
    colors = card.get("colors") or []
    tl = card.get("type_line") or ""
    if len(colors) > 1:  return "MULTI"
    if len(colors) == 1: return colors[0]
    if "Artifact" in tl: return "ARTIFACT"
    if "Land" in tl:     return "LAND"
    return "COLORLESS"


def _parse_mana_syms(cost: str) -> list[str]:
    return re.findall(r"\{([^}]+)\}", cost) if cost else []


def _clean_oracle_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\{T\}", "⟳", text)
    text = re.sub(r"\{Q\}", "↺", text)
    text = re.sub(r"\{E\}", "◈", text)
    text = re.sub(r"\{([WUBRGC])\}", r"(\1)", text)
    text = re.sub(r"\{(\d+)\}", r"\1", text)
    text = re.sub(r"\{X\}", "X", text)
    text = re.sub(r"\{([WUBRG])/([WUBRG])\}", r"(\1/\2)", text)
    text = re.sub(r"\{2/([WUBRG])\}", r"(2/\1)", text)
    text = re.sub(r"\{([WUBRG])/P\}", r"(\1P)", text)
    text = re.sub(r"\{S\}", "❄", text)
    return text


def _draw_mana_pip(p: QPainter, cx: float, cy: float, r: float, sym: str):
    bg, fg = _MANA_PIP.get(sym.upper(), _PIP_GENERIC)
    er = QRectF(cx - r, cy - r, r * 2, r * 2)
    p.setBrush(QBrush(bg))
    p.setPen(QPen(bg.darker(160), max(0.5, r * 0.12)))
    p.drawEllipse(er)
    lbl = (sym.replace("/", "") if "/" in sym else sym)[:2]
    f = QFont(); f.setPixelSize(max(5, int(r * 1.15))); f.setBold(True)
    p.setFont(f); p.setPen(QPen(fg))
    p.drawText(er, Qt.AlignCenter, lbl)


def paint_magic_card(p: QPainter, rect: QRectF, card: dict,
                     selected: bool = False, count: int = 1):
    """
    Render a single Magic card into rect. Everything scales with rect.width().
    Reference size is 160 × 224 px.
    """
    p.save()
    try:
        _paint_magic_card_impl(p, rect, card, selected, count)
    finally:
        p.restore()


def _paint_magic_card_impl(p: QPainter, rect: QRectF, card: dict,
                            selected: bool, count: int):
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    sc = w / 160.0
    fk = _card_frame_key(card)
    fcol, art0, art1, tbg = _CARD_FRAME.get(fk, _CARD_FRAME["COLORLESS"])
    dark = (fk == "B")
    white_txt = QColor("#f8f8f8")

    bw  = max(3, int(sc * 5.5))
    rad = max(6, int(sc * 10))

    # ── Outer rounded frame ────────────────────────────────────────────────────
    outer = QRectF(x + bw / 2, y + bw / 2, w - bw, h - bw)
    p.setBrush(QBrush(fcol))
    p.setPen(QPen(C_ACCENT if selected else fcol.darker(140), bw))
    p.drawRoundedRect(outer, rad, rad)

    pad = bw + 1
    ix, iy, iw = x + pad, y + pad, w - 2 * pad

    # ── Header: name + mana cost ───────────────────────────────────────────────
    hh = max(17, int(sc * 21))
    hr = QRectF(ix, iy, iw, hh)
    hbg = fcol.darker(155 if not dark else 60)
    p.setBrush(QBrush(hbg)); p.setPen(Qt.NoPen)
    p.drawRoundedRect(hr, 3, 3)
    p.drawRect(hr.adjusted(0, int(hh * 0.45), 0, 0))  # square off bottom half

    # Mana pips (right → left)
    syms = _parse_mana_syms(card.get("mana_cost") or "")
    pr = max(4, int(sc * 6.5)); pg = max(1, int(sc * 1.5))
    pcy = iy + hh / 2; prx = ix + iw - pr - 2
    for sym in reversed(syms):
        _draw_mana_pip(p, prx, pcy, pr, sym)
        prx -= pr * 2 + pg

    # Card name
    name_r = QRectF(ix + 3, iy, max(10.0, prx - ix - 1), hh)
    fn = QFont(); fn.setPixelSize(max(7, int(sc * 9))); fn.setBold(True)
    p.setFont(fn); p.setPen(QPen(white_txt))
    nm = (card.get("name") or "").split(" // ")[0]
    p.drawText(name_r, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine,
               QFontMetrics(fn).elidedText(nm, Qt.ElideRight, int(name_r.width())))

    # ── Art box ────────────────────────────────────────────────────────────────
    ah = max(45, int(sc * 75))
    ar = QRectF(ix, iy + hh, iw, ah)
    ag = QLinearGradient(ar.topLeft(), ar.bottomLeft())
    ag.setColorAt(0.0, art0); ag.setColorAt(1.0, art1)
    p.setBrush(QBrush(ag)); p.setPen(Qt.NoPen); p.drawRect(ar)

    fa_sz = max(5, int(sc * 6))
    fa = QFont(); fa.setPixelSize(fa_sz); fa.setItalic(True)
    bottom_lbl_h = fa_sz + 3

    # Content area above the bottom attribution line
    content_r = ar.adjusted(3, 3, -3, -(bottom_lbl_h + 4))

    flavor   = card.get("flavor_text") or ""
    keywords = [k for k in (card.get("keywords") or []) if k]

    if flavor:
        # Draw flavor text, word-wrapped to fit the art box
        fc = QColor("#f0ead8") if not dark else QColor("#b8b0a0")
        p.setFont(fa); p.setPen(QPen(fc))
        fm = QFontMetrics(fa)
        line_h = fa_sz + 2
        max_lines = max(1, int(content_r.height() / line_h))
        words = f'"{flavor}"'.split()
        lines: list[str] = []
        cur = ""
        max_px = int(content_r.width())
        for word in words:
            test = (cur + " " + word).strip()
            if fm.horizontalAdvance(test) <= max_px:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        dy = ar.top() + 4
        for ln in lines[:max_lines]:
            p.drawText(QRectF(ar.left() + 3, dy, iw - 6, line_h),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextSingleLine, ln)
            dy += line_h

    elif keywords:
        # Show keyword abilities as a centred block
        fk2 = QFont(); fk2.setPixelSize(max(5, int(sc * 7))); fk2.setBold(True)
        p.setFont(fk2)
        kc = QColor("#f0ead8") if not dark else QColor("#c0b8a0")
        p.setPen(QPen(kc))
        p.drawText(content_r, Qt.AlignCenter | Qt.TextWordWrap,
                   "\n".join(keywords[:4]))

    else:
        # Watermark: primary card type word, semi-transparent
        tl_words = (card.get("type_line") or "").split("—")[0].strip().split()
        wm = tl_words[-1] if tl_words else ""
        if wm:
            fwm = QFont(); fwm.setPixelSize(max(8, int(sc * 14))); fwm.setBold(True)
            wm_c = QColor(art0.lighter(115)); wm_c.setAlpha(90)
            p.setFont(fwm); p.setPen(QPen(wm_c))
            p.drawText(content_r, Qt.AlignCenter, wm)

    # Set / artist attribution at bottom of art area
    ainfo = (card.get("set") or "").upper()
    artist = card.get("artist") or ""
    if artist:
        ainfo += f" · {artist}"
    p.setFont(fa); p.setPen(QPen(fcol.lighter(185)))
    p.drawText(ar.adjusted(2, 0, -2, -2),
               Qt.AlignBottom | Qt.AlignHCenter | Qt.TextSingleLine, ainfo)

    # ── Type bar ───────────────────────────────────────────────────────────────
    th = max(13, int(sc * 16))
    tr = QRectF(ix, iy + hh + ah, iw, th)
    p.setBrush(QBrush(fcol.darker(120 if not dark else 55))); p.setPen(Qt.NoPen)
    p.drawRect(tr)

    rarity = card.get("rarity") or "common"
    rsym = {"common": "●", "uncommon": "◆", "rare": "★", "mythic": "✦"}.get(rarity, "●")
    rcol = QColor({"common": "#c0c0c0", "uncommon": "#80c880",
                   "rare": "#d4af37", "mythic": "#e87c3e"}.get(rarity, "#aaa"))
    fr = QFont(); fr.setPixelSize(max(6, int(sc * 8.5)))
    rw = int(sc * 12)
    p.setFont(fr); p.setPen(QPen(rcol))
    p.drawText(tr.adjusted(0, 0, -3, 0), Qt.AlignVCenter | Qt.AlignRight, rsym)

    ft = QFont(); ft.setPixelSize(max(5, int(sc * 7.5)))
    tl_str = card.get("type_line") or ""
    p.setFont(ft); p.setPen(QPen(white_txt))
    p.drawText(tr.adjusted(3, 0, -rw - 4, 0),
               Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine,
               QFontMetrics(ft).elidedText(tl_str, Qt.ElideRight, int(tr.width() - rw - 7)))

    # ── Text box ───────────────────────────────────────────────────────────────
    txy = iy + hh + ah + th
    txh = h - (txy - y) - bw
    txr = QRectF(ix, txy, iw, txh)
    text_bg_c = QColor(tbg)
    p.setBrush(QBrush(text_bg_c)); p.setPen(Qt.NoPen); p.drawRect(txr)

    has_cr = "Creature" in tl_str or "Vehicle" in tl_str
    has_pw = "Planeswalker" in tl_str
    ptbh = int(sc * 16) if (has_cr or has_pw) else 0

    fo = QFont(); fo.setPixelSize(max(5, int(sc * 7)))
    p.setFont(fo)
    p.setPen(QPen(QColor("#1a1a1a") if not dark else QColor("#e0e0e0")))
    p.drawText(txr.adjusted(3, 3, -3, -(ptbh + 2)),
               Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
               _clean_oracle_text(card.get("oracle_text") or ""))

    # ── Power/Toughness ────────────────────────────────────────────────────────
    if has_cr:
        pw_v = card.get("power") or "?"; tg_v = card.get("toughness") or "?"
        pbw = max(32, int(sc * 40))
        pbr = QRectF(ix + iw - pbw - 1, txy + txh - ptbh - 1, pbw, ptbh)
        p.setBrush(QBrush(text_bg_c)); p.setPen(QPen(fcol.darker(115), 1.5))
        p.drawRoundedRect(pbr, 3, 3)
        fp = QFont(); fp.setPixelSize(max(6, int(sc * 9))); fp.setBold(True)
        p.setFont(fp)
        p.setPen(QPen(QColor("#1a1a1a") if not dark else QColor("#e8e8e8")))
        p.drawText(pbr, Qt.AlignCenter, f"{pw_v}/{tg_v}")

    # ── Loyalty ────────────────────────────────────────────────────────────────
    elif has_pw:
        loy = card.get("loyalty") or ""
        if loy:
            lbw = max(22, int(sc * 28))
            lbr = QRectF(ix + iw - lbw - 1, txy + txh - ptbh - 1, lbw, ptbh)
            p.setBrush(QBrush(QColor("#1a5fa3"))); p.setPen(Qt.NoPen)
            p.drawRoundedRect(lbr, 4, 4)
            fp = QFont(); fp.setPixelSize(max(6, int(sc * 9))); fp.setBold(True)
            p.setFont(fp); p.setPen(QPen(QColor("#ffffff")))
            p.drawText(lbr, Qt.AlignCenter, str(loy))

    # ── Copy-count badge (top-left) ────────────────────────────────────────────
    if count > 1:
        br = max(8, int(sc * 10))
        bx, by = x + br + 2, y + br + 2
        p.setBrush(QBrush(C_ACCENT)); p.setPen(QPen(QColor("#1a1a1a"), 1))
        p.drawEllipse(QPointF(bx, by), br, br)
        fb = QFont(); fb.setPixelSize(max(6, int(sc * 9))); fb.setBold(True)
        p.setFont(fb); p.setPen(QPen(QColor("#1a1a1a")))
        p.drawText(QRectF(bx - br, by - br, br * 2, br * 2), Qt.AlignCenter, str(count))

    # ── DFC indicator (bottom-right) ──────────────────────────────────────────
    if card.get("card_faces") and len(card.get("card_faces", [])) >= 2:
        fi_sz = max(7, int(sc * 9))
        fi_f = QFont(); fi_f.setPixelSize(fi_sz); fi_f.setBold(True)
        fi_bg = fcol.darker(130); fi_bg.setAlpha(200)
        fi_r = QRectF(x + w - fi_sz * 2.2 - bw, y + h - fi_sz * 1.5 - bw,
                      fi_sz * 2.2, fi_sz * 1.4)
        p.setBrush(QBrush(fi_bg)); p.setPen(Qt.NoPen)
        p.drawRoundedRect(fi_r, 3, 3)
        p.setFont(fi_f); p.setPen(QPen(QColor("#e8e0d0")))
        p.drawText(fi_r, Qt.AlignCenter, "⇌")


# ══════════════════════════════════════════════════════════════════════════════
# RULES DIALOG
# ══════════════════════════════════════════════════════════════════════════════

_KEYWORD_DEFS: dict[str, str] = {
    # ── Evergreen keyword abilities ───────────────────────────────────────────
    "Deathtouch":    "Any amount of damage this creature deals to a creature is enough to destroy it.",
    "Defender":      "This creature can't attack.",
    "Double strike": "This creature deals both first-strike and regular combat damage.",
    "First strike":  "This creature deals combat damage before creatures without first strike.",
    "Flash":         "You may cast this spell any time you could cast an instant.",
    "Flying":        "This creature can't be blocked except by creatures with flying or reach.",
    "Haste":         "This creature can attack and use {T} abilities as though it didn't have summoning sickness.",
    "Hexproof":      "This permanent can't be the target of spells or abilities your opponents control.",
    "Indestructible":"Effects that say 'destroy' don't destroy this. Lethal damage doesn't destroy this creature.",
    "Lifelink":      "Damage dealt by this source also causes you to gain that much life.",
    "Menace":        "This creature can't be blocked except by two or more creatures.",
    "Protection":    "Can't be damaged, enchanted, equipped, blocked, or targeted by the quality it has protection from.",
    "Prowess":       "Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.",
    "Reach":         "This creature can block creatures with flying.",
    "Shroud":        "This permanent or player can't be the target of spells or abilities.",
    "Trample":       "Excess combat damage may be dealt to the player or planeswalker this creature is attacking.",
    "Vigilance":     "Attacking doesn't cause this creature to tap.",
    "Ward":          "Whenever this permanent becomes the target of a spell or ability an opponent controls, counter it unless that player pays the ward cost.",
    # ── Other keyword abilities ───────────────────────────────────────────────
    "Absorb":        "If a source would deal damage to this creature, prevent N of that damage.",
    "Affinity":      "This spell costs {1} less to cast for each [permanent type] you control.",
    "Aftermath":     "Cast this half of the card only from your graveyard, then exile it.",
    "Amplify":       "As this enters the battlefield, put N +1/+1 counters on it for each [creature type] card revealed from your hand.",
    "Annihilator":   "Whenever this creature attacks, defending player sacrifices N permanents.",
    "Ascend":        "If you control ten or more permanents, you get the city's blessing for the rest of the game.",
    "Assist":        "Another player can pay up to the generic mana in this spell's cost.",
    "Aura swap":     "Pay cost: Exchange this Aura with an Aura card in your hand.",
    "Awaken":        "If cast for its awaken cost, also put N +1/+1 counters on target land you control and it becomes a 0/0 Elemental creature with haste in addition to its other types.",
    "Battle cry":    "Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.",
    "Bestow":        "If cast for its bestow cost, it's an Aura spell with enchant creature. It becomes a creature again if it's not attached to a creature.",
    "Bloodthirst":   "If an opponent was dealt damage this turn, this creature enters with N +1/+1 counters.",
    "Bushido":       "Whenever this creature blocks or becomes blocked, it gets +N/+N until end of turn.",
    "Buyback":       "Pay an additional buyback cost: Put this card into your hand instead of your graveyard as it resolves.",
    "Cascade":       "When you cast this spell, exile cards from the top of your library until you exile a nonland card with lesser mana value. You may cast it without paying its mana cost. Put the rest on the bottom in a random order.",
    "Champion":      "When this enters, sacrifice it unless you exile another [type] you control. When this leaves the battlefield, that card returns.",
    "Changeling":    "This card is every creature type at all times.",
    "Cipher":        "Exile this encoded on a creature you control. Whenever that creature deals combat damage to a player, its controller may copy and cast the encoded card for free.",
    "Cleave":        "You may cast this spell for its cleave cost. If you do, remove the words in square brackets.",
    "Companion":     "If this card is your chosen companion, you may put it into your hand from outside the game for {3} once per game.",
    "Conspire":      "Tap two untapped creatures that share a color with this spell: Copy it. You may choose a new target for the copy.",
    "Convoke":       "Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.",
    "Crew":          "Tap any number of creatures with total power N or more: This Vehicle becomes an artifact creature until end of turn.",
    "Cumulative upkeep": "At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter.",
    "Cycling":       "Pay cycling cost, discard this card: Draw a card.",
    "Dash":          "You may cast this for its dash cost. If you do, it gains haste and is returned to its owner's hand at the beginning of the next end step.",
    "Decayed":       "This creature can't block. When it attacks, sacrifice it at end of combat.",
    "Delve":         "Each card you exile from your graveyard while casting this spell pays for {1}.",
    "Demonstrate":   "When you cast this spell, you may copy it. If you do, choose an opponent to also copy it.",
    "Devoid":        "This card has no color.",
    "Devour":        "As this enters, you may sacrifice any number of creatures. This enters with N +1/+1 counters on it for each creature sacrificed.",
    "Disturb":       "You may cast this card from your graveyard transformed for its disturb cost.",
    "Dredge":        "If you would draw a card, you may mill N cards instead. If you do, return this card from your graveyard to your hand.",
    "Echo":          "At the beginning of your upkeep, if this came under your control since your last upkeep, sacrifice it unless you pay its echo cost.",
    "Embalm":        "Pay cost, exile this from your graveyard: Create a token that's a copy of it except it's a white Zombie. Embalm only as a sorcery.",
    "Emerge":        "You may cast this by sacrificing a creature and paying the emerge cost reduced by that creature's mana value.",
    "Entwine":       "Choose both modes if you pay the entwine cost.",
    "Epic":          "For the rest of the game, you can't cast spells. At the beginning of each of your upkeeps, copy this spell except for its epic ability.",
    "Escalate":      "Pay the escalate cost for each mode chosen beyond the first.",
    "Escape":        "You may cast this card from your graveyard for its escape cost.",
    "Eternalize":    "Pay cost, exile this from your graveyard: Create a 4/4 black Zombie copy of it. Eternalize only as a sorcery.",
    "Evoke":         "You may cast this spell for its evoke cost. If you do, it's sacrificed when it enters the battlefield.",
    "Evolve":        "Whenever a creature enters under your control with greater power or toughness than this, put a +1/+1 counter on this creature.",
    "Exalted":       "Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn.",
    "Exploit":       "When this creature enters the battlefield, you may sacrifice a creature.",
    "Extort":        "Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain that much life.",
    "Fabricate":     "When this enters, put N +1/+1 counters on it OR create N 1/1 colorless Servo artifact creature tokens.",
    "Fading":        "This enters with N fade counters. At the beginning of your upkeep, remove a fade counter. If you can't, sacrifice it.",
    "Flanking":      "Whenever a creature without flanking blocks this creature, the blocker gets -1/-1 until end of turn.",
    "Flashback":     "You may cast this card from your graveyard for its flashback cost. Then exile it.",
    "Foretell":      "During your turn, pay {2} and exile this card face down. Cast it on a later turn for its foretell cost.",
    "Fortify":       "Attach to target land you control. Fortify only as a sorcery.",
    "Fuse":          "You may cast one or both halves of this split card from your hand.",
    "Graft":         "This enters with N +1/+1 counters. Whenever another creature enters, you may move a counter from this to it.",
    "Gravestorm":    "When you cast this spell, copy it for each permanent put into a graveyard this turn.",
    "Haunt":         "When this card is put into a graveyard after resolving, exile it haunting target creature. When the haunted creature dies, you may use this card's effect again.",
    "Hideaway":      "When this land enters, look at the top N cards, exile one face down, put the rest on the bottom in any order.",
    "Horsemanship":  "This creature can't be blocked except by creatures with horsemanship.",
    "Improvise":     "Each artifact you tap after you're done activating mana abilities pays for {1}.",
    "Infect":        "This deals damage to creatures as -1/-1 counters and to players as poison counters.",
    "Intimidate":    "This creature can't be blocked except by artifact creatures and/or creatures sharing a color with it.",
    "Jump-start":    "Cast from your graveyard by discarding a card in addition to its other costs, then exile it.",
    "Kicker":        "You may pay an additional kicker cost as you cast this spell for an additional effect.",
    "Level up":      "Pay cost: Put a level counter on this creature. Level up only as a sorcery.",
    "Living weapon": "When this Equipment enters, create a 0/0 black Phyrexian Germ creature token, then attach this to it.",
    "Madness":       "If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.",
    "Megamorph":     "Cast face down as a 2/2 creature for {3}. Turn face up for its megamorph cost and put a +1/+1 counter on it.",
    "Meld":          "Combine two specific cards into one meld card.",
    "Mentor":        "Whenever this creature attacks, put a +1/+1 counter on target attacking creature with lesser power.",
    "Miracle":       "You may cast this card for its miracle cost when you draw it, if it's the first card drawn this turn.",
    "Modular":       "This enters with N +1/+1 counters. When it dies, you may put its counters on target artifact creature.",
    "Monstrosity":   "If this creature isn't monstrous, put N +1/+1 counters on it and it becomes monstrous.",
    "Morph":         "Cast face down as a 2/2 creature for {3}. Turn face up any time for its morph cost.",
    "Mutate":        "If cast for its mutate cost, put it over or under target non-Human creature you own. They mutate into the creature on top plus all abilities from under it.",
    "Ninjutsu":      "Pay cost, return an unblocked attacker you control to hand: Put this card from your hand onto the battlefield tapped and attacking.",
    "Offering":      "Cast this any time you could cast an instant by sacrificing a [creature type] and paying the difference in mana costs.",
    "Outlast":       "Pay cost, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.",
    "Overload":      "You may cast this spell for its overload cost. If you do, change all instances of 'target' to 'each'.",
    "Partner":       "You can have two commanders if both have partner.",
    "Persist":       "When this creature dies with no -1/-1 counters, return it to the battlefield with a -1/-1 counter.",
    "Phasing":       "This phases in or out before you untap during each of your untap steps.",
    "Poisonous":     "Whenever this creature deals combat damage to a player, that player gets N poison counters.",
    "Populate":      "Create a token that's a copy of a creature token you control.",
    "Proliferate":   "Choose any number of permanents and/or players, then give each another counter of each kind they already have.",
    "Provoke":       "Whenever this attacks, you may untap target creature the defender controls and force it to block this creature if able.",
    "Rampage":       "Whenever this creature becomes blocked, it gets +N/+N for each blocking creature beyond the first.",
    "Rebound":       "If cast from hand, exile it as it resolves. At the beginning of your next upkeep, you may cast it without paying its mana cost.",
    "Reinforce":     "Pay cost, discard this card: Put N +1/+1 counters on target creature.",
    "Renown":        "When this deals combat damage to a player, if not renowned, put N +1/+1 counters on it and it becomes renowned.",
    "Replicate":     "When you cast this spell, copy it for each time you paid its replicate cost.",
    "Retrace":       "Cast from your graveyard by discarding a land in addition to its other costs.",
    "Riot":          "This creature enters with your choice of a +1/+1 counter or haste.",
    "Scavenge":      "Pay cost, exile this from your graveyard: Put +1/+1 counters equal to this card's power on target creature. Scavenge only as a sorcery.",
    "Scry":          "Look at the top N cards of your library, then put any number on the bottom and the rest on top in any order.",
    "Shadow":        "This creature can only block or be blocked by creatures with shadow.",
    "Skulk":         "This creature can't be blocked by creatures with greater power.",
    "Soulbond":      "Pair this with another unpaired creature when either enters. They remain paired as long as you control both.",
    "Soulshift":     "When this creature dies, return target Spirit card with lesser mana value from your graveyard to hand.",
    "Spectacle":     "You may cast this for its spectacle cost if an opponent lost life this turn.",
    "Splice":        "As you cast an instant or sorcery, reveal this and pay its splice cost to add its effects to that spell.",
    "Split second":  "As long as this spell is on the stack, players can't cast spells or activate non-mana abilities.",
    "Storm":         "When you cast this spell, copy it for each spell cast before it this turn.",
    "Strive":        "This spell costs more to cast for each target beyond the first.",
    "Sunburst":      "This enters with a charge counter for each color of mana spent to cast it.",
    "Support":       "Put a +1/+1 counter on each of up to N other target creatures.",
    "Surge":         "You may cast this for its surge cost if you or a teammate has cast another spell this turn.",
    "Surveil":       "Look at the top N cards of your library; put any into your graveyard and the rest on top in any order.",
    "Suspend":       "Pay suspend cost, exile with N time counters instead of casting. Remove a counter each upkeep. When the last is removed, cast it for free. If it's a creature, it has haste.",
    "Threshold":     "A bonus that applies if seven or more cards are in your graveyard.",
    "Totem armor":   "If enchanted permanent would be destroyed, instead remove all damage from it and destroy this Aura.",
    "Toxic":         "Whenever this creature deals combat damage to a player, that player gets N poison counters.",
    "Transform":     "Turn this card over to its other face.",
    "Transmute":     "Pay cost, discard this card: Search your library for a card with the same mana value, reveal it, and put it into your hand. Shuffle.",
    "Tribute":       "As this enters, an opponent may put N +1/+1 counters on it. If they don't, [effect].",
    "Undying":       "When this dies with no +1/+1 counters, return it to the battlefield with a +1/+1 counter.",
    "Unearth":       "Return this from your graveyard to the battlefield with haste. Exile it at the next end step. Unearth only as a sorcery.",
    "Unleash":       "This creature may enter with a +1/+1 counter on it. It can't block as long as it has a +1/+1 counter.",
    "Vanishing":     "This enters with N time counters. Remove a counter each upkeep. When the last is removed, sacrifice it.",
    "Wither":        "This source deals damage to creatures in the form of -1/-1 counters.",
    # ── Ability words (appear in italic on actual cards) ──────────────────────
    "Landfall":      "A triggered ability that fires whenever a land enters the battlefield under your control.",
    "Ferocious":     "A bonus that applies if you control a creature with power 4 or greater.",
    "Hellbent":      "A bonus that applies if you have no cards in hand.",
    "Heroic":        "A triggered ability that fires whenever you cast a spell that targets this creature.",
    "Metalcraft":    "A bonus that applies if you control three or more artifacts.",
    "Morbid":        "A bonus that applies if a creature died this turn.",
    "Raid":          "A bonus that applies if you attacked with a creature this turn.",
    "Revolt":        "A bonus that applies if a permanent you controlled left the battlefield this turn.",
    "Spell mastery": "A bonus that applies if there are two or more instant and/or sorcery cards in your graveyard.",
    "Tempting offer":"Starting with you, each player may [do something]. Each player who does [gains benefit].",
    "Constellation": "A triggered ability that fires whenever an enchantment enters the battlefield under your control.",
    "Formidable":    "A bonus that applies if you control creatures with total power 8 or greater.",
    "Join forces":   "Starting with you, each player may pay any amount of mana. Combine amounts for the effect.",
    "Magecraft":     "A triggered ability that fires whenever you cast or copy an instant or sorcery spell.",
    "Venture into the dungeon": "Enter the first room of a dungeon you own from outside the game, or advance through your current dungeon.",
    # ── Ixalan block ─────────────────────────────────────────────────────────
    "Explore":       "Reveal the top card of your library. Put it into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or in your graveyard.",
    "Enrage":        "A triggered ability that fires whenever this creature is dealt damage.",
    # ── Rivals of Ixalan / Core 2019 ─────────────────────────────────────────
    "Afterlife":     "When this permanent dies, create N 1/1 white and black Spirit creature tokens with flying.",
    # ── Guilds / Ravnica Allegiance ──────────────────────────────────────────
    "Addendum":      "A bonus that applies if you cast this spell during your main phase.",
    "Adapt":         "If this creature has no +1/+1 counters on it, put N +1/+1 counters on it.",
    "Amass":         "Put N +1/+1 counters on an Army you control. If you don't control one, create a 0/0 black Zombie Army creature token first.",
    "Spectacle":     "You may cast this spell for its spectacle cost rather than its mana cost if an opponent lost life this turn.",
    "Undergrowth":   "An effect that gets better based on the number of creature cards in your graveyard.",
    # ── War of the Spark / M20 ───────────────────────────────────────────────
    "Proliferate":   "Choose any number of permanents and/or players, then give each another counter of each kind they already have.",
    # ── Throne of Eldraine ───────────────────────────────────────────────────
    "Adamant":       "A bonus that applies if you spent three or more mana of a single color to cast this spell.",
    "Adventure":     "This spell has an instant or sorcery Adventure. Cast it first, exile it, then cast the creature later.",
    "Escape":        "You may cast this card from your graveyard by exiling other cards from your graveyard in addition to paying its mana cost.",
    "Food":          "A Food token is an artifact. Sacrifice it and pay {2}: You gain 3 life.",
    # ── Theros Beyond Death / Ikoria ─────────────────────────────────────────
    "Escape":        "You may cast this card from your graveyard by exiling other cards from your graveyard in addition to paying its mana cost.",
    "Escape":        "You may cast this card from your graveyard for its escape cost.",
    "Constellation": "A triggered ability that fires whenever an enchantment enters the battlefield under your control.",
    "Companion":     "If this card is your chosen companion, you may pay {3} to put it from outside the game into your hand once per game.",
    "Mutate":        "If you cast this for its mutate cost, put it over or under target non-Human creature you own. They mutate into the creature on top plus all abilities from under it.",
    "Cycling":       "Pay the cycling cost and discard this card: Draw a card.",
    # ── Zendikar Rising ──────────────────────────────────────────────────────
    "Kicker":        "You may pay an additional kicker cost as you cast this spell for an additional effect.",
    "Party":         "Your party consists of up to one each of Cleric, Rogue, Warrior, and Wizard among creatures you control.",
    "Modal double-faced": "A card with two different faces. You choose which face to cast.",
    # ── Kaldheim ─────────────────────────────────────────────────────────────
    "Boast":         "Activate this ability only if this creature attacked this turn, and only once each turn.",
    "Foretell":      "During your turn, pay {2} and exile this card face down. Cast it on a later turn for its foretell cost.",
    "Saga":          "An enchantment with chapter abilities that trigger on your draw step, one chapter at a time.",
    # ── Strixhaven ───────────────────────────────────────────────────────────
    "Magecraft":     "A triggered ability that fires whenever you cast or copy an instant or sorcery spell.",
    "Ward":          "Whenever this becomes the target of a spell or ability an opponent controls, counter it unless that player pays the ward cost.",
    "Learn":         "You may reveal a Lesson card you own from outside the game and put it into your hand, or discard a card to draw a card.",
    # ── Adventures in the Forgotten Realms / Innistrad ───────────────────────
    "Dungeon":       "A special zone card explored via Venture into the Dungeon. Three dungeons exist: Dungeon of the Mad Mage, Dungeon of the Lost Mine, and Tomb of Annihilation.",
    "Disturb":       "You may cast this card from your graveyard transformed for its disturb cost, then exile it if it would leave the battlefield.",
    "Flashback":     "You may cast this card from your graveyard for its flashback cost. Then exile it.",
    "Decayed":       "This creature can't block. When it attacks, sacrifice it at end of combat.",
    "Daybound":      "If no spells are cast on a player's turn, it becomes night. Cards with daybound transform to their nightbound face at night.",
    "Nightbound":    "This permanent is on the nightbound face. It transforms back to daybound when it becomes day.",
    "Coven":         "A bonus that applies if you control three or more creatures with different powers.",
    # ── Kamigawa: Neon Dynasty ───────────────────────────────────────────────
    "Modified":      "A creature is modified if it has a counter on it, is equipped, or is enchanted by an Aura you control.",
    "Channel":       "Discard this card: [Effect]. This is an activated ability that can only be used from your hand.",
    "Reconfigure":   "Pay the reconfigure cost: Attach to target creature you control, or unattach. Reconfigure only as a sorcery. While attached, this isn't a creature.",
    "Compleated":    "When casting this planeswalker, you may pay {P} instead of {1} for each Phyrexian mana symbol. If you do, it enters with two fewer loyalty counters.",
    # ── Streets of New Capenna ────────────────────────────────────────────────
    "Blitz":         "If you cast this for its blitz cost, it gains haste and 'When this creature dies, draw a card.' Sacrifice it at the beginning of the next end step.",
    "Casualty":      "As an additional cost, sacrifice a creature with power N or greater. When you do, copy this spell.",
    "Connive":       "Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.",
    "Hideaway":      "When this enters, look at the top N cards of your library, exile one face down, put the rest on the bottom in any order.",
    "Shield counter":"A creature with a shield counter on it is protected. The next time it would be damaged or destroyed, remove the counter instead.",
    # ── Dominaria United / Brothers' War ─────────────────────────────────────
    "Domain":        "An effect that gets better for each basic land type among lands you control (up to 5).",
    "Enlist":        "As this creature attacks, you may tap a nonattacking creature you control without summoning sickness. If you do, add its power to this creature's until end of turn.",
    "Read ahead":    "As this Saga enters, choose a chapter number. Start with that many lore counters.",
    "Unearth":       "Return this card from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step. Unearth only as a sorcery.",
    "Prototype":     "You may cast this spell with its prototype stats (smaller size and alternate mana cost) instead of its regular stats.",
    "Powerstones":   "Powerstone tokens are artifacts. Tap a Powerstone for {C}, which can only be spent on artifact spells or activated abilities of artifacts.",
    # ── Phyrexia: All Will Be One / March of the Machine ─────────────────────
    "For Mirrodin!": "When this Equipment enters the battlefield, create a 2/2 red Rebel creature token, then attach this Equipment to it.",
    "Toxic":         "Whenever this creature deals combat damage to a player, that player gets N poison counters. A player with 10 or more poison counters loses the game.",
    "Corrupted":     "A bonus that applies if an opponent has three or more poison counters.",
    "Incubate":      "Create an Incubator token with N +1/+1 counters on it. It's an artifact. Pay {2}: Transform it into a 0/0 Phyrexian artifact creature.",
    "Backup":        "When this enters, put N +1/+1 counters on target creature. If that's another creature, it gains the following abilities until end of turn: [abilities listed on card].",
    "Convoke":       "Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.",
    "Encore":        "Pay cost, exile this card from your graveyard: For each opponent, create a token copy of it that attacks that opponent this turn. Sacrifice the tokens at the next end step.",
    "Proliferate":   "Choose any number of permanents and/or players, then give each another counter of a kind already on them.",
    # ── Wilds of Eldraine ────────────────────────────────────────────────────
    "Bargain":       "You may sacrifice an artifact, enchantment, or token as you cast this spell for an additional effect.",
    "Celebration":   "A bonus that applies if two or more nonland permanents entered the battlefield under your control this turn.",
    "Role":          "Role tokens are Aura enchantments. Each creature can have only one Role. Attaching a new Role to a creature causes the old one to be sacrificed.",
    "Offspring":     "Pay cost when casting this creature spell: Create a 1/1 token copy of it when it enters the battlefield.",
    # ── Lost Caverns of Ixalan ───────────────────────────────────────────────
    "Craft":         "Pay craft cost, exile this and the other listed cards: Return this card transformed from exile. Craft only as a sorcery.",
    "Descend":       "A bonus that applies based on how many permanent cards are in your graveyard.",
    "Discover":      "Exile cards from the top of your library until you exile a nonland card with mana value N or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.",
    "Explore":       "Reveal the top card of your library. Put it into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put it back or in your graveyard.",
    "Map":           "Map tokens are artifacts. {1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.",
    # ── Murders at Karlov Manor ──────────────────────────────────────────────
    "Clue":          "Clue tokens are artifacts. {2}, Sacrifice this token: Draw a card.",
    "Collect evidence": "Exile cards with total mana value N or greater from your graveyard as an additional cost.",
    "Disguise":      "You may cast this card face down as a 2/2 creature with ward {2} for {3}. Turn it face up any time for its disguise cost.",
    "Investigate":   "Create a Clue token. It's an artifact with '{2}, Sacrifice this token: Draw a card.'",
    "Suspect":       "Suspected creatures have menace and can't block.",
    # ── Outlaws of Thunder Junction ───────────────────────────────────────────
    "Crime":         "You committed a crime whenever you target an opponent, anything an opponent controls, or a card in an opponent's graveyard.",
    "Plot":          "Pay plot cost, exile this card from your hand: Cast it without paying its mana cost on a later turn (as a sorcery).",
    "Saddle":        "Tap any number of other creatures you control with total power N or greater: This Mount becomes an artifact creature until end of turn.",
    "Spree":         "Choose one or more additional modes, each for their listed additional cost.",
    # ── Bloomburrow ──────────────────────────────────────────────────────────
    "Forage":        "Exile three cards from your graveyard and/or sacrifice a Food as part of this cost.",
    "Gift":          "You may promise a gift as you cast this spell. If you do, an opponent gains a benefit and you gain a larger effect.",
    "Offspring":     "Pay {1} more when casting this creature spell: When it enters, create a 1/1 token copy of it.",
    "Valiant":       "A bonus that applies whenever this creature becomes the target of a spell or ability you control if it has been targeted two or more times this turn.",
    "Expend":        "A bonus that applies if you've spent a certain total amount of mana this turn.",
    # ── Duskmourn: House of Horror ────────────────────────────────────────────
    "Eerie":         "A triggered ability that fires whenever an enchantment enters the battlefield under your control or you surveil.",
    "Impending":     "This enters as a non-creature permanent with N time counters. Remove a counter at the beginning of your upkeep. When the last is removed, it becomes a creature.",
    "Manifest dread":"Look at the top two cards of your library. Exile one face down as a 2/2 creature, put the other in your graveyard. You may turn the exiled card face up at any time for its mana cost (or morph/disguise cost).",
    "Room":          "A double-sided enchantment. The left door can be cast normally; the right door can be unlocked for its cost. Each side provides a separate effect.",
    "Survival":      "A triggered ability that fires at the beginning of your end step if you have less than a certain amount of life.",
}

# ── Oracle-text → HTML helpers ────────────────────────────────────────────────

_ORACLE_PIP_COLORS = {
    "W": "#e8d888", "U": "#4898e8", "B": "#c8a8e8",
    "R": "#e86848", "G": "#50c878", "C": "#c0b8a8",
}


def _fmt_oracle_seg(text: str) -> str:
    """Escape HTML in a plain segment and colorize {mana} symbols."""
    import html as _h
    t = _h.escape(text)

    def _mana(m: re.Match) -> str:
        sym = m.group(1).upper()
        c = _ORACLE_PIP_COLORS.get(sym)
        if c:
            return f'<span style="color:{c};font-weight:bold;">[{sym}]</span>'
        if re.fullmatch(r'\d+', sym) or sym in ("X", "Y", "Z"):
            return f'<span style="color:#c8a060;">{sym}</span>'
        if sym == "T":  return '<span style="color:#9090b0;">⟳</span>'
        if sym == "Q":  return '<span style="color:#9090b0;">↺</span>'
        if sym == "E":  return '<span style="color:#9090b0;">◈</span>'
        return m.group(0)

    return re.sub(r'\{([^}]+)\}', _mana, t)


def _oracle_to_html(card: dict) -> str:
    """Convert a card's oracle text to HTML with keyword abilities as clickable links."""
    import html as _h
    text = card.get("oracle_text") or ""
    if not text:
        return '<i style="color:#484f58">No oracle text.</i>'

    # Merge local definitions with the live catalog (catalog may be empty offline)
    all_kws = set(_KEYWORD_DEFS.keys()) | _KEYWORD_CATALOG
    # Collect non-overlapping keyword matches (longest keyword wins over shorter)
    kws = sorted(all_kws, key=len, reverse=True)
    matches: list[tuple[int, int, str]] = []
    used:    list[tuple[int, int]]      = []

    for kw in kws:
        pat = r'(?<![A-Za-z])' + re.escape(kw) + r'(?![A-Za-z])'
        for m in re.finditer(pat, text, re.IGNORECASE):
            s, e = m.start(), m.end()
            if not any(s < ue and e > us for us, ue in used):
                matches.append((s, e, kw))
                used.append((s, e))

    matches.sort(key=lambda x: x[0])

    parts: list[str] = []
    prev = 0
    for start, end, kw in matches:
        parts.append(_fmt_oracle_seg(text[prev:start]))
        display = _h.escape(text[start:end])
        parts.append(
            f'<a href="kw:{kw}" style="color:#58a6ff;'
            f'text-decoration:underline dotted;font-weight:600;">{display}</a>'
        )
        prev = end
    parts.append(_fmt_oracle_seg(text[prev:]))

    return "".join(parts).replace("\n", "<br>")


# ── Scryfall rulings worker ───────────────────────────────────────────────────

class _RulingsFetchWorker(QThread):
    """Fetch official WotC rulings for a card from the Scryfall API."""
    done = Signal(list)   # list of ruling dicts

    def __init__(self, card_id: str):
        super().__init__()
        self._id = card_id

    def run(self):
        try:
            url = f"https://api.scryfall.com/cards/{self._id}/rulings"
            req = _urllib_req.Request(url, headers={"User-Agent": "MTGDeckBuilder/1.0"})
            with _urllib_req.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            self.done.emit(data.get("data", []))
        except Exception:
            self.done.emit([])


# ── Live keyword definition lookup ────────────────────────────────────────────

class _KwDefFetchWorker(QThread):
    """Search Scryfall for an example card that demonstrates a keyword's reminder text."""
    done = Signal(str, str, str)  # (keyword, card_name, excerpt)

    def __init__(self, keyword: str):
        super().__init__()
        self._kw = keyword

    def run(self):
        kw = self._kw
        import urllib.parse as _up
        headers = {"User-Agent": "MTGDeckBuilder/1.0"}

        # Strategy 1: keyword search + has:reminder → get the reminder text
        try:
            q = _up.quote(f'keyword:"{kw}" has:reminder')
            url = f"https://api.scryfall.com/cards/search?q={q}&order=released&dir=asc&unique=cards"
            req = _urllib_req.Request(url, headers=headers)
            with _urllib_req.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            cards = data.get("data", [])
            if cards:
                card = cards[0]
                oracle = card.get("oracle_text") or ""
                # Extract the line(s) containing the keyword or reminder text
                excerpt = _extract_kw_excerpt(oracle, kw)
                self.done.emit(kw, card.get("name", ""), excerpt)
                return
        except Exception:
            pass

        # Strategy 2: ability-word pattern "Keyword — ..." (for ability words)
        try:
            q = _up.quote(f'o:"{kw} —"')
            url = f"https://api.scryfall.com/cards/search?q={q}&order=released&dir=asc&unique=cards"
            req = _urllib_req.Request(url, headers=headers)
            with _urllib_req.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            cards = data.get("data", [])
            if cards:
                card = cards[0]
                oracle = card.get("oracle_text") or ""
                excerpt = _extract_kw_excerpt(oracle, kw)
                self.done.emit(kw, card.get("name", ""), excerpt)
                return
        except Exception:
            pass

        # Strategy 3: plain oracle text search
        try:
            q = _up.quote(f'o:"{kw}"')
            url = f"https://api.scryfall.com/cards/search?q={q}&order=released&dir=asc&unique=cards"
            req = _urllib_req.Request(url, headers=headers)
            with _urllib_req.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            cards = data.get("data", [])
            if cards:
                card = cards[0]
                oracle = card.get("oracle_text") or ""
                excerpt = _extract_kw_excerpt(oracle, kw)
                self.done.emit(kw, card.get("name", ""), excerpt)
                return
        except Exception:
            pass

        self.done.emit(kw, "", "")


def _extract_kw_excerpt(oracle: str, kw: str) -> str:
    """Extract the most relevant line(s) from oracle text for a keyword."""
    lines = oracle.split("\n")
    kw_lower = kw.lower()
    # Lines containing the keyword (case-insensitive)
    relevant = [ln for ln in lines if kw_lower in ln.lower()]
    if relevant:
        return "\n".join(relevant)
    return oracle[:300] if oracle else ""


# ── Rules dialog ──────────────────────────────────────────────────────────────

_RULES_DLG_STYLE = """
    QDialog   { background: #0d1117; color: #e6edf3; }
    QLabel    { color: #e6edf3; }
    QGroupBox {
        color: #8b949e; font-size: 10px; font-weight: 700;
        letter-spacing: 1.2px;
        border: 1px solid #30363d; border-radius: 6px;
        margin-top: 8px; padding-top: 10px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; }
    QTextBrowser {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 6px; color: #e6edf3;
        font-size: 12px; padding: 6px;
        selection-background-color: #1f6feb;
    }
    QTextBrowser a { color: #58a6ff; }
    QPushButton {
        background: #21262d; border: 1px solid #30363d;
        border-radius: 6px; color: #e6edf3;
        padding: 6px 24px; font-size: 12px;
    }
    QPushButton:hover   { background: #30363d; }
    QPushButton:pressed { background: #1f6feb; }
    QSplitter::handle   { background: #30363d; }
"""


class RulesDialog(QDialog):
    """Modal: card oracle text with clickable keyword definitions + live Scryfall rulings."""

    def __init__(self, card: dict, parent=None):
        super().__init__(parent)
        self._card = card
        self._rulings_worker: _RulingsFetchWorker | None = None
        self._kw_def_worker: _KwDefFetchWorker | None = None
        name = (card.get("name") or "Card").split(" // ")[0]
        self.setWindowTitle(f"Rules — {name}")
        self.setMinimumSize(740, 560)
        self.resize(860, 640)
        self.setStyleSheet(_RULES_DLG_STYLE)
        self._build_ui()
        self._fetch_rulings()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        import html as _h
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        card = self._card
        name      = _h.escape((card.get("name") or "").split(" // ")[0])
        type_line = _h.escape(card.get("type_line") or "")
        mc        = _h.escape(card.get("mana_cost") or "")

        hdr = QLabel(
            f'<b style="font-size:15px;color:#e6edf3;">{name}</b>'
            f'&nbsp;&nbsp;<span style="color:#8b949e;font-size:11px;">{type_line}</span>'
            + (f'&nbsp;&nbsp;<span style="color:#c8a060;font-size:11px;">{mc}</span>' if mc else "")
        )
        hdr.setTextFormat(Qt.RichText)
        root.addWidget(hdr)

        # ── Middle: oracle text | keyword definition ───────────────────────
        mid = QSplitter(Qt.Horizontal)
        mid.setHandleWidth(4)
        mid.setChildrenCollapsible(False)

        # Left: oracle text browser
        oracle_box = QGroupBox("ORACLE TEXT")
        ob_l = QVBoxLayout(oracle_box)
        ob_l.setContentsMargins(6, 4, 6, 6)
        self._oracle_br = QTextBrowser()
        self._oracle_br.setOpenLinks(False)
        self._oracle_br.anchorClicked.connect(self._on_link)
        oracle_html = (
            f'<div style="font-family:sans-serif;font-size:12px;line-height:1.65;">'
            f'{_oracle_to_html(card)}</div>'
        )
        # Append any keywords that don't appear literally in oracle text
        # Include keywords from both local defs and live catalog
        known_kws = set(_KEYWORD_DEFS.keys()) | _KEYWORD_CATALOG
        extra = [k for k in (card.get("keywords") or [])
                 if (k in known_kws or True)  # always show card's declared keywords
                 and k.lower() not in (card.get("oracle_text") or "").lower()]
        if extra:
            links = "  ·  ".join(
                f'<a href="kw:{k}" style="color:#58a6ff;font-weight:600;">{_h.escape(k)}</a>'
                for k in extra
            )
            oracle_html += (
                f'<hr style="border:none;border-top:1px solid #30363d;margin:8px 0;">'
                f'<p style="color:#8b949e;font-size:11px;font-family:sans-serif;">'
                f'Keywords: {links}</p>'
            )
        self._oracle_br.setHtml(oracle_html)
        ob_l.addWidget(self._oracle_br)
        mid.addWidget(oracle_box)

        # Right: definition panel
        def_box = QGroupBox("KEYWORD INFO")
        db_l = QVBoxLayout(def_box)
        db_l.setContentsMargins(6, 4, 6, 6)
        self._def_br = QTextBrowser()
        self._def_br.setOpenLinks(False)
        self._def_br.setHtml(
            '<p style="color:#484f58;font-style:italic;font-size:12px;'
            'font-family:sans-serif;padding:6px;">'
            '← Click a highlighted keyword in the oracle text to see its definition.</p>'
        )
        db_l.addWidget(self._def_br)
        mid.addWidget(def_box)

        mid.setSizes([440, 300])
        root.addWidget(mid, 3)

        # ── Official rulings ───────────────────────────────────────────────
        rul_box = QGroupBox("OFFICIAL RULINGS  (Scryfall)")
        rl_l = QVBoxLayout(rul_box)
        rl_l.setContentsMargins(6, 4, 6, 6)
        self._rulings_br = QTextBrowser()
        self._rulings_br.setMaximumHeight(150)
        self._rulings_br.setHtml(
            '<p style="color:#484f58;font-style:italic;font-family:sans-serif;">'
            + ("Loading rulings…" if _HAS_INTERNET else "No internet connection — rulings unavailable.")
            + "</p>"
        )
        rl_l.addWidget(self._rulings_br)
        root.addWidget(rul_box, 1)

        # ── Close ─────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_link(self, url) -> None:
        import html as _h
        href = url.toString()
        if not href.startswith("kw:"):
            return
        kw   = href[3:]
        defn = _KEYWORD_DEFS.get(kw) or _KEYWORD_DEFS.get(kw.title())
        if defn:
            self._def_br.setHtml(
                f'<div style="font-family:sans-serif;font-size:12px;padding:6px;">'
                f'<b style="color:#58a6ff;font-size:13px;">{_h.escape(kw)}</b>'
                f'<br><br>'
                f'<span style="color:#e6edf3;line-height:1.65;">{_h.escape(defn)}</span>'
                f'</div>'
            )
        elif _HAS_INTERNET:
            # No local definition — look it up live from Scryfall
            self._def_br.setHtml(
                f'<div style="font-family:sans-serif;font-size:12px;padding:6px;">'
                f'<b style="color:#58a6ff;font-size:13px;">{_h.escape(kw)}</b>'
                f'<br><br>'
                f'<span style="color:#484f58;font-style:italic;">Searching Scryfall…</span>'
                f'</div>'
            )
            self._fetch_kw_def(kw)
        else:
            self._def_br.setHtml(
                f'<div style="font-family:sans-serif;font-size:12px;padding:6px;">'
                f'<b style="color:#58a6ff;font-size:13px;">{_h.escape(kw)}</b>'
                f'<br><br>'
                f'<span style="color:#484f58;font-style:italic;">'
                f'No local definition available (offline).</span></div>'
            )

    def _fetch_kw_def(self, kw: str) -> None:
        if self._kw_def_worker and self._kw_def_worker.isRunning():
            self._kw_def_worker.done.disconnect()
        self._kw_def_worker = _KwDefFetchWorker(kw)
        self._kw_def_worker.done.connect(self._on_kw_def)
        self._kw_def_worker.start()

    def _on_kw_def(self, kw: str, card_name: str, excerpt: str) -> None:
        import html as _h
        if excerpt:
            source = f'<br><span style="color:#484f58;font-size:10px;">via {_h.escape(card_name)}</span>' if card_name else ""
            self._def_br.setHtml(
                f'<div style="font-family:sans-serif;font-size:12px;padding:6px;">'
                f'<b style="color:#58a6ff;font-size:13px;">{_h.escape(kw)}</b>'
                f'{source}'
                f'<br><br>'
                f'<span style="color:#e6edf3;line-height:1.65;">'
                f'{_h.escape(excerpt).replace(chr(10), "<br>")}</span>'
                f'</div>'
            )
        else:
            self._def_br.setHtml(
                f'<div style="font-family:sans-serif;font-size:12px;padding:6px;">'
                f'<b style="color:#58a6ff;font-size:13px;">{_h.escape(kw)}</b>'
                f'<br><br>'
                f'<span style="color:#484f58;font-style:italic;">'
                f'No definition found on Scryfall.</span></div>'
            )

    def _fetch_rulings(self) -> None:
        if not _HAS_INTERNET:
            return
        card_id = self._card.get("id")
        if not card_id:
            return
        self._rulings_worker = _RulingsFetchWorker(card_id)
        self._rulings_worker.done.connect(self._on_rulings)
        self._rulings_worker.start()

    def _on_rulings(self, rulings: list) -> None:
        import html as _h
        if not rulings:
            self._rulings_br.setHtml(
                '<p style="color:#484f58;font-style:italic;font-family:sans-serif;">'
                'No official rulings for this card.</p>'
            )
            return
        parts = ['<div style="font-family:sans-serif;font-size:12px;line-height:1.6;">']
        for r in rulings:
            date    = _h.escape(r.get("published_at", ""))
            comment = _h.escape(r.get("comment", "")).replace("\n", "<br>")
            parts.append(
                f'<p style="margin:0 0 10px 0;">'
                f'<span style="color:#484f58;font-size:10px;">{date}</span><br>'
                f'<span style="color:#c9d1d9;">{comment}</span></p>'
            )
        parts.append('</div>')
        self._rulings_br.setHtml("".join(parts))

    def closeEvent(self, e):
        if self._rulings_worker and self._rulings_worker.isRunning():
            self._rulings_worker.quit()
            self._rulings_worker.wait(500)
        super().closeEvent(e)


class HoverCardPopup(QWidget):
    """Frameless floating popup: shows enlarged Scryfall image or painted card.
    DFC cards show a 'Right-click to flip' reminder below the card image."""
    PW, PH      = 320, 448   # total popup size
    HINT_H      = 20         # reserved height at bottom for the flip reminder

    def __init__(self):
        super().__init__(
            None,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.PW, self.PH)
        self._card: dict | None = None
        self._pixmap: "QPixmap | None" = None
        self._is_dfc: bool = False

    def show_near(self, card: dict, px: "QPixmap | None", global_pos: QPoint) -> None:
        self._card = card
        self._pixmap = px
        self._is_dfc = _is_dfc(card)
        screen = QApplication.primaryScreen().availableGeometry()
        x = global_pos.x() + 24
        y = global_pos.y() - self.PH // 2
        if x + self.PW > screen.right():
            x = global_pos.x() - self.PW - 24
        y = max(screen.top() + 4, min(y, screen.bottom() - self.PH - 4))
        self.move(x, y)
        self.update()
        self.show()
        self.raise_()

    def update_pixmap(self, px: "QPixmap | None") -> None:
        self._pixmap = px
        if self.isVisible():
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        # Card area: full height minus hint strip (hint strip only reserved when DFC)
        card_h = self.PH - (self.HINT_H if self._is_dfc else 0)
        card_rect = QRectF(0, 0, self.PW, card_h)

        path = QPainterPath()
        path.addRoundedRect(card_rect, 12, 12)
        p.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            p.drawPixmap(card_rect.toRect(), self._pixmap)
        elif self._card:
            paint_magic_card(p, card_rect, self._card)
        else:
            p.fillRect(card_rect.toRect(), QColor("#0d1117"))

        p.setClipping(False)

        # Flip reminder in the hint strip — never overlaps the card
        if self._is_dfc:
            hint_rect = QRectF(0, card_h, self.PW, self.HINT_H)
            p.fillRect(hint_rect, QColor("#0d1117"))
            fh = QFont(); fh.setPointSize(8); fh.setItalic(True)
            p.setFont(fh)
            p.setPen(QPen(QColor("#6e7681")))
            p.drawText(hint_rect, Qt.AlignCenter, "Right-click on card to flip  ⇌")


_HOVER_POPUP_INSTANCE: "HoverCardPopup | None" = None


def _hover_popup() -> HoverCardPopup:
    global _HOVER_POPUP_INSTANCE
    if _HOVER_POPUP_INSTANCE is None:
        _HOVER_POPUP_INSTANCE = HoverCardPopup()
    return _HOVER_POPUP_INSTANCE


class MagicCardWidget(QWidget):
    """Clickable card widget.
    - Shows Scryfall thumbnail when online, painted fallback otherwise.
    - Hover shows an enlarged popup.
    - Right-click on transform/DFC cards shows a menu to flip to the back face.
    """
    card_clicked = Signal(dict)   # emits the face dict currently displayed
    W, H = 160, 224

    def __init__(self, card: dict, count: int = 1, parent=None):
        super().__init__(parent)
        self.card = card          # full Scryfall card object (never mutated)
        self.count = count
        self._selected = False
        self._face_idx = 0        # 0 = front, 1 = back
        self._has_flip = _is_dfc(card)
        self._small_px: "QPixmap | None" = None
        self._normal_url: str | None = None

        self.setFixedSize(self.W, self.H)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

        # Tooltip: card name + flip hint for DFC cards
        tip = (card.get("name") or "").split(" // ")[0]
        if self._has_flip:
            tip += "\nRight-click → flip to back face"
        self.setToolTip(tip)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_hover)

        self._load_face_image()

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_face_image(self) -> None:
        """Request the small (thumbnail) image for the current face."""
        self._small_px = None
        face = _get_card_face(self.card, self._face_idx)
        self._normal_url = _get_image_uri(face, "normal", self._face_idx)
        small_url = _get_image_uri(face, "small", self._face_idx)
        if small_url:
            request_image(small_url, self._on_small_loaded)

    def _on_small_loaded(self, px: "QPixmap | None") -> None:
        if px and not px.isNull():
            self._small_px = px
            self.update()

    # ── Flip ──────────────────────────────────────────────────────────────────

    def _flip(self) -> None:
        self._face_idx = 1 - self._face_idx
        face = _get_card_face(self.card, self._face_idx)
        # Update tooltip
        tip = (face.get("name") or "").split(" // ")[0]
        tip += "\nRight-click → flip to " + ("front face" if self._face_idx == 1 else "back face")
        self.setToolTip(tip)
        self._load_face_image()
        self.update()
        if self._selected:
            self.card_clicked.emit(face)

    # ── Selection ─────────────────────────────────────────────────────────────

    def set_selected(self, v: bool):
        if self._selected != v:
            self._selected = v
            self.update()

    def _display_face(self) -> dict:
        return _get_card_face(self.card, self._face_idx)

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.card_clicked.emit(self._display_face())

    def contextMenuEvent(self, e):
        _MENU_STYLE = """
            QMenu {
                background: #161b22; border: 1px solid #30363d;
                border-radius: 6px; color: #e6edf3;
                font-size: 12px; padding: 4px;
            }
            QMenu::item { padding: 5px 18px; border-radius: 4px; }
            QMenu::item:selected { background: #1f6feb; }
            QMenu::separator { height: 1px; background: #30363d; margin: 3px 6px; }
        """
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        flip_act = None
        if self._has_flip:
            lbl = "⇌  Show back face" if self._face_idx == 0 else "⇌  Show front face"
            flip_act = menu.addAction(lbl)
            menu.addSeparator()

        rules_act = menu.addAction("📖  Rules…")

        chosen = menu.exec(e.globalPos())
        if chosen is None:
            return
        if chosen == rules_act:
            dlg = RulesDialog(self._display_face(), self)
            dlg.exec()
        elif chosen == flip_act:
            self._flip()

    def event(self, e):
        # Suppress the native Qt tooltip while the zoom popup is visible —
        # the flip reminder is shown inside the popup instead.
        if e.type() == QEvent.Type.ToolTip and _hover_popup().isVisible():
            return True
        return super().event(e)

    def enterEvent(self, e):
        self._hover_timer.start(180)

    def leaveEvent(self, e):
        self._hover_timer.stop()
        _hover_popup().hide()

    def _show_hover(self):
        popup = _hover_popup()
        gp = self.mapToGlobal(QPoint(self.W, self.H // 2))
        if self._normal_url:
            cached = _IMAGE_CACHE.get(self._normal_url)
            if cached:
                popup.show_near(self._display_face(), cached, gp)
            else:
                popup.show_near(self._display_face(), None, gp)
                request_image(
                    self._normal_url,
                    lambda px: popup.update_pixmap(px) if popup.isVisible() else None,
                )
        else:
            popup.show_near(self._display_face(), None, gp)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        if self._small_px and not self._small_px.isNull():
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 10, 10)
            p.setClipPath(path)
            p.drawPixmap(self.rect(), self._small_px)
            p.setClipping(False)

            if self._selected:
                p.setPen(QPen(C_ACCENT, 3))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 10, 10)

            if self.count > 1:
                sc = self.W / 160.0
                br = max(8, int(sc * 10))
                bx, by = br + 2, br + 2
                p.setBrush(QBrush(C_ACCENT))
                p.setPen(QPen(QColor("#1a1a1a"), 1))
                p.drawEllipse(QPointF(bx, by), br, br)
                fb = QFont(); fb.setPixelSize(max(6, int(sc * 9))); fb.setBold(True)
                p.setFont(fb); p.setPen(QPen(QColor("#1a1a1a")))
                p.drawText(QRectF(bx - br, by - br, br * 2, br * 2),
                           Qt.AlignCenter, str(self.count))

            # DFC badge over real image (bottom-right corner)
            if self._has_flip:
                fi_sz = 11
                fi_r = QRectF(self.W - fi_sz * 2.4 - 3, self.H - fi_sz * 1.6 - 3,
                              fi_sz * 2.4, fi_sz * 1.5)
                fi_bg = QColor("#1a1a2a"); fi_bg.setAlpha(200)
                p.setBrush(QBrush(fi_bg)); p.setPen(Qt.NoPen)
                p.drawRoundedRect(fi_r, 3, 3)
                ff = QFont(); ff.setPixelSize(fi_sz); ff.setBold(True)
                p.setFont(ff); p.setPen(QPen(QColor("#d0c8f0")))
                p.drawText(fi_r, Qt.AlignCenter, "⇌")
        else:
            paint_magic_card(p, QRectF(self.rect()),
                             self._display_face(), self._selected, self.count)


class CardDetailWidget(QWidget):
    """Renders a card at large size: real Scryfall image or painted fallback.
    Right-click on DFC cards flips between front and back face."""

    face_changed = Signal(dict)   # emitted when the user flips the card here

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card: dict | None = None      # full Scryfall card object
        self._face_idx = 0
        self._normal_px: "QPixmap | None" = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_card(self, card: dict | None):
        self._card = card
        self._face_idx = 0
        self._load_face()

    def _load_face(self):
        self._normal_px = None
        if self._card:
            face = _get_card_face(self._card, self._face_idx)
            url = _get_image_uri(face, "normal", self._face_idx)
            if url:
                cached = _IMAGE_CACHE.get(url)
                if cached:
                    self._normal_px = cached
                else:
                    request_image(url, self._on_image_loaded)
        self.update()

    def _on_image_loaded(self, px: "QPixmap | None") -> None:
        if px and not px.isNull():
            self._normal_px = px
            self.update()

    def contextMenuEvent(self, e):
        if not self._card:
            return
        _MENU_STYLE = """
            QMenu {
                background: #161b22; border: 1px solid #30363d;
                border-radius: 6px; color: #e6edf3;
                font-size: 12px; padding: 4px;
            }
            QMenu::item { padding: 5px 18px; border-radius: 4px; }
            QMenu::item:selected { background: #1f6feb; }
            QMenu::separator { height: 1px; background: #30363d; margin: 3px 6px; }
        """
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        flip_act = None
        if _is_dfc(self._card):
            lbl = "⇌  Show back face" if self._face_idx == 0 else "⇌  Show front face"
            flip_act = menu.addAction(lbl)
            menu.addSeparator()

        rules_act = menu.addAction("📖  Rules…")

        chosen = menu.exec(e.globalPos())
        if chosen is None:
            return
        if chosen == rules_act:
            face = _get_card_face(self._card, self._face_idx)
            dlg = RulesDialog(face, self)
            dlg.exec()
        elif chosen == flip_act:
            self._face_idx = 1 - self._face_idx
            self._load_face()
            self.face_changed.emit(_get_card_face(self._card, self._face_idx))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        if not self._card:
            p.setPen(QPen(C_TEXT_DIM))
            f = QFont(); f.setPointSize(11); f.setItalic(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "← Select a card to preview")
            return

        w, h = self.width(), self.height()
        cw = min(w - 16, int((h - 16) * 160 / 224))
        ch = int(cw * 224 / 160)
        cx = (w - cw) // 2
        cy = (h - ch) // 2

        face = _get_card_face(self._card, self._face_idx)

        if self._normal_px and not self._normal_px.isNull():
            path = QPainterPath()
            path.addRoundedRect(QRectF(cx, cy, cw, ch), 12, 12)
            p.setClipPath(path)
            p.drawPixmap(QRect(cx, cy, cw, ch), self._normal_px)
        else:
            paint_magic_card(p, QRectF(cx, cy, cw, ch), face)

        # Flip hint label for DFC cards (bottom of widget, below the card)
        if _is_dfc(self._card):
            hint = "Right-click to flip ⇌"
            fh = QFont(); fh.setPointSize(9); fh.setItalic(True)
            p.setFont(fh); p.setPen(QPen(QColor("#484f58")))
            hint_r = QRect(0, cy + ch + 4, w, 20)
            p.drawText(hint_r, Qt.AlignHCenter | Qt.AlignTop, hint)


class DeckViewerTab(QWidget):
    """Deck Viewer: scrollable card grid + card detail panel."""

    CARD_W, CARD_H, CARD_GAP = 160, 224, 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[tuple[str, dict, int]] = []
        self._card_widgets: list[MagicCardWidget] = []
        self._selected_widget: MagicCardWidget | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._reflow)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Filter bar
        bar = QWidget()
        bar.setStyleSheet("background: #161b22; border-bottom: 1px solid #30363d;")
        bar.setFixedHeight(40)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 6, 12, 6); bl.setSpacing(8)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter by name, type, or rules text…")
        self._filter.textChanged.connect(self._reflow)
        bl.addWidget(self._filter)
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#8b949e; font-size:11px; min-width:80px;")
        self._count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bl.addWidget(self._count_lbl)
        root.addWidget(bar)

        # Main splitter: grid | detail
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)

        # ── Card grid (scroll area) ───────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background:#0d1117; border:none; }")
        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:#0d1117;")
        self._grid_vbox = QVBoxLayout(self._grid_host)
        self._grid_vbox.setContentsMargins(8, 8, 8, 8)
        self._grid_vbox.setSpacing(4)
        self._grid_vbox.addStretch()
        self._scroll.setWidget(self._grid_host)
        self._splitter.addWidget(self._scroll)

        # ── Detail panel ─────────────────────────────────────────────────────
        detail = QWidget()
        detail.setMinimumWidth(190)
        detail.setStyleSheet("background:#0d1117;")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(4, 8, 8, 8); dl.setSpacing(8)
        self._detail_card = CardDetailWidget()
        self._detail_card.face_changed.connect(self._update_detail_text)
        dl.addWidget(self._detail_card, 3)
        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet("""
            QTextEdit {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #e6edf3;
                font-size: 11px;
                padding: 4px;
            }
        """)
        dl.addWidget(self._detail_text, 2)
        self._splitter.addWidget(detail)
        self._splitter.setSizes([700, 220])
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setVisible(False)
        root.addWidget(self._splitter, 1)

        # Placeholder shown before any deck is generated
        self._placeholder = QLabel("Generate a deck to view cards here.")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "color:#484f58; font-size:13px; font-style:italic;"
        )
        root.addWidget(self._placeholder)

    def set_deck(self, result: dict):
        """Populate the viewer from a generation result dict."""
        from collections import Counter as _Ctr
        entries: list[tuple[str, dict, int]] = []

        if result.get("mode") in ("brawl", "commander") and result.get("commander"):
            entries.append(("Commander", result["commander"], 1))

        # Nonlands: deduplicate, then group by type category sorted by CMC → name
        _TYPE_ORDER = [
            ("Creatures",      lambda tl: "Creature" in tl),
            ("Planeswalkers",  lambda tl: "Planeswalker" in tl),
            ("Battles",        lambda tl: "Battle" in tl),
            ("Instants",       lambda tl: "Instant" in tl),
            ("Sorceries",      lambda tl: "Sorcery" in tl),
            ("Artifacts",      lambda tl: "Artifact" in tl and "Creature" not in tl),
            ("Enchantments",   lambda tl: "Enchantment" in tl and "Creature" not in tl),
            ("Other",          lambda tl: True),
        ]

        nl_counts = _Ctr(c["name"] for c in result.get("nonlands", []))
        nl_seen: dict[str, dict] = {}
        for c in result.get("nonlands", []):
            nl_seen.setdefault(c["name"], c)

        assigned: set[str] = set()
        for group_label, predicate in _TYPE_ORDER:
            group_cards = [
                (nm, card) for nm, card in nl_seen.items()
                if nm not in assigned and predicate(card.get("type_line") or "")
            ]
            for nm, card in sorted(group_cards, key=lambda t: (dgc.get_cmc(t[1]), t[0])):
                entries.append((group_label, card, nl_counts[nm]))
                assigned.add(nm)

        # Lands: group by name with counts
        ld_counts = _Ctr(c["name"] for c in result.get("lands", []))
        ld_seen: dict[str, dict] = {}
        for c in result.get("lands", []):
            ld_seen.setdefault(c["name"], c)
        for nm in sorted(ld_seen):
            entries.append(("Lands", ld_seen[nm], ld_counts[nm]))

        self._entries = entries
        self._placeholder.setVisible(False)
        self._splitter.setVisible(True)
        self._detail_card.set_card(None)
        self._detail_text.clear()
        self._reflow()

    def _reflow(self):
        """Rebuild the card grid based on current filter text and panel width."""
        query = self._filter.text().lower().strip()
        if not self._entries:
            return

        filtered = [
            (grp, card, cnt) for grp, card, cnt in self._entries
            if not query
            or query in (card.get("name") or "").lower()
            or query in (card.get("type_line") or "").lower()
            or query in (card.get("oracle_text") or "").lower()
        ]

        # Column count from current viewport width
        avail = max(self.CARD_W + self.CARD_GAP,
                    self._scroll.viewport().width() - 16)
        cols = max(1, (avail + self.CARD_GAP) // (self.CARD_W + self.CARD_GAP))

        # Tear down existing card widgets
        for cw in self._card_widgets:
            cw.deleteLater()
        self._card_widgets.clear()
        self._selected_widget = None

        while self._grid_vbox.count() > 1:     # leave the trailing stretch
            item = self._grid_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Rebuild row by row
        current_group: str | None = None
        row_w: QWidget | None = None
        row_l: QHBoxLayout | None = None
        col = 0

        def _flush():
            nonlocal row_w, row_l, col
            if row_w is not None:
                row_l.addStretch()
                self._grid_vbox.insertWidget(self._grid_vbox.count() - 1, row_w)
            row_w = QWidget(); row_w.setStyleSheet("background:transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(self.CARD_GAP)
            col = 0

        for grp, card, cnt in filtered:
            if grp != current_group:
                _flush()
                hdr = QLabel(grp.upper())
                hdr.setStyleSheet(
                    "color:#8b949e; font-size:10px; font-weight:700;"
                    "letter-spacing:1.5px; padding:8px 0 3px 2px;"
                )
                self._grid_vbox.insertWidget(self._grid_vbox.count() - 1, hdr)
                current_group = grp

            if col >= cols:
                _flush()

            cw = MagicCardWidget(card, cnt)
            cw.card_clicked.connect(self._on_card_clicked)
            self._card_widgets.append(cw)
            row_l.addWidget(cw)
            col += 1

        _flush()    # commit last row

        shown, total = len(filtered), len(self._entries)
        self._count_lbl.setText(
            f"{shown} cards" if shown == total else f"{shown}/{total}"
        )

    def _on_card_clicked(self, card: dict):
        sender = self.sender()
        if self._selected_widget and self._selected_widget is not sender:
            self._selected_widget.set_selected(False)
        if isinstance(sender, MagicCardWidget):
            sender.set_selected(True)
            self._selected_widget = sender
        self._detail_card.set_card(card)
        self._update_detail_text(card)

    def _update_detail_text(self, card: dict):
        lines: list[str] = []
        mc  = card.get("mana_cost") or ""
        cmc = card.get("cmc")
        if mc:
            lines.append(f"Cost: {mc}  (CMC {int(cmc) if cmc is not None else '?'})")
        rarity   = (card.get("rarity") or "").capitalize()
        set_name = card.get("set_name") or (card.get("set") or "").upper()
        lines.append(f"Rarity: {rarity}  ·  {set_name}")
        artist = card.get("artist") or ""
        if artist:
            lines.append(f"Artist: {artist}")
        pw  = card.get("power");   tg  = card.get("toughness")
        loy = card.get("loyalty")
        if pw  is not None: lines.append(f"P/T: {pw}/{tg}")
        if loy is not None: lines.append(f"Loyalty: {loy}")
        col_ids = card.get("color_identity") or []
        if col_ids:
            cnames = {"W":"White","U":"Blue","B":"Black","R":"Red","G":"Green"}
            lines.append("Colors: " + ", ".join(cnames.get(c, c) for c in col_ids))
        oracle = card.get("oracle_text") or ""
        if oracle:
            lines.append(""); lines.append(oracle)
        flavor = card.get("flavor_text") or ""
        if flavor:
            lines.append(""); lines.append(f'"{flavor}"')
        self._detail_text.setPlainText("\n".join(lines))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(80)


# ══════════════════════════════════════════════════════════════════════════════
# GENERATOR WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class WorkerSignals(QObject):
    progress = Signal(str, int)      # message, percent (0-100)
    result   = Signal(dict)          # full result dict
    error    = Signal(str)           # error message


class GeneratorWorker(QThread):
    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.signals = WorkerSignals()

    def run(self):
        try:
            p = self.params
            colors  = p["colors"]
            arch      = p["archetype"]
            strat     = p["strategy"]
            rarity    = p["max_rarity"]
            seed      = p["seed"]
            no_evo    = p["no_evolve"]
            gens      = p["generations"]
            diversity = p.get("diversity", 1.0)

            if seed is not None:
                random.seed(seed)

            cfg           = dg.ARCHETYPE_CONFIG[arch]
            land_count    = p.get("land_override", cfg["land_count"])
            nonland_slots = 60 - land_count

            self.signals.progress.emit("Loading card database…", 5)
            db = dg.load_card_database()

            self.signals.progress.emit(f"Classifying {len(db):,} cards…", 15)
            tag_index = {name: dg.detect_synergy_tags(card) for name, card in db.items()}

            all_nonlands = [
                card for card in db.values()
                if not dg.is_land(card) and dg.fits_colors(card, colors)
            ]
            all_lands = [card for card in db.values() if dg.is_land(card)]
            usable_lands = [
                land for land in all_lands
                if (dg.land_produces(land) & colors) or
                   ("Basic" in (land.get("type_line") or "") and not dg.land_produces(land))
            ]

            self.signals.progress.emit(
                f"Selecting nonland cards ({nonland_slots} slots)…", 30
            )
            selected_nonlands = dg.select_nonlands(
                all_nonlands, db, tag_index, arch, colors,
                strat, nonland_slots, rarity,
                diversity=diversity,
            )

            if not no_evo:
                self.signals.progress.emit(
                    f"Evolving deck ({gens} generations)…", 55
                )
                selected_nonlands = dg.evolutionary_refine(
                    selected_nonlands, all_nonlands, db, tag_index, arch, gens,
                    max_cmc=cfg.get("max_cmc", 99),
                    strategy_words=[w for w in strat.lower().split() if w],
                    diversity=diversity,
                )

            self.signals.progress.emit("Building mana base…", 85)
            selected_lands = dg.build_mana_base(
                selected_nonlands, usable_lands, colors, land_count
            )

            self.signals.progress.emit("Assembling result…", 95)

            curve = Counter(min(int(dg.get_cmc(c)), 7) for c in selected_nonlands)
            roles_raw: Counter = Counter()
            for card in selected_nonlands:
                for role in set(dg.classify_roles(card)):
                    roles_raw[role] += 1
            roles = dict(roles_raw)

            pip_totals: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
            for card in selected_nonlands:
                mc = card.get("mana_cost") or ""
                for color, val in dg.count_pips(mc).items():
                    pip_totals[color] += val
            pips = {c: v for c, v in pip_totals.items() if v > 0}

            flat_tags: Counter = Counter()
            for name in {c["name"] for c in selected_nonlands}:
                for tag in tag_index.get(name, frozenset()):
                    flat_tags[tag] += 1
            synergies = [
                (t, c) for t, c in flat_tags.most_common()
                if dg.is_reportable_synergy(t, c, flat_tags)
            ]

            tribe_counter: Counter = Counter()
            for card in selected_nonlands:
                for sub in dg.get_subtypes(card):
                    tribe_counter[sub] += 1
            tribes = [(t, c) for t, c in tribe_counter.most_common(8) if c >= 3]

            avg_cmc = (
                sum(dg.get_cmc(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )
            avg_power = (
                sum(dg.score_power(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )
            deck_text_plain = dg.format_mtga(selected_nonlands, selected_lands)
            deck_text_arena = dg.format_mtga_arena(selected_nonlands, selected_lands)

            result = {
                "nonlands":     selected_nonlands,
                "lands":        selected_lands,
                "curve":        dict(curve),
                "roles":        roles,
                "pips":         pips,
                "synergies":    synergies,
                "tribes":       tribes,
                "avg_cmc":      avg_cmc,
                "avg_power":    avg_power,
                "deck_text":    deck_text_plain,
                "deck_text_arena": deck_text_arena,
                "total_cards":  len(selected_nonlands) + len(selected_lands),
                "archetype":    arch,
                "colors":       sorted(colors),
                "land_count":   len(selected_lands),
                "nonland_count":len(selected_nonlands),
                "card_count":   len(set(c["name"] for c in selected_nonlands + selected_lands)),
            }
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())


# ══════════════════════════════════════════════════════════════════════════════
# BRAWL SUPPORT WORKERS
# ══════════════════════════════════════════════════════════════════════════════

class CommanderLoaderWorker(QThread):
    """Load a commander list from a given generator module in a background thread."""
    loaded = Signal(list)
    error  = Signal(str)

    def __init__(self, module=None):
        super().__init__()
        self._module = module or dgc

    def run(self):
        try:
            db = self._module.load_card_database()
            commanders = self._module.get_all_commanders(db)
            self.loaded.emit(commanders)
        except Exception:
            self.error.emit(traceback.format_exc())


class BrawlGeneratorWorker(QThread):
    """Generate a 60-card Historic Brawl deck in a background thread."""

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.signals = WorkerSignals()

    def run(self):
        try:
            p = self.params
            arch           = p["archetype"]
            strat          = p["strategy"]
            rarity         = p["max_rarity"]
            seed           = p["seed"]
            no_evo         = p["no_evolve"]
            gens           = p["generations"]
            diversity      = p.get("diversity", 1.0)
            commander_name = p["commander_name"]

            if seed is not None:
                random.seed(seed)

            cfg           = dgb.ARCHETYPE_CONFIG[arch]
            land_count    = p.get("land_override", cfg["land_count"])
            nonland_slots = dgb.BRAWL_MAIN_SIZE - land_count

            self.signals.progress.emit("Loading Brawl card database…", 5)
            db = dgb.load_card_database()

            commander = db.get(commander_name)
            if commander is None:
                cn_low = commander_name.lower()
                for name, card in db.items():
                    if name.lower() == cn_low:
                        commander = card
                        break
            if commander is None:
                self.signals.error.emit(f"Commander '{commander_name}' not found in database.")
                return

            colors = dgb.get_color_identity(commander) or {"C"}

            self.signals.progress.emit(f"Classifying {len(db):,} cards…", 15)
            tag_index = {name: dgb.detect_synergy_tags(card) for name, card in db.items()}

            all_nonlands = [
                card for card in db.values()
                if not dgb.is_land(card) and dgb.fits_color_identity(card, colors)
            ]
            all_lands = [card for card in db.values() if dgb.is_land(card)]
            usable_lands = [
                land for land in all_lands
                if (dgb.land_produces(land) & colors) or
                   ("Basic" in (land.get("type_line") or "") and not dgb.land_produces(land))
            ]

            self.signals.progress.emit(
                f"Selecting nonland cards ({nonland_slots} slots)…", 30
            )
            selected_nonlands = dgb.select_nonlands(
                all_nonlands, db, tag_index, arch, colors,
                strat, nonland_slots, rarity,
                diversity=diversity,
                commander=commander,
            )

            if not no_evo:
                self.signals.progress.emit(
                    f"Evolving deck ({gens} generations)…", 55
                )
                selected_nonlands = dgb.evolutionary_refine(
                    selected_nonlands, all_nonlands, db, tag_index, arch, gens,
                    max_cmc=cfg.get("max_cmc", 99),
                    strategy_words=[w for w in strat.lower().split() if w],
                    diversity=diversity,
                    commander=commander,
                    land_count=land_count,
                )

            self.signals.progress.emit("Building mana base…", 85)
            selected_lands = dgb.build_mana_base(
                selected_nonlands, usable_lands, colors, land_count
            )

            self.signals.progress.emit("Assembling result…", 95)

            curve = Counter(min(int(dgb.get_cmc(c)), 7) for c in selected_nonlands)
            roles_raw: Counter = Counter()
            for card in selected_nonlands:
                for role in set(dgb.classify_roles(card)):
                    roles_raw[role] += 1
            roles = dict(roles_raw)

            pip_totals: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
            for card in selected_nonlands:
                mc = card.get("mana_cost") or ""
                for color, val in dgb.count_pips(mc).items():
                    pip_totals[color] += val
            pips = {c: v for c, v in pip_totals.items() if v > 0}

            flat_tags: Counter = Counter()
            for name in {c["name"] for c in selected_nonlands}:
                for tag in tag_index.get(name, frozenset()):
                    flat_tags[tag] += 1
            synergies = [
                (t, c) for t, c in flat_tags.most_common()
                if dgb.is_reportable_synergy(t, c, flat_tags)
            ]

            tribe_counter: Counter = Counter()
            for card in selected_nonlands:
                for sub in dgb.get_subtypes(card):
                    tribe_counter[sub] += 1
            tribes = [(t, c) for t, c in tribe_counter.most_common(8) if c >= 3]

            avg_cmc = (
                sum(dgb.get_cmc(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )
            avg_power = (
                sum(dgb.score_power(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )

            deck_text_plain = dgb.format_brawl(commander, selected_nonlands, selected_lands)
            deck_text_arena = dgb.format_brawl_arena(commander, selected_nonlands, selected_lands)

            result = {
                "mode":          "brawl",
                "commander":     commander,
                "nonlands":      selected_nonlands,
                "lands":         selected_lands,
                "curve":         dict(curve),
                "curve_targets": cfg["curve_targets"],
                "roles":         roles,
                "pips":          pips,
                "synergies":     synergies,
                "tribes":        tribes,
                "avg_cmc":       avg_cmc,
                "avg_power":     avg_power,
                "deck_text":     deck_text_plain,
                "deck_text_arena": deck_text_arena,
                "total_cards":   1 + len(selected_nonlands) + len(selected_lands),
                "archetype":     arch,
                "colors":        sorted(colors),
                "land_count":    len(selected_lands),
                "nonland_count": len(selected_nonlands),
                "card_count":    1 + len(set(c["name"] for c in selected_nonlands + selected_lands)),
            }
            self.signals.result.emit(result)

        except Exception:
            self.signals.error.emit(traceback.format_exc())


class CommanderGeneratorWorker(QThread):
    """Generate a 100-card Commander deck in a background thread."""

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.signals = WorkerSignals()

    def run(self):
        try:
            p = self.params
            arch           = p["archetype"]
            strat          = p["strategy"]
            rarity         = p["max_rarity"]
            seed           = p["seed"]
            no_evo         = p["no_evolve"]
            gens           = p["generations"]
            diversity      = p.get("diversity", 1.0)
            commander_name = p["commander_name"]

            if seed is not None:
                random.seed(seed)

            cfg           = dgc.ARCHETYPE_CONFIG[arch]
            land_count    = p.get("land_override", cfg["land_count"])
            nonland_slots = dgc.COMMANDER_MAIN_SIZE - land_count

            self.signals.progress.emit("Loading Commander card database…", 5)
            db = dgc.load_card_database()

            commander = db.get(commander_name)
            if commander is None:
                cn_low = commander_name.lower()
                for name, card in db.items():
                    if name.lower() == cn_low:
                        commander = card
                        break
            if commander is None:
                self.signals.error.emit(f"Commander '{commander_name}' not found in database.")
                return

            colors = dgc.get_color_identity(commander) or {"C"}

            self.signals.progress.emit(f"Classifying {len(db):,} cards…", 15)
            tag_index = {name: dgc.detect_synergy_tags(card) for name, card in db.items()}

            all_nonlands = [
                card for card in db.values()
                if not dgc.is_land(card) and dgc.fits_color_identity(card, colors)
            ]
            all_lands = [card for card in db.values() if dgc.is_land(card)]
            usable_lands = [
                land for land in all_lands
                if (dgc.land_produces(land) & colors) or
                   ("Basic" in (land.get("type_line") or "") and not dgc.land_produces(land))
            ]

            self.signals.progress.emit(
                f"Selecting nonland cards ({nonland_slots} slots)…", 30
            )
            selected_nonlands = dgc.select_nonlands(
                all_nonlands, db, tag_index, arch, colors,
                strat, nonland_slots, rarity,
                diversity=diversity,
                commander=commander,
            )

            if not no_evo:
                self.signals.progress.emit(
                    f"Evolving deck ({gens} generations)…", 55
                )
                selected_nonlands = dgc.evolutionary_refine(
                    selected_nonlands, all_nonlands, db, tag_index, arch, gens,
                    max_cmc=cfg.get("max_cmc", 99),
                    strategy_words=[w for w in strat.lower().split() if w],
                    diversity=diversity,
                    commander=commander,
                    land_count=land_count,
                )

            self.signals.progress.emit("Building mana base…", 85)
            selected_lands = dgc.build_mana_base(
                selected_nonlands, usable_lands, colors, land_count
            )

            self.signals.progress.emit("Assembling result…", 95)

            curve = Counter(min(int(dgc.get_cmc(c)), 7) for c in selected_nonlands)
            roles_raw: Counter = Counter()
            for card in selected_nonlands:
                for role in set(dgc.classify_roles(card)):
                    roles_raw[role] += 1
            roles = dict(roles_raw)

            pip_totals: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
            for card in selected_nonlands:
                mc = card.get("mana_cost") or ""
                for color, val in dgc.count_pips(mc).items():
                    pip_totals[color] += val
            pips = {c: v for c, v in pip_totals.items() if v > 0}

            flat_tags: Counter = Counter()
            for name in {c["name"] for c in selected_nonlands}:
                for tag in tag_index.get(name, frozenset()):
                    flat_tags[tag] += 1
            synergies = [
                (t, c) for t, c in flat_tags.most_common()
                if dgc.is_reportable_synergy(t, c, flat_tags)
            ]

            tribe_counter: Counter = Counter()
            for card in selected_nonlands:
                for sub in dgc.get_subtypes(card):
                    tribe_counter[sub] += 1
            tribes = [(t, c) for t, c in tribe_counter.most_common(8) if c >= 3]

            avg_cmc = (
                sum(dgc.get_cmc(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )
            avg_power = (
                sum(dgc.score_power(c) for c in selected_nonlands)
                / max(len(selected_nonlands), 1)
            )

            deck_text_plain = dgc.format_commander(commander, selected_nonlands, selected_lands)
            deck_text_arena = dgc.format_commander_arena(commander, selected_nonlands, selected_lands)

            result = {
                "mode":          "commander",
                "commander":     commander,
                "nonlands":      selected_nonlands,
                "lands":         selected_lands,
                "curve":         dict(curve),
                "curve_targets": cfg["curve_targets"],
                "roles":         roles,
                "pips":          pips,
                "synergies":     synergies,
                "tribes":        tribes,
                "avg_cmc":       avg_cmc,
                "avg_power":     avg_power,
                "deck_text":     deck_text_plain,
                "deck_text_arena": deck_text_arena,
                "total_cards":   1 + len(selected_nonlands) + len(selected_lands),
                "archetype":     arch,
                "colors":        sorted(colors),
                "land_count":    len(selected_lands),
                "nonland_count": len(selected_nonlands),
                "card_count":    1 + len(set(c["name"] for c in selected_nonlands + selected_lands)),
            }
            self.signals.result.emit(result)

        except Exception:
            self.signals.error.emit(traceback.format_exc())


# ══════════════════════════════════════════════════════════════════════════════
# LEFT PANEL — PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════

class LeftPanel(QWidget):
    generate_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("background: #161b22; border-bottom: 1px solid #30363d;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(20, 12, 20, 12)
        title = QLabel("Commander Deck Generator")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #d4af37; letter-spacing: 0.3px;")
        subtitle = QLabel("EDH / Commander · Procedural")
        subtitle.setStyleSheet("font-size: 11px; color: #8b949e;")
        hl.addWidget(title)
        hl.addWidget(subtitle)
        root.addWidget(header)

        # ── Scrollable settings ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setContentsMargins(16, 16, 16, 8)
        form.setSpacing(16)

        # ── Commander ──────────────────────────────────────────────────────
        self._cmd_section = QWidget()
        _cmd_layout = QVBoxLayout(self._cmd_section)
        _cmd_layout.setContentsMargins(0, 0, 0, 0)
        _cmd_layout.setSpacing(8)

        _cmd_layout.addWidget(SectionLabel("Commander"))
        self._cmd_combo = QComboBox()
        self._cmd_combo.setEditable(True)
        self._cmd_combo.setInsertPolicy(QComboBox.NoInsert)
        self._cmd_combo.lineEdit().setPlaceholderText("Select or search for a commander…")
        self._cmd_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._cmd_combo.addItem("Loading commanders…")
        self._cmd_combo.setEnabled(False)
        _cmd_layout.addWidget(self._cmd_combo)

        self._cmd_identity_lbl = QLabel("")
        self._cmd_identity_lbl.setStyleSheet("color: #8b949e; font-size: 11px; padding: 2px 0;")
        _cmd_layout.addWidget(self._cmd_identity_lbl)

        self._commander_data: list[dict] = []
        self._commanders_loaded = False
        self._cmd_loader: object | None = None
        self._cmd_combo.currentIndexChanged.connect(self._on_commander_changed)
        form.addWidget(self._cmd_section)

        form.addWidget(Divider())

        # ── Archetype ─────────────────────────────────────────────────────
        form.addWidget(SectionLabel("Archetype"))
        self.archetype_combo = QComboBox()
        for arch in ("aggro", "midrange", "control", "combo"):
            self.archetype_combo.addItem(arch.capitalize(), arch)
        form.addWidget(self.archetype_combo)

        self.archetype_desc = QLabel(ARCHETYPE_DESCS["aggro"])
        self.archetype_desc.setWordWrap(True)
        self.archetype_desc.setStyleSheet("color: #8b949e; font-size: 11px; padding: 2px 0;")
        self.archetype_combo.currentIndexChanged.connect(self._on_archetype_changed)
        form.addWidget(self.archetype_desc)

        form.addWidget(Divider())

        # ── Strategy ──────────────────────────────────────────────────────
        form.addWidget(SectionLabel("Strategy Keywords"))
        self.strategy_widget = StrategyWidget()
        form.addWidget(self.strategy_widget)

        form.addWidget(Divider())

        # ── Rarity ────────────────────────────────────────────────────────
        form.addWidget(SectionLabel("Max Rarity"))
        self.rarity_combo = QComboBox()
        for r, label in [("mythic", "✦ Mythic Rare"), ("rare", "★ Rare"),
                          ("uncommon", "◆ Uncommon"), ("common", "● Common")]:
            self.rarity_combo.addItem(label, r)
            self.rarity_combo.setItemData(
                self.rarity_combo.count() - 1,
                RARITY_COLORS[r],
                Qt.ForegroundRole
            )
        form.addWidget(self.rarity_combo)

        form.addWidget(Divider())

        # ── Deck Size ────────────────────────────────────────────────────
        form.addWidget(SectionLabel("Deck Size"))
        size_row = QWidget()
        sl = QHBoxLayout(size_row)
        sl.setContentsMargins(0, 0, 0, 0)
        self.size_label = QLabel("100 cards")
        self.size_label.setStyleSheet("color: #e6edf3; font-size: 12px; min-width: 70px;")
        sl.addWidget(self.size_label)
        self._size_note = QLabel("(99 + Commander)")
        self._size_note.setStyleSheet("color: #8b949e; font-size: 11px;")
        sl.addWidget(self._size_note)
        form.addWidget(size_row)

        form.addWidget(Divider())

        # ── Advanced ──────────────────────────────────────────────────────
        adv_toggle = QPushButton("▶  Advanced Options")
        adv_toggle.setCheckable(True)
        adv_toggle.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #8b949e; font-size: 11px; font-weight: 600;
                text-align: left; padding: 2px 0;
            }
            QPushButton:hover { color: #e6edf3; }
            QPushButton:checked { color: #d4af37; }
        """)
        form.addWidget(adv_toggle)

        self.adv_box = QWidget()
        adv_layout = QVBoxLayout(self.adv_box)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(10)
        self.adv_box.setVisible(False)

        # Seed
        seed_row = QWidget()
        seed_l = QHBoxLayout(seed_row)
        seed_l.setContentsMargins(0, 0, 0, 0)
        seed_l.setSpacing(8)
        seed_label = QLabel("Seed")
        seed_label.setStyleSheet("color: #8b949e; font-size: 12px; min-width: 80px;")
        self.seed_check = QCheckBox("Use seed")
        self.seed_check.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(42)
        self.seed_spin.setEnabled(False)
        self.seed_check.toggled.connect(self.seed_spin.setEnabled)
        seed_l.addWidget(self.seed_check)
        seed_l.addWidget(self.seed_spin)
        adv_layout.addWidget(seed_row)

        # Generations
        gen_row = QWidget()
        gen_l = QHBoxLayout(gen_row)
        gen_l.setContentsMargins(0, 0, 0, 0)
        gen_l.setSpacing(8)
        gen_label = QLabel("Generations")
        gen_label.setStyleSheet("color: #8b949e; font-size: 12px; min-width: 80px;")
        self.gen_spin = QSpinBox()
        self.gen_spin.setRange(0, 2000)
        self.gen_spin.setValue(400)
        self.gen_spin.setSingleStep(50)
        gen_l.addWidget(gen_label)
        gen_l.addWidget(self.gen_spin)
        gen_slider = QSlider(Qt.Horizontal)
        gen_slider.setRange(0, 2000)
        gen_slider.setValue(400)
        gen_slider.setSingleStep(50)
        gen_slider.setPageStep(100)
        gen_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #30363d; height: 4px; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #d4af37; width: 14px; height: 14px;
                border-radius: 7px; margin: -5px 0;
            }
            QSlider::sub-page:horizontal {
                background: #d4af37; height: 4px; border-radius: 2px;
            }
        """)
        gen_slider.valueChanged.connect(self.gen_spin.setValue)
        self.gen_spin.valueChanged.connect(gen_slider.setValue)
        adv_layout.addWidget(gen_row)
        adv_layout.addWidget(gen_slider)

        # Diversity slider
        div_row = QWidget()
        div_l = QHBoxLayout(div_row)
        div_l.setContentsMargins(0, 0, 0, 0)
        div_l.setSpacing(8)
        div_lbl = QLabel("Diversity")
        div_lbl.setStyleSheet("color: #8b949e; font-size: 12px; min-width: 60px;")
        self.div_spin = QDoubleSpinBox()
        self.div_spin.setRange(0.0, 3.0)
        self.div_spin.setSingleStep(0.1)
        self.div_spin.setValue(1.0)
        self.div_spin.setDecimals(1)
        self.div_spin.setFixedWidth(60)
        self.div_spin.setToolTip(
            "0.0 = fully deterministic (same seed → same deck)\n"
            "1.0 = balanced variety (default)\n"
            "3.0 = highly varied — different cards each run"
        )
        div_hint = QLabel("0 = deterministic · 3 = highly varied")
        div_hint.setStyleSheet("color: #6e7681; font-size: 11px;")
        div_l.addWidget(div_lbl)
        div_l.addWidget(self.div_spin)
        div_l.addWidget(div_hint)
        div_l.addStretch()
        adv_layout.addWidget(div_row)

        # Candidate deck shapes
        cand_row = QWidget()
        cand_l = QHBoxLayout(cand_row)
        cand_l.setContentsMargins(0, 0, 0, 0)
        cand_l.setSpacing(8)
        cand_lbl = QLabel("Candidates")
        cand_lbl.setStyleSheet("color: #8b949e; font-size: 12px; min-width: 80px;")
        self.candidate_spin = QSpinBox()
        self.candidate_spin.setRange(1, 20)
        self.candidate_spin.setValue(6)
        self.candidate_spin.setToolTip(
            "How many different deck shapes to explore before choosing the best one.\n"
            "Higher values improve search breadth but take longer."
        )
        cand_l.addWidget(cand_lbl)
        cand_l.addWidget(self.candidate_spin)
        cand_l.addStretch()
        adv_layout.addWidget(cand_row)

        # No-evolve checkbox
        self.no_evolve_check = QCheckBox("Skip evolutionary refinement (faster)")
        self.no_evolve_check.setStyleSheet("color: #8b949e; font-size: 12px;")
        def _toggle_evolve(v):
            gen_slider.setEnabled(not v)
            self.gen_spin.setEnabled(not v)
        self.no_evolve_check.toggled.connect(_toggle_evolve)
        adv_layout.addWidget(self.no_evolve_check)

        # Land count override
        land_row = QWidget()
        land_l = QHBoxLayout(land_row)
        land_l.setContentsMargins(0, 0, 0, 0)
        land_l.setSpacing(8)
        land_lbl = QLabel("Land Override")
        land_lbl.setStyleSheet("color: #8b949e; font-size: 12px; min-width: 80px;")
        self.land_check = QCheckBox("Custom")
        self.land_check.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.land_spin = QSpinBox()
        self.land_spin.setRange(17, 30)
        self.land_spin.setValue(24)
        self.land_spin.setEnabled(False)
        self.land_check.toggled.connect(self.land_spin.setEnabled)
        land_l.addWidget(self.land_check)
        land_l.addWidget(self.land_spin)
        adv_layout.addWidget(land_row)

        form.addWidget(self.adv_box)
        def _toggle_adv(v):
            self.adv_box.setVisible(v)
            adv_toggle.setText("▼  Advanced Options" if v else "▶  Advanced Options")
        adv_toggle.toggled.connect(_toggle_adv)

        form.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # ── Bottom bar ────────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet("background: #161b22; border-top: 1px solid #30363d;")
        bottom.setFixedHeight(130)
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(8)

        self.generate_btn = GenerateButton()
        self.generate_btn.clicked.connect(self._on_generate)
        bl.addWidget(self.generate_btn)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.copy_btn = ActionButton("📋  Copy Deck", primary=True)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._on_copy)
        self.save_btn = ActionButton("💾  Save…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self.copy_btn)
        action_row.addWidget(self.save_btn)
        bl.addLayout(action_row)

        root.addWidget(bottom)

        self._last_deck_text = ""
        self._load_cmd_commanders()

    def _load_cmd_commanders(self):
        """Start background thread to load Commander card database commander list."""
        self._cmd_combo.clear()
        self._cmd_combo.addItem("Loading commanders…")
        self._cmd_combo.setEnabled(False)
        loader = CommanderLoaderWorker(dgc)
        loader.loaded.connect(self._populate_cmd_commanders)
        loader.error.connect(lambda err: self._cmd_combo.setToolTip(f"Load error: {err}"))
        self._cmd_loader = loader
        loader.start()

    def _populate_cmd_commanders(self, commanders: list):
        """Store commander list and fill combo."""
        self._commander_data = commanders
        self._commanders_loaded = True
        self._fill_combo(commanders)

    def _fill_combo(self, commanders: list):
        """Fill the commander combo box with the given list."""
        names = [c.get("name", "") for c in commanders]
        self._cmd_combo.clear()
        for name in names:
            self._cmd_combo.addItem(name)
        completer = QCompleter(names, self._cmd_combo)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._cmd_combo.setCompleter(completer)
        self._cmd_combo.setEnabled(True)
        if names:
            self._cmd_combo.setCurrentIndex(0)
            self._on_commander_changed(0)

    def _on_commander_changed(self, idx: int):
        """Update the color identity label when a commander is selected."""
        data = self._commander_data
        if not data or idx < 0:
            self._cmd_identity_lbl.setText("")
            return
        # Match by current text since completer may change the index
        text = self._cmd_combo.currentText()
        card = next((c for c in data if c.get("name") == text), None)
        if card is None and 0 <= idx < len(data):
            card = data[idx]
        if card is None:
            self._cmd_identity_lbl.setText("")
            return
        identity = sorted(card.get("color_identity") or ["C"])
        color_names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green", "C": "Colorless"}
        pip_html = "  ".join(
            f'<span style="color:{MANA_DEFS[c]["bg"].name() if c in MANA_DEFS else "#aaa"}; '
            f'font-weight:700;">{c}</span>'
            for c in identity
        )
        name_str = " / ".join(color_names.get(c, c) for c in identity)
        self._cmd_identity_lbl.setText(f"Color identity: {pip_html}  ({name_str})")
        self._cmd_identity_lbl.setTextFormat(Qt.RichText)

    def _on_archetype_changed(self, idx: int):
        arch = self.archetype_combo.currentData()
        self.archetype_desc.setText(ARCHETYPE_DESCS.get(arch, ""))

    def _on_generate(self):
        arch = self.archetype_combo.currentData()
        strat = self.strategy_widget.get_strategy_string()
        rarity = self.rarity_combo.currentData()
        seed = self.seed_spin.value() if self.seed_check.isChecked() else None
        no_evo = self.no_evolve_check.isChecked()
        gens = self.gen_spin.value()
        diversity = self.div_spin.value()
        candidate_decks = self.candidate_spin.value()

        idx = self._cmd_combo.currentIndex()
        if idx < 0 or not self._commander_data:
            QMessageBox.warning(self, "No Commander Selected",
                                "Please select a commander.")
            return
        commander_name = self._cmd_combo.currentText()
        match = next((c for c in self._commander_data if c.get("name") == commander_name), None)
        if match is None:
            QMessageBox.warning(self, "Commander Not Found",
                                f"Could not find '{commander_name}' in the database.")
            return
        params = {
            "mode":           "commander",
            "commander_name": commander_name,
            "archetype":      arch,
            "strategy":       strat,
            "max_rarity":     rarity,
            "seed":           seed,
            "no_evolve":      no_evo,
            "generations":    gens,
            "diversity":      diversity,
            "candidate_decks": candidate_decks,
        }

        if self.land_check.isChecked():
            params["land_override"] = self.land_spin.value()

        self.generate_requested.emit(params)

    def set_generating(self, val: bool):
        self.generate_btn.set_loading(val)
        self.archetype_combo.setEnabled(not val)
        self.rarity_combo.setEnabled(not val)
        if self._commanders_loaded:
            self._cmd_combo.setEnabled(not val)

    def enable_actions(self, get_text_fn):
        """get_text_fn: callable returning the current active deck text."""
        self._get_deck_text = get_text_fn
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _on_copy(self):
        if hasattr(self, "_get_deck_text"):
            QApplication.clipboard().setText(self._get_deck_text())

    def _on_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Deck", "deck.txt",
            "Text files (*.txt);;All files (*)"
        )
        if path and hasattr(self, "_get_deck_text"):
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._get_deck_text())


# ══════════════════════════════════════════════════════════════════════════════
# RIGHT PANEL — ANALYSIS + DECK LIST
# ══════════════════════════════════════════════════════════════════════════════

class RightPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        self.header = QWidget()
        self.header.setFixedHeight(72)
        self.header.setStyleSheet("background: #161b22; border-bottom: 1px solid #30363d;")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(20, 12, 20, 12)

        self.deck_title = QLabel("No Deck Generated")
        self.deck_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #8b949e;")
        hl.addWidget(self.deck_title)
        hl.addStretch()

        # Stat badges in header
        self.stat_badges = QWidget()
        sb_l = QHBoxLayout(self.stat_badges)
        sb_l.setContentsMargins(0, 0, 0, 0)
        sb_l.setSpacing(16)
        self._header_stats: dict[str, QLabel] = {}
        for key in ("Cards", "Lands", "Avg CMC", "Power"):
            col = QWidget()
            col_l = QVBoxLayout(col)
            col_l.setContentsMargins(0, 0, 0, 0)
            col_l.setSpacing(1)
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #e6edf3;")
            val_lbl.setAlignment(Qt.AlignHCenter)
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet("font-size: 10px; color: #8b949e; font-weight: 600; letter-spacing: 0.8px;")
            key_lbl.setAlignment(Qt.AlignHCenter)
            col_l.addWidget(val_lbl)
            col_l.addWidget(key_lbl)
            sb_l.addWidget(col)
            self._header_stats[key] = val_lbl
        hl.addWidget(self.stat_badges)
        root.addWidget(self.header)

        # ── Tab widget ─────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border-radius: 0; border: none; border-top: 1px solid #30363d; }")
        root.addWidget(self.tabs)

        # ── Analysis Tab ───────────────────────────────────────────────────
        analysis_scroll = QScrollArea()
        analysis_scroll.setWidgetResizable(True)
        analysis_scroll.setFrameShape(QFrame.NoFrame)
        analysis_scroll.setStyleSheet("QScrollArea { background: #0d1117; border: none; }")

        analysis_inner = QWidget()
        analysis_inner.setStyleSheet("background: #0d1117;")
        al = QVBoxLayout(analysis_inner)
        al.setContentsMargins(20, 20, 20, 20)
        al.setSpacing(20)

        # Stat cards row
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        self.stat_cards: dict[str, StatCard] = {}
        for key, init in [("Unique Cards", "—"), ("Archetypes Fit", "—"),
                           ("Synergy Score", "—"), ("Tribes", "—")]:
            sc = StatCard(key, init)
            self.stat_cards[key] = sc
            stat_row.addWidget(sc)
        al.addLayout(stat_row)

        # Mana curve
        curve_group = QGroupBox("Mana Curve")
        cg_l = QVBoxLayout(curve_group)
        cg_l.setContentsMargins(12, 20, 12, 12)
        self.curve_chart = ManaCurveChart()
        cg_l.addWidget(self.curve_chart)
        al.addWidget(curve_group)

        # Color pips + role bar row
        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        pip_group = QGroupBox("Color Distribution")
        pip_l = QVBoxLayout(pip_group)
        pip_l.setContentsMargins(12, 20, 12, 12)
        self.pip_widget = ColorPipWidget()
        pip_l.addWidget(self.pip_widget)
        mid_row.addWidget(pip_group, 1)

        role_group = QGroupBox("Role Composition")
        role_l = QVBoxLayout(role_group)
        role_l.setContentsMargins(12, 20, 12, 12)
        role_l.setSpacing(6)
        self.role_bar = RoleBreakdownWidget()
        role_l.addWidget(self.role_bar)
        # Role legend
        self.role_legend = QWidget()
        legend_l = QGridLayout(self.role_legend)
        legend_l.setContentsMargins(0, 4, 0, 0)
        legend_l.setSpacing(4)
        self._role_legend_labels: dict[str, tuple[QLabel, QLabel]] = {}
        for i, (role, col) in enumerate(ROLE_COLORS.items()):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {col.name()}; font-size: 14px;")
            lbl = QLabel(role.capitalize())
            lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            count_lbl = QLabel("0")
            count_lbl.setStyleSheet("color: #e6edf3; font-size: 11px; font-weight: 600;")
            count_lbl.setAlignment(Qt.AlignRight)
            row = i % 4
            col_offset = (i // 4) * 3
            legend_l.addWidget(dot, row, col_offset)
            legend_l.addWidget(lbl, row, col_offset + 1)
            legend_l.addWidget(count_lbl, row, col_offset + 2)
            self._role_legend_labels[role] = (lbl, count_lbl)
        role_l.addWidget(self.role_legend)
        mid_row.addWidget(role_group, 2)

        al.addLayout(mid_row)

        # Synergies
        syn_group = QGroupBox("Active Synergies")
        syn_l = QVBoxLayout(syn_group)
        syn_l.setContentsMargins(12, 20, 12, 12)
        self.syn_container = QWidget()
        self.syn_flow = QHBoxLayout(self.syn_container)
        self.syn_flow.setContentsMargins(0, 0, 0, 0)
        self.syn_flow.setSpacing(6)
        self.syn_flow.addStretch()
        syn_l.addWidget(self.syn_container)
        al.addWidget(syn_group)

        # Tribal
        tribe_group = QGroupBox("Tribal Composition")
        tribe_l = QVBoxLayout(tribe_group)
        tribe_l.setContentsMargins(12, 20, 12, 12)
        tribe_l.setSpacing(6)
        self.tribe_container = QWidget()
        self.tribe_layout = QVBoxLayout(self.tribe_container)
        self.tribe_layout.setContentsMargins(0, 0, 0, 0)
        self.tribe_layout.setSpacing(4)
        tribe_l.addWidget(self.tribe_container)
        al.addWidget(tribe_group)

        al.addStretch()
        analysis_scroll.setWidget(analysis_inner)
        self.tabs.addTab(analysis_scroll, "  Analysis  ")

        # ── Deck List Tab ──────────────────────────────────────────────────
        deck_tab = QWidget()
        dl = QVBoxLayout(deck_tab)
        dl.setContentsMargins(12, 12, 12, 12)
        dl.setSpacing(8)

        # Export format toolbar
        fmt_bar = QHBoxLayout()
        fmt_bar.setSpacing(10)
        fmt_lbl = QLabel("Export Format:")
        fmt_lbl.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
        self._fmt_control = SegmentedControl([
            ("Plain  (N Card Name)", "plain"),
            ("MTGA  (N Card Name (SET) #)", "arena"),
        ])
        self._fmt_control.option_changed.connect(self._on_format_changed)
        fmt_bar.addWidget(fmt_lbl)
        fmt_bar.addWidget(self._fmt_control)
        fmt_bar.addStretch()

        # Card count info label
        self._deck_info_lbl = QLabel("")
        self._deck_info_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        fmt_bar.addWidget(self._deck_info_lbl)
        dl.addLayout(fmt_bar)

        self.deck_text = QTextEdit()
        self.deck_text.setReadOnly(True)
        self.deck_text.setPlaceholderText(
            "Generate a deck to see the card list here.\n\n"
            "Plain format works everywhere; MTGA format includes set codes\n"
            "and collector numbers for direct in-game import."
        )
        DeckHighlighter(self.deck_text.document())
        dl.addWidget(self.deck_text)
        self.tabs.addTab(deck_tab, "  Deck List  ")

        self._deck_viewer = DeckViewerTab()
        self.tabs.addTab(self._deck_viewer, "  Deck Viewer  ")

        self._deck_texts: dict[str, str] = {"plain": "", "arena": ""}

        # ── Placeholder / Empty State ──────────────────────────────────────
        self._show_placeholder()

    def _on_format_changed(self, fmt: str):
        text = self._deck_texts.get(fmt, "")
        if text:
            self.deck_text.setPlainText(text)

    def active_deck_text(self) -> str:
        """Returns whichever format is currently displayed."""
        return self._deck_texts.get(self._fmt_control.current(), "")

    def _show_placeholder(self):
        self.curve_chart.curve = {}
        self.curve_chart.update()
        self.deck_text.setPlainText("")

    def update_result(self, result: dict):
        arch = result["archetype"]
        colors = result["colors"]
        arch_col = ARCHETYPE_COLORS.get(arch, C_ACCENT)

        # Header
        arch_str = arch.capitalize()
        cmd = result.get("commander") or {}
        title = f"{cmd.get('name', 'Commander')} — {arch_str} [Commander]"
        self.deck_title.setText(title)
        self.deck_title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; color: {arch_col.name()};"
        )
        self._header_stats["Cards"].setText(str(result["total_cards"]))
        self._header_stats["Lands"].setText(str(result["land_count"]))
        self._header_stats["Avg CMC"].setText(f"{result['avg_cmc']:.2f}")
        self._header_stats["Power"].setText(f"{result['avg_power']:.1f}")

        # Stat cards
        self.stat_cards["Unique Cards"].set_value(str(result["card_count"]))
        n_syn = len(result["synergies"])
        self.stat_cards["Synergy Score"].set_value(str(n_syn))
        n_tribes = len(result["tribes"])
        self.stat_cards["Tribes"].set_value(str(n_tribes) if n_tribes else "—")
        self.stat_cards["Archetypes Fit"].set_value(arch.capitalize())

        # Curve chart
        self.curve_chart.set_data(result["curve"], arch, result.get("curve_targets"))

        # Pips
        self.pip_widget.set_data(result["pips"])

        # Roles
        roles = result["roles"]
        self.role_bar.set_data(roles)
        for role, (lbl, count_lbl) in self._role_legend_labels.items():
            cnt = roles.get(role, 0)
            count_lbl.setText(str(cnt))
            lbl.setStyleSheet(
                f"color: {'#e6edf3' if cnt > 0 else '#484f58'}; font-size: 11px;"
            )

        # Synergies (clear and rebuild)
        while self.syn_flow.count() > 1:
            item = self.syn_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for tag, count in result["synergies"]:
            badge = QLabel(f"  {tag.replace('_', ' ').title()}  {count}  ")
            # Pick badge color based on category
            badge_colors = {
                "tribal": "#f59e0b", "spells": "#3b82f6", "graveyard": "#6b7280",
                "token": "#22c55e", "artifact": "#94a3b8", "enchantment": "#d946ef",
                "etb": "#06b6d4", "sacrifice": "#ef4444", "death": "#ef4444",
                "counters": "#8b5cf6", "landfall": "#16a34a", "anthem": "#fbbf24",
            }
            col = next((c for k, c in badge_colors.items() if k in tag.lower()), "#6b7280")
            badge.setStyleSheet(f"""
                background: {col}22;
                color: {col};
                border: 1px solid {col}55;
                border-radius: 12px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            """)
            self.syn_flow.insertWidget(self.syn_flow.count() - 1, badge)

        # Tribes
        while self.tribe_layout.count():
            item = self.tribe_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        max_tribe = max((c for _, c in result["tribes"]), default=1)
        for tribe, count in result["tribes"]:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            name_lbl = QLabel(tribe)
            name_lbl.setStyleSheet("color: #e6edf3; font-size: 12px; min-width: 100px;")
            bar_w = QWidget()
            bar_w.setFixedHeight(8)
            bar_pct = count / max(max_tribe, 1)
            bar_w.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d4af37, stop:1 #f59e0b);
                border-radius: 4px;
            """)
            bar_w.setFixedWidth(max(4, int(bar_pct * 160)))
            cnt_lbl = QLabel(str(count))
            cnt_lbl.setStyleSheet("color: #8b949e; font-size: 11px; min-width: 24px;")
            rl.addWidget(name_lbl)
            rl.addWidget(bar_w)
            rl.addWidget(cnt_lbl)
            rl.addStretch()
            self.tribe_layout.addWidget(row)

        # Deck texts (both formats)
        self._deck_texts["plain"] = result["deck_text"]
        self._deck_texts["arena"] = result.get("deck_text_arena", result["deck_text"])
        self.deck_text.setPlainText(self._deck_texts[self._fmt_control.current()])

        # Info label
        n_unique = result.get("card_count", 0)
        self._deck_info_lbl.setText(
            f"{result['nonland_count']} spells · {result['land_count']} lands · {n_unique} unique cards"
        )

        self._deck_viewer.set_deck(result)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTG Commander Deck Generator")
        self.resize(1280, 820)
        self.setMinimumSize(900, 640)
        self._worker: CommanderGeneratorWorker | None = None
        self._build_ui()
        self._setup_shortcuts()
        # Populate keyword catalog from Scryfall in background (if online)
        _start_kw_catalog_fetch()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setChildrenCollapsible(False)

        self.left = LeftPanel()
        self.left.generate_requested.connect(self._on_generate)
        splitter.addWidget(self.left)

        self.right = RightPanel()
        splitter.addWidget(self.right)

        # Start with left panel at 300px, right panel takes the rest
        splitter.setSizes([300, 980])
        splitter.setStretchFactor(0, 0)   # left: don't stretch with window
        splitter.setStretchFactor(1, 1)   # right: absorb resize

        root.addWidget(splitter)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setFixedHeight(4)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self.status.addPermanentWidget(self._progress)
        self._status_label = QLabel("Ready — choose a commander and click Generate")
        self.status.addWidget(self._status_label)

    def _setup_shortcuts(self):
        from PySide6.QtGui import QShortcut
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.left._on_generate)
        shortcut2 = QShortcut(QKeySequence("Ctrl+C"), self)
        shortcut2.activated.connect(self.left._on_copy)

    @Slot(dict)
    def _on_generate(self, params: dict):
        if self._worker and self._worker.isRunning():
            return

        self.left.set_generating(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._worker = CommanderGeneratorWorker(params)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.result.connect(self._on_result)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    @Slot(str, int)
    def _on_progress(self, msg: str, pct: int):
        self._status_label.setText(msg)
        self._progress.setValue(pct)

    @Slot(dict)
    def _on_result(self, result: dict):
        self.left.set_generating(False)
        self._progress.setValue(100)
        QTimer.singleShot(800, lambda: self._progress.setVisible(False))
        self._status_label.setText(
            f"✓  {result['total_cards']}-card {result['archetype']} deck generated  "
            f"({result['nonland_count']} nonlands + {result['land_count']} lands)"
        )
        self.right.update_result(result)
        self.left.enable_actions(self.right.active_deck_text)

    @Slot(str)
    def _on_error(self, err: str):
        self.left.set_generating(False)
        self._progress.setVisible(False)
        self._status_label.setText("⚠  Generation failed — see error details")
        msg = QMessageBox(self)
        msg.setWindowTitle("Generation Error")
        msg.setIcon(QMessageBox.Critical)
        msg.setText("An error occurred during deck generation.")
        msg.setDetailedText(err)
        msg.setStyleSheet(STYLESHEET)
        msg.exec()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Ensure we find the commander generator and card data directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = QApplication(sys.argv)
    app.setApplicationName("MTG Commander Generator")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
