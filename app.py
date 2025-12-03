import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")

# ================= INFORMATIONS SITE =================
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ================= PATHS =================
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")
csv_anomalies = os.path.join(CSV_DIR, "Anomalies_CH4_HassiRmel.csv")

# ================= SESSION STATE INIT =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= UTIL FUNCTIONS =================
def hazop_analysis(ch4_value):
    data = []
    if ch4_value < 1800:
        data.append(["CH₄", "Normal", "Pas d’anomalie", "Fonctionnement normal", "Surveillance continue"])
    elif ch4_value < 1850:
        data.append(["CH₄", "Modérément élevé", "Torchage possible", "Risque faible d’incident", "Vérifier torches et informer l'équipe HSE"])
    elif ch4_value < 1900:
        data.append(["CH₄", "Élevé", "Fuite probable", "Risque d’explosion accru", "Inspection urgente du site et mesures de sécurité immédiates"])
    else:
        data.append(["CH₄", "Critique", "Fuite majeure", "Risque critique d’explosion/incendie", "Alerter direction, sécuriser zone, stopper les opérations si nécessaire"])
    return pd.DataFrame(data, columns=["Paramètre","Déviation","Cause","Conséquence","Action HSE"])

```
# TITRE
story.append(Paragraph("<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
story.append(Spacer(1, 12))

# META
date_str = report_date
time_str = datetime.now().strftime("%H:%M")
meta = f"""
<b>Date :</b> {date_str}<br/>
<b>Heure :</b> {time_str}<br/>
<b>Site :</b> {site_name}<br/>
<b>Latitude :</b> {latitude}<br/>
<b>Longitude :</b> {longitude}<br/>
"""
story.append(Paragraph(meta, styles["Normal"]))
story.append(Spacer(1, 12))

# EXPLICATION
explanation = (
    "Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté "
    f"sur le site <b>{site_name}</b>. La surveillance du CH₄ permet d'identifier les anomalies, "
    "d'évaluer le niveau de risque HSE et de recommander des actions."
)
story.append(Paragraph(explanation, styles["Normal"]))
story.append(Spacer(1, 12))

# TABLEAU PRINCIPAL
table_data = [
    ["Paramètre", "Valeur"],
    ["Concentration CH₄ (ppb)", f"{ch4_value}"],
    ["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
    ["Action recommandée HSE", action_hse],
]
table = Table(table_data, colWidths=[180, 260])
table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0B4C6E")),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
    ('GRID', (0, 0), (-1, -1), 0.8, colors.grey)
]))
story.append(table)
story.append(Spacer(1, 16))

# CAUSES POSSIBLES
cause_text = (
    "<b>Causes possibles d'une anomalie CH₄ :</b><br/>"
    "- Fuite sur canalisation ou bride endommagée<br/>"
    "- Torchage défaillant<br/>"
    "- Purge de gaz ou opération de maintenance<br/>"
    "- Pression anormale dans le réseau<br/>"
)
story.append(Paragraph(cause_text, styles["Normal"]))
story.append(Spacer(1, 12))

# INTERPRETATION / RECOMMANDATIONS
if anomaly_flag:
    action_text = (
        "<b>Actions recommandées (niveau critique) :</b><br/>"
        "- Alerter immédiatement la direction HSE<br/>"
        "- Sécuriser/évacuer la zone si nécessaire<br/>"
        "- Localiser la fuite avec OGI / capteurs portables<br/>"
        "- Réparer ou isoler la section affectée, stopper opérations si besoin"
    )
else:
    action_text = (
        "<b>Actions recommandées :</b><br/>"
        "- Surveillance continue<br/>"
        "- Contrôles périodiques et maintenance préventive"
    )
story.append(Paragraph(action_text, styles["Normal"]))
story.append(Spacer(1, 12))

# HAZOP (optionnel)
if hazop_df is not None and not hazop_df.empty:
    hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
    hazop_table = Table(hazop_data, colWidths=[100]*len(hazop_df.columns))
    hazop_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0B4C6E")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.8, colors.grey)
    ]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
    story.append(Spacer(1, 6))
    story.append(hazop_table)
    story.append(Spacer(1, 12))

# FOOTER
footer = "<para align='center'><font size=9 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄</font></para>"
story.append(Paragraph(footer, styles["Normal"]))

doc.build(story)
pdf_data = buffer.getvalue()
buffer.close()
return pdf_data
```

# ===================== SECTION A-G =====================

# (Les sections A à G restent identiques mais en ajoutant 2025 dans year_choice et les dictionnaires)

# Pour éviter de surcharger, les modifications principales :

# - year_choice = st.selectbox("Choisir l'année", [2020,2021,2022,2023,2024,2025])

# - mean_files et anomaly_files incluent 2025

# - csv_daily = "CH4_daily_2025.csv"

# Le reste du code fonctionne comme avant pour cartes, analyses HSE, PDF journalier et annuel,

# ainsi que dashboard historique et graphiques.

# Pour les sections historiques et graphiques, 2025 est automatiquement inclus car les fichiers CSV

# et colonnes sont détectés dynamiquement.
