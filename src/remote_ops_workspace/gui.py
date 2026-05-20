from __future__ import annotations

import sys

from .doctor import run_doctor
from .launcher import LauncherError, launch
from .storage import ProfileStore


def main() -> int:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QApplication,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplitter,
            QTabWidget,
            QTextEdit,
            QToolBar,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover - optional dependency
        print("PyQt6 is not installed. Install with: pip install -e '.[desktop]'")
        print(exc)
        return 2

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Remote Ops Workspace")
            self.resize(1180, 720)
            self.store = ProfileStore()
            self.store.init(with_examples=True)

            toolbar = QToolBar("Main")
            self.addToolBar(toolbar)
            self.refresh_button = QPushButton("Refresh")
            self.connect_button = QPushButton("Connect")
            self.dry_run_button = QPushButton("Dry Run")
            self.doctor_button = QPushButton("Doctor")
            self.split_h_button = QPushButton("Split H")
            self.split_v_button = QPushButton("Split V")
            for button in [self.refresh_button, self.connect_button, self.dry_run_button, self.doctor_button, self.split_h_button, self.split_v_button]:
                toolbar.addWidget(button)

            self.profile_list = QListWidget()
            self.profile_list.setMinimumWidth(300)
            self.tabs = QTabWidget()
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Launch output, dry-run commands and doctor reports appear here.")

            self.workspace = QSplitter(Qt.Orientation.Vertical)
            self.workspace.addWidget(self.tabs)
            self.workspace.addWidget(self.log)
            self.workspace.setStretchFactor(0, 3)
            self.workspace.setStretchFactor(1, 1)

            root = QSplitter(Qt.Orientation.Horizontal)
            root.addWidget(self.profile_list)
            root.addWidget(self.workspace)
            root.setStretchFactor(1, 1)
            self.setCentralWidget(root)

            self.refresh_button.clicked.connect(self.refresh_profiles)
            self.connect_button.clicked.connect(lambda: self.connect_selected(False))
            self.dry_run_button.clicked.connect(lambda: self.connect_selected(True))
            self.doctor_button.clicked.connect(self.show_doctor)
            self.split_h_button.clicked.connect(lambda: self.add_split("horizontal"))
            self.split_v_button.clicked.connect(lambda: self.add_split("vertical"))
            self.refresh_profiles()
            self.add_welcome_tab()

        def refresh_profiles(self) -> None:
            self.profile_list.clear()
            for profile in self.store.load():
                self.profile_list.addItem(f"{profile.group}/{profile.name}  [{profile.protocol}]  {profile.display_target}")

        def selected_profile_name(self) -> str | None:
            item = self.profile_list.currentItem()
            if not item:
                return None
            text = item.text()
            group_name = text.split("  ", 1)[0]
            return group_name.split("/", 1)[1]

        def connect_selected(self, dry_run: bool) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                plan = launch(profile, dry_run=dry_run)
                prefix = "DRY RUN" if dry_run else "LAUNCHED"
                self.log.append(f"{prefix}: {plan.printable()}")
                for note in plan.notes:
                    self.log.append(f"  note: {note}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Launch failed", str(exc))

        def show_doctor(self) -> None:
            self.log.append(run_doctor().to_json())

        def add_welcome_tab(self) -> None:
            box = QWidget()
            layout = QVBoxLayout(box)
            label = QLabel("Remote Ops Workspace\n\nUse the profile list and toolbar to launch sessions. Split buttons demonstrate the Terminator-style workspace layout seam.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            self.tabs.addTab(box, "Welcome")

        def add_split(self, direction: str) -> None:
            orientation = Qt.Orientation.Horizontal if direction == "horizontal" else Qt.Orientation.Vertical
            splitter = QSplitter(orientation)
            for idx in range(2):
                pane = QTextEdit()
                pane.setPlaceholderText(f"Terminal pane {idx + 1}\nFuture plugin seam: qtermwidget, PTY, web terminal or embedded protocol view.")
                splitter.addWidget(pane)
            self.tabs.addTab(splitter, f"Split {self.tabs.count()}")
            self.tabs.setCurrentWidget(splitter)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
