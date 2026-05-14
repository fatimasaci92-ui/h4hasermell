import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json

st.markdown("## 🗺️ GIS Map (Satellite + CSV Data Overlay)")

# ================= SAMPLE CSV (replace with your real df) =================
df = pd.DataFrame({
    "lat": [30.8, 25.2, 40.7, 51.5, 35.7],
    "lon": [50.5, 55.3, -74.0, -0.1, 139.7],
    "value": [120, 80, 300, 50, 200]
})

# Convert to JSON for JS
data_json = df.to_json(orient="records")

# ================= HTML MAP =================
html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
  body {{ margin:0; font-family:sans-serif; }}
  #map {{ height: 650px; width: 100%; }}
</style>
</head>

<body>

<div id="map"></div>

<script>

/* ================= MAP INIT ================= */
const map = L.map('map').setView([30.8, 50.5], 2);

/* ================= BASE LAYERS ================= */

// 🛣️ Street map
const street = L.tileLayer(
  'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{ attribution: '© OpenStreetMap' }}
);

// 🌍 Satellite (ESRI - BEST FREE)
const satellite = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{ attribution: '© ESRI Satellite' }}
);

/* default layer */
street.addTo(map);

/* ================= LAYER SWITCH ================= */
const baseMaps = {{
  "🛣️ Street": street,
  "🌍 Satellite": satellite
}};

const dataLayer = L.layerGroup().addTo(map);

L.control.layers(baseMaps).addTo(map);

/* ================= DATA FROM STREAMLIT ================= */
const data = {data_json};

/* ================= DRAW POINTS ================= */
data.forEach(p => {{

    const color =
        p.value > 200 ? "red" :
        p.value > 100 ? "orange" :
        "green";

    L.circleMarker([p.lat, p.lon], {{
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8
    }})
    .bindPopup(
        `<b>Value:</b> ${p.value}<br>
         <b>Lat:</b> ${p.lat}<br>
         <b>Lon:</b> ${p.lon}`
    )
    .addTo(dataLayer);

}});

</script>

</body>
</html>
"""

components.html(html_code, height=700, scrolling=True)
