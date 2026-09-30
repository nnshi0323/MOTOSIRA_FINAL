"""
MOTOSIRA — exportable technical report (thesis Obj. 5): one PDF per diagnostic session.
Fault identification only — no repair instructions (out of the approved scope).
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
from reportlab.lib.units import mm  # type: ignore
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

import config

SEV_COLOR = {0: "#2E7D32", 1: "#B8860B", 2: "#C1590A", 3: "#C62828"}


def _table(rows, highlight_first=False):
    t = Table(rows, colWidths=[55 * mm, 110 * mm])
    style = [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 10),
             ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if highlight_first:
        style += [("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"), ("FONTSIZE", (1, 0), (1, 0), 13)]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(rec, model_info):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            title=f"MOTOSIRA Diagnosis Report #{rec['id']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#777777"))
    warn = ParagraphStyle("w", parent=ss["Normal"], fontSize=10, textColor=colors.HexColor("#B00020"),
                          borderColor=colors.HexColor("#B00020"), borderWidth=0.8, borderPadding=6,
                          spaceBefore=6, spaceAfter=6)
    el = [Paragraph("MOTOSIRA — Diagnosis Report", h1),
          Paragraph("Motorcycle Sound-based Identification &amp; Reporting Assistant", small),
          Spacer(1, 8)]
    if rec["mode"] == "mock":
        el.append(Paragraph("DEMO MODE — SIMULATED DATA. This report demonstrates the system pipeline "
                            "and is NOT a diagnosis of a real motorcycle.", warn))
    label = rec.get("classification")
    el.append(_table([["Report ID", f"#{rec['id']}"], ["Date / time", rec["time"]],
                      ["Motorcycle model", rec.get("bike") or "—"],
                      ["Mode", config.MODE_LABELS.get(rec["mode"], rec["mode"])],
                      ["Audio source", "INMP441 microphone (Raspberry Pi 4)" if rec["source"] == "inmp441"
                       else "Simulated device"], ["Device", rec.get("device") or "—"]]))
    el.append(Paragraph("Diagnosis result", h2))
    if label:
        sev = rec.get("severity")
        res = _table([["Detected condition", config.CLASS_LABELS.get(label, label)],
                      ["Confidence", f"{(rec.get('confidence') or 0) * 100:.1f} %"],
                      ["Severity level", f"{sev} / 3 — {config.SEVERITY[label]['text']}"]], highlight_first=True)
        res.setStyle(TableStyle([("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor(SEV_COLOR.get(sev, "#000000")))]))
        el.append(res)
        if (rec.get("confidence") or 0) < config.CONFIDENCE_WARN:
            el.append(Paragraph("Low confidence: re-record before relying on this result.", small))
        probs = rec.get("probabilities") or {}
        if probs:
            el.append(Spacer(1, 4))
            el.append(Paragraph("Class probabilities: " + ", ".join(
                f"{config.CLASS_LABELS.get(k, k)} {v * 100:.0f}%" for k, v in
                sorted(probs.items(), key=lambda kv: -kv[1])), small))
    else:
        el.append(Paragraph("Not classified — no trained model for this mode at the time of capture.", ss["Normal"]))
    el.append(Paragraph("Capture diagnostics", h2))
    e2e = rec.get("e2e_ms")
    el.append(_table([
        ["Input / signal quality", f"{rec.get('signal_quality')}" +
         (f" ({rec['quality_reason']})" if rec.get("quality_reason") else "")],
        ["Signal-to-noise ratio", f"{rec.get('snr_db')} dB"], ["Peak level", f"{rec.get('peak_dbfs')} dBFS"],
        ["Engine RPM", f"{rec['rpm']} RPM" if rec.get("rpm") else "Sensor not connected"],
        ["Feature extraction (device)", f"{rec.get('feature_ms')} ms"],
        ["Classification (PC)", f"{rec.get('pc_ms')} ms"],
        ["End-to-end latency", f"{e2e} ms (target ≤ {config.LATENCY_TARGET_MS} ms)" if e2e else "—"]]))
    el.append(Paragraph("Model", h2))
    el.append(_table([["Trained", model_info.get("trained_at") or "—"],
                      ["Training data", f"{model_info.get('samples') or '—'} clips from "
                                        f"{model_info.get('recordings') or '—'} recordings" +
                       (" (SIMULATED)" if rec["mode"] == "mock" else "")],
                      ["Held-out test accuracy", f"{model_info['test_accuracy'] * 100:.1f} %"
                       if model_info.get("test_accuracy") is not None else "—"]]))
    el.append(Spacer(1, 14))
    el.append(Paragraph("MOTOSIRA identifies engine conditions from sound only; it does not connect to the "
                        "motorcycle's electrical or ignition system. Confirm findings with a licensed mechanic.",
                        small))
    doc.build(el)
    return buf.getvalue()
