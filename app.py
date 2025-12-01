import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime

st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")

# ------------------------
# 1) Choix de la localisation
# ------------------------
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

latitude = st.number_input("Latitude du site", value=32.93)
longitude = st.number_input("Longitude du site", value=3.3)
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ------------------------
# 2) Chemins fichiers (sous-dossiers)
# ------------------------
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2025)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2025)}
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")

# ------------------------
# 3) Vérification contenu dossier
# ------------------------
st.subheader("Contenu des sous-dossiers")
st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
st.write("CSV 2020-2024 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ------------------------
# 4) Charger CSV
# ------------------------
df_global = pd.read_csv(csv_global) if os.path.exists(csv_global) else pd.DataFrame()
df_annual = pd.read_csv(csv_annual) if os.path.exists(csv_annual) else pd.DataFrame()
df_monthly = pd.read_csv(csv_monthly) if os.path.exists(csv_monthly) else pd.DataFrame()

# Affichage rapide CSV pour debug
st.write("Aperçu CSV annuel :")
if not df_annual.empty:
    st.write(df_annual.head())
else:
    st.info("CSV annuel introuvable ou vide.")

# ------------------------
# 5) Graphique évolution CH4
# ------------------------
st.markdown("## Évolution CH₄ (2020-2024)")
if not df_annual.empty and 'Year' in df_annual.columns and 'CH4_mean' in df_annual.columns:
    years = df_annual['Year']
    ch4_values = df_annual['CH4_mean']
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(years, ch4_values, marker='o')
    ax.set_title(f"Évolution CH₄ – {site_name}")
    ax.set_xlabel("Année")
    ax.set_ylabel("CH₄ (ppb)")
    ax.grid(True)
    st.pyplot(fig)
else:
    st.info("Pas de données annuelles pour graphique.")

# ------------------------
# 6) Affichage cartes par année
# ------------------------
st.markdown("## Cartes Moyennes et Anomalies CH₄")
year_choice = st.selectbox("Choisir l'année", [2020,2021,2022,2023,2024])

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"CH₄ moyen {year_choice}")
    if os.path.exists(mean_files[year_choice]):
        with rasterio.open(mean_files[year_choice]) as src:
            arr = src.read(1)
        arr[arr <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(arr, cmap='viridis')
        ax.set_title(f"CH₄ moyen {year_choice}")
        ax.axis('off')
        st.pyplot(fig)
    else:
        st.warning("Fichier CH₄ moyen introuvable.")

with col2:
    st.subheader(f"Anomalie CH₄ {year_choice}")
    if os.path.exists(anomaly_files[year_choice]):
        with rasterio.open(anomaly_files[year_choice]) as src:
            arr = src.read(1)
        arr[arr == 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(arr, cmap='coolwarm')
        ax.set_title(f"Anomalie CH₄ {year_choice}")
        ax.axis('off')
        st.pyplot(fig)
    else:
        st.warning("Fichier anomalie CH₄ introuvable.")

# ------------------------
# 7) Analyse HSE automatique
# ------------------------
st.markdown("## Analyse HSE automatique")

mean_ch4_year = None
risk = None
action = None

if not df_annual.empty and 'Year' in df_annual.columns and 'CH4_mean' in df_annual.columns:
    if year_choice in df_annual['Year'].values:
        mean_ch4_year = float(df_annual[df_annual['Year']==year_choice]['CH4_mean'].values[0])
        # Niveau de risque
        if mean_ch4_year < 1800:
            risk = "Faible"
            action = "Surveillance continue."
        elif mean_ch4_year < 1850:
            risk = "Modéré"
            action = "Vérifier les torches et informer l'équipe HSE."
        elif mean_ch4_year < 1900:
            risk = "Élevé"
            action = "Inspection urgente du site et mesures de sécurité immédiates."
        else:
            risk = "Critique"
            action = "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire."

        st.write(f"**Année :** {year_choice}")
        st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
        st.write(f"**Niveau de risque HSE :** {risk}")
        st.write(f"**Actions recommandées :** {action}")
    else:
        st.info("Pas de données CH₄ pour cette année.")
else:
    st.info("Pas assez de données HSE pour cette année.")

# ------------------------
# 8) Export PDF HSE
# ------------------------
st.markdown("## Générer le rapport HSE complet")

def generate_pdf_bytes(year, mean_ch4, risk, action):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # Titre
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 60, f"Rapport HSE – {site_name}")
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 80, f"Année : {year}")
    c.drawString(40, h - 100, f"Date de génération : {datetime.now().strftime('%d/%m/%Y')}")

    # Statistiques
    c.drawString(40, h - 130, f"Moyenne CH₄ : {mean_ch4:.2f} ppb")
    c.drawString(40, h - 150, f"Niveau de risque HSE : {risk}")
    c.drawString(40, h - 170, f"Actions recommandées : {action}")

    # Foo
