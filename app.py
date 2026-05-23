# ================= =================
# 📦 IMPORTS
# ================= =================
import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import tempfile
import io
from datetime import datetime, timedelta

import folium
from streamlit_folium import st_folium

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


# ================= =================
# 🔐 CARBON MAPPER API CONFIG
# ================= =================
BASE_URL = "https://api.carbonmapper.org/api/v1/"

EMAIL = "fatimasaci92@gmail.com"
PASSWORD = "7htdwqsZGE2!Uvh"


# ================= =================
# 🔑 AUTH FUNCTIONS
# ================= =================
def get_access_token():
    r = requests.post(
        BASE_URL + "token/pair",
        json={"email": EMAIL, "password": PASSWORD}
    )
    r.raise_for_status()
    return r.json()["access"]


def get_stac_token(access_token):
    expiration_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    r = requests.post(
        BASE_URL + "account/tokens/create-stac",
        json={"name": "streamlit-app", "expiration_date": expiration_date},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    r.raise_for_status()
    return r.json()["token_value"]


# ================= =================
# 📡 FETCH PLUME DATA
# ================= =================
def fetch_plumes(datetime_range, bbox, limit, gas, stac_token):
    url = BASE_URL + "catalog/plume-csv"
    headers = {"Authorization": f"Bearer {stac_token}"}
    params = {
        "datetime": datetime_range,
        "limit": limit,
        "plume_gas": gas,
        "bbox": bbox
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.text


# ================= =================
# ⚙️ STREAMLIT CONFIG
# ================= =================
st.set_page_config(page_title="CH₄ Monitoring", layout="wide")
st.title("🛰️ Carbon Mapper CH₄ Monitoring Dashboard")


# ================= =================
# 🎛️ USER INPUTS
# ================= =================
st.sidebar.header("Filters")

cm_lat_min = st.sidebar.number_input("Lat min", value=32.45)
cm_lat_max = st.sidebar.number_input("Lat max", value=33.28)
cm_lon_min = st.sidebar.number_input("Lon min", value=2.88)
cm_lon_max = st.sidebar.number_input("Lon max", value=3.81)

cm_date_start = st.sidebar.date_input("Start date", value=datetime(2022, 1, 1))
cm_date_end   = st.sidebar.date_input("End date",   value=datetime.utcnow())

cm_gas = st.sidebar.selectbox("Gas", ["CH4", "CO2"])
limit  = st.sidebar.slider("Limit", 50, 1000, 200)


# ================= =================
# 📥 LOAD DATA BUTTON
# ================= =================
if st.button("📥 Load Carbon Mapper Data"):
    try:
        access_token = get_access_token()
        stac_token   = get_stac_token(access_token)
        bbox = [cm_lon_min, cm_lat_min, cm_lon_max, cm_lat_max]
        csv_text = fetch_plumes(
            datetime_range=f"{cm_date_start}/{cm_date_end}",
            bbox=bbox,
            limit=limit,
            gas=cm_gas,
            stac_token=stac_token
        )
        df = pd.read_csv(io.StringIO(csv_text))
        st.session_state["plume_df"] = df
        st.success("Data loaded successfully ✅")
    except Exception as e:
        st.error(f"Error: {e}")


# ================= =================
# 📊 SHOW TABLE
# ================= =================
if "plume_df" in st.session_state:
    st.markdown("## 📊 Plume Data Table")
    st.dataframe(st.session_state["plume_df"])


# ================= =================
# 🔴 MATRICE DE CRITICITÉ
# FIX 1 : intens_class corrigée (seuils Naus et al. 2023)
# FIX 2 : noms de colonnes cohérents partout
# FIX 3 : color_by_col mis à jour
# FIX 4 : score de risque mis à jour
# ================= =================
st.markdown("## 🔴 Matrice de Criticité des Émissions")
st.caption("Seuils basés sur Naus et al. (2023) — *Environ. Sci. Technol.* — Algérie O&G")

if "plume_df" in st.session_state:
    df = st.session_state["plume_df"]

    df_alg = df[
        (df["plume_latitude"]  >= 18.5) & (df["plume_latitude"]  <= 37.5) &
        (df["plume_longitude"] >= -9.5) & (df["plume_longitude"] <= 12.0)
    ].copy()

    if "emission_auto" in df_alg.columns:
        df_alg["emission_auto"] = pd.to_numeric(df_alg["emission_auto"], errors="coerce")

        # ── FIX 1 : seuils scientifiques Naus et al. 2023 ────────
        def intens_class(val):
            if val > 1000:  return "Super-emitter (>1000)"   # Sentinel-2 detection limit, Algeria
            elif val > 100: return "Detectable (100–1000)"   # GHGSat detection limit ~100 kg/h
            else:           return "Diffuse (<100)"           # Below individual detection

        df_alg["Intensité"] = df_alg["emission_auto"].apply(intens_class)

        if "ipcc_sector" in df_alg.columns:
            pivot = df_alg.groupby(["ipcc_sector", "Intensité"]).size().unstack(fill_value=0)
        else:
            df_alg["ipcc_sector"] = "Non classifié"
            pivot = df_alg.groupby(["ipcc_sector", "Intensité"]).size().unstack(fill_value=0)

        # ── FIX 2 : noms de colonnes cohérents avec intens_class ─
        for col in ["Diffuse (<100)", "Detectable (100–1000)", "Super-emitter (>1000)"]:
            if col not in pivot.columns:
                pivot[col] = 0

        pivot = pivot[["Diffuse (<100)", "Detectable (100–1000)", "Super-emitter (>1000)"]]
        pivot["Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Total", ascending=False)

        # ── FIX 3 : color_by_col avec nouveaux noms ───────────────
        def color_by_col(s):
            styles = []
            for v in s:
                if s.name == "Super-emitter (>1000)":
                    styles.append("background-color: #fde8e8; color: #c0392b; font-weight: bold" if v > 0 else "color:#aaa")
                elif s.name == "Detectable (100–1000)":
                    styles.append("background-color: #fef3e2; color: #e67e22; font-weight: bold" if v > 0 else "color:#aaa")
                elif s.name == "Diffuse (<100)":
                    styles.append("background-color: #eafaf1; color: #27ae60" if v > 0 else "color:#aaa")
                else:
                    styles.append("font-weight: bold")
            return styles

        st.dataframe(pivot.style.apply(color_by_col), use_container_width=True)

        # ── FIX 4 : score de risque avec nouveaux noms ────────────
        st.markdown("### 📊 Score de Risque par Secteur")
        pivot["Score Risque"] = (
            pivot["Diffuse (<100)"]          * 1 +
            pivot["Detectable (100–1000)"]   * 3 +
            pivot["Super-emitter (>1000)"]   * 9
        )
        pivot_sorted = pivot[["Score Risque"]].sort_values("Score Risque", ascending=False)
        st.bar_chart(pivot_sorted)


# ================= =================
# 🗺️ MAP — ALGERIA FULL CSV PLOTTING
# FIX 5 : seuils carte alignés avec Naus et al. 2023
# ================= =================
st.markdown("## 🗺️ Algeria CH₄ Plume Map")

basemap = st.radio("Map style", ["🛣️ Street", "🌍 Satellite"], horizontal=True)

if basemap == "🌍 Satellite":
    m = folium.Map(location=[28.0, 2.5], zoom_start=5, tiles=None)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="ESRI Satellite"
    ).add_to(m)
else:
    m = folium.Map(location=[28.0, 2.5], zoom_start=5, tiles="OpenStreetMap")

ALGERIA_LAT_MIN, ALGERIA_LAT_MAX =  18.5, 37.5
ALGERIA_LON_MIN, ALGERIA_LON_MAX = -9.5,  12.0

if "plume_df" in st.session_state:
    df = st.session_state["plume_df"]
    df = df[
        (df["plume_latitude"]  >= ALGERIA_LAT_MIN) & (df["plume_latitude"]  <= ALGERIA_LAT_MAX) &
        (df["plume_longitude"] >= ALGERIA_LON_MIN) & (df["plume_longitude"] <= ALGERIA_LON_MAX)
    ]

    for _, row in df.iterrows():
        try:
            lat      = float(row["plume_latitude"])
            lon      = float(row["plume_longitude"])
            emission = float(row.get("emission_auto", 0))

            # ── FIX 5 : seuils alignés sur Naus et al. 2023 ──────
            if emission > 1000:       # Super-emitter
                color  = "red"
                radius = 12
            elif emission > 100:      # Detectable (GHGSat limit)
                color  = "orange"
                radius = 8
            else:                     # Diffuse
                color  = "green"
                radius = 5

            folium.CircleMarker(
                location=[lat, lon],
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=f"""
                <b>ID:</b> {row.get('plume_id','N/A')}<br>
                <b>Emission:</b> {emission} kg/h<br>
                <b>Gas:</b> {row.get('gas','N/A')}<br>
                <b>Sector:</b> {row.get('ipcc_sector','N/A')}<br>
                <b>Instrument:</b> {row.get('instrument','N/A')}<br>
                <b>Date:</b> {row.get('datetime','N/A')}
                """
            ).add_to(m)
        except:
            continue

st_folium(m, width=1200, height=650)


# ================= =================
# 📄 PDF REPORT — Style GHGSat
# FIX 6 : matrice PDF avec seuils Naus et al. 2023
# FIX 7 : légende PDF corrigée (liste de listes)
# FIX 8 : summary table alignée sur nouveaux seuils
# ================= =================
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.markdown("## 📄 Rapport Professionnel")

if st.button("Générer Rapport PDF"):

    buffer = io.BytesIO()

    DARK_NAVY   = colors.HexColor("#0D1B3E")
    ACCENT_BLUE = colors.HexColor("#1A6FAF")
    LIGHT_GRAY  = colors.HexColor("#F4F6F9")
    MID_GRAY    = colors.HexColor("#9DA8B7")
    WHITE       = colors.white
    RED_HIGH    = colors.HexColor("#C0392B")
    ORANGE_MED  = colors.HexColor("#E67E22")
    GREEN_LOW   = colors.HexColor("#27AE60")

    PAGE_W, PAGE_H = A4

    def draw_header(c, doc):
        c.saveState()
        c.setFillColor(DARK_NAVY)
        c.rect(0, PAGE_H - 28*mm, PAGE_W, 28*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(15*mm, PAGE_H - 16*mm, "DATA.SAT")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#7FB3D3"))
        c.drawRightString(PAGE_W - 15*mm, PAGE_H - 16*mm, "CH4 Measurement Report")
        c.setFillColor(ACCENT_BLUE)
        c.rect(0, PAGE_H - 30*mm, PAGE_W, 2*mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 8)
        meta_y = PAGE_H - 36*mm
        if "plume_df" in st.session_state:
            df_tmp = st.session_state["plume_df"]
            meta = (
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}    "
                f"Records: {len(df_tmp)}    Gas: CH4    Source: Carbon Mapper API"
            )
        else:
            meta = f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}    Gas: CH4"
        c.drawString(15*mm, meta_y, meta)
        c.restoreState()

    def draw_footer(c, doc):
        c.saveState()
        c.setFillColor(LIGHT_GRAY)
        c.rect(0, 0, PAGE_W, 18*mm, fill=1, stroke=0)
        c.setStrokeColor(MID_GRAY)
        c.setLineWidth(0.5)
        c.line(15*mm, 18*mm, PAGE_W - 15*mm, 18*mm)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawString(15*mm, 10*mm,
            "This document contains proprietary information. Data sourced from Carbon Mapper.")
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(DARK_NAVY)
        c.drawRightString(PAGE_W - 15*mm, 10*mm, f"Page {doc.page}")
        c.restoreState()

    def on_page(c, doc):
        draw_header(c, doc)
        draw_footer(c, doc)

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=42*mm,  bottomMargin=22*mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("ReportTitle", fontName="Helvetica-Bold", fontSize=16,
                                  textColor=DARK_NAVY, spaceAfter=4)
    section_style = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=11,
                                    textColor=ACCENT_BLUE, spaceBefore=10, spaceAfter=4)
    normal_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=9,
                                   textColor=colors.HexColor("#333333"), leading=13)
    label_style  = ParagraphStyle("Label", fontName="Helvetica-Bold", fontSize=8,
                                   textColor=MID_GRAY)
    caption_style = ParagraphStyle("Caption", fontName="Helvetica-Oblique", fontSize=7,
                                    textColor=MID_GRAY, spaceAfter=4)

    story = []

    # ── Titre ────────────────────────────────────────────────────
    story.append(Paragraph("CH<sub>4</sub> Emission Monitoring Report", title_style))
    story.append(Paragraph("Algeria — Oil &amp; Gas Sector", normal_style))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE))
    story.append(Spacer(1, 4*mm))

    # ── Métadonnées ───────────────────────────────────────────────
    story.append(Paragraph("Report Metadata", section_style))
    meta_data = [
        ["Report Date",    datetime.utcnow().strftime("%Y-%m-%d")],
        ["Gas Species",    "CH4 (Methane)"],
        ["Data Source",    "Carbon Mapper API v1"],
        ["Region",         "Algeria (18.5°N–37.5°N / 9.5°W–12°E)"],
        ["Sector",         "Oil & Gas"],
        ["Classification", "Proprietary / Confidential"],
        ["Threshold Ref.", "Naus et al. (2023), Environ. Sci. Technol., 57, 19545-19556"],
    ]
    meta_table = Table(
        [[Paragraph(k, label_style), Paragraph(v, normal_style)] for k, v in meta_data],
        colWidths=[55*mm, 110*mm],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (0, -1), LIGHT_GRAY),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6*mm))

    if "plume_df" in st.session_state:
        df = st.session_state["plume_df"]
        df_alg = df[
            (df["plume_latitude"]  >= 18.5) & (df["plume_latitude"]  <= 37.5) &
            (df["plume_longitude"] >= -9.5) & (df["plume_longitude"] <= 12.0)
        ].copy()

        # ── Emission Summary ──────────────────────────────────────
        story.append(Paragraph("Emission Summary", section_style))

        total = len(df_alg)
        if "emission_auto" in df_alg.columns:
            df_alg["emission_auto"] = pd.to_numeric(df_alg["emission_auto"], errors="coerce")
            em_mean = df_alg["emission_auto"].mean()
            em_max  = df_alg["emission_auto"].max()
            em_tot  = df_alg["emission_auto"].sum()
            # ── FIX 8 : seuils alignés sur Naus et al. 2023 ──────
            superem  = int((df_alg["emission_auto"] > 1000).sum())
            detect   = int(((df_alg["emission_auto"] > 100) & (df_alg["emission_auto"] <= 1000)).sum())
            diffuse  = int((df_alg["emission_auto"] <= 100).sum())
        else:
            em_mean = em_max = em_tot = superem = detect = diffuse = "N/A"

        summary_data = [
            ["Metric", "Value"],
            ["Total Plumes Detected",                    str(total)],
            ["Mean Emission Rate",                       f"{em_mean:.1f} kg/h" if isinstance(em_mean, float) else "N/A"],
            ["Max Emission Rate",                        f"{em_max:.1f} kg/h"  if isinstance(em_max,  float) else "N/A"],
            ["Total Emission (sum)",                     f"{em_tot:.0f} kg/h"  if isinstance(em_tot,  float) else "N/A"],
            ["Super-emitters  (> 1 000 kg/h)",           str(superem)],
            ["Detectable sources (100–1 000 kg/h)",      str(detect)],
            ["Diffuse sources  (< 100 kg/h)",            str(diffuse)],
        ]

        summary_table = Table(summary_data, colWidths=[100*mm, 65*mm])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), DARK_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
            ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
            ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 6*mm))

        # ── Top 20 émetteurs ─────────────────────────────────────
        story.append(Paragraph("Top Emission Events", section_style))

        cols_show = [c for c in [
            "plume_id", "datetime", "plume_latitude", "plume_longitude",
            "emission_auto", "ipcc_sector", "instrument"
        ] if c in df_alg.columns]

        top_df = (df_alg.nlargest(20, "emission_auto") if "emission_auto" in df_alg.columns
                  else df_alg.head(20))[cols_show].fillna("—")

        header_row = [Paragraph(c.replace("_", " ").title(), label_style) for c in cols_show]
        data_rows  = [header_row]

        for _, row in top_df.iterrows():
            r = []
            for c in cols_show:
                val = str(row[c])
                if c == "emission_auto":
                    try:
                        v = float(val)
                        # FIX : couleurs alignées sur nouveaux seuils
                        color_tag = ("red" if v > 1000 else "orange" if v > 100 else "green")
                        val = f'<font color="{color_tag}"><b>{v:.1f}</b></font>'
                    except:
                        pass
                r.append(Paragraph(val, normal_style))
            data_rows.append(r)

        col_widths_top = [(PAGE_W - 30*mm) / len(cols_show)] * len(cols_show)
        top_table = Table(data_rows, colWidths=col_widths_top, repeatRows=1)
        top_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), ACCENT_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 7),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
            ("FONTSIZE",      (0, 1), (-1, -1), 7),
            ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 6*mm))

        # ── Matrice de criticité ──────────────────────────────────
        story.append(Paragraph("Criticality Matrix — Sector × Emission Level", section_style))
        story.append(Paragraph(
            "Source: Naus et al. (2023), Environ. Sci. Technol. 57, 19545–19556. "
            "Superemitter threshold = 1 t/h (Sentinel-2 detection limit, Algeria).",
            caption_style
        ))
        story.append(Spacer(1, 2*mm))

        # ── FIX 6 : seuils PDF alignés sur Naus et al. 2023 ──────
        df_alg["level"] = df_alg["emission_auto"].apply(
            lambda v: "Super-emitter" if v > 1000 else ("Detectable" if v > 100 else "Diffuse")
        )

        sector_col = "ipcc_sector" if "ipcc_sector" in df_alg.columns else None
        if sector_col:
            pivot_pdf = df_alg.groupby([sector_col, "level"]).size().unstack(fill_value=0)
        else:
            df_alg["Sector"] = "Unclassified"
            pivot_pdf = df_alg.groupby(["Sector", "level"]).size().unstack(fill_value=0)

        for col in ["Diffuse", "Detectable", "Super-emitter"]:
            if col not in pivot_pdf.columns:
                pivot_pdf[col] = 0

        pivot_pdf = pivot_pdf[["Diffuse", "Detectable", "Super-emitter"]]
        pivot_pdf["Risk Score"] = (
            pivot_pdf["Diffuse"]        * 1 +
            pivot_pdf["Detectable"]     * 3 +
            pivot_pdf["Super-emitter"]  * 9
        )
        pivot_pdf = pivot_pdf.sort_values("Risk Score", ascending=False)

        matrix_header = [
            Paragraph("Sector",                label_style),
            Paragraph("Diffuse (<100)",         label_style),
            Paragraph("Detectable (100–1000)",  label_style),
            Paragraph("Super-emitter (>1000)",  label_style),
            Paragraph("Risk Score",             label_style),
        ]
        matrix_data = [matrix_header]

        for sector, row in pivot_pdf.iterrows():
            risk = int(row["Risk Score"])
            risk_hex = "#C0392B" if risk > 50 else ("#E67E22" if risk > 15 else "#27AE60")

            matrix_data.append([
                Paragraph(str(sector)[:35], normal_style),
                Paragraph(str(int(row["Diffuse"])),    normal_style),
                Paragraph(str(int(row["Detectable"])), normal_style),
                Paragraph(
                    f'<font color="#C0392B"><b>{int(row["Super-emitter"])}</b></font>'
                    if row["Super-emitter"] > 0 else "0",
                    normal_style
                ),
                Paragraph(f'<font color="{risk_hex}"><b>{risk}</b></font>', normal_style),
            ])

        col_w_matrix = [68*mm, 25*mm, 30*mm, 30*mm, 20*mm]
        matrix_table = Table(matrix_data, colWidths=col_w_matrix, repeatRows=1)
        matrix_table.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), DARK_NAVY),
            ("TEXTCOLOR",      (0, 0), (-1, 0), WHITE),
            ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, 0), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
            ("GRID",           (0, 0), (-1, -1), 0.3, MID_GRAY),
            ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
            ("FONTSIZE",       (0, 1), (-1, -1), 8),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ]))
        story.append(matrix_table)
        story.append(Spacer(1, 4*mm))

        # ── FIX 7 : légende PDF — liste de listes (structure correcte) ──
        legend_data = [
            [
                Paragraph('<font color="#27AE60"><b>● Diffuse</b></font>', normal_style),
                Paragraph("&lt; 100 kg/h — Below individual detection limit (Sentinel-2)", normal_style),
            ],
            [
                Paragraph('<font color="#E67E22"><b>● Detectable</b></font>', normal_style),
                Paragraph("100–1 000 kg/h — GHGSat detection limit (~100 kg/h)", normal_style),
            ],
            [
                Paragraph('<font color="#C0392B"><b>● Super-emitter</b></font>', normal_style),
                Paragraph("&gt; 1 000 kg/h — Superemitter threshold (Naus et al., 2023, Algeria)", normal_style),
            ],
        ]
        legend_table = Table(legend_data, colWidths=[38*mm, 125*mm])
        legend_table.setStyle(TableStyle([
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ]))
        story.append(legend_table)

    else:
        story.append(Paragraph(
            "No data loaded. Please fetch Carbon Mapper data before generating the report.",
            normal_style
        ))

    # ── Build ─────────────────────────────────────────────────────
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)

    st.download_button(
        label="⬇️ Télécharger le Rapport PDF",
        data=buffer,
        file_name=f"CH4_Report_Algeria_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
