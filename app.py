import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.plot import show
import io

st.set_page_config(
page_title="Surveillance CH4 – Hassi R'mel",
layout="wide"
)

# -----------------------------
# ----- Chargement CSV ---------
# -----------------------------
@st.cache_data
def load_csv(file):
return pd.read_csv(file)

data_all = {
"Anomalies 2020-2024": "Anomalies_CH4_HassiRmel.csv",
"CH4 Global 2020-2024": "CH4_HassiRmel_2020_2024.csv",
"CH4 Annuel 2020-2024": "CH4_HassiRmel_annual_2020_2024.csv",
"CH4 Mensuel 2020-2024": "CH4_HassiRmel_monthly_2020_2024.csv",
"CH4 Annuel 2020-2025": "CH4_annual_2020_2025.csv",
"CH4 Quotidien 2025": "CH4_daily_2025.csv"
}

# -----------------------------
# ----- Chargement TIFF -------
# -----------------------------
def load_tif(path):
with rasterio.open(path) as src:
arr = src.read(1)
profile = src.profile
return arr, profile

# Dictionnaires des TIFF
mean_files = {
year: f"CH4_mean_{year}.tif"
for year in range(2020, 2025 + 1)
}

anomaly_files = {
year: f"CH4_anomaly_{year}.tif"
for year in range(2020, 2025 + 1)
}

# -----------------------------
# ----- Interface Streamlit ----
# -----------------------------
st.title(" Surveillance des émissions de Méthane – Hassi R'mel (2020–2025)")

section = st.sidebar.selectbox(
"Choisir une analyse",
["Données CSV", "Moyenne CH4 (TIFF)", "Anomalie CH4 (TIFF)"]
)

# ---------- CSV VIEW ----------
if section == "Données CSV":

st.header(" Analyse des données CSV (2020–2025)")

dataset = st.selectbox("Choisir un fichier", list(data_all.keys()))
df = load_csv(data_all[dataset])

st.subheader("Aperçu des données")
st.dataframe(df)

# Graphique simple
st.subheader(" Graphique")
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

if len(numeric_cols) >= 1:
y_col = st.selectbox("Colonne à afficher", numeric_cols)
fig, ax = plt.subplots()
ax.plot(df[y_col])
ax.set_title(f"{y_col}")
st.pyplot(fig)

# Download
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button(
label=" Télécharger CSV",
data=csv_bytes,
file_name=data_all[dataset],
mime="text/csv"
)

# ---------- MEAN TIFF ----------
elif section == "Moyenne CH4 (TIFF)":
st.header(" Cartes des moyennes CH4 (2020–2025)")

year = st.selectbox("Choisir l'année", list(mean_files.keys()))
tif_path = mean_files[year]

arr, profile = load_tif(tif_path)

st.subheader(f"CH4 Mean – {year}")
fig, ax = plt.subplots()
show(arr, ax=ax)
st.pyplot(fig)

# ---------- ANOMALY TIFF ----------
elif section == "Anomalie CH4 (TIFF)":
st.header(" Cartes des anomalies CH4 (2020–2025)")

year = st.selectbox("Choisir l'année", list(anomaly_files.keys()))
tif_path = anomaly_files[year]

arr, profile = load_tif(tif_path)

st.subheader(f"CH4 Anomaly – {year}")
fig, ax = plt.subplots()
show(arr, ax=ax)
st.pyplot(fig)
