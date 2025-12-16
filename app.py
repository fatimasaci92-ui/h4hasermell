import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium

# ================= INITIALISATION GOOGLE EARTH ENGINE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"],
        key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

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

        value = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point,
            scale=7000,
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

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
DATA_DIR = "data"
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
csv_path = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
if st.button("Afficher CSV historique"):
    if os.path.exists(csv_path):
        df_hist = pd.read_csv(csv_path)
        st.dataframe(df_hist.head(20))
    else:
        st.warning("CSV historique introuvable")

# ================= SECTION C : Cartes CH₄ =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")
year = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])
mean_path = f"data/Moyenne CH4/CH4_mean_{year}.tif"
if st.button("Afficher carte CH₄"):
    if os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(img, cmap="viridis")
        ax.set_title(f"CH₄ moyen {year}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.warning("Carte CH₄ introuvable")

# ================= SECTION D : Analyse HSE annuelle =================
st.markdown("## 🔎 Section D — Analyse HSE annuelle")
csv_annual = "data/2020 2024/CH4_annual_2020_2025.csv"
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

# ================= ANALYSE DU JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour (Google Earth Engine)")
if st.button("Analyser CH₄ du jour"):
    st.session_state.ch4 = None
    st.session_state.date_img = None
    st.session_state.risk = None
    st.session_state.action = None

    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.warning("ℹ️ Aucun passage satellite exploitable sur la période analysée")
    else:
        st.session_state.ch4 = ch4
        st.session_state.date_img = date_img

        if no_pass_today:
            st.info(
                f"☁️ Aucun passage satellite valide aujourd’hui (nuages ou orbite)\n\n"
                f"📅 Dernière image disponible : {date_img}"
            )

        if ch4 >= 1900:
            risk = "Critique"
            action = "Arrêt immédiat des opérations et alerte HSE"
            st.error(f"⚠️ Niveau CRITIQUE — {ch4:.1f} ppb")
        elif ch4 >= 1850:
            risk = "Élevé"
            action = "Inspection HSE urgente"
            st.warning(f"⚠️ Niveau ÉLEVÉ — {ch4:.1f} ppb")
        else:
            risk = "Normal"
            action = "Surveillance continue"
            st.success(f"✅ Niveau NORMAL — {ch4:.1f} ppb")

        st.session_state.risk = risk
        st.session_state.action = action

        st.table(pd.DataFrame([{
            "Site": site_name,
            "Date image": date_img,
            "CH₄ (ppb)": round(ch4,2),
            "Risque HSE": risk,
            "Action recommandée": action
        }]))

# ================= PDF HSE =================
st.markdown("## 📄 Rapport HSE professionnel (PDF du jour)")
if st.button("Générer le rapport PDF du jour"):
    if st.session_state.ch4 is None:
        st.warning("Veuillez d'abord lancer l'analyse CH₄ du jour")
    else:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        # Page de garde avec logo
        if os.path.exists("logo.png"):
            story.append(Image("logo.png", width=140, height=60))
            story.append(Spacer(1,20))

        story.append(Paragraph("<b>RAPPORT HSE – SURVEILLANCE DU MÉTHANE (CH₄)</b>", styles["Title"]))
        story.append(Spacer(1,20))
        story.append(Paragraph(f"<b>Site surveillé :</b> {site_name}", styles["Normal"]))
        story.append(Paragraph(f"<b>Coordonnées :</b> {latitude}, {longitude}", styles["Normal"]))
        story.append(Paragraph(f"<b>Date de l'image satellite :</b> {st.session_state.date_img}", styles["Normal"]))
        story.append(Spacer(1,15))

        # Tableau HSE
        table = Table([
            ["Paramètre","Valeur"],
            ["Concentration CH₄", f"{st.session_state.ch4:.1f} ppb"],
            ["Niveau de risque HSE", st.session_state.risk],
            ["Action recommandée", st.session_state.action]
        ], colWidths=[200,250])
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),1,colors.black),
            ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
            ('BACKGROUND',(0,1),(0,-1),colors.whitesmoke)
        ]))
        story.append(table)
        story.append(Spacer(1,20))

        # Analyse HSE
        story.append(Paragraph("<b>Analyse HSE :</b>", styles["Heading2"]))
        story.append(Paragraph(
            "L'analyse des données satellitaires Sentinel-5P indique le niveau de concentration du méthane (CH₄) "
            "au-dessus du site surveillé. Cette information permet d'évaluer le risque environnemental et opérationnel "
            "lié aux émissions fugitives de gaz.", styles["Normal"]))
        story.append(Spacer(1,10))

        story.append(Paragraph("<b>Seuils de référence HSE :</b>", styles["Heading2"]))
        story.append(Paragraph(
            "• Normal : CH₄ < 1850 ppb<br/>"
            "• Élevé : 1850 ≤ CH₄ < 1900 ppb<br/>"
            "• Critique : CH₄ ≥ 1900 ppb",
            styles["Normal"]))
        story.append(Spacer(1,20))
        story.append(Paragraph(
            f"<b>Conclusion :</b> Le niveau de CH₄ mesuré est classé <b>{st.session_state.risk}</b>. "
            f"L'action HSE recommandée est : <b>{st.session_state.action}</b>.",
            styles["Normal"]))
        story.append(Spacer(1,30))
        story.append(Paragraph(
            f"Rapport généré automatiquement le {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            styles["Italic"]))

        doc.build(story)
        st.download_button(
            "⬇️ Télécharger le rapport PDF",
            buffer.getvalue(),
            f"Rapport_HSE_CH4_{site_name}_{st.session_state.date_img}.pdf",
            "application/pdf"
        )

# ================= GRAPHES TEMPORELS =================
st.markdown("## 📊 Évolution temporelle du CH₄ (2020–2025)")

csv_annual = "data/2020 2024/CH4_annual_2020_2024.csv"
csv_monthly = "data/2020 2024/CH4_HassiRmel_monthly_2020_2024.csv"

# Graphique annuel
if os.path.exists(csv_annual):
    df_a = pd.read_csv(csv_annual)
    fig, ax = plt.subplots()
    ax.plot(df_a["year"], df_a["CH4_mean"])
    ax.axhline(1850, linestyle="--", color="orange")
    ax.axhline(1900, linestyle="--", color="red")
    ax.set_title("CH₄ annuel moyen")
    ax.set_xlabel("Année")
    ax.set_ylabel("CH₄ (ppb)")
    st.pyplot(fig)
else:
    st.warning("CSV annuel introuvable")

# Graphique mensuel
if os.path.exists(csv_monthly):
    df_m = pd.read_csv(csv_monthly)
    st.write("Colonnes CSV mensuel :", df_m.columns)  # <-- Pour vérifier le nom exact
    # Remplace "CH4_mean" par le nom exact affiché
    ax = df_m.plot(x="date", y="CH4_mean", title="CH₄ mensuel")  # <-- Corrige le nom ici
    st.pyplot(ax.figure)
else:
    st.warning("CSV mensuel introuvable")


# ================= CARTE INTERACTIVE =================
st.markdown("## 🗺️ Carte interactive du site")
m = folium.Map(location=[latitude, longitude], zoom_start=7)
color = 'green'
if st.session_state.risk == 'Élevé': color = 'orange'
if st.session_state.risk == 'Critique': color = 'red'
folium.CircleMarker(
    location=[latitude, longitude],
    radius=10,
    color=color,
    fill=True,
    fill_color=color,
    popup=f"{site_name}<br>CH₄: {st.session_state.ch4} ppb<br>Risque: {st.session_state.risk}"
).add_to(m)
st_folium(m, width=700, height=450)

# ================= AGENT IA =================
st.markdown("## 🤖 Agent IA HSE intelligent")
question = st.chat_input("Posez une question libre sur le CH₄, le risque HSE ou les tendances")
if question:
    ch4 = st.session_state.ch4
    risk = st.session_state.risk
    action = st.session_state.action
    if ch4 is None:
        response = "Veuillez d'abord lancer l'analyse CH₄ du jour."
    elif "pourquoi" in question.lower():
        response = f"Le niveau de CH₄ ({ch4:.1f} ppb) est classé {risk} selon les seuils HSE. Cela peut indiquer des émissions fugitives ou une activité anormale."
    elif "danger" in question.lower():
        response = "Le méthane est un gaz inflammable. À forte concentration, il augmente les risques d'explosion et d'impact environnemental."
    elif "tendance" in question.lower():
        response = "Les graphiques montrent l'évolution du CH₄ entre 2020 et 2025, permettant d'identifier une augmentation ou une stabilisation des émissions."
    elif "que faire" in question.lower() or "action" in question.lower():
        response = f"Action recommandée : {action}. Cette décision est basée sur le niveau de risque {risk}."
    else:
        response = f"CH₄ actuel : {ch4:.1f} ppb | Risque : {risk} | Action : {action}."
    st.chat_message("assistant").write(response)

# ================= FIN =================
