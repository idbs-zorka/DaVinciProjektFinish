from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame


class LoadingOverlay(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent=parent)
        # Set initial geometry to match parent
        self.setGeometry(0, 0, parent.width(), parent.height())
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        self.hide()

        # Create a layout for the overlay to manage the label
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add the label to the layout
        self.label = QLabel("Ładowanie...", self)
        self.label.setStyleSheet("background-color: rgba(0,0,0,0); color: white; font-size: 40px")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        # Install event filter on the parent
        parent.installEventFilter(self)

    def eventFilter(self, watched, event):
        parent = self.parent()
        if watched == parent and event.type() == QEvent.Type.Resize:
            # Update geometry to match parent's new size
            self.setGeometry(0, 0, parent.width(), parent.height())
            return False
        return super().eventFilter(watched, event)