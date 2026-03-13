import streamlit as st
import ee
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# -----------------------------
# INITIALISATION GOOGLE EARTH ENGINE
# -----------------------------
try:
    ee.Initialize()
except:
    ee.Authenticate()
    ee.Initialize()

# -----------------------------
# TITRE APPLICATION
# -----------------------------
st.title("Methane Monitoring Platform - Hassi R'Mel")

st.write("Analyse CH4 avec Google Earth Engine et Carbon Mapper")

# -----------------------------
# BOUTON ANALYSE
# -----------------------------
if st.button("Analyse d'aujourd'hui"):

    st.subheader("Concentration CH4 (Sentinel-5P)")

    # zone Hassi R'Mel
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
        maxPixels=1e9,
    )

    ch4_value = stats.getInfo()

    st.write("Valeur moyenne CH4 (ppb)")
    st.write(ch4_value)

# -----------------------------
# DONNEES CARBON MAPPER
# -----------------------------
    st.subheader("Fuites détectées (Carbon Mapper)")

    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"

    try:
        response = requests.get(url)
        data = response.json()

        plumes = pd.json_normalize(data["features"])

        coords = plumes["geometry.coordinates"]

        plumes["lon"] = coords.apply(lambda x: x[0])
        plumes["lat"] = coords.apply(lambda x: x[1])

        # filtrer Hassi R'Mel
        plumes_hrm = plumes[
            (plumes["lon"] > 3.0) &
            (plumes["lon"] < 3.9) &
            (plumes["lat"] > 32.7) &
            (plumes["lat"] < 33.3)
        ]

        if len(plumes_hrm) == 0:
            st.write("Aucune fuite détectée dans cette zone.")

        else:
            st.write("Fuites CH4 détectées :")
            st.dataframe(plumes_hrm[["lat","lon","properties.emission_rate"]])

        # -----------------------------
        # CARTE
        # -----------------------------

        st.subheader("Carte des fuites CH4")

        m = folium.Map(location=[33.0,3.3], zoom_start=8)

        for i,row in plumes_hrm.iterrows():

            folium.CircleMarker(
                location=[row["lat"],row["lon"]],
                radius=6,
                color="red",
                popup=f"Emission: {row['properties.emission_rate']} kg/h"
            ).add_to(m)

        st_folium(m,width=700,height=500)

    except:
        st.write("Erreur connexion Carbon Mapper")
