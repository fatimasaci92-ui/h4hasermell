def generate_pdf_bytes(site_name, latitude, longitude, year, mean_ch4, risk_level, actions_reco):
    buffer = io.BytesIO()

    file_name = f"Rapport_HSE_CH4_{site_name}_{year}.pdf"

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=file_name
    )

    styles = getSampleStyleSheet()
    story = []

    # ---------------------- TITRE ----------------------
    title = """
    <para align='center'>
    <b><font size=18>RAPPORT TECHNIQUE HSE – SURVEILLANCE MÉTHANE</font></b>
    </para>
    """
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 20))

    # ---------------------- MÉTA-DONNÉES ----------------------
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    meta = f"""
    <b>Date du rapport :</b> {date_str}<br/>
    <b>Site analysé :</b> {site_name}<br/>
    <b>Latitude :</b> {latitude}<br/>
    <b>Longitude :</b> {longitude}<br/>
    <b>Année analysée :</b> {year}<br/>
    """
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 20))

    # ---------------------- TABLEAU ----------------------
    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration moyenne CH₄", f"{mean_ch4:.2f} ppb"],
        ["Niveau de risque HSE", risk_level],
    ]

    table = Table(table_data, colWidths=[200, 250])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#F3F4F6")),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
    ]))

    story.append(table)
    story.append(Spacer(1, 25))

    # ---------------------- ANALYSE DU RISQUE ----------------------
    risk_text = f"""
    <b>Analyse du risque :</b><br/><br/>
    Le niveau de risque détecté en <b>{year}</b> est :  
    <b>{risk_level}</b>.<br/><br/>

    Une concentration élevée de CH₄ augmente significativement :<br/>
    • Le risque d'explosion (gaz hautement inflammable)<br/>
    • L’asphyxie en zone confinée<br/>
    • L’instabilité opérationnelle<br/>
    • Le risque d’incendie continu<br/><br/>

    Analyse conforme aux référentiels : API, OSHA, ISO 45001.
    """
    story.append(Paragraph(risk_text, styles["Normal"]))
    story.append(Spacer(1, 25))

    # ---------------------- ACTIONS ----------------------
    actions_text = f"""
    <b>Actions recommandées :</b><br/><br/>
    {actions_reco}<br/><br/>
    """
    story.append(Paragraph(actions_text, styles["Normal"]))
    story.append(Spacer(1, 25))

    # ---------------------- FOOTER ----------------------
    footer = """
    <para align='center'>
    <font size=10 color="#6B7280">
    Rapport généré automatiquement — Système HSE CH₄<br/>
    Conforme aux bonnes pratiques ISO 45001
    </font>
    </para>
    """
    story.append(Paragraph(footer, styles["Normal"]))

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data
