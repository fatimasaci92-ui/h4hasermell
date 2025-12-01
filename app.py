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
# 1) Sélection de la localisation
# ------------------------
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + FIRMS")

latitude = st.number_input("Latitude du site", value=32.93)
longitude = st.number_input("Longitude du site", value=3.3)

site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ------------------------
# 2) Chemins fichiers
# ------------------------
DATA_DIR = "data"
TIF_FILE = "CH4_2023_Hassi_Rmel.tif"
STATS_FILE = "CH4_Stats_Hassi_Rmel (1).csv"
FIRMS_FILE = "FIRMS_Hassi_Rmel_2023 (2).csv"

TIF_PATH = os.path.join(DATA_DIR, TIF_FILE)
STATS_CSV = os.path.join(DATA_DIR, STATS_FILE)
FIRMS_CSV = os.path.join(DATA_DIR, FIRMS_FILE)

# Vérifier fichiers
st.subheader("Contenu du dossier data")
if os.path.exists(DATA_DIR):
    st.write(os.listdir(DATA_DIR))
else:
    st.error("Dossier 'data' introuvable")

# ------------------------
# 3) Charger les données
# ------------------------
df_stats = pd.read_csv(STATS_CSV) if os.path.exists(STATS_CSV) else pd.DataFrame()
df_firms = pd.read_csv(FIRMS_CSV) if os.path.exists(FIRMS_CSV) else pd.DataFrame()

# ------------------------
# 4) Affichage des tableaux
# ------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Statistiques CH₄")
    st.dataframe(df_stats.head(15))

with col2:
    st.subheader("Détections FIRMS (Torchage)")
    st.dataframe(df_firms.head(15))

# ------------------------
# 5) Carte CH4
# ------------------------
st.markdown("## Carte CH₄ (TROPOMI)")
if os.path.exists(TIF_PATH):
    with rasterio.open(TIF_PATH) as src:
        arr = src.read(1)
    arr[arr <= 0] = np.nan

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.imshow(arr, cmap='viridis')
    ax.set_title(f"Carte CH₄ – {site_name}")
    ax.axis('off')
    st.pyplot(fig)
else:
    st.warning("❌ Fichier TIFF introuvable")

# ------------------------
# 6) Analyse HSE automatique
# ------------------------
st.markdown("## Analyse HSE automatique")

if df_stats.empty or df_firms.empty:
    st.info("Pas assez de données pour analyser.")
else:
    mean_ch4 = float(df_stats.select_dtypes(include=[np.number]).mean().iloc[0])
    n_fires = len(df_firms)

    # Niveau de risque
    if mean_ch4 < 1800:
        risk = "Faible"
        action = "Surveillance continue."
    elif mean_ch4 < 1850:
        risk = "Modéré"
        action = "Vérifier les torches et informer l'équipe HSE."
    elif mean_ch4 < 1900:
        risk = "Élevé"
        action = "Inspection urgente du site et mesures de sécurité immédiates."
    else:
        risk = "Critique"
        action = "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire."

    # Conclusion
    if mean_ch4 > 1850 and n_fires == 0:
        conclusion = "Fuite probable de CH₄ (pas de torchage détecté)"
    elif mean_ch4 > 1850 and n_fires > 0:
        conclusion = "Torchage actif avec CH₄ élevé"
    else:
        conclusion = "Situation normale"

    # Affichage
    st.write(f"**Concentration moyenne CH₄ :** {mean_ch4:.2f} ppb")
    st.write(f"**Détections FIRMS :** {n_fires}")
    st.write(f"**Niveau de risque HSE :** {risk}")
    st.write(f"**Actions recommandées :** {action}")
    st.write(f"**Conclusion :** {conclusion}")

# ------------------------
# 7) Export PDF HSE complet
# ------------------------
st.markdown("## Générer le rapport HSE complet")

def generate_pdf_bytes(mean_ch4, n_fires, risk, action, conclusion):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # Titre
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 60, f"Rapport HSE – {site_name}")
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 80, f"Date : {datetime.now().strftime('%d/%m/%Y')}")

    # Données CH4
    c.drawString(40, h - 110, f"Moyenne CH₄ : {mean_ch4:.2f} ppb")
    c.drawString(40, h - 130, f"Détections FIRMS : {n_fires}")

    # Analyse HSE
    c.drawString(40, h - 160, f"Niveau de risque HSE : {risk}")
    c.drawString(40, h - 180, f"Actions recommandées : {action}")
    c.drawString(40, h - 200, f"Conclusion : {conclusion}")

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, 40, "Rapport généré automatiquement via le dashboard HSE CH₄")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if st.button("📄 Générer le PDF HSE"):
    pdf_bytes = generate_pdf_bytes(
        mean_ch4 if not df_stats.empty else 0,
        n_fires,
        risk if not df_stats.empty else "N/A",
        action if not df_stats.empty else "N/A",
        conclusion if not df_stats.empty else "N/A"
    )
    st.download_button(
        label="Télécharger le rapport HSE PDF",
        data=pdf_bytes,
        file_name=f"Rapport_HSE_{site_name}.pdf",
        mime="application/pdf"
    )
