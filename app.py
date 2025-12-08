import streamlit as st
import ee
from datetime import datetime
import pandas as pd

# ------------------ CONFIG ------------------

st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

# ------------------ INITIALISATION EE ------------------

service_account = "[gee-access@methane-ai-hse.iam.gserviceaccount.com](mailto:gee-access@methane-ai-hse.iam.gserviceaccount.com)"
key_file = "methane-ai-hse-a85cc13c510a.json"

credentials = ee.ServiceAccountCredentials(service_account, key_file)
ee.Initialize(credentials)

# ------------------ SITE ------------------

latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = ee.Geometry.Point([longitude, latitude])

# ------------------ UTIL ------------------

def fetch_last_ch4(site_geom):
"""Récupère la dernière valeur TROPOMI CH₄ disponible pour le site."""
import ee

```
dataset = ee.ImageCollection("COPERNICUS/S5P/NRTI/L3_CH4") \
    .filterBounds(site_geom) \
    .sort("system:time_start", False)  # tri décroissant = dernière image

latest_img = dataset.first()
if latest_img is None:
    return None, None

ch4_value = latest_img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=site_geom,
    scale=1000
).get("CH4_column_volume_mixing_ratio_dry_air")

try:
    val = ch4_value.getInfo()
    date = ee.Date(latest_img.get("system:time_start")).format("yyyy-MM-dd").getInfo()
    return val, date
except:
    return None, None
```

def hazop_analysis(ch4_value):
data = []
if ch4_value < 1800:
data.append(["CH₄","Normal","Pas d’anomalie","Fonctionnement normal","Surveillance continue"])
elif ch4_value < 1850:
data.append(["CH₄","Modérément élevé","Torchage possible","Risque faible d’incident","Vérifier torches et informer l'équipe HSE"])
elif ch4_value < 1900:
data.append(["CH₄","Élevé","Fuite probable","Risque d’explosion accru","Inspection urgente"])
else:
data.append(["CH₄","Critique","Fuite majeure","Risque critique","Alerter direction, sécuriser zone, stopper les opérations"])
return pd.DataFrame(data, columns=["Paramètre","Déviation","Cause","Conséquence","Action HSE"])

# ------------------ ANALYSE ------------------

if st.button("Analyser aujourd'hui / dernière donnée disponible"):
ch4, ch4_date = fetch_last_ch4(site_geom)
if ch4 is None:
st.error("⚠️ Pas de donnée CH₄ disponible pour cette zone.")
else:
st.success(f"CH₄ du jour ou dernière donnée : {ch4:.2f} ppb ({ch4_date})")
threshold = 1900.0
if ch4 > threshold:
st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
action_hse = "Alerter, sécuriser la zone et stopper opérations"
elif ch4 > threshold - 50:
st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
action_hse = "Surveillance renforcée et vérification des torches"
else:
st.success("CH₄ normal, aucune anomalie détectée.")
action_hse = "Surveillance continue"

```
    st.markdown("### Tableau HAZOP")
    st.table(hazop_analysis(ch4))

    # ------------------ PDF ------------------
    st.markdown("**Pour générer le PDF, nous pourrons utiliser la fonction ReportLab**")
    st.info("PDF utilisera automatiquement CH₄ = {:.2f}, date = {}".format(ch4, ch4_date))
```
