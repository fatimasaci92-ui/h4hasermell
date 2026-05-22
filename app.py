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

# ⚠️ better: move to st.secrets later
EMAIL = "fatimasaci92@gmail.com"
PASSWORD = "7htdwqsZGE2!Uvh"


# ================= =================
# 🔑 AUTH FUNCTIONS
# ================= =================
def get_access_token():
    """Login and get access token"""
    r = requests.post(
        BASE_URL + "token/pair",
        json={"email": EMAIL, "password": PASSWORD}
    )
    r.raise_for_status()
    return r.json()["access"]


def get_stac_token(access_token):
    """Create STAC token for data access"""
    expiration_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    r = requests.post(
        BASE_URL + "account/tokens/create-stac",
        json={
            "name": "streamlit-app",
            "expiration_date": expiration_date
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    r.raise_for_status()
    return r.json()["token_value"]


# ================= =================
# 📡 FETCH PLUME DATA
# ================= =================
def fetch_plumes(datetime_range, bbox, limit, gas, stac_token):
    """Download plume CSV from Carbon Mapper"""
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
cm_date_end = st.sidebar.date_input("End date", value=datetime.utcnow())

cm_gas = st.sidebar.selectbox("Gas", ["CH4", "CO2"])
limit = st.sidebar.slider("Limit", 50, 1000, 200)


# ================= =================
# 📥 LOAD DATA BUTTON
# ================= =================
if st.button("📥 Load Carbon Mapper Data"):

    try:
        # 1. Auth
        access_token = get_access_token()
        stac_token = get_stac_token(access_token)

        # 2. bbox format: [min_lon, min_lat, max_lon, max_lat]
        bbox = [cm_lon_min, cm_lat_min, cm_lon_max, cm_lat_max]

        # 3. Fetch CSV
        csv_text = fetch_plumes(
            datetime_range=f"{cm_date_start}/{cm_date_end}",
            bbox=bbox,
            limit=limit,
            gas=cm_gas,
            stac_token=stac_token
        )

        # 4. Convert to DataFrame
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
# ================= =================
st.markdown("## 🔴 Matrice de Criticité des Émissions")

if "plume_df" in st.session_state:
    df = st.session_state["plume_df"]

    df_alg = df[
        (df["plume_latitude"] >= 18.5) & (df["plume_latitude"] <= 37.5) &
        (df["plume_longitude"] >= -9.5) & (df["plume_longitude"] <= 12.0)
    ].copy()

    if "emission_auto" in df_alg.columns:
        df_alg["emission_auto"] = pd.to_numeric(df_alg["emission_auto"], errors="coerce")

        # ── Définir les classes de fréquence et d'intensité ──────
        def freq_class(n):
            if n >= 10: return "Fréquent (≥10)"
            elif n >= 5: return "Modéré (5–9)"
            else:        return "Rare (<5)"

        def intens_class(val):
            if val > 1000: return "Critique (>1000)"
            elif val > 300: return "Élevé (300–1000)"
            else:           return "Faible (<300)"

        df_alg["Intensité"] = df_alg["emission_auto"].apply(intens_class)

        # Compter les occurrences par secteur × intensité
        if "ipcc_sector" in df_alg.columns:
            pivot = df_alg.groupby(["ipcc_sector", "Intensité"]).size().unstack(fill_value=0)
        else:
            df_alg["ipcc_sector"] = "Non classifié"
            pivot = df_alg.groupby(["ipcc_sector", "Intensité"]).size().unstack(fill_value=0)

        # S'assurer que toutes les colonnes existent
        for col in ["Faible (<300)", "Élevé (300–1000)", "Critique (>1000)"]:
            if col not in pivot.columns:
                pivot[col] = 0

        pivot = pivot[["Faible (<300)", "Élevé (300–1000)", "Critique (>1000)"]]
        pivot["Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Total", ascending=False)

        # ── Mise en forme colorée ─────────────────────────────────
        def color_cell(val):
            if val == 0:   return "background-color: #f0f0f0; color: #aaa"
            col_name = ""
            return ""

        def color_by_col(s):
            styles = []
            for v in s:
                if s.name == "Critique (>1000)":
                    styles.append("background-color: #fde8e8; color: #c0392b; font-weight: bold" if v > 0 else "color:#aaa")
                elif s.name == "Élevé (300–1000)":
                    styles.append("background-color: #fef3e2; color: #e67e22; font-weight: bold" if v > 0 else "color:#aaa")
                elif s.name == "Faible (<300)":
                    styles.append("background-color: #eafaf1; color: #27ae60" if v > 0 else "color:#aaa")
                else:
                    styles.append("font-weight: bold")
            return styles

        st.dataframe(
            pivot.style.apply(color_by_col),
            use_container_width=True
        )

        # ── Score de risque global par secteur ───────────────────
        st.markdown("### 📊 Score de Risque par Secteur")
        pivot["Score Risque"] = (
            pivot["Faible (<300)"] * 1 +
            pivot["Élevé (300–1000)"] * 3 +
            pivot["Critique (>1000)"] * 9
        )
        pivot_sorted = pivot[["Score Risque"]].sort_values("Score Risque", ascending=False)
        st.bar_chart(pivot_sorted)
# ================= =================
# 🗺️ MAP — ALGERIA FULL CSV PLOTTING
# ================= =================
st.markdown("## 🗺️ Algeria CH₄ Plume Map")

import folium
from streamlit_folium import st_folium

# 🎛️ basemap switch
basemap = st.radio(
    "Map style",
    ["🛣️ Street", "🌍 Satellite"],
    horizontal=True
)

# ================= CREATE MAP =================
if basemap == "🌍 Satellite":
    m = folium.Map(location=[28.0, 2.5], zoom_start=5, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="ESRI Satellite"
    ).add_to(m)

else:
    m = folium.Map(location=[28.0, 2.5], zoom_start=5, tiles="OpenStreetMap")


# ================= ALGERIA FILTER =================
ALGERIA_LAT_MIN = 18.5
ALGERIA_LAT_MAX = 37.5
ALGERIA_LON_MIN = -9.5
ALGERIA_LON_MAX = 12.0


if "plume_df" in st.session_state:
    df = st.session_state["plume_df"]

    # filter ALL Algeria points
    df = df[
        (df["plume_latitude"] >= ALGERIA_LAT_MIN) &
        (df["plume_latitude"] <= ALGERIA_LAT_MAX) &
        (df["plume_longitude"] >= ALGERIA_LON_MIN) &
        (df["plume_longitude"] <= ALGERIA_LON_MAX)
    ]

    # ================= PLOT =================
    for _, row in df.iterrows():
        try:
            lat = float(row["plume_latitude"])
            lon = float(row["plume_longitude"])
            emission = float(row.get("emission_auto", 0))

            # color scale
            if emission > 1000:
                color = "red"
                radius = 12
            elif emission > 300:
                color = "orange"
                radius = 8
            else:
                color = "green"
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


# ================= RENDER =================
st_folium(m, width=1200, height=650)
# ================= =================
# 📄 PDF REPORT — Style GHGSat
# ================= =================
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate


st.markdown("## 📄 Rapport Professionnel")

if st.button("Générer Rapport PDF"):

    buffer = io.BytesIO()

    # ── Couleurs GHGSat ──────────────────────────────────────────
    DARK_NAVY   = colors.HexColor("#0D1B3E")
    ACCENT_BLUE = colors.HexColor("#1A6FAF")
    LIGHT_GRAY  = colors.HexColor("#F4F6F9")
    MID_GRAY    = colors.HexColor("#9DA8B7")
    WHITE       = colors.white
    RED_HIGH    = colors.HexColor("#C0392B")
    ORANGE_MED  = colors.HexColor("#E67E22")
    GREEN_LOW   = colors.HexColor("#27AE60")

    PAGE_W, PAGE_H = A4

    # ── Canvas callbacks (header / footer) ───────────────────────
    def draw_header(c, doc):
        c.saveState()
        # Bande supérieure bleue marine
        c.setFillColor(DARK_NAVY)
        c.rect(0, PAGE_H - 28*mm, PAGE_W, 28*mm, fill=1, stroke=0)

        # Titre gauche
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(15*mm, PAGE_H - 16*mm, "DATA.SAT")

        # Sous-titre droit
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#7FB3D3"))
        c.drawRightString(PAGE_W - 15*mm, PAGE_H - 16*mm, "CH4 Measurement Report")

        # Bande accentuée verte-bleue fine
        c.setFillColor(ACCENT_BLUE)
        c.rect(0, PAGE_H - 30*mm, PAGE_W, 2*mm, fill=1, stroke=0)

        # Méta-données sous la bande (date, région, gaz)
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 8)
        meta_y = PAGE_H - 36*mm
        if "plume_df" in st.session_state:
            df_tmp = st.session_state["plume_df"]
            meta = (
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}    "
                f"Records: {len(df_tmp)}    "
                f"Gas: CH4    "
                f"Source: Carbon Mapper API"
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
        disclaimer = (
            "This document contains proprietary information. Any disclosure, use or duplication "
            "without written authorization is expressly prohibited. Data sourced from Carbon Mapper."
        )
        c.drawString(15*mm, 10*mm, disclaimer)

        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(DARK_NAVY)
        c.drawRightString(PAGE_W - 15*mm, 10*mm, f"Page {doc.page}")
        c.restoreState()

    def on_page(c, doc):
        draw_header(c, doc)
        draw_footer(c, doc)

    # ── Document ─────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=42*mm,
        bottomMargin=22*mm,
    )

    styles = getSampleStyleSheet()

    # Styles personnalisés
    title_style = ParagraphStyle(
        "ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=DARK_NAVY,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "Section",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=ACCENT_BLUE,
        spaceBefore=10,
        spaceAfter=4,
        borderPad=2,
    )
    normal_style = ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13,
    )
    label_style = ParagraphStyle(
        "Label",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=MID_GRAY,
    )

    story = []

    # ── Titre principal ───────────────────────────────────────────
    story.append(Paragraph("CH<sub>4</sub> Emission Monitoring Report", title_style))
    story.append(Paragraph("Algeria — Oil &amp; Gas Sector", normal_style))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_BLUE))
    story.append(Spacer(1, 4*mm))

    # ── Bloc métadonnées (tableau 2 colonnes) ─────────────────────
    story.append(Paragraph("Report Metadata", section_style))

    meta_data = [
        ["Report Date",    datetime.utcnow().strftime("%Y-%m-%d")],
        ["Gas Species",    "CH4 (Methane)"],
        ["Data Source",    "Carbon Mapper API v1"],
        ["Region",         "Algeria (18.5°N–37.5°N / 9.5°W–12°E)"],
        ["Sector",         "Oil & Gas"],
        ["Classification", "Proprietary / Confidential"],
    ]
    meta_table = Table(
        [[Paragraph(k, label_style), Paragraph(v, normal_style)] for k, v in meta_data],
        colWidths=[50*mm, 115*mm],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",       (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6*mm))

    # ── Statistiques sommaires ────────────────────────────────────
    if "plume_df" in st.session_state:
        df = st.session_state["plume_df"]

        # Filtrer Algérie
        df_alg = df[
            (df["plume_latitude"] >= 18.5) & (df["plume_latitude"] <= 37.5) &
            (df["plume_longitude"] >= -9.5) & (df["plume_longitude"] <= 12.0)
        ].copy()

        story.append(Paragraph("Emission Summary", section_style))

        total     = len(df_alg)
        if "emission_auto" in df_alg.columns:
            df_alg["emission_auto"] = pd.to_numeric(df_alg["emission_auto"], errors="coerce")
            em_mean = df_alg["emission_auto"].mean()
            em_max  = df_alg["emission_auto"].max()
            em_tot  = df_alg["emission_auto"].sum()
            high    = int((df_alg["emission_auto"] > 1000).sum())
            med     = int(((df_alg["emission_auto"] > 300) & (df_alg["emission_auto"] <= 1000)).sum())
            low     = int((df_alg["emission_auto"] <= 300).sum())
        else:
            em_mean = em_max = em_tot = high = med = low = "N/A"

        summary_data = [
            ["Metric", "Value"],
            ["Total Plumes Detected",           str(total)],
            ["Mean Emission Rate",               f"{em_mean:.1f} kg/h" if isinstance(em_mean, float) else "N/A"],
            ["Max Emission Rate",                f"{em_max:.1f} kg/h"  if isinstance(em_max,  float) else "N/A"],
            ["Total Emission (sum)",             f"{em_tot:.0f} kg/h"  if isinstance(em_tot,  float) else "N/A"],
            ["High Emitters  (> 1 000 kg/h)",   str(high)],
            ["Medium Emitters (300–1 000 kg/h)", str(med)],
            ["Low Emitters   (< 300 kg/h)",      str(low)],
        ]

        col_w = [95*mm, 70*mm]
        summary_table = Table(summary_data, colWidths=col_w)
        summary_table.setStyle(TableStyle([
            # En-tête
            ("BACKGROUND",    (0, 0), (-1, 0), DARK_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            # Corps
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

        if "emission_auto" in df_alg.columns:
            top_df = df_alg.nlargest(20, "emission_auto")[cols_show].fillna("—")
        else:
            top_df = df_alg.head(20)[cols_show].fillna("—")

        header_row = [Paragraph(c.replace("_", " ").title(), label_style) for c in cols_show]
        data_rows  = [header_row]

        for _, row in top_df.iterrows():
            r = []
            for c in cols_show:
                val = str(row[c])
                if c == "emission_auto":
                    try:
                        v = float(val)
                        color_tag = (
                            "red"    if v > 1000 else
                            "orange" if v > 300  else
                            "green"
                        )
                        val = f'<font color="{color_tag}"><b>{v:.1f}</b></font>'
                    except:
                        pass
                r.append(Paragraph(val, normal_style))
            data_rows.append(r)

        col_widths = [(PAGE_W - 30*mm) / len(cols_show)] * len(cols_show)
        top_table = Table(data_rows, colWidths=col_widths, repeatRows=1)
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
        story.append(Spacer(1, 2*mm))

        df_alg["level"] = df_alg["emission_auto"].apply(
            lambda v: "Critical" if v > 1000 else ("High" if v > 300 else "Low")
        )

        sector_col = "ipcc_sector" if "ipcc_sector" in df_alg.columns else None
        if sector_col:
            pivot_pdf = df_alg.groupby([sector_col, "level"]).size().unstack(fill_value=0)
        else:
            df_alg["Sector"] = "Unclassified"
            pivot_pdf = df_alg.groupby(["Sector", "level"]).size().unstack(fill_value=0)

        for col in ["Low", "High", "Critical"]:
            if col not in pivot_pdf.columns:
                pivot_pdf[col] = 0

        pivot_pdf = pivot_pdf[["Low", "High", "Critical"]]
        pivot_pdf["Risk Score"] = pivot_pdf["Low"]*1 + pivot_pdf["High"]*3 + pivot_pdf["Critical"]*9
        pivot_pdf = pivot_pdf.sort_values("Risk Score", ascending=False)

        # En-tête avec Paragraph (pas de \n)
        matrix_header = [
            Paragraph("Sector",           label_style),
            Paragraph("Low (<300)",        label_style),
            Paragraph("High (300–1000)",   label_style),
            Paragraph("Critical (>1000)",  label_style),
            Paragraph("Risk Score",        label_style),
        ]
        matrix_data = [matrix_header]

        for sector, row in pivot_pdf.iterrows():
            risk = int(row["Risk Score"])
            if risk > 50:
                risk_hex = "#C0392B"
            elif risk > 15:
                risk_hex = "#E67E22"
            else:
                risk_hex = "#27AE60"

            matrix_data.append([
                Paragraph(str(sector)[:35], normal_style),
                Paragraph(str(int(row["Low"])),      normal_style),
                Paragraph(str(int(row["High"])),     normal_style),
                Paragraph(f'<font color="#C0392B"><b>{int(row["Critical"])}</b></font>'
                          if row["Critical"] > 0 else str(int(row["Critical"])), normal_style),
                Paragraph(f'<font color="{risk_hex}"><b>{risk}</b></font>', normal_style),
            ])

        col_w_matrix = [70*mm, 25*mm, 28*mm, 28*mm, 22*mm]
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

        # Légende
        legend_data = [
            [Paragraph('<font color="#27AE60">● Low</font>',    normal_style), Paragraph("< 300 kg/h — Score ×1",       normal_style)],
            [Paragraph('<font color="#E67E22">● High</font>',   normal_style), Paragraph("300–1 000 kg/h — Score ×3",   normal_style)],
            [Paragraph('<font color="#C0392B">● Critical</font>',normal_style),Paragraph("> 1 000 kg/h — Score ×9",     normal_style)],
        ]
        legend_table = Table(legend_data, colWidths=[35*mm, 80*mm])
        legend_table.setStyle(TableStyle([
            ("FONTSIZE",       (0, 0), (-1, -1), 8),
            ("LEFTPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 2),
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
