"""Light desktop presentation helpers; no application or submission actions."""
from html import escape


LIGHT_STYLE = """
QMainWindow, QDialog { background: #ffffff; }
QWidget { color: #101626; font-family: "Helvetica Neue", "Arial", sans-serif; font-size: 14px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #ffffff; }
QWidget#Sidebar { background: #eef3f9; border-right: 1px solid #dce4ed; }
QLabel#Title { font-size: 40px; font-weight: 700; letter-spacing: -1px; }
QLabel#Subtitle { font-size: 20px; color: #657089; }
QLabel#Muted { color: #69758d; }
QLabel#Metric { font-size: 28px; font-weight: 700; }
QLabel#MetricCaption { color: #657089; font-size: 13px; }
QFrame#MetricDivider { background: #e8ecf3; }
QFrame#SourceStrip { background: #ffffff; border: 1px solid #e0e5ee; border-radius: 7px; }
QLabel#Source { padding: 4px 12px; font-size: 13px; }
QPushButton { background: #ffffff; border: 1px solid #d4dce8; border-radius: 6px; padding: 10px 14px; }
QPushButton:hover { background: #edf4ff; border-color: #9ab9eb; }
QPushButton:pressed { background: #dceaff; }
QPushButton:disabled { color: #929fb1; background: #f3f5f8; border-color: #e4e9f0; }
QPushButton#Primary { background: #065dff; border-color: #065dff; color: #ffffff; font-weight: 500; }
QPushButton#Primary:hover { background: #0052e6; }
QPushButton#Primary:disabled { background: #dce8fc; color: #7a95bd; border-color: #dce8fc; }
QPushButton#Outline { color: #005cff; border-color: #6395ff; }
QPushButton#Nav { text-align: left; background: transparent; border: 0; padding: 12px 14px; font-size: 15px; }
QPushButton#Nav:checked { background: #d4e6ff; color: #0054f5; font-weight: 600; }
QPushButton#Nav:hover { background: #e0ebfa; }
QPushButton#FilterTab { background: #f7f9fc; color: #5b6580; padding: 12px 15px; }
QPushButton#FilterTab:checked { background: #065dff; color: #ffffff; border-color: #065dff; }
QPushButton#IconButton { padding: 7px; background: transparent; border: 0; }
QPushButton#IconButton:hover { background: #edf4ff; }
QPushButton#IconButton::menu-indicator { image: none; width: 0; }
QPushButton#Disclosure { text-align: left; border: 0; padding: 6px 0; background: transparent; color: #69758d; font-size: 12px; }
QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #d4dce8; border-radius: 6px; padding: 9px; selection-background-color: #d9e8ff; selection-color: #101626; }
QLineEdit#Search { padding: 12px 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #065dff; }
QComboBox { padding-right: 22px; }
QComboBox QAbstractItemView { background: #fff; color: #101626; selection-background-color: #d9e8ff; selection-color: #101626; }
QTextEdit, QTableWidget { background: #ffffff; border: 1px solid #dce4ee; border-radius: 8px; selection-background-color: #e4efff; selection-color: #101626; }
QTableWidget { gridline-color: #e9edf3; alternate-background-color: #ffffff; }
QTableWidget::item { border-bottom: 1px solid #e9edf3; }
QHeaderView::section { background: #f6f8fb; color: #101626; border: 0; border-bottom: 1px solid #dce4ee; padding: 14px 18px; font-weight: 500; font-size: 13px; }
QFrame#DetailCard { background: #ffffff; border: 1px solid #dce4ee; border-radius: 9px; }
QScrollArea#DetailScroll, QWidget#DetailBody { background: #ffffff; border: 0; }
QLabel#DetailTitle { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#Company { font-size: 19px; }
QFrame#ScoreGood { background: #eefae7; border-radius: 6px; }
QFrame#ScoreReview { background: #fff6de; border-radius: 6px; }
QLabel#ScoreNumber { font-size: 44px; font-weight: 700; }
QLabel#ScoreDenominator { font-size: 22px; }
QLabel#ScoreCaption { font-size: 15px; font-weight: 600; padding-left: 10px; }
QFrame#ScoreDivider { background: #aab5a5; }
QLabel#SectionTitle { font-size: 17px; font-weight: 700; }
QLabel#CheckTitle { font-size: 14px; font-weight: 600; }
QLabel#CheckSubtitle { color: #758098; font-size: 12px; }
QFrame#Separator { background: #dce2eb; }
QLabel#SkillsCaption { font-size: 14px; }
QLabel#SkillChip { background: #f4f7fb; border: 1px solid #dce3ed; border-radius: 10px; padding: 4px 10px; font-size: 11px; color: #4e5b72; }
QLabel#Description { font-size: 13px; color: #4e5b72; }
QFrame#RunJournal { background: #ffffff; border: 1px solid #dce4ee; border-radius: 8px; }
QPushButton#JournalHeader { background: #f6f8fb; border: 0; border-bottom: 1px solid #e0e6ef; border-bottom-left-radius: 0; border-bottom-right-radius: 0; text-align: left; padding: 14px 18px; font-weight: 600; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 16px; background: #eef3fa; }
QTabBar::tab:selected { background: #fff; color: #065dff; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #e7f0ff; }
QToolTip { background: #fff; color: #101626; border: 1px solid #d7e0ec; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 8px; border: 0; }
QScrollBar::handle:vertical { background: #cbd3df; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #ffffff; border: 1px solid #d7e0ec; padding: 5px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #e3eeff; }
"""

