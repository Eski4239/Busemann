"""Explain mode (spec 4.6, M8.2 structure): a topic tree in the right column and a popup
window with the chosen explanation.

Tree: Freestream; Ramp shock 1…N; Regions (one child per region); Terminal shock; Cowl lip;
Design method; Off-design; Separation (approximate). Clicking a topic opens (or updates) one
non-modal popup with the governing relations as equations, the same relations with this
case's numbers, plain words and the assumptions. The canvas selection highlights its topic
(and updates the popup while it is open). Content is the templated .md files in
resources/explain (busemann.explain.content); every number is an api value formatted by the
template, never computed here.
"""
import hashlib
import html

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal
from PySide6.QtGui import QImage, QPainter, QTextDocument
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QTextBrowser, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout,
)

from ..explain import content as C
from ..explain.mathsvg import PT_TO_PX, tex_to_svg
from ..explain.select import build_context, topic_context
from ..theme import tokens
from ..tooltips import tip

DRAWER_W = tokens.RIGHT_PANEL_WIDTH     # the tree fits the normal right column
SLIDE_MS = 200
POPUP_SIZE = (500, 600)
_MARGIN = 2 * tokens.space(2) + 8      # text-browser margins + scrollbar, px
ROLE = Qt.ItemDataRole.UserRole


