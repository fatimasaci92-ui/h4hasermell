import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os, io, json, tempfile
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import ee

# ================= GOOGLE EARTH ENGINE =================
try:
    key = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(key, f)
        path = f.name
    ee.Initialize(ee.ServiceAccountCredentials(key["client_email"], path))
    os.remove(path)
except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= STREAMLIT =================
st.set_page_config("Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

latitude = st.number_input("Latitude", value=32.93)
longitude = st.number_input("Longitude", value=3.30)
site_name = st.text_input("Site", "Hassi R'mel")

# ================= FONCTION GEE CORRIGÉE =================
def get_latest_ch4_from_gee(lat, lon, days=30):
    point = ee.Geometry.Point([lon, lat])
    end = ee.Date(datetime.utcnow())
    start = end.advance(-days, "day")

    col = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
           .filterBounds(point)
           .filterDate(start, end)
           .select("CH4_column_volume_mixing_ratio_dry_air")
           .sort("system:time_start", False))

    img = col.first()
    if img is None:
        return None, None

    value = img.reduceRegion(
        ee.Reducer.mean(), point, 7000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    if value.getInfo() is None:
        return None, None

    ch4 = float(value.getInfo()) * 1e9  # ✔️ conversion correcte
    date_img = ee.Date(img.get("system:time_start")).format("yyyy-MM-dd").getInfo()
    return ch4, date_img

# ================= HAZOP =================
def hazop(ch4):
    if ch4 < 1800:
        return "Normal", "Surveillance continue"
    elif ch4 < 1850:
        return "Modéré", "Vérifier torches"
    elif ch4 < 1900:
        return "Élevé", "Inspection urgente"
    else:
        return "Critique", "Arrêt + alerte HSE"

# ================= PDF =================
def pdf_report(site, lat, lon, date_img, ch4, risk, action):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    s = []

    s.append(Paragraph("<b>RAPPORT HSE – CH₄</b>", styles["Title"]))
    s.append(Spacer(1, 12))

    meta = f"""
    Site : {site}<br/>
    Latitude : {lat}<br/>
    Longitude : {lon}<br/>
    Date image satellite : {date_img}<br/>
    """
    s.append(Paragraph(meta, styles["Normal"]))
    s.append(Spacer(1, 12))

    table = Table([
        ["CH₄ (ppb)", f"{ch4:.1f}"],
        ["Niveau", risk],
        ["Action HSE", action]
    ])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey)
    ]))
    s.append(table)

    doc.build(s)
    return buf.getvalue()

# ================= ANALYSE DU JOUR =================
st.header("Analyse CH₄ du jour (Satellite)")

if st.button("Analyser"):
    ch4, date_img = get_latest_ch4_from_gee(latitude, longitude)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    if ch4 is None:
        st.error("❌ Aucune image satellite disponible (30 jours)")
        st.stop()

    if date_img != today:
        st.warning("☁️ Pas de passage satellite aujourd’hui")
        st.info(f"➡️ Dernière image disponible : {date_img}")

    risk, action = hazop(ch4)

    st.success(f"CH₄ = {ch4:.1f} ppb")
    st.write(f"Niveau : **{risk}**")
    st.write(f"Action : **{action}**")

    df = pd.DataFrame([{
        "Date image": date_img,
        "CH₄ (ppb)": ch4,
        "Niveau": risk,
        "Action HSE": action
    }])
    st.table(df)

    pdf = pdf_report(site_name, latitude, longitude, date_img, ch4, risk, action)
    st.download_button(
        "📄 Télécharger PDF du jour",
        pdf,
        f"Rapport_CH4_{site_name}_{date_img}.pdf",
        "application/pdf"
    )
