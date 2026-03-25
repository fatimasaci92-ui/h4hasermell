# ================= app.py — VERSION COMPLÈTE FINALE + CARTE STABLE =================
import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium
import requests
# ================= INITIALISATION GOOGLE EARTH ENGINE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()
# ================= CARBON MEPPER API =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")
if not CARBON_API_TOKEN:
    st.error("❌ Token Carbon Mapper manquant dans secrets.toml")
# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= CHEMINS DES FICHIERS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"
csv_monthly = "data/2020 2024/CH4_HassiRmel_monthly_2020_2024.csv"

# ================= FONCTION GEE =================
def get_latest_ch4_from_gee(latitude, longitude, days_back=60):
    point = ee.Geometry.Point([longitude, latitude])
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(point)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )
    size = collection.size().getInfo()
    if size == 0:
        return None, None, True
    images = collection.toList(size)
    for i in range(size):
        img = ee.Image(images.get(i))
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        value = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=7000, maxPixels=1e9).get("CH4_column_volume_mixing_ratio_dry_air")
        try:
            v = value.getInfo()
        except:
            v = None
        if v is None:
            continue
        ch4_ppb = float(v) * 1000
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today
        return ch4_ppb, date_img, no_pass_today
    return None, None, True

# ================= SECTION A : Contenu des dossiers =================
st.markdown("## 📁 Section A — Contenu des données")
if st.button("Afficher les dossiers de données"):
    if os.path.exists(DATA_DIR):
        for root, dirs, files in os.walk(DATA_DIR):
            st.write("📂", root)
            for f in files:
                st.write(" └─", f)
    else:
        st.warning("Dossier data introuvable")

# ================= SECTION B : Aperçu CSV =================
st.markdown("## 📑 Section B — Aperçu des données historiques")
if st.button("Afficher CSV historique"):
    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)
        st.dataframe(df_hist.head(20))
    else:
        st.warning("CSV historique introuvable")

# ================= SECTION C : Carte CH₄ moyenne =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")
year_mean = st.selectbox("Choisir l'année pour la carte", [2020, 2021, 2022, 2023, 2024, 2025])
if st.button("Afficher carte CH₄ moyenne"):
    mean_path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"
    if os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(img, cmap="viridis")
        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.warning("Carte CH₄ introuvable")

# ================= SECTION D : Analyse HSE annuelle =================
st.markdown("## 🔎 Section D — Analyse HSE annuelle")
year = st.selectbox("Choisir l'année pour analyse HSE", [2020, 2021, 2022, 2023, 2024, 2025])
if st.button("Analyser année sélectionnée"):
    if os.path.exists(csv_annual):
        df_year = pd.read_csv(csv_annual)
        if year in df_year["year"].values:
            val = df_year[df_year["year"] == year]["CH4_mean"].values[0]
            if val >= 1900:
                risk = "Critique"
                action = "Arrêt + alerte HSE"
            elif val >= 1850:
                risk = "Élevé"
                action = "Inspection urgente"
            else:
                risk = "Normal"
                action = "Surveillance continue"
            st.success(f"CH₄ moyen {year} : {val:.1f} ppb")
            st.write("Risque :", risk)
            st.write("Action :", action)
        else:
            st.warning("Année non trouvée")
    else:
        st.warning("CSV annuel introuvable")

# ================= SECTION E : Analyse CH₄ du jour =================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE)")