class ExplainPopup(QDialog):
    """Non-modal window with one explanation; reused for every topic."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("explainPopup")
        self.setWindowTitle("Explain")
        self.setModal(False)
        self.resize(*POPUP_SIZE)
        self.title = QLabel("Explain")
        self.title.setObjectName("drawerTitle")
        self.title.setToolTip(tip("drawer.title"))
        self.title.setWordWrap(True)
        self.body = QTextBrowser()
        self.body.setObjectName("explainBody")
        self.body.setOpenLinks(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2),
                                  tokens.space(1))
        layout.setSpacing(tokens.space(1))
        layout.addWidget(self.title)
        layout.addWidget(self.body, 1)
        self.images = {}                 # tex -> QImage (for tests)

    def show_rendered(self, rendered):
        self.title.setText(rendered.title)
        self.setWindowTitle(f"Explain — {rendered.title}")
        self.body.setHtml(self._html(rendered))

    def show_message(self, title, text):
        self.title.setText(title)
        self.setWindowTitle(f"Explain — {title}")
        self.body.setHtml(f"<p>{html.escape(text)}</p>")

    # --- html + equation images -----------------------------------------------------------
    def _html(self, rendered):
        muted = tokens.COLORS["text_muted"]
        parts = []
        for section in C.SECTIONS:
            lines = rendered.sections.get(section, [])
            if not lines:
                continue
            parts.append(f'<p style="color:{muted}; font-size:11px; font-weight:600; '
                         f'margin-top:14px; margin-bottom:2px;">{section.upper()}</p>')
            bullets = []
            for ln in lines:
                if ln.kind == "equation":
                    parts.append(f"<p>{self._img(ln.text)}</p>")
                    if ln.source:
                        parts.append(f'<p style="color:{muted}; font-size:10px; '
                                     f'margin-top:-6px;">{html.escape(ln.source)}</p>')
                elif ln.kind == "bullet":
                    bullets.append(f"<li>{html.escape(ln.text)}</li>")
                else:
                    parts.append(f"<p>{html.escape(ln.text)}</p>")
            if bullets:
                parts.append("<ul>" + "".join(bullets) + "</ul>")
        return "".join(parts)

    def _img(self, tex):
        image = self._image(tex)
        key = hashlib.sha1(tex.encode("utf-8")).hexdigest()[:16]
        url = QUrl(f"eq:{key}")
        self.body.document().addResource(QTextDocument.ResourceType.ImageResource, url, image)
        w = round(image.width() / image.devicePixelRatio())
        h = round(image.height() / image.devicePixelRatio())
        return f'<img src="eq:{key}" width="{w}" height="{h}">'

    def _image(self, tex):
        if tex in self.images:
            return self.images[tex]
        renderer = QSvgRenderer(QByteArray(tex_to_svg(tex, tokens.COLORS["text"])))
        size = renderer.defaultSize()                           # pt from the SVG
        max_w = POPUP_SIZE[0] - _MARGIN - 2 * tokens.space(2)
        scale = min(PT_TO_PX, max_w / max(size.width(), 1))     # long equations shrink to fit
        w, h = max(1, round(size.width() * scale)), max(1, round(size.height() * scale))
        dpr = max(2.0, self.devicePixelRatioF())
        image = QImage(round(w * dpr), round(h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        image.setDevicePixelRatio(dpr)
        self.images[tex] = image
        return image


class ExplainDrawer(QFrame):
    content_changed = Signal(str)       # entry name now shown in the popup

    def __init__(self, state, parent):
        super().__init__(parent)
        self.state = state
        self.setObjectName("explainDrawer")
        self.title = QLabel("Explain")
        self.title.setObjectName("drawerTitle")
        self.title.setToolTip(tip("drawer.title"))
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setObjectName("drawerClose")
        self.close_button.setToolTip(tip("drawer.close"))
        self.hint = QLabel("Click a topic to open its explanation.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.setToolTip(tip("drawer.topics"))
        self.tree = QTreeWidget()
        self.tree.setObjectName("explainTree")
        self.tree.setHeaderHidden(True)
        self.tree.setToolTip(tip("drawer.topics"))
        self.tree.itemClicked.connect(lambda item, _col: self.open_topic(item.data(0, ROLE)))
        self.tree.itemActivated.connect(lambda item, _col: self.open_topic(item.data(0, ROLE)))

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.title, 1)
        head.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(1), tokens.space(1),
                                  tokens.space(1))
        layout.setSpacing(tokens.space(1) // 2)
        layout.addLayout(head)
        layout.addWidget(self.hint)
        layout.addWidget(self.tree, 1)

        self.popup = ExplainPopup(self.window() if parent is not None else None)
        self.is_open = False
        self.entry_name = None
        self.rendered = None
        self._current = ("topic", "method", None)
        self._items = {}                # key -> QTreeWidgetItem
        state.design_ready.connect(lambda *_: self._on_result())
        state.off_design_ready.connect(lambda *_: self.refresh())
        state.view_changed.connect(lambda *_: self.refresh())
        # while a slider or a corner is dragged the popup waits (new numbers would render
        # equations on the GUI thread at every step)
        state.dragging_changed.connect(lambda dragging: None if dragging else self._flush())
        self._pending = False
        self._build_tree()

    @property
    def images(self):
        return self.popup.images

    @property
    def body(self):
        return self.popup.body

    # --- tree -----------------------------------------------------------------------------
    def topic_keys(self):
        """Keys of the tree items, in display order (children after their parent)."""
        return list(self._items)

    def _build_tree(self):
        selected = self._current
        self.tree.clear()
        self._items = {}
        d = self.state.design
        n = d.inputs.n_ramps if d is not None else 0
        terminal = d is not None and any(s.kind == "normal" for s in d.shock_states)
        n_regions = len(d.regions) if d is not None else 0

        def add(label, key, parent=None):
            item = QTreeWidgetItem([label])
            item.setData(0, ROLE, key)
            item.setToolTip(0, tip("drawer.topic"))
            (parent.addChild(item) if parent is not None else self.tree.addTopLevelItem(item))
            self._items[key] = item
            return item

        add("Freestream", ("item", "region", 0))
        for k in range(n):
            add(f"Ramp shock {k + 1}", ("item", "shock", k))
        regions = add("Regions", ("group", "regions", None))
        for i in range(1, n_regions):
            label = "Duct" if i == n_regions - 1 and terminal else f"Behind ramp shock {i}"
            add(label, ("item", "region", i), regions)
        if terminal:
            add("Terminal shock", ("item", "shock", n))
        add("Cowl lip", ("item", "cowl", 0))
        add("Design method", ("topic", "method", None))
        add("Off-design", ("topic", "offdesign", None))
        add("Separation (approximate)", ("topic", "separation", None))
        regions.setExpanded(True)
        self.highlight(*selected[1:]) if selected[0] == "item" else None

    def highlight(self, kind, index):
        """Select the tree item of a canvas selection (no popup)."""
        key = ("item", kind, index)
        if kind == "region" and key not in self._items and index is not None:
            regions = [k for k in self._items if k[:2] == ("item", "region")]
            key = regions[-1] if regions else None
        item = self._items.get(key)
        self.tree.setCurrentItem(item) if item is not None else self.tree.clearSelection()
        return item is not None

    def current_key(self):
        item = self.tree.currentItem()
        return item.data(0, ROLE) if item is not None else None

    # --- open / close (the main window shows the column) ---------------------------------
    def open(self):
        if not self.is_open:
            self.is_open = True
            self._build_tree()

    def close_drawer(self):
        self.is_open = False
        self.popup.hide()

    # --- content ------------------------------------------------------------------------
    def show_item(self, kind, index):
        """The canvas selection: highlight its topic; update the popup if it is open."""
        if kind is None:
            self.tree.clearSelection()
            return
        self.highlight(kind, index)
        if self.popup.isVisible():
            self._current = ("item", kind, index)
            self.refresh()

    def show_topic(self, topic):
        self._current = ("topic", topic, None)
        self.refresh(show=True)

    def open_topic(self, key):
        if key is None or key[0] == "group":
            return
        self._current = key
        self.refresh(show=True)

    def _flush(self):
        if self._pending:
            self._pending = False
            self.refresh()

    def _on_result(self):
        self._build_tree()
        self.refresh()

    def refresh(self, show=False):
        if not self.is_open:
            return
        if self.state.dragging:
            self._pending = True
            return
        if not (show or self.popup.isVisible()):
            return
        s = self.state
        popup = self.popup
        if show:
            self._place_popup()
            popup.show()
            popup.raise_()
        if s.design is None:
            self.entry_name, self.rendered = None, None
            popup.show_message("No valid design", s.design_error or "")
            return
        mode, a, b = self._current
        if mode == "topic":
            if a == "offdesign" and s.off_design is None:
                popup.show_message("Off design", s.off_design_error or
                                   "No off-design result at this Mach.")
                return
            name, ctx = topic_context(a, s.design, s.off_design, s.freestream, s.off_freestream)
        else:
            name, ctx = build_context(s.design, s.off_design, s.freestream, s.off_freestream,
                                      s.active_view, a, b)
            if ctx["fs"] is None and name == "freestream":
                popup.show_message("Freestream", s.freestream_error or "")
                return
        rendered = C.render(C.load(name), ctx)
        self.entry_name, self.rendered = name, rendered
        popup.show_rendered(rendered)
        self.content_changed.emit(name)

    def _place_popup(self):
        """Beside the drawer, over the centre column (never over the tree)."""
        if self.popup.isVisible():
            return
        top_left = self.mapToGlobal(self.rect().topLeft())
        w, h = POPUP_SIZE
        self.popup.move(max(0, top_left.x() - w - tokens.space(1)), top_left.y())
