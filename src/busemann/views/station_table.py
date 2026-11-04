"""Station table (results panel): every flow region of the inlet shown on the active canvas.

Columns Region | M | p/p∞ | T/T∞ | p0/p0∞ | flow angle, monospaced and right-aligned. A row
click emits row_clicked(index); select_row() highlights a row without emitting, so canvas
and table selections can follow each other without loops. to_tsv() is the clipboard text.
"""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..crashlog import guarded

# (header shown, TSV header, RegionState attribute, format)
COLUMNS = (
    ("#", "Region", "name", None),
    ("M", "M", "M", "{:.3f}"),
    ("p/p∞", "p/p_inf", "p_ratio", "ratio"),
    ("T/T∞", "T/T_inf", "T_ratio", "ratio"),
    ("p0/p0∞", "p0/p0_inf", "p0_ratio", "{:.4f}"),
    ("φ°", "flow angle (°)", "theta_deg", "{:.1f}"),
)
ROW_H = 22
CELL_PAD = 10         # px added to the widest text (covers the style's cell margins)


def ratio_text(x):
    """3 decimals below 10, then 4 significant digits (keeps the column narrow)."""
    if abs(x) < 10:
        return f"{x:.3f}"
    return f"{x:.{max(0, 3 - int(math.floor(math.log10(abs(x)))))}f}"


def short_name(name):
    """'freestream' -> '∞', 'behind shock 2' -> '2', 'duct (...)' -> 'duct'."""
    if name == "freestream":
        return "∞"
    if name.startswith("behind shock "):
        return name.removeprefix("behind shock ")
    return name.split(" (")[0]


class StationTable(QTableWidget):
    row_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self.setObjectName("stationTable")
        self.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        for c, (_, _, attr, _) in enumerate(COLUMNS):
            self.horizontalHeaderItem(c).setToolTip(tip(f"stations.{attr}"))
        self.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignLeft
                                                      | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().hide()
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)   # spare width
        header.setMinimumSectionSize(8)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        self.verticalHeader().setDefaultSectionSize(ROW_H)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFont(theme.mono_font(tokens.SIZE_LABEL))
        self.regions = []
        self._guard = False
        self.itemSelectionChanged.connect(self._on_selection)
        self._fit_height()

    def set_regions(self, regions):
        """regions: RegionState per canvas region (same order and indices as the canvas)."""
        selected = self.selected_row()
        self._guard = True
        try:
            self.regions = list(regions)
            self.clearContents()
            self.setRowCount(len(self.regions))
            for r, st in enumerate(self.regions):
                for c, (_, _, attr, fmt) in enumerate(COLUMNS):
                    value = getattr(st, attr)
                    if fmt is None:
                        text = short_name(value)
                    elif fmt == "ratio":
                        text = ratio_text(value)
                    else:
                        text = fmt.format(value)
                    item = QTableWidgetItem(text)
                    item.setTextAlignment((Qt.AlignmentFlag.AlignLeft if c == 0 else
                                           Qt.AlignmentFlag.AlignRight)
                                          | Qt.AlignmentFlag.AlignVCenter)
                    if c == 0:
                        item.setToolTip(st.name)
                    self.setItem(r, c, item)
            if selected is not None and selected < len(self.regions):
                self.selectRow(selected)
        finally:
            self._guard = False
        self._fit_columns()
        self._fit_height()

    def needed_width(self, col):
        """Width (px) column `col` needs: widest cell or header text plus the cell margin."""
        self.ensurePolished()                        # QSS sets the table font
        self.horizontalHeader().ensurePolished()
        cell_fm, head_fm = self.fontMetrics(), self.horizontalHeader().fontMetrics()
        texts = [self.item(r, col).text() for r in range(self.rowCount()) if self.item(r, col)]
        return max([cell_fm.horizontalAdvance(t) for t in texts]
                   + [head_fm.horizontalAdvance(COLUMNS[col][0])]) + CELL_PAD

    def _fit_columns(self):
        """Numeric columns exactly as wide as their widest text (cell or header); the
        region column takes the rest (it stretches)."""
        for c in range(1, len(COLUMNS)):
            self.setColumnWidth(c, self.needed_width(c))

    def column_overflow(self):
        """[(column, needed px, available px)] for every column that would clip its text."""
        problems = [(c, self.needed_width(c), self.columnWidth(c))
                    for c in range(len(COLUMNS)) if self.columnWidth(c) < self.needed_width(c)]
        total = sum(self.needed_width(c) for c in range(len(COLUMNS)))
        if total > self.viewport().width():
            problems.append(("all", total, self.viewport().width()))
        return problems

    @guarded()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    @guarded()
    def showEvent(self, event):
        super().showEvent(event)
        self._fit_columns()

    def _fit_height(self):
        self.setFixedHeight(self.horizontalHeader().sizeHint().height()
                            + ROW_H * max(self.rowCount(), 1) + 2 * self.frameWidth())

    def select_row(self, index):
        """Highlight a row (None clears) without emitting row_clicked."""
        self._guard = True
        try:
            if index is None or not 0 <= index < self.rowCount():
                self.clearSelection()
            else:
                self.selectRow(index)
        finally:
            self._guard = False

    def selected_row(self):
        rows = self.selectionModel().selectedRows() if self.selectionModel() else []
        return rows[0].row() if rows else None

    def _on_selection(self):
        if self._guard:
            return
        row = self.selected_row()
        if row is not None:
            self.row_clicked.emit(row)

    def to_tsv(self):
        """Header + one line per region; full region names, 6 significant figures."""
        lines = ["\t".join(c[1] for c in COLUMNS)]
        for st in self.regions:
            cells = [st.name] + [f"{getattr(st, attr):.6g}" for _, _, attr, _ in COLUMNS[1:]]
            lines.append("\t".join(cells))
        return "\n".join(lines) + "\n"

    def text(self, row, col):
        return self.item(row, col).text()
