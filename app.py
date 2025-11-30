import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="CH4 Hassi R'mel", layout="wide")

# ------------------------
# Chemins fichiers
# ------------------------
DATA_DIR = "data"  # dossier contenant tes fichiers
TIF_PATH = os.path.join(DATA_DIR, "CH4_2023_Hassi_Rmel.tif")
STATS_CSV = os.path.join(DATA_DIR, "CH4_Stats_Hassi_Rmel (1).csv")
FIRMS_CSV = os.path.join(DATA_DIR, "FIRMS_Hassi_Rmel_2023 (2).csv")

st.title("Surveillance du Méthane – Hassi R'mel")
st.markdown("## Dashboard interactif CH₄ + FIRMS")

# ------------------------
# Vérifier si le dossier et fichiers existent
# ------------------------
if os.path.exists(DATA_DIR):
    st.write("Contenu du dossier data :", os.listdir(DATA_DIR))
else:
    st.warning("❌ Dossier 'data' introuvable sur le serveur")

# ------------------------
# Charger les données
# ------------------------
df_stats = pd.read_csv(STATS_CSV) if os.path.exists(STATS_CSV) else pd.DataFrame()
df_firms = pd.read_csv(FIRMS_CSV) if os.path.exists(FIRMS_CSV) else pd.DataFrame()

# ------------------------
# Affichage des tableaux
# ------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Statistiques CH₄")
    st.dataframe(df_stats.head(15))

with col2:
    st.subheader("Détections FIRMS (Torchage)")
    st.dataframe(df_firms.head(15))

# ------------------------
# Carte CH4
# ------------------------
st.markdown("## Carte CH₄ (TROPOMI)")

if os.path.exists(TIF_PATH):
    with rasterio.open(TIF_PATH) as src:
        arr = src.read(1)
    arr[arr <= 0] = np.nan

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.imshow(arr, cmap='viridis')
    ax.axis('off')
    st.pyplot(fig)
else:
    st.warning("❌ Fichier TIFF introuvable dans data/")

# ------------------------
# Analyse automatique
# ------------------------
st.markdown("## Analyse automatique")

mean_ch4 = float(df_stats.select_dtypes(include=[np.number]).mean().iloc[0]) if not df_stats.empty else None
n_fires = len(df_firms)

if mean_ch4 is None:
    st.info("Pas assez de données pour analyser.")
else:
    st.write(f"**Concentration moyenne CH₄ :** {mean_ch4:.2f} ppb")
    st.write(f"**Détections FIRMS :** {n_fires}")

    if mean_ch4 > 1850 and n_fires == 0:
        st.error("🔥 FUITE probable de CH₄ (pas de torchage détecté)")
    elif mean_ch4 > 1850 and n_fires > 0:
        st.warning("⚠️ Torchage actif (CH₄ élevé + feux détectés)")
    else:
        st.success("✓ Situation normale")

# ------------------------
# Export PDF
# ------------------------
st.markdown("## Export PDF")

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

if st.button("📄 Générer le PDF"):
    pdf_bytes = generate_pdf_bytes(mean_ch4 if mean_ch4 else 0, n_fires)
    st.download_button(
        label="Télécharger le rapport PDF",
        data=pdf_bytes,
        file_name="Rapport_CH4_HassiRmel.pdf",
        mime="application/pdf"
    )
