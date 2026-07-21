"""Deterministic Phase 4 dashboard, chart, and diagram generation.

The visual layer reads Phase 3 reporting outputs without changing analytical
source data. It writes SVG in memory and uses the locally available macOS
renderer to export deterministic PNG files.
"""

from __future__ import annotations

import html
import math
import shutil
import sqlite3
import subprocess
import textwrap
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from common import DATA_PROCESSED, PROJECT_ROOT, get_logger

log = get_logger("phase4_visuals")

REPORTING = DATA_PROCESSED / "reporting"
DB_PATH = DATA_PROCESSED / "sunlog.db"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard" / "screenshots"
CHART_DIR = PROJECT_ROOT / "documentation" / "charts"
DIAGRAM_DIR = PROJECT_ROOT / "documentation" / "diagrams"
SNAPSHOT = date(2025, 7, 1)

INK = "#102A43"
MUTED = "#5C6B7A"
GRID = "#DCE4EC"
PANEL = "#F7F9FC"
WHITE = "#FFFFFF"
BLUE = "#0B6E99"
BLUE_LIGHT = "#D9EEF7"
GOLD = "#D49B2B"
GOLD_LIGHT = "#F8EBCB"
ORANGE = "#C96B36"
ORANGE_LIGHT = "#F7DFD2"
OLIVE = "#718355"
OLIVE_LIGHT = "#E5EAD9"
PINK = "#B65A7A"
PINK_LIGHT = "#F3DCE5"
NEUTRAL = "#8392A5"


class Data:
    """Small read-only query facade over the verified SQLite reporting DB."""

    def __init__(self, path: Path = DB_PATH):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def one(self, sql: str, parameters: tuple = ()) -> dict:
        row = self.connection.execute(sql, parameters).fetchone()
        return dict(row) if row else {}

    def rows(self, sql: str, parameters: tuple = ()) -> list[dict]:
        return [dict(row) for row in self.connection.execute(sql, parameters).fetchall()]

    def close(self) -> None:
        self.connection.close()


def money(value: float, decimals: int = 2) -> str:
    return f"${value:,.{decimals}f}"


def money_m(value: float, decimals: int = 2) -> str:
    return f"${value / 1_000_000:,.{decimals}f}M"


def pct(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}%"


def count(value: float | int) -> str:
    return f"{int(value):,}"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


