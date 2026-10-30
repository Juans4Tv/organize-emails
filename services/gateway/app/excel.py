import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from shared.db import Document, Email, Place


def documents_workbook(rows: list[tuple[Document, Place | None, Email | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Documentos"

    headers = [
        "Lugar", "Archivo", "Tipo", "Flujo", "Monto", "Moneda",
        "Fecha documento", "Estado", "Confianza", "Cuenta",
        "Correo origen", "Link manual",
    ]
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    flow_labels = {"gasto": "Gasto", "ganancia": "Ganancia", "neutral": "Neutro"}

    for i, (doc, place, email) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=place.name if place else "")
        ws.cell(row=i, column=2, value=doc.original_name)
        ws.cell(row=i, column=3, value=doc.doc_kind)
        ws.cell(row=i, column=4, value=flow_labels.get(doc.flow, doc.flow))
        amount_cell = ws.cell(row=i, column=5, value=doc.amount)
        amount_cell.number_format = "#,##0.00"
        ws.cell(row=i, column=6, value=doc.currency)
        date_value = doc.doc_date.strftime("%Y-%m-%d") if doc.doc_date else ""
        ws.cell(row=i, column=7, value=date_value)
        estado = doc.status + (" (revisar)" if doc.needs_review else "")
        ws.cell(row=i, column=8, value=estado)
        ws.cell(row=i, column=9, value=round(doc.confidence, 2))
        ws.cell(row=i, column=10, value=doc.account)
        if email is not None:
            ws.cell(row=i, column=11,
                    value=f"{email.sender_name} <{email.sender_email}> {email.date_received.strftime('%Y-%m-%d') if email.date_received else ''}")
        ws.cell(row=i, column=12, value=doc.link_url or "")

    widths = [28, 36, 14, 12, 14, 9, 15, 20, 11, 30, 42, 40]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(2, len(rows) + 1)}"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