if st.button("Analyser CH₄ du jour"):
    st.info("Analyse en cours...")
    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible sur la période analysée.")
        st.stop()

    # Vérifier passage satellite
    if no_pass_today:
        st.error("☁️ Pas de passage satellite valide aujourd’hui (nuages ou orbite)")
        st.warning(f"➡️ Dernière image disponible sur GEE : **{date_img}**")

    st.success(f"CH₄ : **{ch4:.1f} ppb** (image du {date_img})")

    # Définir niveau de risque HSE
    if ch4 >= 1900:
        risk = "Critique"
        action = "Alerter, sécuriser la zone et stopper opérations"
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4 >= 1850:
        risk = "Élevé"
        action = "Inspection urgente"
        st.warning("⚠️ Niveau CH₄ élevé")
    else:
        risk = "Normal"
        action = "Surveillance continue"
        st.success("CH₄ normal")

    # Affichage tableau résumé
    df_day = pd.DataFrame([{
        "Date image": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ (ppb)": round(ch4, 2),
        "Anomalie": "Oui" if ch4 >= 1900 else "Non",
        "Risque": risk,
        "Action HSE": action
    }])
    st.table(df_day)

    # =================== Vérification fuite automatique ===================
    st.markdown("### 🔎 Vérification fuite Carbon Mapper automatique")
    if ch4 >= 1850:
        plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

        if len(plumes) > 0:
            st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
            for plume in plumes:
                st.write(f"- Emission {plume['emission']} kg/h à ({plume['lat']:.4f}, {plume['lon']:.4f})")
        else:
            st.success("✅ Aucune fuite détectée par Carbon Mapper")
# ================= ANALYSE CARBON MAPPER =================

def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"

    headers = {
        "Authorization": f"Bearer {CARBON_API_TOKEN}"
    }

    # 🔥 Ajout du filtre géographique (bbox ±0.5° autour du site)
    params = {
        "gas": "CH4",
        "limit": 20,
        "bbox": f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code == 401:
            st.error("❌ Token Carbon Mapper invalide")
            return []

        if response.status_code != 200:
            st.warning(f"⚠️ API erreur: {response.status_code}")
            return []

        data = response.json()
        plumes = []

        for item in data.get("features", []):
            coords = item["geometry"]["coordinates"]
            props = item["properties"]

            plumes.append({
                "lat": coords[1],
                "lon": coords[0],
                "emission": props.get("emission_rate", 0)
            })

        return plumes

    except Exception as e:
        st.error(f"Erreur Carbon Mapper : {e}")
        return []
# ================= SECTION F : PDF Professionnel =================
def generate_professional_pdf(site_name, date_img, ch4_value, action, responsable="HSE Manager"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Rapport Professionnel HSE – Surveillance CH₄</b>", styles["Title"]))
    story.append(Spacer(1,12))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(f"<b>Site :</b> {site_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date du rapport :</b> {now}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date image satellite :</b> {date_img}", styles["Normal"]))
    story.append(Paragraph(f"<b>Responsable action :</b> {responsable}", styles["Normal"]))
    story.append(Spacer(1,12))
    story.append(Paragraph(
        "Ce rapport présente la surveillance du méthane (CH₄) sur le site, "
        "les valeurs mesurées, et les actions correctives recommandées. "
        "Les seuils HSE sont : Élevé ≥1850 ppb, Critique ≥1900 ppb. "
        "Le suivi quotidien permet de détecter rapidement toute anomalie et de sécuriser le site.",
        styles["Normal"]
    ))
    story.append(Spacer(1,12))

    data_table = [
        ["Paramètre", "Valeur"],
        ["CH₄ mesuré (ppb)", f"{ch4_value:.1f}"],
        ["Anomalie détectée", "Oui" if ch4_value >= 1900 else "Non"],
        ["Action corrective", action]
    ]
    t = Table(data_table, hAlign="LEFT", colWidths=[200,250])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,0),12),
        ('BOTTOMPADDING',(0,0),(-1,0),6),
        ('BACKGROUND',(0,1),(-1,-1),colors.lightblue),
        ('GRID',(0,0),(-1,-1),1,colors.black),
    ]))
    story.append(t)
    story.append(Spacer(1,12))

    doc.build(story)
    buffer.seek(0)
    return buffer

