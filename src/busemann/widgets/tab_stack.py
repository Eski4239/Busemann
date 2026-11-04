"""Pages with a detachable tab bar (M8.2 layout): the QTabBar lives in the toolbar row and
the pages in the centre column. The API is the subset of QTabWidget the app uses."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QTabBar, QVBoxLayout, QWidget


class TabStack(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack)
        self._bar = QTabBar()
        self._bar.setObjectName("mainTabs")
        self._bar.setDocumentMode(True)
        self._bar.setDrawBase(False)
        self._bar.setExpanding(False)
        self._bar.currentChanged.connect(self._from_bar)
        self.stack.currentChanged.connect(self._from_stack)

    # --- QTabWidget subset -----------------------------------------------------------------
    def tabBar(self):
        return self._bar

    def addTab(self, widget, text):
        index = self.stack.addWidget(widget)
        self._bar.addTab(text)
        return index

    def count(self):
        return self.stack.count()

    def widget(self, index):
        return self.stack.widget(index)

    def indexOf(self, widget):
        return self.stack.indexOf(widget)

    def currentIndex(self):
        return self.stack.currentIndex()

    def currentWidget(self):
        return self.stack.currentWidget()

    def setCurrentIndex(self, index):
        self.stack.setCurrentIndex(index)

    def setCurrentWidget(self, widget):
        self.stack.setCurrentWidget(widget)

    def tabText(self, index):
        return self._bar.tabText(index)

    def setTabToolTip(self, index, text):
        self._bar.setTabToolTip(index, text)

    def tabToolTip(self, index):
        return self._bar.tabToolTip(index)

    def setDocumentMode(self, on):           # kept for API compatibility
        self._bar.setDocumentMode(on)

    # --- sync -------------------------------------------------------------------------------
    def _from_bar(self, index):
        if index >= 0 and index != self.stack.currentIndex():
            self.stack.setCurrentIndex(index)

    def _from_stack(self, index):
        if self._bar.currentIndex() != index:
            self._bar.setCurrentIndex(index)
        self.currentChanged.emit(index)