DECISION_LABELS = {
    "APPLY": "Подходит", "REVIEW": "Проверить", "SKIP": "Пропущено",
    "QUEUED": "В очереди", "INTERESTING": "Избранное", "SUBMITTED": "Отправлено",
}


def display_decision(record, overrides):
    if record.get("status") in {"SUBMITTED", "SUBMITTED_MANUALLY", "APPLICATION_CONFIRMED"}:
        return "SUBMITTED"
    override = str(overrides.get(str(record.get("job_id", "")), {}).get("decision", "")).upper()
    return "QUEUED" if override == "MANUAL_APPLY" else (override or str(record.get("decision", "")))


def vacancy_detail_html(record, decision):
    """Escape every remote/saved value before presenting rich text."""
    def e(value):
        return escape(str(value if value is not None else ""))
    score = e(record.get("score", "—"))
    title = e(record.get("title", "Вакансия"))
    company = e(record.get("company") or "Компания не определена")
    location = e(record.get("resolved_location") or record.get("location") or "Место не определено")
    label = e(DECISION_LABELS.get(decision, decision))
    color = "#23713e" if decision in {"APPLY", "SUBMITTED"} else "#8a600d"
    evidence = {"strong": "Описание получено", "medium": "Описание неполное", "weak": "Нужно загрузить описание"}.get(record.get("evidence_quality"), "Описание не проверено")
    checks = [e(evidence)]
    if record.get("entry_role"):
        checks.append("Стартовая позиция в названии")
    if record.get("candidate_fit") is not None:
        fit = "Совпадение навыков: " + e(record["candidate_fit"])
        if record.get("expanded_candidate_fit_min") is not None:
            fit += " · минимум " + e(record["expanded_candidate_fit_min"])
        checks.append(fit)
    if record.get("hard_experience"):
        checks.append("Требование опыта 3+ лет")
    if record.get("source") == "startupjobs.cz":
        checks.append("StartupJobs: отклик на сайте вручную")
    blockers = record.get("expanded_apply_blockers") or []
    explanation = "".join("<p>• " + e(b) + "</p>" for b in blockers)
    signals = " · ".join(e(s) for s in (record.get("expanded_signals") or []))
    reason = e(record.get("reason", ""))
    description = e(record.get("description") or "Подробное описание появится после поиска.").replace("\n", "<br>")
    return f"""<html><body style="font-family: sans-serif; color:#192639;">
    <p style="color:#708097;font-size:11px;">{e(record.get('source', ''))}</p>
    <h2 style="font-size:21px;">{title}</h2>
    <p style="font-size:15px;">{company}</p><p style="color:#708097;">{location}</p>
    <table width="100%" bgcolor="#edf6ed" cellpadding="12"><tr><td>
    <span style="font-size:30px;font-weight:700;color:{color};">{score}</span> / 100
    </td><td align="right" style="color:{color};">{label}</td></tr></table>
    <h3>Соответствие вакансии</h3>{''.join('<p>• '+c+'</p>' for c in checks)}
    {('<h3>Что требует проверки</h3>'+explanation) if explanation else ''}
    {('<p style="color:#546982;">'+signals+'</p>') if signals else ''}
    <h3>Описание</h3><p>{description}</p>
    {('<h3>Подробности решения</h3><p style="color:#708097;font-size:11px;">'+reason+'</p>') if reason else ''}
    </body></html>"""
