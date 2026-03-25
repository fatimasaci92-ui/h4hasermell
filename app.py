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
        action = "Arrêt + alerte HSE"
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
        action = "Alerter, sécuriser la zone et stopper opérations"
    elif ch4 >= 1850:
        risk = "Élevé"
        action = "Inspection urgente"
        st.warning("⚠️ Niveau CH₄ élevé")
    else:
        st.success("CH₄ normal")
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

    if ch4 >= 1850:  # seuil à partir duquel on vérifie les plumes
        plumes = get_ch4_plumes_carbonmapper(latitude, longitude)
        if len(plumes) > 0:
            st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
            for plume in plumes:
                st.write(f"- Emission {plume['emission']} kg/h à ({plume['lat']:.4f}, {plume['lon']:.4f})")
        else:
            st.success("✅ Aucune fuite détectée par Carbon Mapper")
    else:
        st.info("Niveau CH₄ normal → pas de vérification Carbon Mapper nécessaire")
# ================= ANALYSE CARBON MAPPER =================

plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

try:
    plumes = get_ch4_plumes_carbonmapper(latitude, longitude)
    if len(plumes) > 0:
        st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
    else:
        st.success("✅ Aucune fuite détectée par Carbon Mapper")
except Exception as e:
    st.warning("⚠️ Carbon Mapper indisponible ou token invalide")
    st.info("L’analyse continue avec GEE et données locales")
    plumes = []
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

plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

for plume in plumes:
    folium.CircleMarker(
        location=[plume["lat"], plume["lon"]],
        radius=7,
        color="purple",
        fill=True,
        fill_color="purple",
        fill_opacity=0.9,
        tooltip=f"Plume CH4: {plume['emission']} kg/h"
    ).add_to(m)
    # Marker du site principal
    site_name = "Hassi R'mel"
    folium.Marker([latitude, longitude],
                  tooltip=f"Analyse CH₄ – {site_name}",
                  icon=folium.Icon(color="black", icon="info-sign")).add_to(m)

    folium.LayerControl().add_to(m)
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
