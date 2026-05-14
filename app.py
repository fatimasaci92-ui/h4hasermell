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
from reportlab.lib.pagesizes import A4


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



# ================= SECTION H — DÉTECTION DES POINTS DE FUITE CH₄ =================
# À insérer dans app.py, après la Section G et avant la Section I

import streamlit as st
import numpy as np
import rasterio
import rasterio.transform
import folium
import pandas as pd
import ee
from datetime import datetime, timedelta

st.markdown("## 🔥 Détection automatique des points de fuite CH₄")

col1, col2 = st.columns(2)
with col1:
    year_leak = st.selectbox("Année du raster", [2020, 2021, 2022, 2023, 2024], key="year_leak")
with col2:
    n_hotspots = st.slider("Nombre de points de fuite à détecter", 1, 20, 5)

validate_gee = st.checkbox("Valider les hotspots via GEE (satellite récent)", value=True)

if st.button("🔍 Détecter les fuites et cartographier"):

    raster_path = f"data/Moyenne CH4/CH4_mean_{year_leak}.tif"

    if not os.path.exists(raster_path):
        st.error(f"❌ Raster introuvable : {raster_path}")
        st.stop()

    # -------- Lecture raster --------
    with rasterio.open(raster_path) as src:
        img = src.read(1).astype(float)
        transform = src.transform
        crs = src.crs

    img[img <= 0] = np.nan

    # -------- Détection des N hotspots --------
    # Masque valide
    valid_mask = ~np.isnan(img)
    flat_valid_indices = np.flatnonzero(valid_mask)

    # Top-N indices
    flat_vals = img.flatten()
    flat_vals_clean = np.where(np.isnan(flat_vals), -np.inf, flat_vals)
    top_n_flat = np.argsort(flat_vals_clean)[-n_hotspots:][::-1]

    hotspots = []
    for flat_idx in top_n_flat:
        row, col = np.unravel_index(flat_idx, img.shape)
        val = img[row, col]
        # Conversion pixel → coordonnées géographiques
        lon, lat = rasterio.transform.xy(transform, row, col)
        hotspots.append({
            "rank": len(hotspots) + 1,
            "lat": lat,
            "lon": lon,
            "ch4_raster": round(float(val), 2),
            "row": int(row),
            "col": int(col)
        })

    # -------- Validation GEE optionnelle --------
    if validate_gee:
        today = datetime.utcnow()
        start = today - timedelta(days=14)
        try:
            collection = (
                ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                .filterDate(start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
                .select("CH4_column_volume_mixing_ratio_dry_air")
            )
            gee_image = collection.mean()
        except Exception as e:
            st.warning(f"⚠️ GEE non disponible : {e}")
            gee_image = None
    else:
        gee_image = None

    for hp in hotspots:
        val_gee = None
        if gee_image:
            try:
                point = ee.Geometry.Point([hp["lon"], hp["lat"]])
                val_gee = gee_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=point,
                    scale=7000,
                    maxPixels=1e9,
                    bestEffort=True
                ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()
            except:
                val_gee = None

        hp["ch4_gee"] = round(val_gee, 2) if val_gee else "N/A"

        # Score IA combiné
        val_ref = val_gee if val_gee else hp["ch4_raster"]
        status, score = detect_ch4_anomaly(np.array([[val_ref]]))
        hp["statut_ia"] = status
        hp["score_ia"] = score

    # -------- Affichage tableau --------
    df_hp = pd.DataFrame(hotspots)[["rank", "lat", "lon", "ch4_raster", "ch4_gee", "statut_ia", "score_ia"]]
    df_hp.columns = ["#", "Latitude", "Longitude", "CH₄ raster (ppb)", "CH₄ GEE (ppb)", "Statut IA", "Score IA"]
    st.dataframe(df_hp, use_container_width=True)

    # -------- Carte interactive Folium --------
    center_lat = np.mean([hp["lat"] for hp in hotspots])
    center_lon = np.mean([hp["lon"] for hp in hotspots])

    m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles=None)

    # Fond satellite ESRI
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="ESRI World Imagery",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Carte").add_to(m)
    folium.LayerControl().add_to(m)

    # Couleur selon statut
    def _color(status):
        if "critique" in status:
            return "red"
        elif "Suspect" in status:
            return "orange"
        else:
            return "green"

    # Groupe de marqueurs pour les hotspots
    fg_leaks = folium.FeatureGroup(name="Points de fuite CH₄")

    for hp in hotspots:
        color = _color(hp["statut_ia"])
        ch4_gee_str = f"{hp['ch4_gee']} ppb" if hp["ch4_gee"] != "N/A" else "N/A"

        popup_html = f"""
        <div style='font-family:sans-serif;font-size:13px;min-width:180px'>
            <b>Point #{hp['rank']}</b><br>
            📍 {round(hp['lat'],4)}, {round(hp['lon'],4)}<br>
            📡 Raster: <b>{hp['ch4_raster']} ppb</b><br>
            🛰 GEE récent: <b>{ch4_gee_str}</b><br>
            🤖 IA: <b>{hp['statut_ia']}</b> (score {hp['score_ia']})<br>
        </div>
        """

        # Marqueur pulsant pour les fuites critiques
        if color == "red":
            folium.CircleMarker(
                location=[hp["lat"], hp["lon"]],
                radius=14,
                color="darkred",
                fill=True,
                fill_color="red",
                fill_opacity=0.25,
                tooltip=f"Zone critique #{hp['rank']}"
            ).add_to(fg_leaks)

        folium.CircleMarker(
            location=[hp["lat"], hp["lon"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            tooltip=f"#{hp['rank']} | {hp['ch4_raster']} ppb",
            popup=folium.Popup(popup_html, max_width=220)
        ).add_to(fg_leaks)

        # Numéro du point
        folium.Marker(
            location=[hp["lat"], hp["lon"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:10px;font-weight:bold;color:white;'
                     f'background:{color};border-radius:50%;width:18px;height:18px;'
                     f'line-height:18px;text-align:center;margin-top:-9px;margin-left:-9px">'
                     f'{hp["rank"]}</div>',
                icon_size=(18, 18),
                icon_anchor=(9, 9)
            )
        ).add_to(fg_leaks)

    fg_leaks.add_to(m)

    # Légende
    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:1000;background:rgba(255,255,255,0.9);
         padding:10px 14px;border-radius:8px;font-size:12px;font-family:sans-serif;
         box-shadow:0 2px 6px rgba(0,0,0,0.2)'>
    <b>Légende</b><br>
    <span style='color:red'>●</span> Fuite critique (&gt;1920 ppb)<br>
    <span style='color:orange'>●</span> Suspect (&gt;1880 ppb)<br>
    <span style='color:green'>●</span> Normal
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st.write("### 🗺️ Carte des points de fuite détectés")
    st_folium(m, width=None, height=520, returned_objects=[])

    # -------- Résumé HSE --------
    n_critical = sum(1 for hp in hotspots if "critique" in hp["statut_ia"])
    n_suspect = sum(1 for hp in hotspots if "Suspect" in hp["statut_ia"])

    if n_critical > 0:
        st.error(f"⚠️ {n_critical} point(s) de fuite **critique(s)** détecté(s) — inspection terrain requise immédiatement.")
    if n_suspect > 0:
        st.warning(f"🔎 {n_suspect} zone(s) **suspecte(s)** — surveillance renforcée recommandée.")
    if n_critical == 0 and n_suspect == 0:
        st.success("✅ Aucune anomalie critique détectée sur les hotspots sélectionnés.")
























# ================= SECTION I+J OPTIMISÉE — Carte + PDF PRO =================
st.markdown("## 🚀 Rapport CH₄ Ultra PRO avec Plume et Points Critiques")

days = st.number_input("Analyser les derniers jours", min_value=1, max_value=30, value=7, key="days_pro")

if st.button("📊 Analyser et Générer Carte + PDF"):

    today = datetime.utcnow()
    start = today - timedelta(days=days)

    # ------------------- Définition zones -------------------
    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]

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
        center_lat = np.mean([r[5] for r in results if r[5] != "N/A"])
        center_lon = np.mean([r[6] for r in results if r[6] != "N/A"])

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
        if lat=="N/A" or lon=="N/A":
            continue
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

    # Build PDF
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


# ================= SECTION K — CARBON MAPPER (VERSION CORRIGÉE FINALE) =================

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import base64
import json
from datetime import datetime
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

st.markdown("## 🛰️ Carbon Mapper — Fuites CH₄ réelles géolocalisées")

st.info(
    "Source : Carbon Mapper (Tanager-1, NASA EMIT, AVIRIS-NG). "
    "Résolution 3–50 m. Données réelles de panaches géolocalisés."
)

# ================= TOKEN =================

CM_TOKEN = ""

try:
    CM_TOKEN = (
        st.secrets.get("CARBON_API_TOKEN")
        or ""
    ).strip()
except:
    CM_TOKEN = ""

if not CM_TOKEN:
    st.error(
        "❌ Token Carbon Mapper introuvable.\n\n"
        "Ajoutez dans secrets.toml :\n"
        'CARBON_API_TOKEN = "VOTRE_TOKEN"'
    )
    st.stop()

# ================= PARAMÈTRES =================

col1, col2 = st.columns(2)

with col1:
    cm_lat_min = st.number_input(
        "Lat min",
        value=32.45,
        format="%.4f"
    )

    cm_lat_max = st.number_input(
        "Lat max",
        value=33.28,
        format="%.4f"
    )

with col2:
    cm_lon_min = st.number_input(
        "Lon min",
        value=2.88,
        format="%.4f"
    )

    cm_lon_max = st.number_input(
        "Lon max",
        value=3.81,
        format="%.4f"
    )

col3, col4 = st.columns(2)

with col3:
    cm_date_start = st.date_input(
        "Date début",
        value=datetime(2022, 1, 1)
    )

with col4:
    cm_date_end = st.date_input(
        "Date fin",
        value=datetime.utcnow()
    )

cm_gas = st.selectbox(
    "Gaz",
    ["CH4", "CO2"]
)

cm_sector = st.selectbox(
    "Secteur",
    [
        "Tous",
        "oil-and-gas",
        "solid-waste",
        "coal",
        "agriculture",
        "wastewater"
    ]
)

sector_val = "" if cm_sector == "Tous" else cm_sector

# ================= BBOX CORRIGÉ =================

bbox_val = [
    float(cm_lon_min),
    float(cm_lat_min),
    float(cm_lon_max),
    float(cm_lat_max)
]

# ================= TOKEN BASE64 =================

token_b64 = base64.b64encode(
    CM_TOKEN.encode()
).decode()

# ================= HTML + JS =================

html_code = f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="utf-8"/>

<link rel="stylesheet"
href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>

* {{
box-sizing:border-box;
margin:0;
padding:0;
font-family:sans-serif;
}}

body {{
padding:6px;
}}

#map {{
width:100%;
height:500px;
border-radius:10px;
border:1px solid #ddd;
display:none;
margin-top:10px;
}}