st.markdown("## 📄 Télécharger PDF Professionnel")
if st.button("Générer PDF Professionnel"):
    if "ch4" not in locals():
        st.warning("Lancez d'abord l'analyse du jour pour générer le PDF")
    else:
        pdf_buffer = generate_professional_pdf(site_name, date_img, ch4, action)
        st.download_button(
            "⬇️ Télécharger le PDF Professionnel",
            pdf_buffer,
            f"Rapport_HSE_CH4_{site_name}_{date_img}.pdf",
            "application/pdf"
        )

# ================= SECTION G : Graphiques temporels =================
st.markdown("## 📊 Graphiques temporels 2020–2025")
if st.button("Afficher graphiques CH₄"):
    if os.path.exists(csv_annual):
        df_a = pd.read_csv(csv_annual)
        fig, ax = plt.subplots(figsize=(8,4))
        ax.plot(df_a["year"], df_a["CH4_mean"], marker="o")
        ax.axhline(1850, linestyle="--", color="orange", label="Seuil HSE élevé")
        ax.axhline(1900, linestyle="--", color="red", label="Seuil HSE critique")
        ax.set_title("CH₄ annuel moyen")
        ax.set_xlabel("Année")
        ax.set_ylabel("CH₄ (ppb)")
        ax.legend()
        st.pyplot(fig)
    else:
        st.warning("CSV annuel introuvable")
    if os.path.exists(csv_monthly):
        df_m = pd.read_csv(csv_monthly)
        date_col = df_m.columns[0]
        ch4_col = df_m.columns[1]
        df_m[date_col] = pd.to_datetime(df_m[date_col])
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(df_m[date_col], df_m[ch4_col], marker="o")
        ax.axhline(1850, linestyle="--", color="orange", label="Seuil HSE élevé")
        ax.axhline(1900, linestyle="--", color="red", label="Seuil HSE critique")
        ax.set_title("CH₄ mensuel moyen")
        ax.set_xlabel("Date")
        ax.set_ylabel("CH₄ (ppb)")
        ax.legend()
        plt.xticks(rotation=45)
        st.pyplot(fig)
    else:
        st.warning("CSV mensuel introuvable")

# ================= SECTION H : Carte interactive stable =================
import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import pandas as pd
import os

st.markdown("## 🗺️ Carte interactive stable – Tous les sites Oil & Gas")

# Sélection zone
zone_select = st.selectbox("Sélectionner une zone", ["Toutes", "Centre", "Nord", "Sud"])

# Charger CSV historique une seule fois
if "df_all_sites" not in st.session_state:
    csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
    if os.path.exists(csv_hist):
        st.session_state.df_all_sites = pd.read_csv(csv_hist)
    else:
        st.session_state.df_all_sites = pd.DataFrame(columns=["Latitude","Longitude","Site"])

# Définir polygones zones (global)
zones = {
    "Centre": [[32.75662617,3.37696562],[32.75663435,3.61159117],[33.01349055,3.60634757],
               [33.02401464,2.93385218],[32.89394392,2.92757292],[32.88954646,3.3769424],[32.75662617,3.37696562]],
    "Sud": [[32.45093128,2.88567251],[32.45092697,3.37963967],[32.88379946,3.37964793],
            [32.88378899,2.88561768],[32.45093128,2.88567251]],
    "Nord": [[33.01358581,3.18513508],[33.28297225,3.18482285],[33.27857017,3.81093387],
             [33.01358819,3.81077745],[33.01358581,3.18513508]]
}
colors = {"Centre":"red","Sud":"green","Nord":"blue"}

# Créer la carte qu'une seule fois
if "folium_map" not in st.session_state:
    # Carte de base
    latitude, longitude = 32.93, 3.30
    m = folium.Map(location=[latitude, longitude], zoom_start=8, tiles="CartoDB Positron")

    # Ajouter tous les sites Oil & Gas
    for _, r in st.session_state.df_all_sites.iterrows():
        try:
            folium.CircleMarker(
                location=[r["Latitude"], r["Longitude"]],
                radius=5,
                color="darkred",
                fill=True,
                fill_opacity=0.8,
                tooltip=r.get("Site","Site Oil & Gas")
            ).add_to(m)
        except:
            pass

    # Ajouter polygones zones
    for z_name, coords in zones.items():
        folium.Polygon(coords, color=colors[z_name], fill=True, fill_opacity=0.2, tooltip=f"Zone {z_name}").add_to(m)