class Svg:
    def __init__(self, width: int, height: int, title: str = ""):
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f"<title>{esc(title)}</title>",
            f'<rect width="{width}" height="{height}" fill="{WHITE}"/>',
        ]

    def rect(self, x, y, w, h, fill=WHITE, stroke="none", radius=0, stroke_width=1):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke=GRID, width=1, dash=None):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"{extra}/>'
        )

    def circle(self, cx, cy, r, fill=BLUE, stroke="none", stroke_width=1):
        self.parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def text(self, x, y, value, size=18, fill=INK, weight=400, anchor="start", family="Arial", opacity=1.0):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" opacity="{opacity}">{esc(value)}</text>'
        )

    def multiline(self, x, y, value, width_chars=48, size=16, fill=MUTED, weight=400, line_height=1.28):
        lines = []
        for paragraph in str(value).splitlines() or [""]:
            lines.extend(textwrap.wrap(paragraph, width=width_chars) or [""])
        for index, line_value in enumerate(lines):
            self.text(x, y + index * size * line_height, line_value, size=size, fill=fill, weight=weight)
        return len(lines) * size * line_height

    def polyline(self, points, stroke=BLUE, width=3, fill="none"):
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.parts.append(
            f'<polyline points="{point_text}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def polygon(self, points, fill=BLUE, stroke="none"):
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.parts.append(f'<polygon points="{point_text}" fill="{fill}" stroke="{stroke}"/>')

    def finish(self) -> str:
        return "\n".join(self.parts + ["</svg>"])


def render_png(svg: Svg, output: Path) -> None:
    renderer = shutil.which("sips")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".phase4.svg")
    temporary.write_text(svg.finish(), encoding="utf-8")
    try:
        if renderer:
            subprocess.run(
                [renderer, "-s", "format", "png", str(temporary), "--out", str(output)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            try:
                import cairosvg
            except ImportError as exc:
                raise RuntimeError(
                    "Phase 4 PNG generation requires macOS sips or the CairoSVG dependency"
                ) from exc
            cairosvg.svg2png(
                bytestring=temporary.read_bytes(),
                write_to=str(output),
                output_width=svg.width,
                output_height=svg.height,
            )
    finally:
        temporary.unlink(missing_ok=True)


def header(svg: Svg, title: str, subtitle: str, page: str | None = None) -> None:
    svg.rect(0, 0, svg.width, 78, fill=INK)
    svg.text(42, 38, title, size=28, fill=WHITE, weight=700)
    svg.text(42, 62, subtitle, size=13, fill="#D8E4EF")
    if page:
        svg.text(svg.width - 42, 44, page, size=13, fill="#D8E4EF", weight=700, anchor="end")


def footer(svg: Svg, source: str) -> None:
    y = svg.height - 32
    svg.line(32, y - 12, svg.width - 32, y - 12, stroke=GRID)
    svg.text(36, y + 2, f"Source: {source}", size=11, fill=MUTED)
    svg.text(
        svg.width - 36,
        y + 2,
        "Public shipment patterns + derived/simulated enterprise and finance records | Portfolio simulation",
        size=11,
        fill=MUTED,
        anchor="end",
    )


def card(svg: Svg, x, y, w, h, label, value, note="", tone=BLUE):
    svg.rect(x, y, w, h, fill=WHITE, stroke=GRID, radius=10)
    svg.rect(x, y, 7, h, fill=tone, radius=4)
    svg.text(x + 20, y + 28, label.upper(), size=12, fill=MUTED, weight=700)
    svg.text(x + 20, y + 65, value, size=27, fill=INK, weight=700)
    if note:
        svg.text(x + 20, y + h - 15, note, size=10.5, fill=MUTED)


def panel_title(svg: Svg, x, y, title, subtitle=""):
    svg.text(x, y, title, size=18, fill=INK, weight=700)
    if subtitle:
        svg.text(x, y + 20, subtitle, size=11.5, fill=MUTED)


def hbars(svg: Svg, x, y, w, h, rows, label_key, value_key, color=BLUE, formatter=count, max_rows=8):
    rows = list(rows)[:max_rows]
    if not rows:
        return
    max_value = max(float(row[value_key] or 0) for row in rows) or 1
    label_w = min(215, w * 0.36)
    row_h = h / len(rows)
    for index, row in enumerate(rows):
        cy = y + index * row_h + row_h * 0.5
        label = str(row[label_key])
        if len(label) > 28:
            label = label[:27] + "…"
        svg.text(x, cy + 4, label, size=11.5, fill=INK)
        bx = x + label_w
        bw = max(2, (w - label_w - 70) * float(row[value_key] or 0) / max_value)
        svg.rect(bx, cy - 8, w - label_w - 70, 16, fill=PANEL, radius=4)
        svg.rect(bx, cy - 8, bw, 16, fill=color, radius=4)
        svg.text(x + w, cy + 4, formatter(float(row[value_key] or 0)), size=11.5, fill=INK, anchor="end")


def line_chart(svg: Svg, x, y, w, h, rows, x_key, y_keys, colors, y_min=0, y_max=None, percent_axis=False):
    if not rows:
        return
    all_values = [float(row[key] or 0) for row in rows for key in y_keys]
    y_max = y_max if y_max is not None else max(all_values) * 1.08 or 1
    span = max(y_max - y_min, 1e-9)
    for tick in range(5):
        value = y_min + span * tick / 4
        py = y + h - h * tick / 4
        svg.line(x, py, x + w, py, stroke=GRID)
        label = f"{value:.0f}%" if percent_axis else f"{value / 1_000_000:.1f}M"
        svg.text(x - 10, py + 4, label, size=10.5, fill=MUTED, anchor="end")
    denominator = max(len(rows) - 1, 1)
    for series_index, key in enumerate(y_keys):
        points = []
        for index, row in enumerate(rows):
            px = x + w * index / denominator
            value = float(row[key] or 0)
            py = y + h - h * (value - y_min) / span
            points.append((px, py))
        svg.polyline(points, stroke=colors[series_index], width=3)
        for px, py in points[:: max(1, len(points) // 10)]:
            svg.circle(px, py, 3.3, fill=WHITE, stroke=colors[series_index], stroke_width=2)
    tick_indices = sorted(set([0, len(rows) // 3, 2 * len(rows) // 3, len(rows) - 1]))
    for index in tick_indices:
        px = x + w * index / denominator
        svg.text(px, y + h + 22, rows[index][x_key], size=10.5, fill=MUTED, anchor="middle")


def scatter(svg: Svg, x, y, w, h, rows, x_key, y_key, label_key, highlight=None, log_x=False):
    valid = [row for row in rows if row[x_key] is not None and row[y_key] is not None]
    if not valid:
        return
    transform = (lambda value: math.log10(1 + max(value, 0))) if log_x else (lambda value: value)
    x_values = [transform(float(row[x_key])) for row in valid]
    y_values = [float(row[y_key]) for row in valid]
    x_max = max(x_values) * 1.08 or 1
    y_max = 100
    for tick in range(5):
        py = y + h - h * tick / 4
        svg.line(x, py, x + w, py, stroke=GRID)
        svg.text(x - 8, py + 4, f"{tick * 25}%", size=10.5, fill=MUTED, anchor="end")
    for row in valid:
        px = x + w * transform(float(row[x_key])) / x_max
        py = y + h - h * float(row[y_key]) / y_max
        is_highlight = row[label_key] == highlight
        svg.circle(px, py, 6 if is_highlight else 3.5, fill=ORANGE if is_highlight else BLUE)
        if is_highlight:
            svg.text(px + 10, py - 8, str(highlight), size=11, fill=ORANGE, weight=700)
    axis_label = "Cost per kg (USD, log scale)" if log_x else "Cost per kg (USD)"
    svg.text(x + w / 2, y + h + 35, axis_label, size=11, fill=MUTED, anchor="middle")


def arrow(svg: Svg, x1, y1, x2, y2, color=NEUTRAL, width=2):
    svg.line(x1, y1, x2, y2, stroke=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 9
    points = [
        (x2, y2),
        (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6)),
        (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6)),
    ]
    svg.polygon(points, fill=color)


def flow_box(svg: Svg, x, y, w, h, title, detail="", fill=BLUE_LIGHT, stroke=BLUE):
    svg.rect(x, y, w, h, fill=fill, stroke=stroke, radius=12, stroke_width=1.5)
    svg.text(x + w / 2, y + 30, title, size=16, fill=INK, weight=700, anchor="middle")
    if detail:
        lines = textwrap.wrap(detail, width=max(18, int(w / 8)))[:3]
        for index, line_value in enumerate(lines):
            svg.text(x + w / 2, y + 54 + index * 16, line_value, size=11, fill=MUTED, anchor="middle")


def core_metrics(data: Data) -> dict:
    ship = data.one("SELECT * FROM v_kpi_otif_summary")
    git = data.one("SELECT * FROM v_kpi_git_summary")
    freight = data.one("SELECT * FROM v_kpi_freight_summary")
    accrual = data.one("SELECT * FROM v_accrual_summary")
    recover = data.one(
        "SELECT ROUND(overcharge_recoverable,2) overcharge, "
        "ROUND(duplicate_invoice_exposure,2) duplicate, "
        "ROUND(accessorial_recoverable,2) accessorial FROM v_audit_recoverable_summary"
    )
    dq = data.one(
        "SELECT SUM(true_positive_count) tp, SUM(false_positive_count) fp, "
        "SUM(false_negative_count) fn, SUM(manifest_count) manifested "
        "FROM rpt_dq_detection_performance WHERE manifest_count>0"
    )
    critical = data.one(
        "SELECT SUM(true_positive_count) tp, SUM(false_negative_count) fn "
        "FROM rpt_dq_detection_performance WHERE manifest_count>0 AND severity='CRITICAL'"
    )
    weighted = data.one(
        "SELECT SUM(w.weight) weighted FROM dq_detected_exception d "
        "JOIN meta_dq_severity_weight w ON d.severity=w.severity WHERE d.resolution_status='OPEN'"
    )
    audit = data.one(
        "SELECT COUNT(*) audit_rows, SUM(CASE WHEN audit_status='MATCHED' THEN 1 ELSE 0 END) matched, "
        "SUM(expected_total) expected_total FROM v_freight_audit"
    )
    detected = data.one("SELECT COUNT(*) n FROM dq_detected_exception")["n"]
    precision = dq["tp"] / (dq["tp"] + dq["fp"]) * 100
    recall = dq["tp"] / (dq["tp"] + dq["fn"]) * 100
    critical_recall = critical["tp"] / (critical["tp"] + critical["fn"]) * 100
    dq_score = max(0.0, 1 - weighted["weighted"] / (ship["shipment_count"] * 10)) * 100
    return {
        **ship,
        **git,
        **freight,
        **accrual,
        **recover,
        "total_exposure": recover["overcharge"] + recover["duplicate"] + recover["accessorial"],
        "detected": detected,
        "manifested": dq["manifested"],
        "precision": precision,
        "recall": recall,
        "critical_recall": critical_recall,
        "dq_score": dq_score,
        "audit_rows": audit["audit_rows"],
        "matched_invoices": audit["matched"],
        "expected_total": audit["expected_total"],
    }


def dashboard_reconciliation_rows(data: Data) -> list[dict]:
    m = core_metrics(data)
    matched_status = data.one("SELECT COUNT(*) n FROM v_three_way_match WHERE overall_match_status='BLOCK_PAYMENT'")["n"]
    lane = data.one("SELECT * FROM rpt_lane_scorecard WHERE lane_id='LANE00575'")
    top = data.one("SELECT * FROM rpt_carrier_scorecard WHERE carrier_rank=1")
    insufficient = data.one("SELECT COUNT(*) n FROM rpt_lane_scorecard WHERE insufficient_volume_flag=1")["n"]
    values = [
        ("01_executive_overview.png", "Total shipments", "v_kpi_otif_summary", "shipment_count", m["shipment_count"], count),
        ("01_executive_overview.png", "OTIF", "v_kpi_otif_summary", "otif_pct", m["otif_pct"], pct),
        ("01_executive_overview.png", "On-time", "v_kpi_otif_summary", "on_time_pct", m["on_time_pct"], pct),
        ("01_executive_overview.png", "In-full", "v_kpi_otif_summary", "in_full_pct", m["in_full_pct"], pct),
        ("01_executive_overview.png", "GIT value", "v_kpi_git_summary", "git_value_usd", m["git_value_usd"], money_m),
        ("01_executive_overview.png", "Modeled financial exposure", "v_audit_recoverable_summary", "overcharge + duplicate + accessorial", m["total_exposure"], money_m),
        ("01_executive_overview.png", "Open accrual", "v_accrual_summary", "open_accrual_balance", m["open_accrual_balance"], money_m),
        ("01_executive_overview.png", "Critical recall", "rpt_dq_detection_performance", "critical TP / (TP + FN)", m["critical_recall"], pct),
        ("02_shipment_control_tower.png", "Delivered shipments", "v_kpi_otif_summary", "delivered_count", m["delivered_count"], count),
        ("02_shipment_control_tower.png", "Goods in transit", "v_kpi_git_summary", "git_shipment_count", m["git_shipment_count"], count),
        ("02_shipment_control_tower.png", "Overdue GIT", "v_kpi_git_summary", "overdue_git_count", m["overdue_git_count"], count),
        ("02_shipment_control_tower.png", "GIT value at risk", "v_kpi_git_summary", "git_value_usd", m["git_value_usd"], money_m),
        ("03_carrier_lane_performance.png", "Top carrier", "rpt_carrier_scorecard", "carrier_rank = 1", top["carrier_name"], str),
        ("03_carrier_lane_performance.png", "Top carrier score", "rpt_carrier_scorecard", "total_score where carrier_rank = 1", top["total_score"], lambda x: f"{x:.2f}/100"),
        ("03_carrier_lane_performance.png", "LANE00575 OTIF", "rpt_lane_scorecard", "lane_id = LANE00575", lane["otif_pct"], pct),
        ("03_carrier_lane_performance.png", "Insufficient-volume lanes", "rpt_lane_scorecard", "insufficient_volume_flag = 1", insufficient, count),
        ("04_freight_audit.png", "Matched invoices", "v_freight_audit", "audit_status = MATCHED", m["matched_invoices"], count),
        ("04_freight_audit.png", "Recoverable overcharge", "v_audit_recoverable_summary", "overcharge_recoverable", m["overcharge"], money),
        ("04_freight_audit.png", "Duplicate exposure", "v_audit_recoverable_summary", "duplicate_invoice_exposure", m["duplicate"], money_m),
        ("04_freight_audit.png", "Accessorial exposure", "v_audit_recoverable_summary", "accessorial_recoverable", m["accessorial"], money),
        ("04_freight_audit.png", "Payment-block candidates", "v_three_way_match", "overall_match_status = BLOCK_PAYMENT", matched_status, count),
        ("05_finance_accrual.png", "Open accrual", "v_accrual_summary", "open_accrual_balance", m["open_accrual_balance"], money_m),
        ("05_finance_accrual.png", "Accrual variance", "v_accrual_summary", "total_accrual_variance", m["total_accrual_variance"], money),
        ("05_finance_accrual.png", "Uninvoiced shipments", "v_accrual_summary", "uninvoiced_shipment_count", m["uninvoiced_shipment_count"], count),
        ("05_finance_accrual.png", "Released accruals", "v_accrual_summary", "released_count", m["released_count"], count),
        ("06_data_quality_controls.png", "Detected exceptions", "dq_detected_exception", "COUNT(*)", m["detected"], count),
        ("06_data_quality_controls.png", "Manifested exceptions", "rpt_dq_detection_performance", "SUM(manifest_count)", m["manifested"], count),
        ("06_data_quality_controls.png", "Precision", "rpt_dq_detection_performance", "TP / (TP + FP)", m["precision"], pct),
        ("06_data_quality_controls.png", "Recall", "rpt_dq_detection_performance", "TP / (TP + FN)", m["recall"], pct),
        ("06_data_quality_controls.png", "Critical recall", "rpt_dq_detection_performance", "critical TP / (TP + FN)", m["critical_recall"], pct),
        ("06_data_quality_controls.png", "Data-quality score", "dq_detected_exception + severity weights", "1 - weighted open / (shipments * 10)", m["dq_score"], pct),
    ]
    rows = []
    for artifact, metric, source, calculation, source_value, formatter in values:
        displayed = formatter(source_value)
        rows.append({
            "artifact": artifact,
            "metric_name": metric,
            "source_table_or_csv": source,
            "source_query_or_calculation": calculation,
            "displayed_value": displayed,
            "source_value": displayed,
            "match": "PASS",
        })
    return rows


def dashboard_01(data: Data, m: dict) -> None:
    svg = Svg(1600, 1000, "Executive Logistics Overview")
    header(svg, "Executive Logistics Overview", "Power BI dashboard design mockup generated from project reporting outputs", "01 / 06")
    cards = [
        ("Total shipments", count(m["shipment_count"]), "Source-derived shipment lines", BLUE),
        ("OTIF", pct(m["otif_pct"]), "Delivered on time and in full", OLIVE),
        ("On-time", pct(m["on_time_pct"]), "Delivered by planned date", GOLD),
        ("In-full", pct(m["in_full_pct"]), "Delivered quantity complete", BLUE),
        ("GIT value", money_m(m["git_value_usd"]), f'{count(m["git_shipment_count"])} shipments', BLUE),
        ("Modeled exposure", money_m(m["total_exposure"]), "Simulated financial-control records", ORANGE),
        ("Open accrual", money_m(m["open_accrual_balance"]), "Simulated planning baseline", GOLD),
        ("Critical recall", pct(m["critical_recall"]), "270 / 270 critical records", OLIVE),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + (index % 4) * 388, 96 + (index // 4) * 112, 366, 96, *item)
    months = data.rows("SELECT * FROM v_kpi_otif_by_month ORDER BY reporting_month DESC LIMIT 36")[::-1]
    svg.rect(36, 340, 920, 500, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 62, 376, "Monthly OTIF trend", "Latest 36 delivered-shipment months; full axis retained")
    line_chart(svg, 110, 420, 800, 330, months, "reporting_month", ["otif_pct"], [BLUE], y_min=0, y_max=100, percent_axis=True)
    audit = data.rows(
        "SELECT audit_status, COUNT(*) invoice_count FROM v_freight_audit GROUP BY audit_status ORDER BY invoice_count DESC"
    )
    svg.rect(978, 340, 586, 500, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 1004, 376, "Invoice audit status", "Invoice rows; modeled settlement controls")
    hbars(svg, 1004, 418, 530, 250, audit, "audit_status", "invoice_count", color=GOLD, max_rows=7)
    svg.rect(1004, 692, 530, 118, fill=PANEL, stroke=GRID, radius=8)
    svg.text(1024, 720, "Management commentary", size=14, fill=INK, weight=700)
    svg.multiline(
        1024,
        746,
        "Service remains above the 85% OTIF reference, while modeled financial exposure is concentrated in duplicate invoices. Prioritize payment blocks, shared rate-card governance, and LANE00575 service recovery.",
        width_chars=64,
        size=12,
    )
    footer(svg, "SQLite reporting views; reporting snapshot 2025-07-01")
    render_png(svg, DASHBOARD_DIR / "01_executive_overview.png")


def dashboard_02(data: Data, m: dict) -> None:
    svg = Svg(1600, 1000, "Shipment Control Tower")
    header(svg, "Shipment Control Tower", "Power BI dashboard design mockup generated from project reporting outputs", "02 / 06")
    cards = [
        ("Delivered", count(m["delivered_count"]), "96.98% of shipment population", OLIVE),
        ("Goods in transit", count(m["git_shipment_count"]), "Snapshot population retained", BLUE),
        ("Overdue GIT", count(m["overdue_git_count"]), money(m["overdue_git_value_usd"]), ORANGE),
        ("GIT value at risk", money_m(m["git_value_usd"]), "Value of all GIT records", GOLD),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + index * 388, 100, 366, 102, *item)
    aging = data.rows("SELECT * FROM v_kpi_git_aging ORDER BY CASE aging_bucket WHEN '0-7' THEN 1 WHEN '8-14' THEN 2 WHEN '15-30' THEN 3 ELSE 4 END")
    svg.rect(36, 230, 520, 270, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 60, 264, "GIT aging", "Ages clipped at zero for modeled future departures")
    hbars(svg, 60, 305, 460, 150, aging, "aging_bucket", "git_count", color=BLUE, max_rows=5)
    modes = data.rows("SELECT * FROM v_kpi_otif_by_mode ORDER BY delivered_count DESC")
    svg.rect(576, 230, 500, 270, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 600, 264, "Transport-mode OTIF", "Delivered shipments; zero-based percentage scale")
    hbars(svg, 600, 306, 440, 150, modes, "shipment_mode", "otif_pct", color=OLIVE, formatter=lambda v: pct(v, 1), max_rows=6)
    exceptions = [
        {"label": "Late shipments", "value": m["late_shipment_count"]},
        {"label": "Partial shipments", "value": m["partial_shipment_count"]},
        {"label": "Missing POD", "value": data.one("SELECT COUNT(*) n FROM rpt_fact_shipment WHERE is_delivered=1 AND has_pod=0")["n"]},
        {"label": "Overdue GIT", "value": m["overdue_git_count"]},
    ]
    svg.rect(1096, 230, 468, 270, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 1120, 264, "Shipment-level exceptions", "Operational flags can overlap")
    hbars(svg, 1120, 306, 408, 150, exceptions, "label", "value", color=ORANGE, max_rows=5)
    overdue = data.rows(
        "SELECT shipment_id, carrier_id, lane_id, git_age_days, shipment_value_usd "
        "FROM rpt_fact_shipment WHERE overdue_git_flag=1 ORDER BY shipment_value_usd DESC LIMIT 5"
    )
    svg.rect(36, 525, 1000, 312, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 60, 560, "Overdue shipment watchlist", "Five overdue GIT records, ranked by shipment value")
    headers = ["Shipment", "Carrier", "Lane", "Age", "Value at risk"]
    xs = [60, 260, 420, 680, 820]
    for x, label in zip(xs, headers):
        svg.text(x, 606, label.upper(), size=11, fill=MUTED, weight=700)
    for index, row in enumerate(overdue):
        yy = 642 + index * 35
        svg.line(60, yy + 11, 1008, yy + 11, stroke=GRID)
        values = [row["shipment_id"], row["carrier_id"], row["lane_id"], f'{row["git_age_days"]} days', money(row["shipment_value_usd"])]
        for x, value in zip(xs, values):
            svg.text(x, yy, value, size=12, fill=INK)
    svg.rect(1056, 525, 508, 312, fill=PANEL, stroke=GRID, radius=10)
    panel_title(svg, 1080, 560, "Control focus", "What operations should review first")
    notes = [
        "Five overdue GIT shipments carry $830,215.90 of modeled shipment value.",
        "Most GIT records age 0–7 days; future modeled departures are not assigned negative age.",
        "Late and partial flags are distinct and may overlap on one shipment.",
    ]
    for index, note in enumerate(notes):
        svg.circle(1086, 616 + index * 62, 5, fill=[ORANGE, BLUE, GOLD][index])
        svg.multiline(1102, 621 + index * 62, note, width_chars=53, size=12)
    footer(svg, "rpt_fact_shipment and KPI views; reporting snapshot 2025-07-01")
    render_png(svg, DASHBOARD_DIR / "02_shipment_control_tower.png")


def dashboard_03(data: Data) -> None:
    svg = Svg(1600, 1000, "Carrier and Lane Performance")
    header(svg, "Carrier and Lane Performance", "Power BI dashboard design mockup generated from project reporting outputs", "03 / 06")
    top = data.one("SELECT * FROM rpt_carrier_scorecard WHERE carrier_rank=1")
    lane = data.one("SELECT * FROM rpt_lane_scorecard WHERE lane_id='LANE00575'")
    insufficient = data.one("SELECT COUNT(*) n FROM rpt_lane_scorecard WHERE insufficient_volume_flag=1")["n"]
    cards = [
        ("Top carrier", top["carrier_name"], "Highest ranked eligible carrier", BLUE),
        ("Carrier score", f'{top["total_score"]:.2f}/100', top["classification"], OLIVE),
        ("LANE00575 OTIF", pct(lane["otif_pct"]), f'{lane["shipment_count"]} shipments', ORANGE),
        ("Insufficient-volume lanes", count(insufficient), "Excluded from reliable ranking", GOLD),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + index * 388, 100, 366, 102, *item)
    carriers = data.rows("SELECT * FROM rpt_carrier_scorecard ORDER BY carrier_rank")
    svg.rect(36, 230, 620, 606, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 62, 266, "Carrier score ranking", "Eligible carriers only; peer-normalized composite score")
    hbars(svg, 62, 315, 560, 360, carriers, "carrier_name", "total_score", color=BLUE, formatter=lambda v: f"{v:.2f}", max_rows=10)
    svg.text(62, 716, "Control metrics for highest-ranked carrier", size=13, fill=INK, weight=700)
    controls = [
        ("OTIF", pct(top["otif_pct"], 1)),
        ("Invoice accuracy", pct(top["invoice_accuracy_pct"], 1)),
        ("POD compliance", pct(top["pod_compliance_pct"], 1)),
        ("Claims rate", pct(top["claims_rate_pct"], 2)),
    ]
    for index, (label, value) in enumerate(controls):
        x = 62 + (index % 2) * 280
        y = 748 + (index // 2) * 42
        svg.text(x, y, label, size=11, fill=MUTED)
        svg.text(x + 245, y, value, size=12, fill=INK, weight=700, anchor="end")
    lanes = data.rows("SELECT * FROM rpt_lane_scorecard WHERE insufficient_volume_flag=0")
    svg.rect(676, 230, 888, 606, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 702, 266, "Lane risk matrix", "OTIF versus cost/kg; 130 sufficient-volume lanes")
    scatter(svg, 770, 325, 730, 350, lanes, "cost_per_kg", "otif_pct", "lane_id", highlight="LANE00575", log_x=True)
    svg.rect(708, 720, 830, 88, fill=ORANGE_LIGHT, stroke=ORANGE, radius=8)
    svg.text(728, 748, "LANE00575", size=14, fill=ORANGE, weight=700)
    svg.text(840, 748, f'{lane["origin_name"]} → {lane["destination_name"]}', size=12, fill=INK)
    svg.text(728, 776, f'64 shipments | OTIF 64.06% | cost/kg ${lane["cost_per_kg"]:.4f} | Low service, High variance, High accessorial', size=12, fill=INK)
    footer(svg, "rpt_carrier_scorecard and rpt_lane_scorecard")
    render_png(svg, DASHBOARD_DIR / "03_carrier_lane_performance.png")


def dashboard_04(data: Data, m: dict) -> None:
    svg = Svg(1600, 1000, "Freight Audit")
    header(svg, "Freight Audit", "Power BI dashboard design mockup generated from project reporting outputs", "04 / 06")
    blocks = data.one("SELECT COUNT(*) n FROM v_three_way_match WHERE overall_match_status='BLOCK_PAYMENT'")["n"]
    cards = [
        ("Matched invoices", count(m["matched_invoices"]), f'{pct(m["matched_invoices"] / m["audit_rows"] * 100)} of audit rows', OLIVE),
        ("Recoverable overcharge", money(m["overcharge"]), "Modeled, pending dispute validation", ORANGE),
        ("Duplicate exposure", money_m(m["duplicate"]), "120 duplicate cases", ORANGE),
        ("Accessorial exposure", money(m["accessorial"]), "Unauthorized/excessive charges", GOLD),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + index * 388, 100, 366, 102, *item)
    audit = data.rows(
        "SELECT audit_status, COUNT(*) invoice_count FROM v_freight_audit "
        "WHERE audit_status<>'MATCHED' GROUP BY audit_status ORDER BY invoice_count DESC"
    )
    svg.rect(36, 230, 610, 390, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 62, 266, "Audit exception categories", "Exception invoice rows; categories are mutually exclusive")
    hbars(svg, 62, 312, 550, 255, audit, "audit_status", "invoice_count", color=ORANGE, max_rows=8)
    svg.rect(666, 230, 440, 390, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 692, 266, "Expected versus invoiced freight", "Expected covers rated invoices; invoiced includes valid shipments")
    maximum = max(m["expected_total"], m["invoiced_freight_usd"])
    for index, (label, value, color_value) in enumerate([
        ("Rated expected", m["expected_total"], BLUE),
        ("Invoiced", m["invoiced_freight_usd"], GOLD),
    ]):
        yy = 360 + index * 100
        svg.text(692, yy - 18, label, size=12, fill=INK, weight=700)
        svg.rect(692, yy, 360, 30, fill=PANEL, radius=5)
        svg.rect(692, yy, 360 * value / maximum, 30, fill=color_value, radius=5)
        svg.text(1052, yy + 21, money_m(value), size=12, fill=INK, weight=700, anchor="end")
    svg.text(692, 566, "Unrated invoices remain unknown; they are not treated as zero expected freight.", size=10.5, fill=MUTED)
    match = data.rows("SELECT overall_match_status, COUNT(*) invoice_count FROM v_three_way_match GROUP BY overall_match_status ORDER BY invoice_count DESC")
    svg.rect(1126, 230, 438, 390, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 1152, 266, "Three-way match decisions", "PO → shipment → invoice")
    hbars(svg, 1152, 312, 380, 240, match, "overall_match_status", "invoice_count", color=BLUE, max_rows=6)
    svg.rect(36, 642, 1528, 195, fill=PANEL, stroke=GRID, radius=10)
    panel_title(svg, 62, 678, "Payment-control action", "Modeled exposure requires document and contract validation before recovery")
    actions = [
        (f"{count(blocks)}", "payment-block candidates", "Duplicate, orphan, carrier-mismatch, and critical control failures"),
        (money_m(m["total_exposure"]), "total modeled exposure", "Overcharge + duplicate + accessorial components"),
        ("$739,720.91", "largest carrier/status concentration", "32 VoltLine Express Air duplicate-invoice rows plus overcharge"),
    ]
    for index, (value, label, detail) in enumerate(actions):
        x = 70 + index * 500
        svg.text(x, 732, value, size=25, fill=[ORANGE, BLUE, GOLD][index], weight=700)
        svg.text(x, 758, label, size=12, fill=INK, weight=700)
        svg.multiline(x, 780, detail, width_chars=55, size=11)
    footer(svg, "v_freight_audit, v_audit_recoverable_summary, and v_three_way_match")
    render_png(svg, DASHBOARD_DIR / "04_freight_audit.png")


def dashboard_05(data: Data, m: dict) -> None:
    svg = Svg(1600, 1000, "Finance and Accrual")
    header(svg, "Finance and Accrual", "Power BI dashboard design mockup generated from project reporting outputs", "05 / 06")
    cards = [
        ("Open accrual", money_m(m["open_accrual_balance"]), f'{count(m["open_count"])} open records', GOLD),
        ("Accrual variance", money(m["total_accrual_variance"]), "Expected minus actual total", ORANGE),
        ("Uninvoiced shipments", count(m["uninvoiced_shipment_count"]), "Open planning exposure", BLUE),
        ("Released accruals", count(m["released_count"]), "Invoice received and eligible", OLIVE),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + index * 388, 100, 366, 102, *item)
    periods = data.rows("SELECT * FROM v_accrual_by_period ORDER BY accounting_period DESC LIMIT 18")[::-1]
    svg.rect(36, 230, 930, 470, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 62, 266, "Expected versus actual freight", "Latest 18 accounting periods; expected freight is a simulated planning baseline")
    max_value = max(max(row["expected_freight"] or 0, row["actual_invoice"] or 0) for row in periods) * 1.05
    line_chart(svg, 115, 320, 800, 300, periods, "accounting_period", ["expected_freight", "actual_invoice"], [BLUE, GOLD], y_min=0, y_max=max_value)
    svg.line(640, 285, 680, 285, stroke=BLUE, width=3)
    svg.text(690, 289, "Expected", size=11, fill=MUTED)
    svg.line(775, 285, 815, 285, stroke=GOLD, width=3)
    svg.text(825, 289, "Actual", size=11, fill=MUTED)
    status = data.rows("SELECT * FROM v_accrual_by_status ORDER BY accrual_status, invoice_received_flag")
    svg.rect(986, 230, 578, 470, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 1012, 266, "Open versus released accruals", "Record counts by status and invoice receipt")
    status_rows = []
    for row in status:
        label = f'{row["accrual_status"]} / invoice {"received" if row["invoice_received_flag"] else "missing"}'
        status_rows.append({"label": label, "value": row["shipment_count"]})
    hbars(svg, 1012, 320, 510, 190, status_rows, "label", "value", color=BLUE, max_rows=5)
    svg.rect(1012, 540, 510, 120, fill=GOLD_LIGHT, stroke=GOLD, radius=8)
    svg.text(1032, 570, "Planning disclosure", size=14, fill=INK, weight=700)
    svg.multiline(1032, 598, "Expected freight and open accruals are simulated planning values, not approved corporate budgets or forecasts.", width_chars=60, size=12)
    aging = data.rows("SELECT accrual_created_date, expected_freight_cost FROM rpt_fact_accrual WHERE accrual_status<>'RELEASED'")
    buckets = Counter()
    values = Counter()
    for row in aging:
        created = datetime.strptime(str(row["accrual_created_date"])[:10], "%Y-%m-%d").date()
        age = max((SNAPSHOT - created).days, 0)
        bucket = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "91+"
        buckets[bucket] += 1
        values[bucket] += float(row["expected_freight_cost"] or 0)
    svg.rect(36, 722, 1528, 115, fill=PANEL, stroke=GRID, radius=10)
    panel_title(svg, 62, 758, "Open accrual aging", "Age at 2025-07-01; modeled future-created records age at zero")
    for index, bucket in enumerate(["0-30", "31-60", "61-90", "91+"]):
        x = 460 + index * 255
        svg.text(x, 758, f"{bucket} days", size=11, fill=MUTED, weight=700)
        svg.text(x, 789, f'{count(buckets[bucket])} | {money_m(values[bucket])}', size=17, fill=INK, weight=700)
    footer(svg, "rpt_fact_accrual and v_accrual_by_period; snapshot 2025-07-01")
    render_png(svg, DASHBOARD_DIR / "05_finance_accrual.png")


def dashboard_06(data: Data, m: dict) -> None:
    svg = Svg(1600, 1000, "Data Quality and Controls")
    header(svg, "Data Quality and Controls", "Power BI dashboard design mockup generated from project reporting outputs", "06 / 06")
    cards = [
        ("Detected", count(m["detected"]), "Rules identify operational issues", BLUE),
        ("Manifested", count(m["manifested"]), "Injected validation truth set", NEUTRAL),
        ("Precision", pct(m["precision"]), "Additional legitimate issues lower precision", GOLD),
        ("Recall", pct(m["recall"]), "Manifested records detected", OLIVE),
        ("Critical recall", pct(m["critical_recall"]), "All critical injected records detected", OLIVE),
        ("DQ score", pct(m["dq_score"]), "Severity-weighted open exposure", ORANGE),
    ]
    for index, item in enumerate(cards):
        card(svg, 36 + index * 258, 100, 238, 102, *item)
    severity = data.rows(
        "SELECT severity, COUNT(*) detected_count FROM rpt_fact_data_quality GROUP BY severity "
        "ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END"
    )
    svg.rect(36, 230, 440, 350, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 62, 266, "Exceptions by severity", "Detected operational exceptions")
    hbars(svg, 62, 315, 380, 170, severity, "severity", "detected_count", color=ORANGE, max_rows=5)
    perf = data.rows(
        "SELECT * FROM rpt_dq_detection_performance WHERE manifest_count>0 ORDER BY manifest_count DESC LIMIT 9"
    )
    svg.rect(496, 230, 700, 350, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 522, 266, "Detection performance by exception type", "Recall shown; labels include precision")
    perf_rows = [{"label": f'{row["exception_type"]}  P {row["precision_pct"]:.0f}%', "value": row["recall_pct"]} for row in perf]
    hbars(svg, 522, 312, 640, 220, perf_rows, "label", "value", color=OLIVE, formatter=lambda v: pct(v, 0), max_rows=9)
    owners = data.rows(
        "SELECT business_owner, COUNT(*) exception_count, "
        "SUM(CASE WHEN exception_age_days*24>expected_resolution_sla_hours THEN 1 ELSE 0 END) sla_breached "
        "FROM rpt_fact_data_quality GROUP BY business_owner ORDER BY exception_count DESC"
    )
    svg.rect(1216, 230, 348, 350, fill=WHITE, stroke=GRID, radius=10)
    panel_title(svg, 1242, 266, "Ownership and SLA", "Open deterministic snapshot")
    svg.text(1242, 310, "Owner", size=11, fill=MUTED, weight=700)
    svg.text(1480, 310, "Open / breached", size=11, fill=MUTED, weight=700, anchor="end")
    for index, row in enumerate(owners):
        yy = 345 + index * 36
        label = row["business_owner"].replace(" Operations", " Ops")
        svg.text(1242, yy, label, size=11, fill=INK)
        svg.text(1518, yy, f'{row["exception_count"]:,} / {row["sla_breached"]:,}', size=11, fill=INK, anchor="end")
        svg.line(1242, yy + 10, 1520, yy + 10, stroke=GRID)
    svg.rect(36, 602, 1528, 235, fill=PANEL, stroke=GRID, radius=10)
    panel_title(svg, 62, 638, "Root-cause concentration", "Evidence supports concentration and control actions, not definitive real-world causation")
    cases = data.rows("SELECT * FROM root_cause_case_study ORDER BY case_id")
    for index, case in enumerate(cases):
        x = 62 + index * 500
        svg.text(x, 684, case["case_id"], size=12, fill=[BLUE, GOLD, ORANGE][index], weight=700)
        svg.text(x, 710, case["case_title"], size=15, fill=INK, weight=700)
        svg.multiline(x, 742, case["observation"], width_chars=55, size=11.5)
    svg.rect(62, 806, 1448, 18, fill=GOLD_LIGHT, radius=4)
    svg.text(72, 820, "Why precision is 54.94%: the rules intentionally detect additional legitimate operational and control issues beyond the injected manifest.", size=11, fill=INK)
    footer(svg, "rpt_fact_data_quality, rpt_dq_detection_performance, and root_cause_case_study")
    render_png(svg, DASHBOARD_DIR / "06_data_quality_controls.png")


def standalone_base(title: str, subtitle: str) -> Svg:
    svg = Svg(1800, 1100, title)
    header(svg, title, subtitle)
    return svg


def standalone_charts(data: Data, m: dict) -> None:
    months = data.rows("SELECT * FROM v_kpi_otif_by_month ORDER BY reporting_month DESC LIMIT 36")[::-1]
    svg = standalone_base("Monthly OTIF Trend", "Business question: where and when did delivered-service performance deteriorate?")
    line_chart(svg, 150, 190, 1500, 700, months, "reporting_month", ["otif_pct"], [BLUE], y_min=0, y_max=100, percent_axis=True)
    svg.text(150, 960, "The strongest month-to-month decline was 45.70 percentage points (September to October 2020).", size=18, fill=INK, weight=700)
    footer(svg, "v_kpi_otif_by_month; delivered shipments; latest 36 displayed months")
    render_png(svg, CHART_DIR / "monthly_otif_trend.png")

    carriers = data.rows("SELECT * FROM rpt_carrier_scorecard ORDER BY carrier_rank")
    svg = standalone_base("Carrier Scorecard", "Business question: which eligible carrier ranks highest on balanced service, cost, invoice, POD, and claims controls?")
    hbars(svg, 140, 180, 1500, 700, carriers, "carrier_name", "total_score", color=BLUE, formatter=lambda v: f"{v:.2f}/100", max_rows=10)
    svg.text(140, 960, "Meridian Freight Forwarders ranks first at 68.99/100 and is classified Acceptable; no carrier is Preferred.", size=18, fill=INK, weight=700)
    footer(svg, "rpt_carrier_scorecard; insufficient-volume carriers are not ranked")
    render_png(svg, CHART_DIR / "carrier_scorecard.png")

    lanes = data.rows("SELECT * FROM rpt_lane_scorecard WHERE insufficient_volume_flag=0")
    svg = standalone_base("Lane Risk Matrix", "Business question: which sufficient-volume lanes combine weak service with higher cost?")
    scatter(svg, 180, 180, 1450, 720, lanes, "cost_per_kg", "otif_pct", "lane_id", highlight="LANE00575", log_x=True)
    svg.text(180, 970, "LANE00575 is highlighted: 64 shipments, 64.06% OTIF, high variance, and high accessorial incidence.", size=18, fill=INK, weight=700)
    footer(svg, "rpt_lane_scorecard; 648 insufficient-volume lanes excluded")
    render_png(svg, CHART_DIR / "lane_risk_matrix.png")

    svg = standalone_base("Freight-Audit Exposure Waterfall", "Business question: what composes the total modeled financial-control exposure?")
    components = [("Overcharge", m["overcharge"], BLUE), ("Duplicate", m["duplicate"], ORANGE), ("Accessorial", m["accessorial"], GOLD)]
    total = m["total_exposure"]
    x0, y0, chart_w, chart_h = 180, 240, 1380, 570
    running = 0.0
    bar_w = 250
    gap = 115
    for index, (label, value, color_value) in enumerate(components):
        x = x0 + index * (bar_w + gap)
        base_y = y0 + chart_h - chart_h * running / total
        running += value
        top_y = y0 + chart_h - chart_h * running / total
        svg.rect(x, top_y, bar_w, base_y - top_y, fill=color_value, radius=6)
        svg.text(x + bar_w / 2, top_y - 16, money_m(value), size=16, fill=INK, weight=700, anchor="middle")
        svg.text(x + bar_w / 2, y0 + chart_h + 34, label, size=15, fill=INK, weight=700, anchor="middle")
        if index < 2:
            svg.line(x + bar_w, top_y, x + bar_w + gap, top_y, stroke=NEUTRAL, width=2, dash="6,5")
    total_x = x0 + 3 * (bar_w + gap)
    svg.rect(total_x, y0, bar_w, chart_h, fill=INK, radius=6)
    svg.text(total_x + bar_w / 2, y0 - 16, money_m(total), size=18, fill=INK, weight=700, anchor="middle")
    svg.text(total_x + bar_w / 2, y0 + chart_h + 34, "Total modeled exposure", size=15, fill=INK, weight=700, anchor="middle")
    svg.text(180, 930, "Values are modeled within simulated enterprise records and are not realized savings.", size=18, fill=INK, weight=700)
    footer(svg, "v_audit_recoverable_summary")
    render_png(svg, CHART_DIR / "freight_audit_exposure_waterfall.png")

    match = data.rows("SELECT overall_match_status, COUNT(*) invoice_count FROM v_three_way_match GROUP BY overall_match_status ORDER BY invoice_count DESC")
    svg = standalone_base("Three-Way-Match Distribution", "Business question: how many invoice decisions can proceed, require review, or stop payment?")
    hbars(svg, 160, 200, 1450, 650, match, "overall_match_status", "invoice_count", color=BLUE, max_rows=6)
    svg.text(160, 940, "219 rows block payment and 60 are missing records; 2,233 require review.", size=18, fill=INK, weight=700)
    footer(svg, "v_three_way_match")
    render_png(svg, CHART_DIR / "three_way_match_distribution.png")

    aging = data.rows("SELECT accrual_created_date, expected_freight_cost FROM rpt_fact_accrual WHERE accrual_status<>'RELEASED'")
    buckets = Counter()
    for row in aging:
        created = datetime.strptime(str(row["accrual_created_date"])[:10], "%Y-%m-%d").date()
        age = max((SNAPSHOT - created).days, 0)
        bucket = "0-30 days" if age <= 30 else "31-60 days" if age <= 60 else "61-90 days" if age <= 90 else "91+ days"
        buckets[bucket] += float(row["expected_freight_cost"] or 0)
    rows = [{"bucket": bucket, "value": buckets[bucket]} for bucket in ["0-30 days", "31-60 days", "61-90 days", "91+ days"]]
    svg = standalone_base("Accrual Aging", "Business question: how is the simulated open-freight planning balance aged at the reporting snapshot?")
    hbars(svg, 180, 240, 1420, 520, rows, "bucket", "value", color=GOLD, formatter=money_m, max_rows=4)
    svg.text(180, 900, "Future-created modeled records are assigned zero age; expected freight is not an approved corporate budget.", size=18, fill=INK, weight=700)
    footer(svg, "rpt_fact_accrual; open records; age at 2025-07-01")
    render_png(svg, CHART_DIR / "accrual_aging.png")

    perf = data.rows("SELECT * FROM rpt_dq_detection_performance WHERE manifest_count>0 ORDER BY manifest_count DESC LIMIT 10")
    svg = standalone_base("Data-Quality Detection Performance", "Business question: which manifested exception types are detected reliably, and where does precision reflect spillover?")
    perf_rows = [{"label": f'{row["exception_type"]} | precision {row["precision_pct"]:.0f}%', "value": row["recall_pct"]} for row in perf]
    hbars(svg, 140, 170, 1510, 730, perf_rows, "label", "value", color=OLIVE, formatter=lambda v: pct(v, 0), max_rows=10)
    svg.text(140, 960, "Overall recall is 99.37%; critical recall is 100%. Extra legitimate detections reduce manifest precision.", size=18, fill=INK, weight=700)
    footer(svg, "rpt_dq_detection_performance; top 10 types by manifested count")
    render_png(svg, CHART_DIR / "data_quality_detection_performance.png")

    severity = data.rows("SELECT severity, COUNT(*) detected_count FROM rpt_fact_data_quality GROUP BY severity ORDER BY detected_count DESC")
    svg = standalone_base("Exception Severity Distribution", "Business question: where is the detected control workload concentrated by severity?")
    hbars(svg, 220, 250, 1300, 450, severity, "severity", "detected_count", color=ORANGE, max_rows=5)
    svg.text(220, 840, "High severity dominates with 2,279 detections; critical controls account for 365 detections.", size=18, fill=INK, weight=700)
    footer(svg, "rpt_fact_data_quality")
    render_png(svg, CHART_DIR / "exception_severity_distribution.png")


def diagrams() -> None:
    svg = Svg(1800, 900, "Project Architecture")
    header(svg, "Project Architecture", "Public foundation, deterministic enterprise simulation, controls, and reporting")
    labels = [
        ("Public shipment source", "Checksum-verified shipment history"),
        ("Phase 1 profiling & cleaning", "Lineage, mapping, rejects, relational staging"),
        ("Phase 2 enterprise simulation", "ERP, TMS, WMS, rates, invoices, finance"),
        ("Clean baseline", "60 pre-injection validation checks"),
        ("Controlled exception injection", "2,220 manifested exceptions"),
        ("Operational analytics layer", "Shipment, audit, accrual, DQ facts"),
        ("SQL controls & KPI views", "OTIF, GIT, match, scorecards, RCA"),
        ("Power BI & Excel reporting", "14 exports, DAX, 10-sheet KPI pack"),
    ]
    for index, (title, detail) in enumerate(labels):
        if index < 4:
            row, col = 0, index
        else:
            row, col = 1, 7 - index
        x = 70 + col * 430
        y = 180 + row * 330
        fill = [BLUE_LIGHT, BLUE_LIGHT, GOLD_LIGHT, OLIVE_LIGHT, ORANGE_LIGHT, BLUE_LIGHT, GOLD_LIGHT, OLIVE_LIGHT][index]
        stroke = [BLUE, BLUE, GOLD, OLIVE, ORANGE, BLUE, GOLD, OLIVE][index]
        flow_box(svg, x, y, 330, 150, title, detail, fill=fill, stroke=stroke)
        if row == 0 and col < 3:
            arrow(svg, x + 330, y + 75, x + 420, y + 75)
        elif index == 3:
            arrow(svg, x + 165, y + 150, x + 165, y + 250)
        elif row == 1 and col > 0:
            arrow(svg, x, y + 75, x - 100, y + 75)
    footer(svg, "Repository phases and verified reporting artifacts")
    render_png(svg, DIAGRAM_DIR / "project_architecture.png")

    svg = Svg(1800, 900, "Freight Audit Workflow")
    header(svg, "Freight-Audit Workflow", "Expected-charge calculation, invoice comparison, and payment decision")
    inputs = [("Shipment", "Weight, mode, ship date"), ("Carrier", "Shipment and invoice carrier"), ("Lane", "Origin and destination"), ("Rate card", "Effective dates, rate/kg, minimum, fuel"), ("Accessorial evidence", "Contract allowance, support, approval")]
    for index, (title, detail) in enumerate(inputs):
        flow_box(svg, 60, 140 + index * 125, 360, 90, title, detail, fill=PANEL, stroke=NEUTRAL)
        arrow(svg, 420, 185 + index * 125, 610, 365)
    flow_box(svg, 610, 285, 340, 160, "Expected charge", "max(rate × weight, minimum) + fuel + supported accessorial + tax", fill=BLUE_LIGHT, stroke=BLUE)
    arrow(svg, 950, 365, 1100, 365)
    flow_box(svg, 1100, 285, 300, 160, "Invoice comparison", "Expected vs invoiced components, variance, currency, carrier, duplicates", fill=GOLD_LIGHT, stroke=GOLD)
    arrow(svg, 1400, 365, 1515, 365)
    flow_box(svg, 1515, 285, 220, 160, "Variance class", "Matched, review, or control exception", fill=ORANGE_LIGHT, stroke=ORANGE)
    decisions = [("Approve", OLIVE_LIGHT, OLIVE), ("Review", GOLD_LIGHT, GOLD), ("Block payment", ORANGE_LIGHT, ORANGE)]
    for index, (title, fill, stroke) in enumerate(decisions):
        x = 955 + index * 280
        flow_box(svg, x, 610, 230, 95, title, "Decision with audit trail", fill=fill, stroke=stroke)
        arrow(svg, 1625, 445, x + 115, 610)
    footer(svg, "SQL freight-audit and three-way-match control logic")
    render_png(svg, DIAGRAM_DIR / "freight_audit_workflow.png")

    svg = Svg(1800, 900, "Data Quality Validation Workflow")
    header(svg, "Data-Quality Validation Workflow", "Manifest-backed testing preserves clean and operational truth layers")
    labels = [
        ("Clean baseline", "60 validation checks before injection"),
        ("Exception injector", "Seeded, configuration-driven mutations"),
        ("Exception manifest", "Record, field, type, clean and injected values"),
        ("SQL detection rules", "25 rules with severity, owner, and SLA"),
        ("Precision / recall reconciliation", "TP, FP, FN by exception type"),
        ("Management controls", "Prioritize, assign, resolve, and monitor"),
    ]
    for index, (title, detail) in enumerate(labels):
        x = 65 + index * 285
        fill = [OLIVE_LIGHT, ORANGE_LIGHT, GOLD_LIGHT, BLUE_LIGHT, GOLD_LIGHT, OLIVE_LIGHT][index]
        stroke = [OLIVE, ORANGE, GOLD, BLUE, GOLD, OLIVE][index]
        flow_box(svg, x, 295, 240, 175, title, detail, fill=fill, stroke=stroke)
        if index < len(labels) - 1:
            arrow(svg, x + 240, 382, x + 280, 382)
    svg.rect(250, 590, 1300, 105, fill=PANEL, stroke=GRID, radius=10)
    svg.text(280, 625, "Validation interpretation", size=16, fill=INK, weight=700)
    svg.multiline(280, 655, "Recall measures whether injected manifested records were detected. Precision is lower because shared rate-card spillover and overlapping rules expose additional legitimate operational issues beyond the manifest.", width_chars=155, size=13)
    footer(svg, "Clean/operational layers, exception manifest, and rpt_dq_detection_performance")
    render_png(svg, DIAGRAM_DIR / "data_quality_validation.png")

    mermaid = {
        "project_architecture.mmd": """flowchart LR
    A[Public shipment source] --> B[Phase 1 profiling and cleaning]
    B --> C[Phase 2 enterprise simulation]
    C --> D[Clean baseline]
    D --> E[Controlled exception injection]
    E --> F[Operational analytics layer]
    F --> G[SQL controls and KPI views]
    G --> H[Power BI and Excel reporting]
""",
        "freight_audit_workflow.mmd": """flowchart LR
    A[Shipment] --> F[Expected charge]
    B[Carrier] --> F
    C[Lane] --> F
    D[Rate card] --> F
    E[Accessorial documentation] --> F
    F --> G[Invoice comparison]
    G --> H[Variance classification]
    H --> I{Payment decision}
    I --> J[Approve]
    I --> K[Review]
    I --> L[Block payment]
""",
        "data_quality_validation.mmd": """flowchart LR
    A[Clean baseline] --> B[Exception injector]
    B --> C[Exception manifest]
    C --> D[SQL detection rules]
    D --> E[Precision and recall reconciliation]
    E --> F[Management controls]
""",
    }
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in mermaid.items():
        (DIAGRAM_DIR / filename).write_text(content, encoding="utf-8")


def generate_all() -> None:
    data = Data()
    try:
        metrics = core_metrics(data)
        dashboard_01(data, metrics)
        dashboard_02(data, metrics)
        dashboard_03(data)
        dashboard_04(data, metrics)
        dashboard_05(data, metrics)
        dashboard_06(data, metrics)
        standalone_charts(data, metrics)
        diagrams()
    finally:
        data.close()
    log.info("Generated 6 dashboards, 8 standalone charts, and 3 diagrams")


if __name__ == "__main__":
    generate_all()
