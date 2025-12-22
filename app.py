# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import ee
import json
import tempfile
import os
from datetime import datetime
import folium
from streamlit_folium import st_folium
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import smtplib
from email.mime.text import MIMEText

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("🛢️ Système intelligent de surveillance du méthane (CH₄) – HSE")

# ===================== GEE INIT =====================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ===================== SIDEBAR =====================
st.sidebar.header("📍 Paramètres du site")

sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}

selected_site = st.sidebar.selectbox("Site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== CHOIX ANNÉE =====================
st.sidebar.header("📅 Année d’analyse")
selected_year = st.sidebar.selectbox(
    "Choisir l’année",
    [2020, 2021, 2022, 2023, 2024]
)

# ===================== CSV HISTORIQUE =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"

if not os.path.exists(csv_hist):
    st.error(f"Fichier introuvable : {csv_hist}")
    st.stop()

df_hist = pd.read_csv(csv_hist)

# ===================== FONCTIONS =====================
def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    st.error("❌ Aucune colonne CH₄ détectée")
    st.stop()

def detect_anomaly(value, series):
    std = series.std()
    if std == 0 or np.isnan(std):
        return 0
    return (value - series.mean()) / std

# ===================== SESSION STATE =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False

# ===================== BOUTON PRINCIPAL =====================
st.markdown("## 🚀 Analyse annuelle CH₄")

if st.button("📊 Lancer l’analyse de l’année sélectionnée"):

    # ---- filtrer l’année ----
    df_hist["date"] = pd.to_datetime(df_hist.iloc[:, 0])
    df_year = df_hist[df_hist["date"].dt.year == selected_year]

    if df_year.empty:
        st.warning("Aucune donnée pour cette année")
        st.stop()

    ch4_series = get_ch4_series(df_year)
    ch4_mean = ch4_series.mean()
    z = detect_anomaly(ch4_mean, ch4_series)

    if z > 3:
        risk, color = "Critique", "red"
    elif z > 2:
        risk, color = "Anomalie", "orange"
    else:
        risk, color = "Normal", "green"

    st.session_state.analysis_done = True
    st.session_state.results = {
        "year": selected_year,
        "ch4": ch4_mean,
        "z": z,
        "risk": risk,
        "color": color
    }

# ===================== RÉSULTATS =====================
if st.session_state.analysis_done:
    r = st.session_state.results

    st.markdown(f"## 📌 Résultats – Année {r['year']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("CH₄ moyen (ppb)", round(r["ch4"], 1))
    c2.metric("Z-score", round(r["z"], 2))
    c3.metric("Risque", r["risk"])

    st.markdown(
        f"<h3 style='color:{r['color']}'>Niveau de risque : {r['risk']}</h3>",
        unsafe_allow_html=True
    )

    # ===================== CARTE =====================
    st.markdown("## 🗺️ Carte du site")
    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)
    folium.Circle(
        [lat_site, lon_site],
        radius=3500,
        color=r["color"],
        fill=True
    ).add_to(m)
    folium.Marker([lat_site, lon_site], tooltip=selected_site).add_to(m)
    st_folium(m, width=750, height=450)

    # ===================== GRAPHIQUE =====================
    st.markdown("## 📈 Évolution annuelle CH₄")
    fig = px.line(
        df_year,
        x="date",
        y=ch4_series,
        title=f"CH₄ – {selected_site} ({r['year']})"
    )
    fig.add_hline(
        y=ch4_series.mean(),
        line_dash="dash",
        annotation_text="Moyenne annuelle"
    )
    st.plotly_chart(fig, use_container_width=True)


