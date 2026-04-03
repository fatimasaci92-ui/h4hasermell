# ================= app.py — VERSION FINALE AVEC IA LÉGÈRE =================

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image
from reportlab.lib.units import inch
import matplotlib.pyplot as plt 
# ================= INIT GEE =================
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

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= IA LÉGÈRE (SANS TORCH) =================
def detect_ch4_anomaly(image_array):
    """IA simplifiée par seuils, compatible Streamlit Cloud"""
    val = np.nanmean(image_array)
    if np.isnan(val):
        return "❌ Pas de données", 0.0
    elif val > 1920:
        return "🔥 Fuite critique", 1.0
    elif val > 1880:
        return "⚠️ Suspect", 0.7
    else:
        return "✅ Normal", 0.1

# ================= ZONES FIXES =================
zoneCentre = ee.Geometry.Polygon([
  [3.37696562, 32.75662617],
  [3.61159117, 32.75663435],
  [3.60634757, 33.01349055],
  [2.93385218, 33.02401464],
  [2.92757292, 32.89394392],
  [3.3769424, 32.88954646],
  [3.37696562, 32.75662617]
])

zoneSud = ee.Geometry.Polygon([
  [2.88567251, 32.45093128],
  [3.37963967, 32.45092697],
  [3.37964793, 32.88379946],
  [2.88561768, 32.88378899],
  [2.88567251, 32.45093128]
])

zoneNord = ee.Geometry.Polygon([
  [3.18513508, 33.01358581],
  [3.18482285, 33.28297225],
  [3.81093387, 33.27857017],
  [3.81077745, 33.01358819],
  [3.18513508, 33.01358581]
])

# ================= PATHS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"

# ================= SECTION A =================
st.markdown("## 📁 Section A — Données")
if st.button("Afficher dossiers"):
    for root, dirs, files in os.walk(DATA_DIR):
        st.write(root)
        for f in files:
            st.write(" └─", f)

# ================= SECTION B =================
st.markdown("## 📑 Section B — CSV")
if st.button("Afficher CSV"):
    if os.path.exists(csv_hist):
        df = pd.read_csv(csv_hist)
        st.dataframe(df.head())
    else:
        st.warning("CSV introuvable")

# ================= SECTION C =================
st.markdown("## 🗺️ Carte CH₄ moyenne")
year_mean = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])
if st.button("Afficher carte CH₄ moyenne"):
    path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"
    if os.path.exists(path):
        with rasterio.open(path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        fig, ax = plt.subplots()
        im = ax.imshow(img, cmap="viridis")
        plt.colorbar(im, ax=ax, label="CH₄ (ppb)")
        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.warning("Carte introuvable")

# ================= SECTION D =================
st.markdown("## 🔎 Analyse annuelle")
if st.button("Analyser année"):
    if os.path.exists(csv_annual):
        df = pd.read_csv(csv_annual)
        st.dataframe(df)

# ================= SECTION E =================
st.markdown("## 📊 Analyse CH₄ par Zone et Année")
year = st.selectbox("Choisir année analyse", [2020, 2021, 2022, 2023, 2024, 2025])
if st.button("Lancer analyse CH₄"):
    start = ee.Date(f"{year}-01-01")
    end = ee.Date(f"{year}-12-31")
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )

    def compute(zone, name):
        value = collection.mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=7000,
            maxPixels=1e9,
            bestEffort=True
        ).get("CH4_column_volume_mixing_ratio_dry_air")
        try:
            val = value.getInfo()
        except:
            val = None
        return {"Zone": name, "CH₄ (ppb)": val}

    results = [compute(zoneCentre, "Centre"), compute(zoneSud, "Sud"), compute(zoneNord, "Nord")]
    df = pd.DataFrame(results)
    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))

# ================= SECTION F =================
st.markdown("## 📡 Analyse CH₄ récente par zone")
if st.button("Analyser CH₄ (derniers jours)"):
    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )
    image = collection.mean()
    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]
    results = []

    for name, zone in zones:
        value = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=7000,
            maxPixels=1e9,
            bestEffort=True
        ).get("CH4_column_volume_mixing_ratio_dry_air")
        try:
            val = value.getInfo()
        except:
            val = None

        status_ia, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
        results.append({
            "Zone": name,
            "CH₄": round(val,2) if val else "No data",
            "Risque IA": status_ia,
            "Score IA": round(score,2)
        })

    df = pd.DataFrame(results)
    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))

# ================= SECTION G =================

st.markdown("## 🎯 Détection locale")
lat_point = st.number_input("Latitude", value=32.90)
lon_point = st.number_input("Longitude", value=3.30)

if st.button("Analyser point"):
    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )
    image = collection.mean()
    point = ee.Geometry.Point([lon_point, lat_point])
    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000,
        maxPixels=1e9,
        bestEffort=True
    ).get("CH4_column_volume_mixing_ratio_dry_air")
    try:
        val = value.getInfo()
    except:
        val = None

    status_ia, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
    if val:
        st.success(f"CH₄ : {round(val,2)} ppb — IA: {status_ia} (Score {round(score,2)})")
    else:
        st.error("❌ Pas de donnée")




