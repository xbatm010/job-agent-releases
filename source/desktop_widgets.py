"""Native, resolution-independent components for the light desktop workspace."""
import re
from PySide6.QtCore import Qt, QRect, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton,
    QScrollArea, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)
from desktop_theme import DECISION_LABELS


INK = "#101626"
MUTED = "#69758d"
SOURCE_NAMES = {"jobs.cz": "Jobs.cz", "prace.cz": "Prace.cz", "startupjobs.cz": "StartupJobs.cz"}
SOURCE_COLORS = {"jobs.cz": "#092e9b", "prace.cz": "#df1735", "startupjobs.cz": "#182038"}
ICON_PATHS = {
    "home": '<path d="m3 10 9-8 9 8M5 9v12h5v-7h4v7h5V9"/>',
    "search": '<circle cx="10.5" cy="10.5" r="7.5"/><path d="m16 16 6 6"/>',
    "document": '<path d="M6 2h9l4 4v16H6zM14 2v5h5M9 11h7M9 15h7M9 19h5"/>',
    "list": '<path d="M7 5h14M7 12h14M7 19h14M2 5h1M2 12h1M2 19h1"/>',
    "person": '<circle cx="12" cy="7" r="4"/><path d="M3 22v-3a7 7 0 0 1 7-7h4a7 7 0 0 1 7 7v3z"/>',
    "settings": '<path d="m9 3 1-2h4l1 3 3 1 3-1 2 4-2 2v4l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-4L1 8l2-4 3 1z"/><circle cx="12" cy="12" r="3.5"/>',
    "bookmark": '<path d="M6 3h12v19l-6-4-6 4z"/>',
    "external": '<path d="M14 3h7v7M21 3 11 13M10 5H4v16h16v-6"/>',
    "pin": '<path d="M19 9c0 5-7 12-7 12S5 14 5 9a7 7 0 1 1 14 0z"/><circle cx="12" cy="9" r="2.5"/>',
    "briefcase": '<rect x="3" y="6" width="18" height="15" rx="2"/><path d="M8 6V3h8v3M3 11l9 3 9-3M10 12v4h4v-4"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
    "chevron": '<path d="m8 4 8 8-8 8"/>',
    "down": '<path d="m4 8 8 8 8-8"/>',
    "more": '<circle cx="4" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="20" cy="12" r="1"/>',
    "filter": '<path d="M3 6h18M3 18h18M8 3v6M16 15v6"/>',
    "update": '<path d="M20 8a8 8 0 1 0 0 8M20 2v6h-6"/>',
}


def icon_pixmap(name, color=INK, size=24, background=None):
    """Draw simple line icons at 2x; no platform-dependent emoji glyphs."""
    radius = 12 if name in {"check", "info"} else 5
    bg = f'<rect width="24" height="24" rx="{radius}" fill="{background}"/>' if background else ""
    content = ICON_PATHS.get(name, ICON_PATHS["document"])
    transform = 'transform="translate(4 4) scale(.67)"' if background else ""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{bg}<g {transform} fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{content}</g></svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def ui_icon(name, color=INK, size=24):
    return QIcon(icon_pixmap(name, color, size))


def text_label(text="", name=None, wrap=False):
    label = QLabel(str(text))
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def employment_label(record):
    value = str(record.get("employment_type") or "")
    if value:
        return value
    title = str(record.get("title") or "").lower()
    if re.search(r"part[ -]?time|částečn|zkrácen", title):
        return "Частичная занятость"
    return ""


