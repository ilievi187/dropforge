#!/usr/bin/env python3
"""DropForge — Drag & Drop Offline Media & Image Studio (Qt 6 / PySide6 + Live Omarchy Theme)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QUrl, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import dropforge as df
from theme import ThemePalette, ThemeWatcher, build_stylesheet


class GlowButton(QPushButton):
    def __init__(self, text: str = "", glow_hex: str = "#7376b7", max_blur: float = 18.0, parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_blur = max_blur
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setBlurRadius(0.0)
        self.update_glow_color(glow_hex)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def update_glow_color(self, hex_color: str) -> None:
        c = QColor(hex_color)
        c.setAlpha(150)
        self._shadow.setColor(c)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(self._max_blur)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)


class ConvertWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path, preset: df.ConvertPreset) -> None:
        super().__init__()
        self._path = path
        self._preset = preset

    def run(self) -> None:
        try:
            self.finished_ok.emit(df.run_conversion(self._path, self._preset))
        except Exception as exc:
            self.failed.emit(str(exc))


class DropZone(QFrame):
    file_dropped = Signal(str)

    def __init__(self, on_browse: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("EmptyCard")
        self.setAcceptDrops(True)
        self.setMinimumHeight(145)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel("Drop any Video, Image, or Audio file here")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = QLabel("100% offline via local ffmpeg · MP4, MKV, MOV, PNG, JPG, WebP, MP3, WAV, FLAC")
        self.sub_lbl.setObjectName("SubtitleLabel")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.browse_btn = GlowButton("Choose File...", max_blur=20.0)
        self.browse_btn.setObjectName("PrimaryButton")
        self.browse_btn.setFixedWidth(160)
        self.browse_btn.clicked.connect(on_browse)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.sub_lbl)
        layout.addSpacing(4)
        layout.addWidget(self.browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_selected_file(self, path: Path) -> None:
        kind = df.detect_kind(path).upper()
        size = df.human_bytes(path.stat().st_size) if path.exists() else ""
        self.title_lbl.setText(f"{path.name}  ({kind} · {size})")
        self.sub_lbl.setText(str(path.parent))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            local = urls[0].toLocalFile()
            if local:
                self.file_dropped.emit(local)


class DropForgeWindow(QMainWindow):
    def __init__(self, watcher: ThemeWatcher) -> None:
        super().__init__()
        self.watcher = watcher
        self.palette_data: ThemePalette = watcher.palette
        self.selected_file: Optional[Path] = None
        self.last_output: Optional[Path] = None
        self._worker: Optional[ConvertWorker] = None
        self._glow_buttons: list[GlowButton] = []

        self.setWindowTitle("DropForge — Offline Media & Image Studio")
        self.resize(900, 660)
        self.setMinimumSize(740, 540)

        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme(self.palette_data)
        self.watcher.theme_changed.connect(self.apply_theme)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        # Header
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        hl = QHBoxLayout(header_card)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(14)

        logo = QLabel("✦")
        logo.setObjectName("LogoBadge")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(logo)

        tcol = QVBoxLayout()
        tcol.setSpacing(2)
        t = QLabel("DropForge")
        t.setObjectName("TitleLabel")
        sub = QLabel("Drag & drop offline video, image & audio studio")
        sub.setObjectName("SubtitleLabel")
        tcol.addWidget(t)
        tcol.addWidget(sub)
        hl.addLayout(tcol)
        hl.addStretch()

        self.open_out_btn = GlowButton("Open Output Folder", glow_hex=self.palette_data.accent, max_blur=14.0)
        self.open_out_btn.setObjectName("CardAction")
        self.open_out_btn.clicked.connect(self._open_output_folder)
        self.open_out_btn.hide()
        self._glow_buttons.append(self.open_out_btn)
        hl.addWidget(self.open_out_btn)
        root.addWidget(header_card)

        # Drop Zone
        self.drop_zone = DropZone(self._choose_file)
        self.drop_zone.file_dropped.connect(self._load_file)
        self._glow_buttons.append(self.drop_zone.browse_btn)
        root.addWidget(self.drop_zone)

        # Progress bar + status toast
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        self.toast = QFrame()
        self.toast.setObjectName("ToastBanner")
        tl = QHBoxLayout(self.toast)
        tl.setContentsMargins(14, 9, 14, 9)
        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("font-weight: 600;")
        tl.addWidget(self.toast_lbl, 1)
        self.toast.hide()
        root.addWidget(self.toast)

        # Presets Grid
        self.section_lbl = QLabel("1-Click Conversion Presets")
        self.section_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        root.addWidget(self.section_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 6, 6)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        # Footer
        footer = QHBoxLayout()
        self.status_lbl = QLabel("Drop a file or click Choose File to begin")
        self.status_lbl.setObjectName("SubtitleLabel")
        self.theme_lbl = QLabel("")
        self.theme_lbl.setObjectName("SubtitleLabel")
        support_btn = GlowButton("☕  Support", glow_hex=self.palette_data.accent, max_blur=14.0)
        support_btn.setObjectName("ChipButton")
        support_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/aurorauap")))
        self._glow_buttons.append(support_btn)
        footer.addWidget(self.status_lbl)
        footer.addStretch()
        footer.addWidget(self.theme_lbl)
        footer.addWidget(support_btn)
        root.addLayout(footer)

        self._render_presets()

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, self._choose_file)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette_data = palette
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(palette))
        for b in self._glow_buttons:
            b.update_glow_color(palette.accent)
        self.theme_lbl.setText(f"{palette.source_name} ({palette.mode}) · {palette.accent}")
        self._render_presets()

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Video, Image, or Audio File",
            str(Path.home()),
            "Media Files (*.mp4 *.mkv *.mov *.webm *.avi *.png *.jpg *.jpeg *.webp *.heic *.mp3 *.wav *.flac *.ogg *.m4a);;All Files (*)",
        )
        if path:
            self._load_file(path)

    def _load_file(self, path_str: str) -> None:
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            return
        self.selected_file = p
        self.drop_zone.set_selected_file(p)
        self.status_lbl.setText(f"Ready to convert {p.name}")
        self._render_presets()

    def _render_presets(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        presets = df.presets_for_file(self.selected_file) if self.selected_file else df.PRESETS[:6]
        for idx, preset in enumerate(presets):
            card = QFrame()
            card.setObjectName("JobCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(6)

            title = QLabel(preset.title)
            title.setStyleSheet("font-size: 14px; font-weight: 700;")
            desc = QLabel(preset.description)
            desc.setObjectName("SubtitleLabel")
            desc.setWordWrap(True)

            btn = GlowButton(f"Convert → {preset.output_ext.upper()}", glow_hex=self.palette_data.accent, max_blur=16.0)
            btn.setObjectName("RunAction")
            btn.setEnabled(self.selected_file is not None and self._worker is None)
            btn.clicked.connect(lambda checked=False, pr=preset: self._start_convert(pr))

            cl.addWidget(title)
            cl.addWidget(desc)
            cl.addStretch()
            cl.addWidget(btn)
            self.grid.addWidget(card, idx // 2, idx % 2)

    def _start_convert(self, preset: df.ConvertPreset) -> None:
        if not self.selected_file or self._worker is not None:
            return
        self.progress.show()
        self.toast.hide()
        self.status_lbl.setText(f"Converting {self.selected_file.name} ({preset.title})...")
        self._worker = ConvertWorker(self.selected_file, preset)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._render_presets()
        self._worker.start()

    def _on_done(self, result: df.ConvertResult) -> None:
        self._worker = None
        self.progress.hide()
        self.last_output = result.output_path
        self.open_out_btn.show()
        self.toast_lbl.setText(f"✓  {result.summary}")
        self.toast.show()
        self.status_lbl.setText("Conversion complete")
        self._render_presets()

    def _on_fail(self, msg: str) -> None:
        self._worker = None
        self.progress.hide()
        self.toast_lbl.setText(f"Error: {msg}")
        self.toast.show()
        self.status_lbl.setText("Conversion failed")
        self._render_presets()

    def _open_output_folder(self) -> None:
        if self.last_output and self.last_output.parent.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output.parent)))


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DropForge")
    app.setDesktopFileName("dropforge")
    watcher = ThemeWatcher(app)
    win = DropForgeWindow(watcher)
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        win._load_file(sys.argv[1])
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
