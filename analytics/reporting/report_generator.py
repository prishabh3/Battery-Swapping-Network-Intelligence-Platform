"""
Executive Report Generator.
Produces PDF and Excel reports for the Chairman's Office and Product Analytics teams.
"""
import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class ExcelReportGenerator:
    """Generates multi-sheet Excel analytics report."""

    def generate(
        self,
        network_kpis: dict,
        batteries_df: pd.DataFrame,
        stations_df: pd.DataFrame,
        optimization_result: dict,
        output_path: Optional[str] = None,
    ) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            wb = writer.book

            # Styles
            header_fmt = wb.add_format({
                "bold": True, "bg_color": "#1a1f36", "font_color": "white",
                "border": 1, "align": "center", "valign": "vcenter",
            })
            _currency_fmt = wb.add_format({"num_format": "₹#,##0", "border": 1})
            _pct_fmt = wb.add_format({"num_format": "0.0%", "border": 1})
            cell_fmt = wb.add_format({"border": 1})

            # ── Sheet 1: Network KPIs ──────────────────────────
            ws = wb.add_worksheet("Network KPIs")
            ws.set_column("A:A", 35)
            ws.set_column("B:B", 20)
            ws.write(0, 0, "BSIP Executive Report", wb.add_format({"bold": True, "font_size": 14}))
            ws.write(1, 0, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
            ws.write(3, 0, "Metric", header_fmt)
            ws.write(3, 1, "Value", header_fmt)
            for i, (k, v) in enumerate(network_kpis.items(), start=4):
                ws.write(i, 0, k.replace("_", " ").title(), cell_fmt)
                ws.write(i, 1, str(v), cell_fmt)

            # ── Sheet 2: Battery Health ────────────────────────
            if not batteries_df.empty:
                display_cols = ["battery_id", "chemistry_type", "current_health",
                                "cycle_count", "replacement_risk", "status"]
                display_cols = [c for c in display_cols if c in batteries_df.columns]
                batteries_df[display_cols].head(2000).to_excel(
                    writer, sheet_name="Battery Health", index=False
                )
                ws2 = writer.sheets["Battery Health"]
                for col_num, col_name in enumerate(display_cols):
                    ws2.write(0, col_num, col_name.replace("_", " ").title(), header_fmt)

            # ── Sheet 3: Station Performance ───────────────────
            if not stations_df.empty:
                display_cols = ["station_id", "name", "city", "capacity", "inventory_count",
                                "status", "utilization_rate", "daily_swaps_7d_avg"]
                display_cols = [c for c in display_cols if c in stations_df.columns]
                stations_df[display_cols].to_excel(
                    writer, sheet_name="Station Performance", index=False
                )

            # ── Sheet 4: Optimization Transfers ───────────────
            if optimization_result.get("recommendations"):
                pd.DataFrame(optimization_result["recommendations"]).to_excel(
                    writer, sheet_name="Transfer Plan", index=False
                )

        buffer.seek(0)
        content = buffer.read()
        if output_path:
            Path(output_path).write_bytes(content)
            logger.info("Excel report saved to %s", output_path)
        return content


class PDFReportGenerator:
    """Generates PDF executive summary using ReportLab."""

    def generate(
        self,
        network_kpis: dict,
        battery_summary: dict,
        optimization_result: dict,
        output_path: Optional[str] = None,
    ) -> bytes:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
            )
        except ImportError:
            logger.warning("ReportLab not available — PDF generation skipped")
            return b""

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                topMargin=2 * cm, bottomMargin=2 * cm,
                                leftMargin=2 * cm, rightMargin=2 * cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title2", parent=styles["Title"],
                                     fontSize=20, textColor=colors.HexColor("#1a1f36"))
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"],
                                  fontSize=13, textColor=colors.HexColor("#4f6bed"),
                                  spaceAfter=6)
        body_style = styles["Normal"]

        story = []

        story.append(Paragraph("Battery Swapping Intelligence Platform", title_style))
        story.append(Paragraph("Executive Performance Report", styles["Heading2"]))
        story.append(Paragraph(f"Report Date: {date.today().strftime('%d %B %Y')}", body_style))
        story.append(Spacer(1, 0.4 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.4 * cm))

        # ── Network KPIs section ───────────────────────────────
        story.append(Paragraph("1. Network Performance Summary", h2_style))
        kpi_items = [
            ("Total Swaps Today", f"{network_kpis.get('total_swaps_today', 0):,}"),
            ("Total Swaps This Month", f"{network_kpis.get('total_swaps_month', 0):,}"),
            ("Revenue Today (est.)", f"₹{network_kpis.get('estimated_revenue_today_inr', 0):,.0f}"),
            ("Revenue This Month (est.)", f"₹{network_kpis.get('estimated_revenue_month_inr', 0):,.0f}"),
            ("Active Stations", str(network_kpis.get("active_stations", 0))),
            ("Offline Stations", str(network_kpis.get("offline_stations", 0))),
            ("Average Network SOH", f"{network_kpis.get('avg_soh_network', 0) * 100:.1f}%"),
            ("Network Utilization", f"{network_kpis.get('network_utilization_rate', 0) * 100:.1f}%"),
        ]
        kpi_table_data = [["Metric", "Value"]] + kpi_items
        kpi_table = Table(kpi_table_data, colWidths=[10 * cm, 6 * cm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1f36")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6fa")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 0.5 * cm))

        # ── Battery Health ─────────────────────────────────────
        story.append(Paragraph("2. Battery Fleet Health", h2_style))
        if battery_summary:
            health_items = [
                ("Total Batteries", str(battery_summary.get("total_batteries", 0))),
                ("Average SOH", f"{battery_summary.get('avg_soh', 0) * 100:.1f}%"),
                ("Critical Risk Batteries", str(battery_summary.get("risk_distribution", {}).get("critical", 0))),
                ("Batteries Needing Replacement (30d)", str(battery_summary.get("batteries_needing_replacement_30d", 0))),
            ]
            dist = battery_summary.get("soh_distribution", {})
            for cat, count in dist.items():
                health_items.append((f"SOH Category — {cat}", str(count)))

            health_table_data = [["Metric", "Value"]] + health_items
            health_table = Table(health_table_data, colWidths=[10 * cm, 6 * cm])
            health_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f6bed")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6fa")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(health_table)

        story.append(Spacer(1, 0.5 * cm))

        # ── Optimization ───────────────────────────────────────
        story.append(Paragraph("3. Inventory Optimization Recommendations", h2_style))
        story.append(Paragraph(
            f"Solver: {optimization_result.get('solver_status', 'N/A')} | "
            f"Total Transfers: {optimization_result.get('total_transfers', 0)} | "
            f"Batteries to Redistribute: {optimization_result.get('batteries_to_redistribute', 0)}",
            body_style,
        ))
        story.append(Spacer(1, 0.3 * cm))

        recs = optimization_result.get("recommendations", [])[:8]
        if recs:
            rec_data = [["From Station", "To Station", "Qty", "Priority"]]
            for r in recs:
                rec_data.append([
                    r.get("from_station_name", "")[:25],
                    r.get("to_station_name", "")[:25],
                    str(r.get("quantity", 0)),
                    r.get("priority", ""),
                ])
            rec_table = Table(rec_data, colWidths=[6 * cm, 6 * cm, 2 * cm, 3 * cm])
            rec_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10b981")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6fa")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(rec_table)

        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb")))
        story.append(Paragraph(
            "Confidential — For internal use by SUN Mobility Chairman's Office and Strategy Teams only.",
            ParagraphStyle("Footer", parent=body_style, fontSize=8,
                           textColor=colors.HexColor("#9ca3af")),
        ))

        doc.build(story)
        content = buffer.getvalue()
        if output_path:
            Path(output_path).write_bytes(content)
            logger.info("PDF report saved to %s", output_path)
        return content