# ================= AJOUT PLUMES CARBON MAPPER =================

if "plumes" in locals():
    pass
else:
    plumes = []

# Ajouter plumes
for plume in plumes:
    folium.CircleMarker(
        location=[plume["lat"], plume["lon"]],
        radius=7,
        color="purple",
        fill=True,
        fill_opacity=0.9,
        tooltip=f"Plume CH4: {plume['emission']} kg/h"
    ).add_to(m)

# Marker du site UNE SEULE FOIS
folium.Marker(
    [latitude, longitude],
    tooltip=f"Analyse CH₄ – {site_name}",
    icon=folium.Icon(color="black")
).add_to(m)

# Marker du site principal
site_name = "Hassi R'mel"
    # Ajouter plumes
for plume in plumes:
    folium.CircleMarker(
        location=[plume["lat"], plume["lon"]],
        radius=7,
        color="purple",
        fill=True,
        fill_opacity=0.9,
        tooltip=f"Plume CH4: {plume['emission']} kg/h"
    ).add_to(m)

# Marker du site UNE SEULE FOIS
folium.Marker(
    [latitude, longitude],
    tooltip=f"Analyse CH₄ – {site_name}",
    icon=folium.Icon(color="black")
).add_to(m)

# Contrôle des couches
folium.LayerControl().add_to(m)

# Sauvegarde carte
st.session_state.folium_map = m
# Récupérer la carte
# Récupérer ou créer la carte
m_to_show = st.session_state.get("folium_map", None)

if m_to_show is None:
    latitude, longitude = 32.93, 3.30
    m_to_show = folium.Map(location=[latitude, longitude], zoom_start=8, tiles="CartoDB Positron")

    # Ajouter tous les sites Oil & Gas
    for _, r in st.session_state.df_all_sites.iterrows():
        try:
            folium.CircleMarker(
                location=[r["Latitude"], r["Longitude"]],
                radius=5,
                color="darkred",
                fill=True,
                fill_opacity=0.8,
                tooltip=r.get("Site", "Site Oil & Gas")
            ).add_to(m_to_show)
        except:
            pass

    # Ajouter polygones zones
    for z_name, coords in zones.items():
        folium.Polygon(coords, color=colors[z_name], fill=True, fill_opacity=0.2, tooltip=f"Zone {z_name}").add_to(m_to_show)

    st.session_state.folium_map = m_to_show

# Recentrer selon la zone sélectionnée
if zone_select != "Toutes":
    z_coords = zones[zone_select]
    lat_center = np.mean([c[0] for c in z_coords])
    lon_center = np.mean([c[1] for c in z_coords])
    m_to_show.location = [lat_center, lon_center]
    m_to_show.zoom_start = 10

# Afficher carte **une seule fois**, stable
st_folium(m_to_show, width=900, height=550)

# ================= SECTION I : Agent IA =================
st.markdown("## 🤖 Agent IA – Posez vos questions")
user_question = st.text_input("Posez votre question sur le CH₄ ou HSE")
if st.button("Obtenir réponse IA"):
    if user_question.strip() != "":
        if "niveau" in user_question.lower():
            st.info("Le niveau de CH₄ est affiché dans les sections Analyse du jour et Graphiques temporels.")
        elif "risque" in user_question.lower():
            st.info("Les seuils HSE sont : Élevé ≥1850 ppb, Critique ≥1900 ppb.")
        else:
            st.info("Votre question sera analysée dans la prochaine version IA intelligente.")
    else:
        st.warning("Veuillez poser une question")
