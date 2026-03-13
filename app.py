import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import ee

# -----------------------------
# INITIALISATION EARTH ENGINE
# -----------------------------
ee_available = True

try:
    ee.Initialize()
except Exception:
    ee_available = False

# -----------------------------
# TITRE
# -----------------------------
st.title("Methane Monitoring Platform - Hassi R'Mel")

st.write("Analyse CH4 combinant Google Earth Engine et Carbon Mapper")

# -----------------------------
# BOUTON ANALYSE
# -----------------------------
if st.button("Analyse d'aujourd'hui"):

    # -----------------------------
    # PARTIE CH4 (EARTH ENGINE)
    # -----------------------------
    st.subheader("Concentration CH4 (Satellite)")

    if ee_available:

        try:

            region = ee.Geometry.Rectangle([3.0, 32.7, 3.9, 33.3])

            dataset = (
                ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                .filterBounds(region)
                .filterDate("2024-01-01", "2024-12-31")
            )

            image = dataset.mean()

            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=region,
                scale=7000,
                maxPixels=1e9
            )

            ch4 = stats.getInfo()

            st.success("Valeur moyenne CH4 (ppb)")
            st.write(ch4)

        except Exception as e:
            st.warning("Impossible de récupérer les données CH4.")
            st.write(e)

    else:
        st.warning("Google Earth Engine non connecté.")

    # -----------------------------
    # PARTIE CARBON MAPPER
    # -----------------------------
    st.subheader("Fuites détectées (Carbon Mapper)")

    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"

    try:

        response = requests.get(url, timeout=10)
        data = response.json()

        plumes = pd.json_normalize(data["features"])

        coords = plumes["geometry.coordinates"]

        plumes["lon"] = coords.apply(lambda x: x[0])
        plumes["lat"] = coords.apply(lambda x: x[1])

        # filtrage zone Hassi R'Mel
        plumes_hrm = plumes[
            (plumes["lon"] > 3.0) &
            (plumes["lon"] < 3.9) &
            (plumes["lat"] > 32.7) &
            (plumes["lat"] < 33.3)
        ]

        if len(plumes_hrm) == 0:

            st.info("Aucune fuite détectée dans cette zone.")

        else:

            st.write("Fuites CH4 détectées :")

            st.dataframe(
                plumes_hrm[["lat", "lon", "properties.emission_rate"]]
            )

        # -----------------------------
        # CARTE
        # -----------------------------
        st.subheader("Carte des fuites")

        m = folium.Map(location=[33.0, 3.3], zoom_start=8)

        for i, row in plumes_hrm.iterrows():

            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=6,
                color="red",
                fill=True,
                popup=f"Emission: {row['properties.emission_rate']} kg/h"
            ).add_to(m)

        st_folium(m, width=700, height=500)

    except Exception as e:

        st.warning("Erreur connexion Carbon Mapper")
        st.write(e)