#status {{
margin:8px 0;
font-size:13px;
color:#666;
}}

#btn {{
width:100%;
padding:10px;
border-radius:8px;
border:1px solid #ccc;
background:white;
cursor:pointer;
font-size:14px;
}}

#btn:hover {{
background:#f5f5f5;
}}

table {{
width:100%;
border-collapse:collapse;
margin-top:10px;
}}

th, td {{
padding:6px;
font-size:12px;
border-bottom:1px solid #eee;
}}

th {{
background:#f5f5f5;
}}

</style>

</head>

<body>

<button id="btn" onclick="run()">
🛰️ Rechercher les fuites {cm_gas}
</button>

<div id="status">
Cliquez pour interroger Carbon Mapper...
</div>

<div id="map"></div>

<div id="table_wrap"></div>

<script>

const TOKEN = atob("{token_b64}");

const GAS = "{cm_gas}";
const SECTOR = "{sector_val}";

const BBOX = {json.dumps(bbox_val)};

const DATE_START = "{cm_date_start}";
const DATE_END = "{cm_date_end}";

const API_URL =
"https://api.carbonmapper.org/api/v1/catalog/plumes/annotated";

let map = null;
let layer = null;

function setStatus(msg,color="#666") {{
    const s = document.getElementById("status");
    s.innerHTML = msg;
    s.style.color = color;
}}

