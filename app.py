import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# ------------------------
# Configuration page
# ------------------------
st.set_page_config(page_title="CH4 Hassi R'mel", layout="wide")
st.title("Surveillance du Méthane – Hassi R'mel")
st.markdown("## Dashboard interactif CH₄ + FIRMS")

# ------------------------
# Chemins fichiers
# ------------------------
DATA_DIR = "data"  # minuscule !

# CSV
CSV_FOLDER = os.path.join(DATA_DIR, "2020-2024")
CSV_GLOBAL = os.path.join(CSV_FOLDER, "CH4-2020-2024-CSV.csv")
CSV_ANNUAL = os.path.join(CSV_FOLDER, "CH4-annuel-2020-2024-CSV.csv")
CSV_MONTHLY = os.path.join(CSV_FOLDER, "CH4-mensuel-2020-2024-CSV.csv")

# GeoTIFF Moyenne
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")  # garder exact nom du dossier
mean_tifs = [os.path.join(MEAN_DIR, f"CH4-{y}-TIF.tif") for y in range(2020, 2025)]

# GeoTIFF Anomalie
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
anomaly_tifs = [os.path.join(ANOMALY_DIR, f"CH4-anomalie-{y}-TIF.tif") for y in range(2020, 2025)]

# ------------------------
# Vérifier le dossier Data
# ------------------------
if os.path.exists(DATA_DIR):
    st.write("Contenu du dossier Data :", os.listdir(DATA_DIR))
else:
    st.warning("❌ Dossier 'Data' introuvable sur le serveur")

# ------------------------
# Charger CSV
# ------------------------
df_global = pd.read_csv(CSV_GLOBAL) if os.path.exists(CSV_GLOBAL) else pd.DataFrame()
df_annual = pd.read_csv(CSV_ANNUAL) if os.path.exists(CSV_ANNUAL) else pd.DataFrame()
df_monthly = pd.read_csv(CSV_MONTHLY) if os.path.exists(CSV_MONTHLY) else pd.DataFrame()

# ------------------------
# Affichage tableaux
# ------------------------
st.subheader("📊 TimeSeries CH₄ Globale")
st.dataframe(df_global.head(10))

st.subheader("📊 TimeSeries CH₄ Annuelle")
st.dataframe(df_annual.head(10))

st.subheader("📊 TimeSeries CH₄ Mensuelle")
st.dataframe(df_monthly.head(10))

# ------------------------
# Carte CH4 avec choix année et type
# ------------------------
st.markdown("## 🗺 Carte CH₄ (TROPOMI)")

year = st.selectbox("Sélectionner l’année pour la carte CH₄", [2020, 2021, 2022, 2023, 2024])
show_type = st.radio("Type de carte", ["Moyenne", "Anomalie"])

tif_path = mean_tifs[year-2020] if show_type=="Moyenne" else anomaly_tifs[year-2020]

if os.path.exists(tif_path):
    with rasterio.open(tif_path) as src:
        arr = src.read(1)
    arr[arr <= 0] = np.nan

    fig, ax = plt.subplots(figsize=(7,5))
    ax.imshow(arr, cmap='viridis')
    ax.axis('off')
    st.pyplot(fig)
else:
    st.warning(f"Fichier TIFF introuvable : {tif_path}")

# ------------------------
# Analyse automatique
# ------------------------
st.markdown("## 🔍 Analyse automatique")

mean_ch4 = float(df_annual.select_dtypes(include=[np.number]).mean().iloc[0]) if not df_annual.empty else None
n_fires = len(df_global)  # ou df_firms si tu ajoutes FIRMS

if mean_ch4 is None:
    st.info("Pas assez de données pour analyser.")
else:
    st.write(f"**Concentration moyenne CH₄ :** {mean_ch4:.2f} ppb")
    st.write(f"**Nombre d’événements FIRMS :** {n_fires}")

    if mean_ch4 > 1850 and n_fires == 0:
        st.error("🔥 FUITE probable de CH₄ (pas de torchage détecté)")
    elif mean_ch4 > 1850 and n_fires > 0:
        st.warning("⚠️ Torchage actif (CH₄ élevé + feux détectés)")
    else:
        st.success("✓ Situation normale")

# ------------------------
# Export PDF
# ------------------------
st.markdown("## 📄 Export PDF")

def generate_pdf_bytes(mean_ch4, n_fires):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 60, "Rapport CH₄ – Hassi R'mel")

    c.setFont("Helvetica", 10)
    c.drawString(40, h - 90, f"Moyenne CH₄ : {mean_ch4:.2f} ppb")
    c.drawString(40, h - 110, f"FIRMS détectés : {n_fires}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if st.button("Générer le PDF"):
    pdf_bytes = generate_pdf_bytes(mean_ch4 if mean_ch4 else 0, n_fires)
    st.download_button(
        label="Télécharger le rapport PDF",
        data=pdf_bytes,
        file_name="Rapport_CH4_HassiRmel.pdf",
        mime="application/pdf"
    )