class FlowLayout(QLayout):
    """Wrap short skill tags at the actual available card width."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect, apply):
        x, y, row_height = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, row_height = rect.x(), y + row_height + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, min(size.width(), rect.width()), size.height()))
            x += size.width() + self.spacing()
            row_height = max(row_height, size.height())
        return y + row_height - rect.y()


class VacancyDelegate(QStyledItemDelegate):
    """Three-line vacancy rows, source marks and semantic score/status pills."""
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        value = str(index.data(Qt.DisplayRole) or "")
        record = index.data(Qt.UserRole + 1) or {}
        decision = index.data(Qt.UserRole + 2) or ""
        opt.text = ""
        opt.state &= ~QStyle.State_HasFocus
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        painter.setClipRect(opt.rect)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = opt.rect.adjusted(18, 0, -12, 0)
        font = QFont(opt.font)
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QColor(INK))
        if index.column() == 0:
            title, _, company = value.partition("\n")
            font.setPixelSize(16)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(rect.x(), rect.y() + 12, rect.width(), 22), Qt.AlignVCenter, painter.fontMetrics().elidedText(title, Qt.ElideRight, rect.width()))
            font.setBold(False)
            font.setPixelSize(15)
            painter.setFont(font)
            painter.setPen(QColor(MUTED))
            painter.drawText(QRect(rect.x(), rect.y() + 36, rect.width(), 20), Qt.AlignVCenter, painter.fontMetrics().elidedText(company, Qt.ElideRight, rect.width()))
            location = str(record.get("resolved_location") or record.get("location") or "Место не определено")
            employment = employment_label(record)
            meta = location + ("  ·  " + employment if employment else "")
            font.setPixelSize(13)
            painter.setFont(font)
            painter.drawPixmap(rect.x(), rect.y() + 62, icon_pixmap("pin", MUTED, 14))
            painter.drawText(QRect(rect.x() + 20, rect.y() + 59, rect.width() - 20, 20), Qt.AlignVCenter, painter.fontMetrics().elidedText(meta, Qt.ElideRight, rect.width() - 20))
        elif index.column() == 1:
            source = str(record.get("source") or "")
            rect = opt.rect.adjusted(12, 0, -6, 0)
            mark = QRectF(rect.x(), rect.center().y() - 13, 26, 26)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(SOURCE_COLORS.get(source, MUTED)))
            painter.drawRoundedRect(mark, 5, 5)
            font.setPixelSize(20)
            font.setBold(True)
            font.setItalic(source != "startupjobs.cz")
            painter.setFont(font)
            painter.setPen(Qt.white)
            painter.drawText(mark, Qt.AlignCenter, source[:1].upper() or "?")
            font.setPixelSize(13)
            font.setBold(False)
            font.setItalic(False)
            painter.setFont(font)
            painter.setPen(QColor(INK))
            painter.drawText(rect.adjusted(36, 0, 0, 0), Qt.AlignVCenter, SOURCE_NAMES.get(source, value))
        else:
            if index.column() == 2:
                try:
                    strong = int(record.get("score", 0)) >= 70
                except (ValueError, TypeError):
                    strong = False
                bg, fg = ("#dcf5d5", INK) if strong else ("#edf0f5", INK)
                width = 76
            else:
                bg, fg = {"APPLY": ("#dcf5d5", "#164a21"), "SUBMITTED": ("#dceaff", "#005af5"), "REVIEW": ("#fff0c2", "#865207"), "QUEUED": ("#e0ebff", "#225bac")}.get(decision, ("#edf0f5", "#434d60"))
                font.setPixelSize(12)
                painter.setFont(font)
                width = min(painter.fontMetrics().horizontalAdvance(value) + 20, opt.rect.width() - 26)
            pill = QRectF(opt.rect.x() + 10, opt.rect.center().y() - 14, width, 28)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bg))
            painter.drawRoundedRect(pill, 6, 6)
            painter.setPen(QColor(fg))
            painter.drawText(pill, Qt.AlignCenter, value)
            if index.column() == 3 and opt.state & QStyle.State_Selected and opt.rect.width() > width + 36:
                painter.drawPixmap(opt.rect.right() - 21, opt.rect.center().y() - 7, icon_pixmap("chevron", INK, 14))
        painter.restore()


class VacancyDetail(QScrollArea):
    """Native card body. All vacancy text is plain text, including descriptions."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DetailScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("DetailBody")
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 4, 0)
        self.content.setSpacing(8)
        self.setWidget(self.body)
        self.record = {}

    def _clear(self):
        while self.content.count():
            item = self.content.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def setPlainText(self, text):
        self._clear()
        self.content.addWidget(text_label(text, "Muted", True))
        self.content.addStretch()

    def set_record(self, record, decision):
        self.record = record
        self._clear()
        title = text_label(record.get("title") or "Вакансия", "DetailTitle", True)
        self.content.addWidget(title)
        self.content.addWidget(text_label(record.get("company") or "Компания не определена", "Company", True))
        meta = QWidget()
        row = QHBoxLayout(meta)
        row.setContentsMargins(0, 0, 0, 0)
        pin = QLabel()
        pin.setPixmap(icon_pixmap("pin", MUTED, 18))
        row.addWidget(pin)
        location = str(record.get("resolved_location") or record.get("location") or "Место не определено")
        employment = employment_label(record)
        row.addWidget(text_label(location + ("  ·  " + employment if employment else ""), "Muted", True), 1)
        self.content.addWidget(meta)

        score_panel = QFrame()
        good = decision in {"APPLY", "SUBMITTED"}
        score_panel.setObjectName("ScoreGood" if good else "ScoreReview")
        score_row = QHBoxLayout(score_panel)
        score_row.setContentsMargins(18, 12, 18, 12)
        score_number = text_label(record.get("score", "—"), "ScoreNumber")
        score_row.addWidget(score_number)
        score_row.addWidget(text_label("/ 100", "ScoreDenominator"))
        score_row.addStretch()
        divider = QFrame()
        divider.setObjectName("ScoreDivider")
        divider.setFixedSize(1, 40)
        score_row.addWidget(divider)
        caption = {"APPLY": "Хорошее\nсоответствие", "SUBMITTED": "Отклик\nотправлен", "REVIEW": "Нужна\nпроверка"}.get(decision, DECISION_LABELS.get(decision, decision))
        score_row.addWidget(text_label(caption, "ScoreCaption"))
        self.content.addWidget(score_panel)
        self.content.addWidget(text_label("Почему подходит" if decision == "APPLY" else "Соответствие вакансии", "SectionTitle"))

        if record.get("entry_role"):
            self._check("Стартовая позиция", "Junior / Student / Trainee в названии", True)
        elif record.get("hard_experience"):
            self._check("Требуется опыт работы", "В описании есть требование 3+ лет", False)
        else:
            self._check("Уровень позиции", "Стартовый уровень не подтверждён", None)
        fit, minimum = record.get("candidate_fit"), record.get("expanded_candidate_fit_min")
        if fit is not None:
            try:
                skills_good = float(fit) >= float(minimum) if minimum is not None else None
            except (TypeError, ValueError):
                skills_good = None
            self._check("Совпадение навыков", f"Оценка профиля: {fit}" + (f" · минимум {minimum}" if minimum is not None else ""), skills_good)
        evidence = record.get("evidence_quality")
        self._check("Описание проверено" if evidence == "strong" else "Описание требует проверки", "Полное описание получено" if evidence == "strong" else "Данных для уверенной оценки недостаточно", evidence == "strong")

        gate = str(record.get("location_gate") or "")
        if "unknown" in gate:
            self._check("Место работы не подтверждено", "Нужно уточнить город перед подготовкой отклика", False)
        elif gate.startswith("outside_prague"):
            self._check("За пределами выбранного региона", location, False)
        for blocker in record.get("expanded_apply_blockers") or []:
            self._check("Условие отбора не выполнено", str(blocker), False)
        if record.get("source") == "startupjobs.cz":
            self._check("Отклик на сайте", "StartupJobs: заполни форму работодателя вручную", None)

        line = QFrame()
        line.setObjectName("Separator")
        line.setFixedHeight(1)
        self.content.addWidget(line)
        if fit is not None:
            self.content.addWidget(text_label(f"Навыки: {fit}" + (f" / минимум {minimum}" if minimum is not None else ""), "SkillsCaption"))
        signals = record.get("expanded_signals") or []
        if signals:
            tags = QWidget()
            flow = FlowLayout(tags)
            names = {"sql": "SQL", "excel": "Excel", "python": "Python", "bi_reporting": "BI / Reporting", "analytics": "Анализ данных", "reporting": "Reporting", "power_bi": "Power BI", "data": "Данные", "database": "Базы данных"}
            for signal in signals:
                chip = text_label(names.get(signal, str(signal)), "SkillChip")
                chip.setToolTip("Навык или направление, найденное в описании вакансии")
                flow.addWidget(chip)
            self.content.addWidget(tags)

        self.description_toggle = QPushButton("Описание и детали оценки")
        self.description_toggle.setObjectName("Disclosure")
        self.description_toggle.setIcon(ui_icon("down", MUTED, 14))
        self.description_toggle.setCheckable(True)
        self.content.addWidget(self.description_toggle)
        details = text_label((record.get("description") or "Описание пока не получено.") + ("\n\n" + str(record["reason"]) if record.get("reason") else ""), "Description", True)
        details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details.hide()
        self.description_toggle.toggled.connect(details.setVisible)
        self.content.addWidget(details)
        self.content.addStretch()
        self.verticalScrollBar().setValue(0)

    def _check(self, title, subtitle, good):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(12)
        mark = QLabel()
        color = "#33a129" if good else "#d69624" if good is False else "#8b97aa"
        mark.setPixmap(icon_pixmap("check" if good else "info", "#ffffff", 26, color))
        row.addWidget(mark, 0, Qt.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        copy.addWidget(text_label(title, "CheckTitle", True))
        copy.addWidget(text_label(subtitle, "CheckSubtitle", True))
        row.addLayout(copy, 1)
        self.content.addWidget(row_widget)