async function run() {{

    setStatus("Chargement...", "#888");

    const params = {{
        limit: 200,
        offset: 0,
        gas: GAS,
        bbox: BBOX.join(","),
        datetime:
            DATE_START + "T00:00:00Z/" +
            DATE_END + "T23:59:59Z"
    }};

    if (SECTOR) {{
        params.sector = SECTOR;
    }}

    const qs = new URLSearchParams(params).toString();

    const final_url = API_URL + "?" + qs;

    console.log(final_url);

    try {{

        const response = await fetch(
            final_url,
            {{
                headers: {{
                    "Authorization":
                        "Bearer " + TOKEN
                }}
            }}
        );

        console.log("STATUS:", response.status);

        const txt = await response.text();

        console.log(txt);

        if (!response.ok) {{

            setStatus(
                "❌ Erreur API : " +
                response.status,
                "red"
            );

            return;
        }}

        const data = JSON.parse(txt);

        const items = data.items || [];

        if (items.length === 0) {{

            setStatus(
                "⚠️ Aucun panache trouvé",
                "orange"
            );

            return;
        }}

        setStatus(
            "✅ " + items.length +
            " panache(s) détecté(s)",
            "green"
        );

        renderMap(items);

        renderTable(items);

    }}

    catch(err) {{

        console.log(err);

        setStatus(
            "❌ Erreur réseau/API",
            "red"
        );
    }}
}}

