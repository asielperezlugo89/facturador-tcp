"""Generador PDF de FACTURA DE VENTA y OFERTA COMERCIAL (formato TCP Cuba).
Replica el formato del Factura.pdf original. Usa fpdf2 (puro Python,
compatible con Wasmer Edge). Soporta cuno/firma PNG como bytes.
"""
import io
from fpdf import FPDF


def _t(s):
    """Sanitiza texto para fuentes core (latin-1): evita crash con emojis/raros."""
    return str(s if s is not None else "").encode("latin-1", "replace").decode("latin-1")


def fmt_money(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        n = 0.0
    entero = int(round(n))
    dec = int(round((n - int(n)) * 100))
    if dec < 0:
        dec = 0
    s = f"{entero:,}".replace(",", " ")
    return f"{s}.{dec:02d}"


def fmt_fecha(fecha_iso):
    # 'YYYY-MM-DD' -> 'DD/MM/YYYY'
    if not fecha_iso:
        return ""
    p = str(fecha_iso).split(" ")[0].split("-")
    if len(p) == 3:
        return f"{p[2]}/{p[1]}/{p[0]}"
    return str(fecha_iso)


class DocPDF(FPDF):
    pass


def _header_block(pdf, tcp, tipo, numero_txt, fecha_txt, contrato):
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _t(tipo), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, _t(f"No. {numero_txt}"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _t(f"FECHA: {fecha_txt}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    def fila(label, val):
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(5.5, _t(label + " "))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5.5, _t(val or ""))

    fila("NOMBRE Y APELLIDOS: T.C.P.", tcp.get("nombre_apellidos", ""))
    fila("DIRECCIÓN:", tcp.get("direccion", ""))
    pdf.set_font("Helvetica", "B", 10)
    pdf.write(5.5, "CARNÉ DE IDENTIDAD: ")
    pdf.set_font("Helvetica", "", 10)
    pdf.write(5.5, _t(str(tcp.get("ci", ""))) + "      ")
    pdf.set_font("Helvetica", "B", 10)
    pdf.write(5.5, "NIT: ")
    pdf.set_font("Helvetica", "", 10)
    pdf.write(5.5, _t(str(tcp.get("nit", ""))))
    pdf.ln(5.5)
    fila("CUENTA BANCARIA CUP:", tcp.get("cuenta_cup", ""))
    fila("AGENCIA BANCARIA:", tcp.get("agencia", ""))
    fila("CÓDIGO DE BARRA:", tcp.get("codigo_barra", ""))
    if contrato is not None:
        fila("CONTRATO No.:", contrato if contrato else "_____________.")
    pdf.ln(2)


def _tabla_items(pdf, items):
    W = pdf.w - pdf.l_margin - pdf.r_margin
    cols = [
        ("DESCRIPCIÓN", W * 0.44),
        ("U/M", W * 0.08),
        ("CANTIDAD", W * 0.12),
        ("PRECIO", W * 0.17),
        ("IMPORTE", W * 0.19),
    ]
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 10)
    for titulo, ancho in cols:
        pdf.cell(ancho, 7, titulo, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    total = 0.0
    line_h = 6
    for it in items:
        desc = _t(it.get("descripcion", ""))
        um = _t(it.get("um", "U"))
        try:
            cant = float(it.get("cantidad", 0))
        except (TypeError, ValueError):
            cant = 0
        try:
            precio = float(it.get("precio", 0))
        except (TypeError, ValueError):
            precio = 0
        imp = cant * precio
        total += imp
        cant_txt = f"{cant:g}"
        n_lines = max(1, int(pdf.get_string_width(desc) / (cols[0][1] - 2)) + 1)
        h = max(line_h, n_lines * line_h)
        if pdf.get_y() + h > pdf.page_break_trigger:
            pdf.add_page()
        x0, y0 = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x0, y0)
        pdf.multi_cell(cols[0][1], line_h, desc, border=1)
        h_real = pdf.get_y() - y0
        pdf.set_xy(x0 + cols[0][1], y0)
        pdf.cell(cols[1][1], h_real, um, border=1, align="C")
        pdf.cell(cols[2][1], h_real, cant_txt, border=1, align="C")
        pdf.cell(cols[3][1], h_real, fmt_money(precio), border=1, align="R")
        pdf.cell(cols[4][1], h_real, fmt_money(imp), border=1, align="R")
        pdf.ln()
        pdf.set_y(y0 + h_real)
    pdf.set_font("Helvetica", "B", 11)
    w_total_label = sum(c[1] for c in cols[:-1])
    pdf.cell(w_total_label, 8, "TOTAL", border=1, align="R")
    pdf.cell(cols[-1][1], 8, fmt_money(total), border=1, align="R")
    pdf.ln()
    return total


def _bloque_cliente(pdf, cli):
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "CLIENTE", new_x="LMARGIN", new_y="NEXT")

    def fila(label, val, placeholder_len=45):
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(5.5, _t(label + " "))
        pdf.set_font("Helvetica", "", 10)
        v = _t(val or "")
        if not v:
            v = "_" * placeholder_len
        pdf.multi_cell(0, 5.5, v)

    fila("EMPRESA:", cli.get("empresa", ""))
    fila("CUENTA BANCARIA CUP:", cli.get("cuenta_cup", ""), 28)
    fila("CUENTA BANCARIA CUC:", cli.get("cuenta_cuc", ""), 28)
    fila("AGENCIA BANCARIA:", cli.get("agencia", ""), 40)
    fila("CÓDIGO:", cli.get("codigo", ""), 20)
    fila("NIT:", cli.get("nit", ""), 20)