# ================= SECTION I PDF PRO FUITES =================
st.markdown("## 🧾 Rapport CH₄ avec Point de Fuite")

if st.button("📄 Générer Rapport Fuite"):

    import io
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from datetime import datetime
    from PIL import Image as PILImage
    import numpy as np
    import matplotlib.pyplot as plt
    import tempfile
    import os

    today = datetime.utcnow()

    # ------------------- Récupération des données CH4 -------------------
    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]
    results = []

    # On prend l'image moyenne de 7 derniers jours
    try:
        start = ee.Date(today.strftime("%Y-%m-%d")).advance(-7, "day")
        collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4") \
            .filterDate(start, ee.Date(today.strftime("%Y-%m-%d"))) \
            .select("CH4_column_volume_mixing_ratio_dry_air")
        image = collection.mean()

        last_image = collection.sort('system:time_start', False).first()
        last_date = ee.Date(last_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    except:
        st.warning("⚠️ Erreur récupération données satellite")
        image = None
        last_date = "N/A"

    # ------------------- Analyse par zone -------------------
    table_data = [["Zone", "CH₄ (ppb)", "Débit", "Statut IA", "Lat", "Lon"]]

    for name, zone in zones:
        val = None
        if image:
            try:
                val = image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=zone,
                    scale=7000,
                    maxPixels=1e9,
                    bestEffort=True
                ).getInfo().get("CH4_column_volume_mixing_ratio_dry_air")
            except:
                val = None

        # IA légère
        status, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
        debit = round((val-1800)*0.5,2) if val else "N/A"

        # Coordonnées du centre
        try:
            lon, lat = zone.centroid().coordinates().getInfo()
        except:
            lat, lon = "N/A", "N/A"

        table_data.append([name, round(val,2) if val else "N/A", debit, status, lat, lon])
        results.append((name, val, status, lat, lon))

    # ------------------- Détection point de fuite le plus élevé -------------------
    # On récupère le point le plus chaud du raster si possible
    try:
        # On utilise le fichier raster CH4 moyen de 2024 (ou l'année en cours)
        raster_path = f"data/Moyenne CH4/CH4_mean_2024.tif"
        import rasterio
        with rasterio.open(raster_path) as src:
            img = src.read(1)
        img[img <=0] = np.nan

        # Point de fuite max
        y, x = np.unravel_index(np.nanargmax(img), img.shape)
        max_val = img[y, x]

        # Création image zoom plume
        size = 60
        y1, y2 = max(0, y-size), min(img.shape[0], y+size)
        x1, x2 = max(0, x-size), min(img.shape[1], x+size)
        zoom = img[y1:y2, x1:x2]

        fig, ax = plt.subplots()
        im = ax.imshow(zoom, cmap="jet", vmin=np.nanpercentile(zoom,5), vmax=np.nanpercentile(zoom,98))
        ax.set_title(f"Point de fuite CH₄ ({round(max_val,2)} ppb)")
        ax.axis("off")
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label("CH₄ (ppb)")

        tmp_img = os.path.join(tempfile.gettempdir(), "ch4_fuite.png")
        plt.savefig(tmp_img, bbox_inches='tight', dpi=300)
        plt.close()
    except Exception as e:
        st.warning(f"⚠️ Impossible de générer image fuite: {e}")
        tmp_img = None

    # ------------------- Génération PDF -------------------
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("<b>DATA.SAT</b>", styles["Title"]))
    elements.append(Paragraph("CH₄ Detection Report", styles["Heading2"]))
    elements.append(Spacer(1,10))
    elements.append(Paragraph(f"<b>Date:</b> {today.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Last Satellite Pass:</b> {last_date}", styles["Normal"]))
    elements.append(Spacer(1,10))

    # Image plume
    if tmp_img:
        img_pdf = Image(tmp_img)
        img_pdf.drawHeight = 4*inch
        img_pdf.drawWidth = 6*inch
        elements.append(Paragraph("<b>Detection Point de Fuite</b>", styles["Heading3"]))
        elements.append(img_pdf)
        elements.append(Spacer(1,15))

    # Tableau
    table = Table(table_data, colWidths=[70,70,70,80,60,60])
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#1f4e79")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('GRID',(0,0),(-1,-1),0.5,colors.black),
        ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
    ]))
    elements.append(Paragraph("<b>Analyse par Zone</b>", styles["Heading3"]))
    elements.append(table)
    elements.append(Spacer(1,20))

    # HSE
    elements.append(Paragraph("<b>HSE Risk Analysis</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Les anomalies CH₄ détectées via satellite indiquent des fuites potentielles. "
        "Les zones critiques peuvent présenter un risque incendie/explosion et un impact environnemental.",
        styles["Normal"]
    ))

    # Actions
    elements.append(Spacer(1,12))
    elements.append(Paragraph("<b>Recommended Actions</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "- Field inspection\n- Leak verification\n- Maintenance\n- Continuous monitoring",
        styles["Normal"]
    ))

    # Build PDF
    try:
        doc.build(elements)
        buffer.seek(0)
        st.download_button(
            "📥 Télécharger Rapport Fuite CH₄",
            data=buffer,
            file_name=f"rapport_CH4_fuite_{today.strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Erreur PDF: {e}")






























