import streamlit as st
import os
import pandas as pd
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium

# =====================
# Variables site
# =====================
site_name = "MonSite"
latitude = 33.05   # exemple
longitude = 3.5    # exemple
altitude = 100     # exemple
csv_hist = "historique.csv"
csv_annual = "annual.csv"
csv_monthly = "monthly.csv"

# =====================
# Fonctions fictives (à remplacer par tes fonctions réelles)
# =====================
def get_latest_ch4_from_gee(lat, lon):
    # Exemple : retourner valeurs simulées
    return 1920, "2026-03-15", False

def generate_professional_pdf(site_name, date_img, ch4, action, altitude):
    from io import BytesIO
    pdf_buffer = BytesIO()
    pdf_buffer.write(b"PDF exemple")
    pdf_buffer.seek(0)
    return pdf_buffer

# =====================
# Initialisation session_state
# =====================
if "ch4_day" not in st.session_state:
    st.session_state.ch4_day = None
    st.session_state.date_img_day = None
    st.session_state.no_pass_today = False
    st.session_state.action_day = None

# =====================
# SECTION A : Données historiques
# =====================
st.markdown("## 📑 Section A — Données historiques")
if os.path.exists(csv_hist):
    df_hist = pd.read_csv(csv_hist)
    st.dataframe(df_hist.head(20))
else:
    st.warning("CSV historique introuvable")

# =====================
# SECTION B : Analyse CH₄ du jour
# =====================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE)")
if st.button("Analyser CH₄ du jour"):
    st.session_state.ch4_day, st.session_state.date_img_day, st.session_state.no_pass_today = get_latest_ch4_from_gee(latitude, longitude)
    if st.session_state.ch4_day is None:
        st.error("⚠️ Aucune image satellite disponible")
    else:
        if st.session_state.no_pass_today:
            st.warning(f"☁️ Pas de passage satellite aujourd’hui. Dernière image : {st.session_state.date_img_day}")
        st.success(f"CH₄ : **{st.session_state.ch4_day:.1f} ppb** (image du {st.session_state.date_img_day})")
        if st.session_state.ch4_day >= 1900:
            st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
            st.session_state.action_day = "Alerter, sécuriser la zone et stopper opérations"
        else:
            st.session_state.action_day = "Surveillance continue"

# Affichage permanent si analyse déjà faite
if st.session_state.ch4_day is not None:
    df_day = pd.DataFrame([{
        "Date image": st.session_state.date_img_day,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "Altitude (m)": altitude,
        "CH₄ (ppb)": round(st.session_state.ch4_day, 2),
        "Anomalie": "Oui" if st.session_state.ch4_day >= 1900 else "Non",
        "Action HSE": st.session_state.action_day
    }])
    st.table(df_day)

    # Carte avec cercle critique + zones
    st.subheader("🗺️ Carte du site avec zone critique CH₄ et zones")
    m = folium.Map(location=[latitude, longitude], zoom_start=9)

    # Cercle critique CH₄
    color_circle = "red" if st.session_state.ch4_day >= 1900 else "green"
    folium.Circle(
        location=[latitude, longitude],
        radius=3500,
        color=color_circle,
        fill=True,
        fill_opacity=0.4,
        tooltip=f"CH₄ : {st.session_state.ch4_day:.1f} ppb"
    ).add_to(m)

    # =====================
    # POLYGONES DES ZONES
    # =====================
    zone_centre_coords = [
        [32.75662617, 3.37696562],
        [32.75663435, 3.61159117],
        [33.01349055, 3.60634757],
        [33.02401464, 2.93385218],
        [32.89394392, 2.92757292],
        [32.88954646, 3.3769424],
        [32.75662617, 3.37696562]
    ]

    zone_sud_coords = [
        [32.45093128, 2.88567251],
        [32.45092697, 3.37963967],
        [32.88379946, 3.37964793],
        [32.88378899, 2.88561768],
        [32.45093128, 2.88567251]
    ]

    zone_nord_coords = [
        [33.01358581, 3.18513508],
        [33.28297225, 3.18482285],
        [33.27857017, 3.81093387],
        [33.01358819, 3.81077745],
        [33.01358581, 3.18513508]
    ]

    # Ajouter polygones
    folium.Polygon(zone_centre_coords, color="red", fill=True, fill_opacity=0.2, tooltip="Zone Centre").add_to(m)
    folium.Polygon(zone_sud_coords, color="green", fill=True, fill_opacity=0.2, tooltip="Zone Sud").add_to(m)
    folium.Polygon(zone_nord_coords, color="blue", fill=True, fill_opacity=0.2, tooltip="Zone Nord").add_to(m)

    # Ajouter labels au centre
    def add_label(coords, label, color):
        lat_center = sum([c[0] for c in coords]) / len(coords)
        lon_center = sum([c[1] for c in coords]) / len(coords)
        folium.Marker([lat_center, lon_center], tooltip=label, icon=folium.Icon(color=color)).add_to(m)

    add_label(zone_centre_coords, "Centre", "red")
    add_label(zone_sud_coords, "Sud", "green")
    add_label(zone_nord_coords, "Nord", "blue")

    st_folium(m, width=800, height=500)

    # PDF
    st.subheader("📄 Générer PDF Professionnel")
    pdf_buffer = generate_professional_pdf(site_name, st.session_state.date_img_day, st.session_state.ch4_day, st.session_state.action_day, altitude)
    st.download_button(
        "⬇️ Télécharger le PDF Professionnel",
        pdf_buffer,
        f"Rapport_HSE_CH4_{site_name}_{st.session_state.date_img_day}.pdf",
        "application/pdf"
    )

# =====================
# SECTION C : Graphiques temporels
# =====================
st.markdown("## 📊 Graphiques temporels 2020–2025")
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
    df_m[df_m.columns[0]] = pd.to_datetime(df_m[df_m.columns[0]])
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(df_m[df_m.columns[0]], df_m[df_m.columns[1]], marker="o")
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
