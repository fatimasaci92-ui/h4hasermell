# app.py (version complète et corrigée)
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

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2025)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2025)}
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")
csv_daily = os.path.join(CSV_DIR, "Anomalies_CH4_HassiRmel.csv")

# ================= SESSION STATE INIT =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None  # will hold dict with ch4_today, threshold, action, date

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

def generate_pdf_bytes_professional(site_name, latitude, longitude, report_date, ch4_value, anomaly_flag, action_hse, hazop_df=None):
    """
    Retourne des bytes PDF (ReportLab) pour téléchargement.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Rapport_HSE_{site_name}_{report_date}")
    styles = getSampleStyleSheet()
    story = []

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

    # Build
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ===================== SECTION A: Contenu des sous-dossiers (bouton) =====================
st.markdown("## 📁 Contenu des sous-dossiers")
if st.button("Afficher le contenu des sous-dossiers"):
    st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
    st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
    st.write("CSV 2020-2024 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ===================== SECTION B: Aperçu CSV annuel (bouton) =====================
st.markdown("## 📑 Aperçu CSV annuel")
if st.button("Afficher aperçu CSV annuel"):
    if os.path.exists(csv_annual):
        try:
            df_annual = pd.read_csv(csv_annual)
            st.write(df_annual.head())
        except Exception as e:
            st.error(f"Erreur lecture CSV annuel: {e}")
    else:
        st.warning("CSV annuel introuvable.")

# ===================== SECTION C: Cartes par année (bouton) =====================
st.markdown("## 🗺️ Cartes Moyenne & Anomalie par année")
year_choice = st.selectbox("Choisir l'année", [2020,2021,2022,2023,2024])

if st.button("Afficher les cartes de l'année sélectionnée"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"CH₄ moyen {year_choice}")
        mean_path = mean_files.get(year_choice)
        if mean_path and os.path.exists(mean_path):
            try:
                with rasterio.open(mean_path) as src:
                    arr = src.read(1)
                arr = np.array(arr)
                arr[arr <= 0] = np.nan
                fig, ax = plt.subplots(figsize=(6,5))
                ax.imshow(arr, cmap='viridis')
                ax.set_title(f"CH₄ moyen {year_choice}")
                ax.axis('off')
                st.pyplot(fig)
            except Exception as e:
                st.error(f"Erreur affichage CH4 mean: {e}")
        else:
            st.warning("Fichier CH₄ moyen introuvable.")

    with col2:
        st.subheader(f"Anomalie CH₄ {year_choice}")
        an_path = anomaly_files.get(year_choice)
        if an_path and os.path.exists(an_path):
            try:
                with rasterio.open(an_path) as src:
                    arr2 = src.read(1)
                arr2 = np.array(arr2)
                arr2[arr2 == 0] = np.nan
                fig2, ax2 = plt.subplots(figsize=(6,5))
                ax2.imshow(arr2, cmap='coolwarm')
                ax2.set_title(f"Anomalie CH₄ {year_choice}")
                ax2.axis('off')
                st.pyplot(fig2)
            except Exception as e:
                st.error(f"Erreur affichage anomalie CH4: {e}")
        else:
            st.warning("Fichier anomalie CH₄ introuvable.")

# ===================== SECTION D: Analyse HSE annuelle (bouton) =====================
st.markdown("## 🔎 Analyse HSE annuelle")
if st.button("Afficher l'analyse HSE pour l'année sélectionnée"):
    if os.path.exists(csv_annual):
        try:
            df_annual_local = pd.read_csv(csv_annual)
            if year_choice in df_annual_local['year'].values:
                mean_ch4_year = float(df_annual_local[df_annual_local['year']==year_choice]['CH4_mean'].values[0])
                if mean_ch4_year < 1800:
                    risk = "Faible"
                    action = "Surveillance continue."
                elif mean_ch4_year < 1850:
                    risk = "Modéré"
                    action = "Vérifier les torches et informer l'équipe HSE."
                elif mean_ch4_year < 1900:
                    risk = "Élevé"
                    action = "Inspection urgente du site et mesures de sécurité immédiates."
                else:
                    risk = "Critique"
                    action = "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire."

                st.success(f"Année : {year_choice}")
                st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
                st.write(f"**Niveau de risque HSE :** {risk}")
                st.write(f"**Actions recommandées :** {action}")

                # HAZOP
                df_hazop_local = hazop_analysis(mean_ch4_year)
                st.markdown("### Tableau HAZOP")
                st.table(df_hazop_local)
            else:
                st.warning("Pas de données CH₄ pour cette année dans CSV annuel.")
        except Exception as e:
            st.error(f"Erreur lors de la lecture/analyses annuelles: {e}")
    else:
        st.warning("CSV annuel introuvable.")

# ===================== SECTION E: Analyse CH4 du jour (bouton) =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
    # Priorité: lire le CSV daily si présent (export GEE)
    if os.path.exists(csv_daily):
        try:
            df_daily_local = pd.read_csv(csv_daily)
            # on prend la dernière ligne si elle contient colonnes valides
            if not df_daily_local.empty:
                last = df_daily_local.iloc[-1]
                # Cherche une colonne plausible pour valeur CH4 : 'CH4' ou 'value' ou 'CH4_mean' ou 'CH4_ppb'
                ch4_candidates = [c for c in df_daily_local.columns if 'ch4' in c.lower() or 'value' in c.lower() or 'ppb' in c.lower()]
                if ch4_candidates:
                    ch4_col = ch4_candidates[0]
                    ch4_today = float(last[ch4_col])
                else:
                    # fallback : essayer colonnes numériques
                    numeric_cols = df_daily_local.select_dtypes(include=[np.number]).columns.tolist()
                    if numeric_cols:
                        ch4_today = float(last[numeric_cols[-1]])
                    else:
                        ch4_today = 0.0
            else:
                ch4_today = 0.0
        except Exception as e:
            st.error(f"Erreur lecture CSV daily: {e}")
            ch4_today = 0.0
    else:
        # Si pas de CSV daily, on simule (ou tu peux remplacer par appel GEE)
        ch4_today = 1935.0

    threshold = 1900.0
    date_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Déterminer l'action HSE
    if ch4_today > threshold:
        action_hse = "Alerter, sécuriser la zone et stopper opérations"
    elif ch4_today > threshold - 50:
        action_hse = "Surveillance renforcée et vérification des torches"
    else:
        action_hse = "Surveillance continue"

    # Stocker en session pour PDF
    st.session_state['analysis_today'] = {
        "date": date_now,
        "ch4": ch4_today,
        "anomaly": ch4_today > threshold,
        "action": action_hse,
        "threshold": threshold
    }

    # Affichage
    st.write(f"**CH₄ du jour :** {ch4_today} ppb  ({date_now})")
    if ch4_today > threshold:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4_today > threshold - 50:
        st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
    else:
        st.success("CH₄ normal, aucune anomalie détectée.")

    # Tableau
    anomalies_today_df = pd.DataFrame([{
        "Date": date_now.split()[0],
        "Heure": date_now.split()[1],
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH4 (ppb)": ch4_today,
        "Anomalie": "Oui" if ch4_today > threshold else "Non",
        "Action HSE": action_hse
    }])
    st.table(anomalies_today_df)

# ===================== SECTION F: Générer PDF du jour (bouton) =====================
st.markdown("## 📄 Générer rapport PDF du jour (professionnel)")
if st.button("Générer rapport PDF du jour"):
    analysis = st.session_state.get('analysis_today')
   with colp2:
    if st.button("Générer rapport période (PDF)"):
        if filtered.empty:
            st.warning("Aucune donnée pour la période sélectionnée.")
        else:
            # calcul synthèse
            val_col = None
            for c in filtered.columns:
                if 'ch4' in c.lower() and ('mean' in c.lower() or 'value' in c.lower() or 'ppb' in c.lower()):
                    val_col = c
                    break
            if val_col is None:
                numeric_cols = filtered.select_dtypes(include=[np.number]).columns.tolist()
                val_col = numeric_cols[0] if numeric_cols else None

            if val_col:
                mean_period = float(filtered[val_col].mean())
            else:
                mean_period = 0.0

            anomaly_flag_period = mean_period >= 1900
            action_period = ("Alerter, sécuriser la zone et stopper opérations" if anomaly_flag_period else "Surveillance continue")
            hazop_df_period = hazop_analysis(mean_period)

            report_date_str = f"{pdf_date_range[0]}_to_{pdf_date_range[1]}"
            pdf_bytes_period = generate_pdf_bytes_professional(
                site_name=site_name,
                latitude=latitude,
                longitude=longitude,
                report_date=report_date_str,
                ch4_value=round(mean_period,2),
                anomaly_flag=anomaly_flag_period,
                action_hse=action_period,
                hazop_df=hazop_df_period
            )
            st.download_button(
                label="⬇ Télécharger le rapport PDF (période sélectionnée)",
                data=pdf_bytes_period,
                file_name=f"Rapport_HSE_CH4_{site_name}_{report_date_str}.pdf",
                mime="application/pdf"
            )

# ===================== SECTION G: Rapport PDF professionnel annuel (bouton) =====================
st.markdown("## 📄 Générer rapport PDF professionnel (annuel)")
if st.button("Générer rapport PDF professionnel (année sélectionnée)"):
    # Utilise df_annual si disponible
    if os.path.exists(csv_annual):
        try:
            df_annual_local = pd.read_csv(csv_annual)
            if year_choice in df_annual_local['year'].values:
                mean_ch4_year = float(df_annual_local[df_annual_local['year']==year_choice]['CH4_mean'].values[0])
                risk = ("Faible" if mean_ch4_year < 1800 else
                        "Modéré" if mean_ch4_year < 1850 else
                        "Élevé" if mean_ch4_year < 1900 else "Critique")
                action = ("Surveillance continue." if mean_ch4_year < 1800 else
                          "Vérifier les torches et informer l'équipe HSE." if mean_ch4_year < 1850 else
                          "Inspection urgente du site et mesures de sécurité immédiates." if mean_ch4_year < 1900 else
                          "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire.")
                hazop_df_local = hazop_analysis(mean_ch4_year)
                pdf_bytes = generate_pdf_bytes_professional(
                    site_name=site_name,
                    latitude=latitude,
                    longitude=longitude,
                    report_date=str(year_choice),
                    ch4_value=mean_ch4_year,
                    anomaly_flag=(mean_ch4_year >= 1900),
                    action_hse=action,
                    hazop_df=hazop_df_local
                )
                st.download_button(
                    label="⬇ Télécharger le rapport PDF professionnel (annuel)",
                    data=pdf_bytes,
                    file_name=f"Rapport_HSE_CH4_{site_name}_{year_choice}.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Données annuelles pour cette année non trouvées.")
        except Exception as e:
            st.error(f"Erreur génération PDF annuel: {e}")
    else:
        st.warning("CSV annuel introuvable, impossible de générer le PDF annuel.")
# ------------------------ ETAPE 5 : DASHBOARD HISTORIQUE & ANALYSES ------------------------
st.markdown("## 📈 Dashboard Historique CH₄ (2020-2024)")

# --- 1) Charger (ou valider) les CSV historiques ---
# On réutilise csv_global, csv_annual, csv_monthly définis plus haut ; sinon on essaie de les lire à la volée.
df_hist = pd.DataFrame()
if os.path.exists(csv_global):
    try:
        df_hist = pd.read_csv(csv_global)
    except Exception as e:
        st.error(f"Erreur lecture {csv_global}: {e}")

# Si pas de csv_global, essayer csv_monthly/annual to build basic frame
if df_hist.empty and os.path.exists(csv_monthly):
    try:
        df_hist = pd.read_csv(csv_monthly)
    except Exception:
        df_hist = pd.DataFrame()

# --- 2) Normaliser colonne date si présente ---
def find_date_col(df):
    if df is None or df.empty:
        return None
    for c in df.columns:
        if 'date' in c.lower() or 'time' in c.lower():
            return c
    # fallback: try parse first column
    try:
        pd.to_datetime(df.iloc[:, 0])
        return df.columns[0]
    except Exception:
        return None

date_col = find_date_col(df_hist)
if date_col:
    try:
        df_hist['__date'] = pd.to_datetime(df_hist[date_col])
    except Exception:
        # try infer
        df_hist['__date'] = pd.to_datetime(df_hist[date_col], errors='coerce')
else:
    df_hist['__date'] = pd.NaT

# --- 3) UI : filtres (période, anomalie, année) ---
st.markdown("### 🔎 Filtres historiques")
colf1, colf2, colf3 = st.columns([2,2,2])

with colf1:
    if not df_hist.empty and df_hist['__date'].notna().any():
        min_date = df_hist['__date'].min().date()
        max_date = df_hist['__date'].max().date()
    else:
        # fallback dates
        min_date = datetime(2020,1,1).date()
        max_date = datetime.now().date()
    date_range = st.date_input("Période", [min_date, max_date])

with colf2:
    anomaly_filter = st.selectbox("Filtrer par anomalie", ["Tous","Anomalies seulement","Normales seulement"])

with colf3:
    year_filter = st.selectbox("Filtrer par année (optionnel)", ["Toutes"] + [2020,2021,2022,2023,2024])

# --- 4) Appliquer filtres ---
filtered = df_hist.copy() if not df_hist.empty else pd.DataFrame()
if not filtered.empty and '__date' in filtered.columns:
    start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered = filtered[(filtered['__date'] >= pd.to_datetime(start_d)) & (filtered['__date'] <= pd.to_datetime(end_d + pd.Timedelta(days=1)))]
# anomaly column detection
anomaly_col = None
for c in filtered.columns:
    if 'anomal' in c.lower() or 'alert' in c.lower() or 'flag' in c.lower():
        anomaly_col = c
        break
# try common names
if anomaly_col is None:
    for c in filtered.columns:
        if 'ch4' in c.lower() and 'mean' not in c.lower():
            # leave
            pass

if anomaly_filter != "Tous" and not filtered.empty:
    if anomaly_col:
        if anomaly_filter == "Anomalies seulement":
            filtered = filtered[filtered[anomaly_col].astype(bool)]
        elif anomaly_filter == "Normales seulement":
            filtered = filtered[~filtered[anomaly_col].astype(bool)]

if year_filter != "Toutes" and not filtered.empty:
    if '__date' in filtered.columns:
        filtered = filtered[filtered['__date'].dt.year == int(year_filter)]

# --- 5) Afficher tableau historique filtré et options d'export ---
st.markdown("### 🗂️ Historique filtré")
if filtered.empty:
    st.info("Aucune donnée historique trouvée pour les critères sélectionnés.")
else:
    # show dataframe (remove internal __date if present)
    to_show = filtered.copy()
    if '__date' in to_show.columns:
        to_show['Date'] = to_show['__date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        to_show = to_show.drop(columns=['__date'])
    st.dataframe(to_show, use_container_width=True)

    # Export CSV du filtre
    csv_bytes = to_show.to_csv(index=False).encode('utf-8')
    st.download_button("⬇ Exporter historique filtré (CSV)", data=csv_bytes, file_name=f"Historique_CH4_{date_range[0]}_to_{date_range[1]}.csv", mime="text/csv")

# --- 6) Graphiques : mensuel / anomalies / comparatif annuel ---
st.markdown("### 📊 Graphiques")

# 6a) Série temporelle mensuelle (si monthly CSV disponible)
if os.path.exists(csv_monthly):
    try:
        df_month = pd.read_csv(csv_monthly)
        # chercher colonnes
        # supposer colonnes 'year','month','CH4_mean' ou 'date' et 'CH4'...
        if 'year' in df_month.columns and 'month' in df_month.columns and 'CH4_mean' in df_month.columns:
            # créer date
            df_month['__date'] = pd.to_datetime(df_month['year'].astype(str) + '-' + df_month['month'].astype(str) + '-01')
            fig, ax = plt.subplots(figsize=(8,3))
            ax.plot(df_month['__date'], df_month['CH4_mean'], marker='o')
            ax.set_title("CH₄ mensuel (moyenne)")
            ax.set_xlabel("Date")
            ax.set_ylabel("CH₄ (ppb)")
            ax.grid(True)
            st.pyplot(fig)
        else:
            st.info("CSV monthly présent mais format inattendu pour le graphique mensuel.")
    except Exception as e:
        st.error(f"Erreur génération graphique mensuel: {e}")
else:
    st.info("CSV mensuel introuvable pour graphique mensuel.")

# 6b) Anomalies over time (count per month) built from df_hist if exists
if not df_hist.empty and '__date' in df_hist.columns:
    try:
        tmp = df_hist.copy()
        # try find ch4 value column
        val_col = None
        for c in tmp.columns:
            if 'ch4' in c.lower() and ('mean' in c.lower() or 'value' in c.lower() or 'ppb' in c.lower()):
                val_col = c
                break
        if val_col is None:
            # fallback numeric column
            numeric_cols = tmp.select_dtypes(include=[np.number]).columns.tolist()
            val_col = numeric_cols[0] if numeric_cols else None

        if val_col:
            tmp['year_month'] = tmp['__date'].dt.to_period('M').dt.to_timestamp()
            # anomaly if >1900 or if anomaly column present
            if anomaly_col:
                tmp['is_anomaly'] = tmp[anomaly_col].astype(bool)
            else:
                tmp['is_anomaly'] = tmp[val_col].astype(float) >= 1900
            monthly = tmp.groupby('year_month')['is_anomaly'].sum().reset_index()
            fig2, ax2 = plt.subplots(figsize=(8,3))
            ax2.bar(monthly['year_month'].dt.strftime('%Y-%m'), monthly['is_anomaly'], color='red')
            ax2.set_title("Nombre d'anomalies détectées par mois")
            ax2.set_xticklabels(monthly['year_month'].dt.strftime('%Y-%m'), rotation=45, ha='right')
            st.pyplot(fig2)
        else:
            st.info("Impossible de déterminer la colonne CH₄ pour le graphique anomalies.")
    except Exception as e:
        st.error(f"Erreur génération graphique anomalies: {e}")
else:
    st.info("Données historiques insuffisantes pour graphique anomalies.")

# 6c) Comparatif annuel (utilise csv_annual si disponible ou agrégé de df_hist)
st.markdown("### 📈 Comparatif annuel")
df_ann_local = pd.DataFrame()
if os.path.exists(csv_annual):
    try:
        df_ann_local = pd.read_csv(csv_annual)
    except Exception as e:
        st.error(f"Erreur lecture CSV annuel: {e}")

if df_ann_local.empty and not df_hist.empty and '__date' in df_hist.columns:
    try:
        tmp2 = df_hist.copy()
        # detect val column
        val_col = None
        for c in tmp2.columns:
            if 'ch4' in c.lower() and ('mean' in c.lower() or 'value' in c.lower() or 'ppb' in c.lower()):
                val_col = c
                break
        if val_col:
            tmp2['year'] = tmp2['__date'].dt.year
            df_ann_local = tmp2.groupby('year')[val_col].mean().reset_index().rename(columns={val_col:'CH4_mean'})
    except Exception:
        df_ann_local = pd.DataFrame()

if not df_ann_local.empty and 'year' in df_ann_local.columns and 'CH4_mean' in df_ann_local.columns:
    fig3, ax3 = plt.subplots(figsize=(8,3))
    ax3.plot(df_ann_local['year'], df_ann_local['CH4_mean'], marker='o')
    ax3.set_title("Comparatif annuel CH₄")
    ax3.set_xlabel("Année")
    ax3.set_ylabel("CH₄ (ppb)")
    ax3.grid(True)
    st.pyplot(fig3)
else:
    st.info("Pas de données annuelles disponibles pour comparatif.")

# --- 7) Exporter une période en PDF (synthèse période) ---
st.markdown("## 📝 Générer un rapport PDF pour une période")
colp1, colp2 = st.columns([2,1])
with colp1:
    pdf_date_range = st.date_input("Choisir période pour le rapport", [min_date, max_date])
with colp2:
    if st.button("Générer rapport période (PDF)"):
        if filtered.empty:
            st.warning("Aucune donnée pour la période sélectionnée.")
        else:
            # calcul synthèse
            # choose ch4 mean from filtered numeric column
            val_col = None
            for c in filtered.columns:
                if 'ch4' in c.lower() and ('mean' in c.lower() or 'value' in c.lower() or 'ppb' in c.lower()):
                    val_col = c
                    break
            if val_col is None:
                numeric_cols = filtered.select_dtypes(include=[np.number]).columns.tolist()
                val_col = numeric_cols[0] if numeric_cols else None

            if val_col:
                mean_period = float(filtered[val_col].mean())
            else:
                mean_period = 0.0

            anomaly_flag_period = mean_period >= 1900
            action_period = ("Alerter, sécuriser la zone et stopper opérations" if anomaly_flag_period else "Surveillance continue")
            # Create HAZOP summary
            hazop_df_period = hazop_analysis(mean_period)

            report_date_str = f"{pdf_date_range[0]}_to_{pdf_date_range[1]}"
            pdf_bytes_period = generate_pdf_bytes_professional(
                site_name=site_name,
                latitude=latitude,
                longitude=longitude,
                report_date=report_date_str,
                ch4_value=round(mean_period,2),
                anomaly_flag=anomaly_flag_period,
                action_hse=action_period,
                hazop_df=hazop_df_period
            )
            st.download_button(
                label="⬇ Télécharger le rapport PDF (période sélectionnée)",
