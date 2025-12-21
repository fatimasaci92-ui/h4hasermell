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
import matplotlib.pyplot as plt
import plotly.express as px

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")
st.info(
    "⚠️ Ce système permet une surveillance régionale du CH₄ à partir de données satellitaires "
    "(Sentinel-5P). Il ne remplace pas les inspections terrain."
)

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

# ===================== SITE INPUT =====================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", "Hassi R'mel")
selected_site = site_name

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
try:
    df_hist = pd.read_csv(csv_hist)
except FileNotFoundError:
    st.error(f"❌ Fichier historique CH₄ introuvable : {csv_hist}")
    st.stop()

# ===================== FUNCTIONS =====================
def get_latest_ch4(latitude, longitude, days_back=60):
    geom = ee.Geometry.Point([longitude, latitude]).buffer(3500)  # pixel TROPOMI
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    img = ee.Image(col.first())
    if img is None:
        return None, None

    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    ch4_dict = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=7000,
        maxPixels=1e9
    ).getInfo()

    if not ch4_dict:
        return None, None

    return list(ch4_dict.values())[0] * 1000, date_img  # ppb


def get_wind_speed(latitude, longitude, date):
    point = ee.Geometry.Point([longitude, latitude])
    era5 = (
        ee.ImageCollection("ECMWF/ERA5/DAILY")
        .filterDate(date, date)
        .first()
    )

    u = era5.select("u_component_of_wind_10m")
    v = era5.select("v_component_of_wind_10m")
    wind = u.pow(2).add(v.pow(2)).sqrt()

    speed = wind.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=10000,
        maxPixels=1e9
    ).getInfo()

    return list(speed.values())[0]


def detect_anomaly_zscore(value, series):
    mean = series.mean()
    std = series.std()
    z = (value - mean) / std
    return z


def get_ch4_series(df):
    if "CH4_ppb" in df.columns:
        return df["CH4_ppb"]
    else:
        return df.iloc[:, 1]


def log_hse_alert(site, lat, lon, ch4, z, risk, decision):
    # Ici on peut logger dans un fichier ou base de données
    pass


def send_email_alert(to_email, subject, body):
    # Ici envoyer l'email via SMTP
    pass

# ===================== ANALYSE =====================
st.markdown("## 🔍 Analyse journalière CH₄")
if st.button("Lancer l’analyse"):
    ch4, date_img = get_latest_ch4(latitude, longitude)

    if ch4 is None:
        st.error("Aucune donnée CH₄ disponible.")
        st.stop()

    wind = get_wind_speed(latitude, longitude, date_img)
    z = detect_anomaly_zscore(ch4, df_hist["CH4_ppb"])

    st.session_state.analysis_done = True
    st.session_state.results = {"ch4": ch4, "date_img": date_img}

    # ===================== LOGIQUE DE DÉCISION =====================
    if z > 3:
        risk, decision, color = "Critique", "Alerte HSE immédiate", "red"
        log_hse_alert(selected_site, latitude, longitude, ch4, z, risk, decision)

        # Sécuriser l'envoi d'email
        try:
            hse_email = st.secrets["HSE_EMAIL"]
        except KeyError:
            hse_email = None
            st.warning("⚠️ HSE_EMAIL non défini dans les secrets – email non envoyé.")

        if hse_email:
            send_email_alert(
                hse_email,
                f"ALERTE CH₄ CRITIQUE {selected_site}",
                f"CH4={ch4:.1f} ppb, Z={z:.2f}, Action={decision}"
            )

    elif z > 2:
        risk, decision, color = "Anomalie", "Inspection terrain requise", "orange"
    else:
        risk, decision, color = "Normal", "Surveillance continue", "green"

    # ===================== AFFICHAGE =====================
    st.success(f"📅 Date image : {date_img}")
    st.metric("CH₄ (ppb)", round(ch4, 1))
    st.metric("Z-score anomalie", round(z, 2))
    st.metric("Vent moyen (m/s)", round(wind, 2))

    st.warning(
        f"⚠️ Anomalie atmosphérique détectée : **{risk}**\n\n"
        f"➡️ Action recommandée : **{decision}**"
    )

# ===================== GRAPHIQUE TEMPOREL =====================
st.markdown("## 📈 Évolution CH₄ historique")
ch4_series = get_ch4_series(df_hist)
df_hist_plot = df_hist.copy()
df_hist_plot["CH4_ppb"] = ch4_series
df_hist_plot["date"] = pd.to_datetime(df_hist_plot.iloc[:,0])

fig = px.line(
    df_hist_plot,
    x="date",
    y="CH4_ppb",
    title=f"Évolution CH₄ – {selected_site}"
)

fig.add_hline(
    y=ch4_series.mean(),
    line_dash="dash",
    line_color="green",
    annotation_text="Moyenne"
)
fig.add_hrect(
    y0=ch4_series.mean()-2*ch4_series.std(),
    y1=ch4_series.mean()+2*ch4_series.std(),
    fillcolor="lightgreen",
    opacity=0.2,
    line_width=0
)

# Ajouter le point du jour si analyse faite
if st.session_state.get("analysis_done", False):
    r = st.session_state.results
    try:
        if r["date_img"] != "Historique CSV":
            date_point = pd.to_datetime(r["date_img"], errors="coerce")
            if pd.isna(date_point):
                date_point = df_hist_plot["date"].max()
        else:
            date_point = df_hist_plot["date"].max()
    except Exception:
        date_point = df_hist_plot["date"].max()

    fig.add_scatter(
        x=[date_point],
        y=[r["ch4"]],
        mode="markers",
        marker=dict(color="red", size=12),
        name="Analyse du jour"
    )

st.plotly_chart(fig, use_container_width=True)

