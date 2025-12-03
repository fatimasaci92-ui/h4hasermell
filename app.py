import os
import streamlit as st
import pandas as pd
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt

# ================= PATHS =================

DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2025")  # mis à jour pour inclure 2025

# Fichiers tifs moyens et anomalies 2020-2025

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

# CSV

csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2025.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2020_2025.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2025.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")

# ================== Titre ==================

st.title("📊 Analyse des données CH4 – Hassi R'mel 2020-2025")

# ================== Section A: Données globales ==================

st.header("📄 Données globales")
if os.path.exists(csv_global):
df_global = pd.read_csv(csv_global)
st.dataframe(df_global)
else:
st.warning(f"Le fichier {csv_global} est introuvable.")

# ================== Section B: Données annuelles et mensuelles ==================

st.header("📆 Données annuelles et mensuelles")
if os.path.exists(csv_annual):
df_annual = pd.read_csv(csv_annual)
st.line_chart(df_annual.set_index("Year")["CH4_mean"])
else:
st.warning(f"Le fichier {csv_annual} est introuvable.")

if os.path.exists(csv_monthly):
df_monthly = pd.read_csv(csv_monthly)
st.line_chart(df_monthly.set_index("Month")["CH4_mean"])
else:
st.warning(f"Le fichier {csv_monthly} est introuvable.")

# ================== Section C: Cartes par année ==================

st.header("🗺️ Cartes Moyenne & Anomalie par année")
year_choice = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])

# Affichage moyenne

mean_path = mean_files.get(year_choice)
if mean_path and os.path.exists(mean_path):
with rasterio.open(mean_path) as src:
fig, ax = plt.subplots(figsize=(6,6))
show(src, ax=ax)
ax.set_title(f"CH4 moyenne {year_choice}")
st.pyplot(fig)
else:
st.warning(f"Fichier moyen pour {year_choice} introuvable.")

# Affichage anomalie

anomaly_path = anomaly_files.get(year_choice)
if anomaly_path and os.path.exists(anomaly_path):
with rasterio.open(anomaly_path) as src:
fig, ax = plt.subplots(figsize=(6,6))
show(src, ax=ax)
ax.set_title(f"Anomalie CH4 {year_choice}")
st.pyplot(fig)
else:
st.warning(f"Fichier anomalie pour {year_choice} introuvable.")

# ================== Section D: Données quotidiennes 2025 ==================

st.header("📅 Données quotidiennes 2025")
if os.path.exists(csv_daily):
df_daily = pd.read_csv(csv_daily)
st.line_chart(df_daily.set_index("Date")["CH4_value"])
else:
st.warning(f"Le fichier {csv_daily} est introuvable.")

