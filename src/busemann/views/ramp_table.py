"""Compact per-ramp table: Ramp | θ | β | M after [| ∂η/∂θ] (mono, right-aligned numbers).

The ∂η/∂θ column (total-pressure recovery change per degree of that ramp, addendum C3) is
shown in custom-angle mode only.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip

HEADERS = (("Ramp", ""), ("θ", "(°)"), ("β", "(°)"), ("M after", ""), ("∂η/∂θ", "(/°)"))
HEADER_TIPS = ("ramp_table.ramp", "ramp_table.theta", "ramp_table.beta", "ramp_table.m_after",
               "ramp_table.sensitivity")
SENS_COL = 4


class RampTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rampTable")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(tokens.space(2))
        self._grid.setVerticalSpacing(3)
        self.headers = []
        for c, (name, unit) in enumerate(HEADERS):
            text = f"{name} {unit}".strip()
            head = QLabel(text)
            head.setObjectName("readoutLabel")
            head.setAlignment(_align(c))
            head.setToolTip(tip(HEADER_TIPS[c]))
            self._grid.addWidget(head, 0, c)
            self._grid.setColumnStretch(c, 0 if c == 0 else 1)
            self.headers.append(head)
        self._cells = []
        self._columns = len(HEADERS) - 1
        self.empty = QLabel("No ramps (pitot inlet)")
        self.empty.setObjectName("selectionHint")
        self.empty.setToolTip(tip("ramp_table.row"))
        self._grid.addWidget(self.empty, 1, 0, 1, len(HEADERS))
        self.rows = []
        self._show_sensitivity(False)

    def _show_sensitivity(self, on):
        self.headers[SENS_COL].setVisible(on)
        self._columns = len(HEADERS) if on else len(HEADERS) - 1
        self._grid.setHorizontalSpacing(tokens.space(1) if on else tokens.space(2))

    def sensitivity_visible(self):
        return self._columns == len(HEADERS)

    def set_rows(self, rows, sensitivity=None):
        """rows: [(theta_deg, beta_deg, M_after), ...]; [] shows the no-ramp note.
        sensitivity: d(eta)/d(theta_k) per degree for each row (None hides the column)."""
        for w in self._cells:
            w.deleteLater()
        self._cells = []
        self.rows = list(rows)
        self._show_sensitivity(sensitivity is not None and bool(rows))
        self.empty.setText("No ramps (pitot inlet)")
        self.empty.setVisible(not rows)
        for r, (theta, beta, mach) in enumerate(rows, start=1):
            texts = [str(r), f"{theta:.2f}", f"{beta:.2f}", f"{mach:.3f}"]
            if self.sensitivity_visible():
                s = sensitivity[r - 1]
                texts.append("—" if s is None else f"{s:+.4f}")
            for c, text in enumerate(texts):
                cell = QLabel(text)
                cell.setObjectName("readoutValue")
                cell.setFont(theme.mono_font())
                cell.setAlignment(_align(c))
                cell.setToolTip(tip("ramp_table.sensitivity" if c == SENS_COL
                                    else "ramp_table.row"))
                self._grid.addWidget(cell, r, c)
                self._cells.append(cell)

    def column_overflow(self):
        """[(row, column, needed px, available px)] for every visible cell or header whose
        text is wider than its cell (would be clipped)."""
        out = []
        cells = [(0, c, h) for c, h in enumerate(self.headers)]
        cols = self._columns
        cells += [(1 + k // cols, k % cols, w) for k, w in enumerate(self._cells)]
        for r, c, w in cells:
            if not w.isVisibleTo(self):
                continue
            need = w.fontMetrics().horizontalAdvance(w.text())
            if w.width() < need:
                out.append((r, c, need, w.width()))
        return out

    def clear(self):
        self.set_rows([])
        self.empty.setText("—")
        self.empty.show()

    def text(self, row, col):
        return self._cells[row * self._columns + col].text()


def _align(col):
    h = Qt.AlignmentFlag.AlignLeft if col == 0 else Qt.AlignmentFlag.AlignRight
    return h | Qt.AlignmentFlag.AlignVCenter