function renderMap(items) {{

    document.getElementById("map").style.display = "block";

    let pts = [];

    items.forEach(p => {{

        const prop = p.properties || p;

        let lat =
            prop.source_lat ||
            prop.lat ||
            null;

        let lon =
            prop.source_lon ||
            prop.lon ||
            null;

        if (!lat && p.geometry) {{
            lon = p.geometry.coordinates[0];
            lat = p.geometry.coordinates[1];
        }}

        if (lat && lon) {{
            pts.push([lat, lon, prop]);
        }}
    }});

    if (pts.length === 0) return;

    const centerLat =
        pts.reduce((a,b)=>a+b[0],0)/pts.length;

    const centerLon =
        pts.reduce((a,b)=>a+b[1],0)/pts.length;

    if (!map) {{

        map = L.map("map").setView(
            [centerLat, centerLon],
            8
        );

        L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
            {{
                attribution:"ESRI"
            }}
        ).addTo(map);

    }} else {{

        map.setView(
            [centerLat, centerLon],
            8
        );

        if (layer) {{
            map.removeLayer(layer);
        }}
    }}

    layer = L.layerGroup().addTo(map);

    pts.forEach(p => {{

        const lat = p[0];
        const lon = p[1];
        const prop = p[2];

        const emission =
            prop.emission_auto ||
            prop.emission ||
            0;

        let color = "green";

        if (emission > 1000)
            color = "red";
        else if (emission > 300)
            color = "orange";

        L.circleMarker(
            [lat, lon],
            {{
                radius:10,
                color:color,
                fillColor:color,
                fillOpacity:0.8
            }}
        )
        .bindPopup(
            "<b>Débit:</b> " +
            emission +
            " kg/h"
        )
        .addTo(layer);

    }});
}}

function renderTable(items) {{

    let html = `
    <table>
    <thead>
    <tr>
        <th>ID</th>
        <th>Date</th>
        <th>Débit kg/h</th>
    </tr>
    </thead>
    <tbody>
    `;

    items.forEach(p => {{

        const prop = p.properties || p;

        html += `
        <tr>
            <td>${{prop.id || "N/A"}}</td>
            <td>${{prop.acquisition_date || "N/A"}}</td>
            <td>${{
                prop.emission_auto ||
                prop.emission ||
                "N/A"
            }}</td>
        </tr>
        `;
    }});

    html += `
    </tbody>
    </table>
    `;

    document.getElementById(
        "table_wrap"
    ).innerHTML = html;
}}

</script>

</body>
</html>
"""

components.html(
    html_code,
    height=800,
    scrolling=True
)

# ================= PDF =================

st.markdown("### 📄 Rapport PDF Carbon Mapper")

if st.button("📥 Générer rapport PDF"):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            "<b>DATA.SAT — Carbon Mapper Report</b>",
            styles["Title"]
        )
    )

    elements.append(Spacer(1,10))

    elements.append(
        Paragraph(
            f"Gaz : {cm_gas}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Secteur : {cm_sector}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Période : {cm_date_start} → {cm_date_end}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1,15))

    elements.append(
        Paragraph(
            "Analyse Carbon Mapper des panaches CH₄.",
            styles["Normal"]
        )
    )

    doc.build(elements)

    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger PDF",
        data=buffer,
        file_name="carbon_mapper_report.pdf",
        mime="application/pdf"
    )
