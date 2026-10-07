"""Light desktop presentation helpers; no application or submission actions."""
from html import escape


LIGHT_STYLE = """
QMainWindow, QDialog { background: #f8faff; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #f8faff; }
QWidget { color: #192639; font-size: 13px; }
QWidget#Sidebar { background: #eef3fa; border-right: 1px solid #dce4ef; }
QLabel#Title { font-size: 27px; font-weight: 700; }
QLabel#Muted { color: #6b7990; }
QLabel#Metric { font-size: 25px; font-weight: 700; }
QLabel#Source { background: #fff; border: 1px solid #dde5ef; border-radius: 8px; padding: 10px; }
QPushButton { background: #fff; border: 1px solid #d4dfed; border-radius: 7px; padding: 9px 12px; }
QPushButton:hover { background: #edf4ff; border-color: #91b8f8; }
QPushButton:pressed { background: #dceaff; }
QPushButton:disabled { color: #96a1b1; background: #f2f5f9; border-color: #e3e8f0; }
QPushButton#Primary { background: #0866f5; border-color: #0866f5; color: #fff; font-weight: 600; }
QPushButton#Primary:hover { background: #0058da; }
QPushButton#Primary:disabled { background: #d7e4f8; color: #7894bf; border-color: #d7e4f8; }
QPushButton#Nav { text-align: left; background: transparent; border: 0; padding: 13px 14px; }
QPushButton#Nav:checked { background: #d9e8ff; color: #065acb; font-weight: 600; }
QPushButton#Nav:hover { background: #e1eafa; }
QLineEdit, QComboBox, QSpinBox { background: #fff; border: 1px solid #d7e0ec; border-radius: 6px; padding: 7px; selection-background-color: #d9e8ff; selection-color: #192639; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #0866f5; }
QComboBox { padding-right: 22px; }
QComboBox QAbstractItemView { background: #fff; color: #192639; selection-background-color: #d9e8ff; selection-color: #192639; }
QTextEdit, QTableWidget { background: #fff; border: 1px solid #dce4ee; border-radius: 8px; selection-background-color: #e3eeff; selection-color: #192639; }
QTableWidget { gridline-color: #edf1f7; alternate-background-color: #fbfcff; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #edf1f7; }
QHeaderView::section { background: #f3f6fb; color: #66758a; border: 0; border-bottom: 1px solid #dce4ee; padding: 12px 8px; font-weight: 600; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 16px; background: #eef3fa; }
QTabBar::tab:selected { background: #fff; color: #0866f5; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #d9e8ff; }
QToolTip { background: #fff; color: #192639; border: 1px solid #d7e0ec; padding: 6px; }
QScrollBar:vertical { background: #f4f7fb; width: 10px; border: 0; }
QScrollBar::handle:vertical { background: #bdcada; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: #fff; border: 1px solid #d7e0ec; padding: 5px; }
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
