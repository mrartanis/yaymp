from __future__ import annotations


def build_main_window_stylesheet(*, accent: str, accent_text: str) -> str:
    return f"""
            QMainWindow, QWidget {{
                background: #101116;
                color: #eceef7;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
                font-size: 12px;
            }}
            QDialog {{
                background: #101116;
            }}
            QFrame#top-bar {{
                background: #0d0f15;
                border: 0;
                border-radius: 10px;
            }}
            QWidget#title-drag-handle {{
                background: transparent;
            }}
            QFrame {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QFrame#sidebar {{
                background: #121520;
                border-radius: 14px;
            }}
            QLabel {{
                border: 0;
                background: transparent;
            }}
            QLabel#now-playing {{
                color: #aeb6d6;
                font-weight: 600;
            }}
            QLabel#track-title {{
                color: #ffffff;
                font-size: 28px;
                font-weight: 800;
            }}
            QLabel#track-artist {{
                color: #d8dceb;
                font-size: 16px;
                font-weight: 600;
            }}
            QLabel#track-album, QLabel#track-tech, QLabel#playback-state,
            QLabel#inline-status, QLabel#queue-summary {{
                color: #9ba4c2;
            }}
            QLabel#track-tech {{
                font-size: 11px;
                font-weight: 650;
                color: #7f88a8;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
            }}
            QLabel#queue-audio-info, QLabel#seek-label {{
                color: #d7dcea;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QLabel#queue-audio-info {{
                color: #9ba4c2;
            }}
            QLabel#auth-label {{
                color: #aeb6d6;
                font-size: 11px;
                font-weight: 650;
            }}
            QLabel#browser-title {{
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#nav-section {{
                color: #7f88a8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QLabel#settings-section {{
                color: #7f88a8;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
                padding-top: 2px;
            }}
            QLabel#album-art {{
                background: #0b0c11;
                border: 0;
                border-radius: 16px;
                color: #737b99;
            }}
            QLabel#art-thumb {{
                background: #1a1e2b;
                border-radius: 6px;
                color: #737b99;
            }}
            QLabel#queue-title, QLabel#browser-art-title {{
                color: #eef1fb;
                font-weight: 650;
            }}
            QLabel#queue-title {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-subtitle, QLabel#browser-art-subtitle {{
                color: #8f98b5;
                font-size: 11px;
            }}
            QLabel#queue-subtitle {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-duration {{
                color: #d7dcea;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QWidget#queue-row-active {{
                background: rgba(82, 110, 232, 0.22);
                border-radius: 8px;
            }}
            QWidget#queue-row-selected {{
                background: {accent};
                border-radius: 8px;
            }}
            QWidget#queue-row-selected QLabel#queue-title,
            QWidget#queue-row-selected QLabel#queue-subtitle,
            QWidget#queue-row-selected QLabel#queue-duration {{
                color: {accent_text};
            }}
            QWidget#queue-row {{
                background: transparent;
            }}
            QWidget#queue-text, QWidget#browser-art-text {{
                background: transparent;
            }}
            QFrame#queue-separator {{
                background: #2b2f3d;
                border: 0;
            }}
            QFrame#settings-popup, QFrame#volume-popup {{
                background: #101116;
                border: 0;
                border-radius: 12px;
            }}
            QFrame#settings-popup {{
                background: #101116;
                border: 1px solid {accent};
                border-radius: 12px;
            }}
            QFrame#volume-popup {{
                background: #101116;
                border: 1px solid {accent};
                border-radius: 14px;
            }}
            QPushButton {{
                background: #222637;
                border: 1px solid #33394e;
                border-radius: 9px;
                color: #eef1fb;
                padding: 4px 8px;
                font-weight: 650;
            }}
            QPushButton:hover {{
                border-color: {accent};
                background: #2a3044;
            }}
            QPushButton:checked {{
                background: {accent};
                color: {accent_text};
            }}
            QPushButton#play-button {{
                background: qradialgradient(cx:0.5, cy:0.45, radius:0.8,
                    fx:0.5, fy:0.4, stop:0 {accent}, stop:1 #252a3f);
                border: 1px solid {accent};
                border-radius: 16px;
            }}
            QPushButton#my-wave-button {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 #2c355f);
                border-color: {accent};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton#panel-close-button {{
                padding: 0;
                border-radius: 10px;
                font-size: 18px;
            }}
            QPushButton#window-control-button, QPushButton#window-close-button {{
                background: transparent;
                border: 0;
                border-radius: 9px;
                padding: 0;
            }}
            QPushButton#window-control-button:hover {{
                background: #1a1f2c;
                border: 0;
            }}
            QPushButton#window-close-button:hover {{
                background: #8f2d3f;
                border: 0;
            }}
            QPushButton#queue-icon-button {{
                padding: 0;
                border-radius: 10px;
                font-size: 16px;
            }}
            QPushButton#quality-option {{
                background: #222637;
                border: 1px solid #33394e;
                color: #eef1fb;
                padding: 6px 11px;
                border-radius: 10px;
                min-width: 38px;
            }}
            QPushButton#quality-option:hover {{
                border-color: {accent};
                background: #2a3044;
            }}
            QPushButton#quality-option:checked {{
                background: {accent};
                border-color: {accent};
                color: {accent_text};
            }}
            QPushButton#settings-action {{
                background: #151923;
                border: 1px solid #2d3343;
                border-radius: 9px;
                color: #eef1fb;
                padding: 6px 10px;
                text-align: left;
            }}
            QPushButton#settings-action:hover {{
                background: #1b2030;
            }}
            QPushButton#settings-action:disabled {{
                color: #6f7896;
                border-color: #23283a;
            }}
            QLineEdit, QComboBox {{
                background: #0f1118;
                border: 1px solid #30364a;
                border-radius: 8px;
                color: #eef1fb;
                padding: 4px 7px;
            }}
            QListWidget {{
                background: #0f1118;
                border: 0;
                border-radius: 10px;
                alternate-background-color: #131723;
                padding: 4px;
            }}
            QListWidget::item {{
                border-radius: 7px;
                padding: 5px;
            }}
            QListWidget#queue-list::item {{
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background: {accent};
                color: {accent_text};
            }}
            QTabWidget::pane {{
                border: 0;
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background: #171a25;
                color: #b7bfd8;
                padding: 5px 9px;
                border-top-left-radius: 9px;
                border-top-right-radius: 9px;
            }}
            QTabBar::tab:selected {{
                color: {accent_text};
                background: {accent};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: #252a3a;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #ffffff;
                border: 2px solid {accent};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider#volume-slider {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider:hover {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider::groove:vertical {{
                width: 8px;
                background: #222637;
                border-radius: 4px;
            }}
            QSlider#volume-slider::sub-page:vertical {{
                background: #222637;
                border-radius: 4px;
            }}
            QSlider#volume-slider::add-page:vertical {{
                background: {accent};
                border-radius: 4px;
            }}
            QSlider#volume-slider::handle:vertical {{
                background: {accent};
                border: 2px solid #101116;
                height: 16px;
                margin: 0 -7px;
                border-radius: 9px;
            }}
            QSlider#volume-slider:focus {{
                outline: 0;
                border: 0;
                background: transparent;
            }}
            QScrollBar {{
                width: 0;
                height: 0;
                background: transparent;
            }}
            """
