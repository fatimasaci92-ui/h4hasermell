import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="Surveillance CH₄ – Multi-sites", layout="wide")

st.title("Surveillance du Méthane – Multi-sites")
st.markdown("## Dashboard automatique CH₄ + FIRMS")

# ------------------------
# Choix de la localisation
# ------------------------
DATA_DIR = "data"

# Lister automatiquement les sites disponibles à partir des fichiers CSV
sites = []
for f in os.listdir(DATA_DIR):
    if f.startswith("CH4_Stats_") and f.endswith(".csv"):
        site_name = f.replace("CH4_Stats_", "").replace(".csv", "").replace("_", " ")
        sites.append(site_name)

if not sites:
    st.error("❌ Aucun site disponible dans le dossier data/")
    st.stop()

site = st.selectbox("Choisissez le site :", sites)

# ------------------------
# Construire les chemins fichiers automatiquement
# ------------------------
tif_path = os.path.join(DATA_DIR, f"CH4_2023_{site.replace(' ', '_')}.tif")
stats_csv = os.path.join(DATA_DIR, f"CH4_Stats_{site.replace(' ', '_')}.csv")
firms_csv = os.path.join(DATA_DIR, f"FIRMS_{site.replace(' ', '_')}_2023.csv")

# ------------------------
# Vérifier l'existence des fichiers
# ------------------------
for f in [tif_path, stats_csv, firms_csv]:
    if not os.path.exists(f):
        st.warning(f"❌ Fichier introuvable : {f}")

# ------------------------
# Charger les données
# ------------------------
df_stats = pd.read_csv(stats_csv) if os.path.exists(stats_csv) else pd.DataFrame()
df_firms = pd.read_csv(firms_csv) if os.path.exists(firms_csv) else pd.DataFrame()

# ------------------------
# Affichage des tableaux
# ------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader(f"Statistiques CH₄ – {site}")
    st.dataframe(df_stats.head(15))

with col2:
    st.subheader(f"Détections FIRMS (Torchage) – {site}")
    st.dataframe(df_firms.head(15))

# ------------------------
# Carte CH₄
# ------------------------
st.markdown(f"## Carte CH₄ – {site}")

if os.path.exists(tif_path):
    with rasterio.open(tif_path) as src:
        arr = src.read(1)
    arr[arr <= 0] = np.nan

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.imshow(arr, cmap='viridis')
    ax.axis('off')
    st.pyplot(fig)
else:
    st.warning(f"❌ Fichier TIFF introuvable pour {site}")

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

def generate_pdf_bytes(site, mean_ch4, n_fires):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 60, f"Rapport CH₄ – {site}")

    c.setFont("Helvetica", 10)
    c.drawString(40, h - 90, f"Moyenne CH₄ : {mean_ch4:.2f} ppb")
    c.drawString(40, h - 110, f"FIRMS détectés : {n_fires}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

if st.button("📄 Générer le PDF"):
    pdf_bytes = generate_pdf_bytes(site, mean_ch4 if mean_ch4 else 0, n_fires)
    st.download_button(
        label="Télécharger le rapport PDF",
        data=pdf_bytes,
        file_name=f"Rapport_CH4_{site.replace(' ', '_')}.pdf",
        mime="application/pdf"
    )
