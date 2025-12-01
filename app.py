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
# 2) Chemins fichiers
# ------------------------
DATA_DIR = "data"

# Moyennes annuelles
mean_files = [f"CH4_mean_{year}.tif" for year in range(2020, 2025)]
# Anomalies annuelles
anomaly_files = [f"CH4_anomaly_{year}.tif" for year in range(2020, 2025)]
# CSV données
csv_files = {
    "global": "CH4_HassiRmel_2020_2024.csv",
    "annual": "CH4_HassiRmel_annual_2020_2024.csv",
    "monthly": "CH4_HassiRmel_monthly_2020_2024.csv"
}

# ------------------------
# 3) Vérifier contenu dossier
# ------------------------
st.subheader("Contenu du dossier data")
if os.path.exists(DATA_DIR):
    st.write(os.listdir(DATA_DIR))
else:
    st.error("Dossier 'data' introuvable")

# ------------------------
# 4) Charger CSV
# ------------------------
df_global = pd.read_csv(os.path.join(DATA_DIR, csv_files["global"])) if os.path.exists(os.path.join(DATA_DIR, csv_files["global"])) else pd.DataFrame()
df_annual = pd.read_csv(os.path.join(DATA_DIR, csv_files["annual"])) if os.path.exists(os.path.join(DATA_DIR, csv_files["annual"])) else pd.DataFrame()
df_monthly = pd.read_csv(os.path.join(DATA_DIR, csv_files["monthly"])) if os.path.exists(os.path.join(DATA_DIR, csv_files["monthly"])) else pd.DataFrame()

# ------------------------
# 5) Graphiques CH₄
# ------------------------
st.markdown("## Évolution CH₄ (2020-2024)")
if not df_annual.empty:
    years = df_annual['Year'] if 'Year' in df_annual.columns else range(2020, 2025)
    ch4_values = df_annual['CH4_mean'] if 'CH4_mean' in df_annual.columns else [0]*len(years)
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
mean_path = os.path.join(DATA_DIR, f"CH4_mean_{year_choice}.tif")
anomaly_path = os.path.join(DATA_DIR, f"CH4_anomaly_{year_choice}.tif")

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"CH₄ moyen {year_choice}")
    if os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
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
    if os.path.exists(anomaly_path):
        with rasterio.open(anomaly_path) as src:
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
# 7) Analyse HSE automatique par année
# ------------------------
st.markdown("## Analyse HSE automatique")

if not df_annual.empty:
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
    st.info("Pas assez de données HSE pour cette année.")

# ------------------------
# 8) Export PDF HSE complet
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

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, 40, "Rapport généré automatiquement via le dashboard HSE CH₄")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if st.button("📄 Générer le PDF HSE"):
    pdf_bytes = generate_pdf_bytes(year_choice, mean_ch4_year, risk, action)
    st.download_button(
        label="Télécharger le rapport HSE PDF",
        data=pdf_bytes,
        file_name=f"Rapport_HSE_{site_name}_{year_choice}.pdf",
        mime="application/pdf"
    )