def _firmas_factura(pdf, tcp, cuno_bytes, firma_bytes):
    pdf.ln(4)
    y_top = pdf.get_y()
    if y_top > pdf.page_break_trigger - 45:
        pdf.add_page()
        y_top = pdf.get_y()
    W = pdf.w - pdf.l_margin - pdf.r_margin
    col = W / 2
    x0 = pdf.l_margin

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(x0, y_top)
    pdf.cell(col, 6, "VENDEDOR")
    pdf.cell(col, 6, "RECIBIDO")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(x0)
    pdf.cell(col, 6, "Confeccionado por:")
    pdf.cell(col, 6, "")
    pdf.ln()

    def two(a, b):
        pdf.set_x(x0)
        pdf.cell(col, 6, _t(a))
        pdf.cell(col, 6, _t(b))
        pdf.ln()

    two(f"Nombre: {tcp.get('nombre_apellidos','')}"[:40], "Nombre Apellidos: _______________")
    two(f"Cargo: {tcp.get('cargo','TCP')}", "Cargo: ______________________")
    two(f"Carné Identidad: {tcp.get('ci','')}", "Carné Identidad: ______________")

    y_firma = pdf.get_y() + 2
    # Cuno: esquina inferior-derecha de la columna vendedor, junto a la firma, sin tapar texto
    if cuno_bytes:
        try:
            pdf.image(io.BytesIO(cuno_bytes), x=x0 + col - 38, y=y_firma - 14, w=34)
        except Exception:
            pass
    # Firma sobre su raya
    if firma_bytes:
        try:
            pdf.image(io.BytesIO(firma_bytes), x=x0 + 14, y=y_firma - 12, w=42)
        except Exception:
            pass
    pdf.set_xy(x0, y_firma)
    pdf.cell(col, 6, "Firma: ________________")
    pdf.cell(col, 6, "Firma: ________________")


def _firmas_oferta(pdf, tcp, cuno_bytes, firma_bytes):
    pdf.ln(4)
    y_top = pdf.get_y()
    if y_top > pdf.page_break_trigger - 40:
        pdf.add_page()
        y_top = pdf.get_y()
    x0 = pdf.l_margin
    pdf.set_xy(x0, y_top)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Confeccionado por:", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _t(f"Nombre y Apellidos: {tcp.get('nombre_apellidos','')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _t(f"Cargo: {tcp.get('cargo','TCP')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _t(f"Carné Identidad: {tcp.get('ci','')}"), new_x="LMARGIN", new_y="NEXT")
    y_firma = pdf.get_y() + 2
    # Cuno a la derecha de la firma, sin tapar texto
    if cuno_bytes:
        try:
            pdf.image(io.BytesIO(cuno_bytes), x=x0 + 110, y=y_firma - 16, w=34)
        except Exception:
            pass
    if firma_bytes:
        try:
            pdf.image(io.BytesIO(firma_bytes), x=x0 + 14, y=y_firma - 12, w=42)
        except Exception:
            pass
    pdf.set_xy(x0, y_firma)
    pdf.cell(0, 6, "Firma: ________________")


def generar_pdf(tipo, tcp, cliente, items, numero_txt, fecha_txt, contrato="",
                numero_blanco=False, fecha_blanco=False,
                cuno_bytes=None, firma_bytes=None):
    """Devuelve bytes del PDF. tipo: 'factura' u 'oferta'."""
    pdf = DocPDF("P", "mm", "Letter")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    es_factura = (tipo == "factura")
    titulo = "FACTURA DE VENTA" if es_factura else "OFERTA COMERCIAL"
    num = "_______" if numero_blanco or not numero_txt else numero_txt
    fec = "__/__/____" if fecha_blanco or not fecha_txt else fecha_txt

    _header_block(pdf, tcp, titulo, num, fec, contrato if es_factura else None)
    _tabla_items(pdf, items)
    _bloque_cliente(pdf, cliente or {})
    if es_factura:
        _firmas_factura(pdf, tcp, cuno_bytes, firma_bytes)
    else:
        _firmas_oferta(pdf, tcp, cuno_bytes, firma_bytes)

    out = pdf.output()
    return bytes(out)
