from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .theme import (
    PRIMARY,
    SECONDARY,
    SUCCESS,
    WARNING,
    LIGHT,
    DARK_TEXT,
    TITLE_FONT,
    TEXT_FONT,
    MARGIN,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    WEBSITE,
    VERSION_LABEL,
)


def crear_doc(path):
    return SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )


def estilos():
    base = getSampleStyleSheet()

    base.add(ParagraphStyle(
        name="LexTitle",
        parent=base["Title"],
        fontName=TITLE_FONT,
        fontSize=22,
        textColor=colors.HexColor(PRIMARY),
        spaceAfter=10,
    ))

    base.add(ParagraphStyle(
        name="LexSubtitle",
        parent=base["BodyText"],
        fontName=TEXT_FONT,
        fontSize=10,
        textColor=colors.HexColor(DARK_TEXT),
        spaceAfter=12,
    ))

    base.add(ParagraphStyle(
        name="LexSmall",
        parent=base["BodyText"],
        fontName=TEXT_FONT,
        fontSize=8,
        textColor=colors.HexColor(DARK_TEXT),
    ))

    return base


def header(story, titulo, subtitulo=""):
    s = estilos()

    story.append(Paragraph(PRODUCT_NAME.upper(), s["LexSmall"]))
    story.append(Paragraph(titulo, s["LexTitle"]))

    if subtitulo:
        story.append(Paragraph(subtitulo, s["LexSubtitle"]))

    story.append(Spacer(1, 10))


def resumen_cards(story, cards):
    data = []

    for label, value in cards:
        data.append([
            Paragraph(f"<b>{value}</b><br/>{label}", estilos()["BodyText"])
        ])

    table = Table(data, colWidths=[480])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(SECONDARY)),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(table)
    story.append(Spacer(1, 14))


def tabla(story, headers, rows):
    data = [headers] + rows

    table = Table(data, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PRIMARY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), TITLE_FONT),
        ("FONTNAME", (0, 1), (-1, -1), TEXT_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    story.append(table)
    story.append(Spacer(1, 14))


def parrafo(story, texto):
    s = estilos()
    story.append(Paragraph(texto, s["BodyText"]))
    story.append(Spacer(1, 8))


def footer(story):
    s = estilos()

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generado automáticamente por <b>{PRODUCT_NAME}</b><br/>"
        f"{PRODUCT_TAGLINE}<br/>"
        f"{VERSION_LABEL} · {WEBSITE}<br/>"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        s["LexSmall"]
    ))