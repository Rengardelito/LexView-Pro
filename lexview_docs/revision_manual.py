import os

from .pdf import crear_doc, header, resumen_cards, tabla, parrafo, footer


def generar_revision_manual(
    ruta_local,
    fallidos,
    descargas_totales=0,
    motivo="Forum devolvió error o no permitió reintentar algunos archivos.",
):
    os.makedirs(ruta_local, exist_ok=True)

    pdf_path = os.path.join(ruta_local, "REVISION MANUAL - LEER.pdf")

    doc = crear_doc(pdf_path)
    story = []

    header(
        story,
        "Informe de sincronización parcial",
        "Algunos documentos no pudieron descargarse automáticamente y requieren verificación manual.",
    )

    resumen_cards(story, [
        ("Documentos descargados correctamente", descargas_totales),
        ("Documentos pendientes de revisión", len(fallidos)),
        ("Estado", "Sincronización parcial"),
    ])

    parrafo(story, f"<b>Motivo:</b> {motivo}")

    rows = []
    for item in fallidos:
        rows.append([
            str(item.get("fecha_iso", "")),
            str(item.get("tipo_str", ""))[:70],
            str(item.get("numero_id", "")),
            str(item.get("pagina", "")),
        ])

    tabla(
        story,
        ["Fecha", "Extracto", "ID Forum", "Página"],
        rows,
    )

    parrafo(
        story,
        "Acción sugerida: ingresar manualmente al expediente en Forum y verificar los documentos indicados.",
    )

    footer(story)

    doc.build(story)

    print(f"📝 Informe de revisión manual generado: {pdf_path}")
    return pdf_path