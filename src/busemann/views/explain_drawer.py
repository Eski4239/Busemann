"""Explain drawer (spec 4.6): shown in the right column, which widens to DRAWER_W while it
is open (the centre column shrinks; nothing is covered).

For the selected item (or a topic) it shows the governing relations as equations, the same
relations with this case's numbers, a plain-language note and the assumptions. Content is
the templated .md files in resources/explain (busemann.explain.content); every number is an
api value formatted by the template, never computed here.
"""
import hashlib
import html

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal
from PySide6.QtGui import QImage, QPainter, QTextDocument
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTextBrowser, QToolButton, QVBoxLayout

from ..explain import content as C
from ..explain.mathsvg import PT_TO_PX, tex_to_svg
from ..explain.select import build_context, topic_context
from ..theme import tokens
from ..tooltips import tip

DRAWER_W = 420          # px, right-column width while the drawer is open
SLIDE_MS = 200          # column width animation
_MARGIN = 2 * tokens.space(2) + 8      # text-browser margins + scrollbar, px


class ExplainDrawer(QFrame):
    content_changed = Signal(str)       # entry name now shown

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
        link = f'style="color:{tokens.COLORS["accent"]}; text-decoration:none;"'
        self.topics = QLabel(
            f'<a href="method" {link}>Design method</a> · '
            f'<a href="offdesign" {link}>Off-design</a> · <a href="selection" {link}>Selection</a>')
        self.topics.setObjectName("drawerTopics")
        self.topics.setToolTip(tip("drawer.topics"))
        self.topics.linkActivated.connect(self._on_topic)
        self.body = QTextBrowser()
        self.body.setObjectName("explainBody")
        self.body.setOpenLinks(False)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.title, 1)
        head.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(1), tokens.space(1), 0)
        layout.setSpacing(tokens.space(1) // 2)
        layout.addLayout(head)
        layout.addWidget(self.topics)
        layout.addWidget(self.body, 1)

        self.is_open = False
        self.entry_name = None
        self.rendered = None
        self.images = {}                # tex -> QImage (for tests)
        self._current = ("item", None, None)
        state.design_ready.connect(lambda *_: self.refresh())
        state.off_design_ready.connect(lambda *_: self.refresh())
        state.view_changed.connect(lambda *_: self.refresh())
        # while a Mach slider is dragged the drawer waits: new numbers would mean rendering
        # equations on the GUI thread at every step
        state.dragging_changed.connect(lambda dragging: None if dragging else self._flush())
        self._pending = False

    # --- open / close (the main window animates the column width) --------------------
    def open(self):
        if not self.is_open:
            self.is_open = True
            self.refresh()

    def close_drawer(self):
        self.is_open = False

    # --- content ------------------------------------------------------------------------
    def show_item(self, kind, index):
        """Explain a canvas / table selection; nothing selected shows the design method."""
        self._current = ("item", kind, index)
        self.refresh()

    def show_topic(self, topic):
        self._current = ("topic", topic, None)
        self.refresh()

    def _on_topic(self, link):
        if link == "selection":
            canvas_sel = self.window().current_canvas().selection
            self.show_item(*canvas_sel)
        else:
            self.show_topic(link)

    def _flush(self):
        if self._pending:
            self._pending = False
            self.refresh()

    def refresh(self):
        if not self.is_open:
            return
        if self.state.dragging:
            self._pending = True
            return
        s = self.state
        if s.design is None:
            self._show_message("No valid design", s.design_error or "")
            return
        mode, a, b = self._current
        if mode == "topic":
            if a == "offdesign" and s.off_design is None:
                self._show_message("Off design", s.off_design_error or
                                   "No off-design result at this Mach.")
                return
            name, ctx = topic_context(a, s.design, s.off_design, s.freestream, s.off_freestream)
        else:
            name, ctx = build_context(s.design, s.off_design, s.freestream, s.off_freestream,
                                      s.active_view, a, b)
            if ctx["fs"] is None and name == "freestream":
                self._show_message("Freestream", s.freestream_error or "")
                return
        rendered = C.render(C.load(name), ctx)
        self.entry_name, self.rendered = name, rendered
        self.title.setText(rendered.title)
        self.body.setHtml(self._html(rendered))
        self.content_changed.emit(name)

    def _show_message(self, title, text):
        self.entry_name, self.rendered = None, None
        self.title.setText(title)
        self.body.setHtml(f"<p>{html.escape(text)}</p>")

    # --- html + equation images -------------------------------------------------------------
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
        max_w = DRAWER_W - _MARGIN - 2 * tokens.space(2)
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