# ================= SECTION I+J OPTIMISÉE — Carte + PDF PRO =================
st.markdown("## 🚀 Rapport CH₄ Ultra PRO avec Plume et Points Critiques")

days = st.number_input("Analyser les derniers jours", min_value=1, max_value=30, value=7, key="days_pro")

if st.button("📊 Analyser et Générer Carte + PDF"):

    today = datetime.utcnow()
    start = today - timedelta(days=days)

    # ------------------- Récupération données satellite -------------------
    try:
        collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4") \
            .filterDate(start, today) \
            .select("CH4_column_volume_mixing_ratio_dry_air")
        image = collection.mean()
        last_image = collection.sort('system:time_start', False).first()
        last_date = ee.Date(last_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    except:
        st.warning("⚠️ Impossible de récupérer les données satellite")
        image = None
        last_date = "N/A"

    results = []
    critical_points = []

    # ------------------- Analyse par zone -------------------
    for name, zone in zones:
        val = None
        if image:
            try:
                val = image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=zone,
                    scale=7000,
                    maxPixels=1e9,
                    bestEffort=True
                ).getInfo().get("CH4_column_volume_mixing_ratio_dry_air")
            except:
                val = None

        status, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
        debit = round((val-1800)*0.5,2) if val else "N/A"
        try:
            lon, lat = zone.centroid().coordinates().getInfo()
        except:
            lat, lon = "N/A", "N/A"

        results.append([name, round(val,2) if val else "N/A", debit, status, round(score,2), lat, lon])
        if status=="🔥 Fuite critique":
            critical_points.append({"lat":lat,"lon":lon,"zone":name,"val":val})

    df_results = pd.DataFrame(results, columns=["Zone","CH₄ (ppb)","Débit","Statut IA","Score IA","Lat","Lon"])
    st.dataframe(df_results)

    # ------------------- Carte interactive -------------------
    if critical_points:
        center_lat = critical_points[0]['lat']
        center_lon = critical_points[0]['lon']
    else:
        center_lat = np.mean([r[5] for r in results])
        center_lon = np.mean([r[6] for r in results])

    m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles=None)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="ESRI Satellite",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Carte simple").add_to(m)
    folium.LayerControl().add_to(m)

    # Ajout zones + points critiques
    for r in results:
        zone_name, val, debit, status, score, lat, lon = r
        color = "green" if status=="✅ Normal" else ("orange" if status=="⚠️ Suspect" else "red")
        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            color=color,
            fill=True,
            fill_opacity=0.7,
            tooltip=f"{zone_name} | CH₄: {val} ppb | IA: {status} | Débit: {debit}"
        ).add_to(m)

    # Affichage carte
    st.write("🗺️ Carte CH₄ et Points Critiques")
    st.components.v1.html(m._repr_html_(), height=500)

    # ------------------- Génération PDF -------------------
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("<b>DATA.SAT</b>", styles["Title"]))
    elements.append(Paragraph("CH₄ Detection Ultra PRO Report", styles["Heading2"]))
    elements.append(Spacer(1,10))
    elements.append(Paragraph(f"<b>Date:</b> {today.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Last Satellite Pass:</b> {last_date}", styles["Normal"]))
    elements.append(Spacer(1,10))

    # Carte image snapshot temporaire
    try:
        tmp_map = os.path.join(tempfile.gettempdir(), "ch4_map.png")
        m.save(tmp_map.replace(".png",".html"))  # sauvegarde html
    except:
        tmp_map = None

    # Table
    table = Table([["Zone","CH₄ (ppb)","Débit","Statut IA","Score IA","Lat","Lon"]] + results, colWidths=[50,50,50,70,50,50,50])
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#1f4e79")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('GRID',(0,0),(-1,-1),0.5,colors.black),
        ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
    ]))
    elements.append(Paragraph("<b>Analyse par Zone</b>", styles["Heading3"]))
    elements.append(table)
    elements.append(Spacer(1,15))

    # HSE Analysis
    elements.append(Paragraph("<b>HSE Risk Analysis</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Les anomalies CH₄ détectées via satellite indiquent des fuites potentielles. "
        "Les zones critiques peuvent présenter un risque incendie/explosion et un impact environnemental.",
        styles["Normal"]
    ))
    elements.append(Spacer(1,12))
    elements.append(Paragraph("<b>Recommended Actions</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "- Field inspection\n- Leak verification\n- Maintenance\n- Continuous monitoring",
        styles["Normal"]
    ))

    try:
        doc.build(elements)
        buffer.seek(0)
        st.download_button(
            label="📥 Télécharger Rapport PDF Ultra PRO",
            data=buffer,
            file_name=f"rapport_CH4_pro_{today.strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Erreur génération PDF : {e}")
