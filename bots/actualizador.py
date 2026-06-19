# bots/actualizador.py
import os
import re
import time
import shutil
from datetime import date, datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from bots.forum_driver import login_forum, descargar_pdfs_nuevos, buscar_expediente, esperar_tabla_actuaciones
from bots.driver_manager import get_driver, release_driver, is_logged_in, marcar_ocupado, marcar_libre
from database.models import db, CausaInfo, Usuario
import config

from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import traceback
import json     
    
    

# ══════════════════════════════════════════════════════════════════════════════
# MEJORA 1 — PDF UNIFICADO
# ══════════════════════════════════════════════════════════════════════════════

def _es_proveido(nombre_pdf: str) -> bool:
    """
    Determina si un PDF es un proveído (resolución del juzgado) o un escrito de parte.
    
    Lógica: en Forum, el Extracto de los escritos empieza con la fecha de presentación
    en formato DD/MM/YYYY o DD_MM_YYYY. Los proveídos empiezan con texto descriptivo.
    
    El nombre del archivo tiene formato: "YYYY-MM-DD - EXTRACTO_numero.pdf"
    Entonces miramos lo que viene después del " - " inicial.
    """
    import re
    nombre = os.path.basename(nombre_pdf)
    # Quitar prefijo de fecha del nombre: "2026-05-08 - "
    partes = nombre.split(' - ', 1)
    if len(partes) < 2:
        return True  # si no tiene formato esperado, incluir por las dudas
    extracto = partes[1]
    # Si el extracto empieza con una fecha DD/MM/YYYY o DD_MM_YYYY → escrito de parte
    patron_fecha = r'^\d{1,2}[/_]\d{1,2}[/_]\d{2,4}'
    if re.match(patron_fecha, extracto):
        return False  # es escrito de parte, NO es proveído
    return True  # es proveído


def generar_pdf_resumen(pdfs_del_dia: list[dict], fecha_str: str | None, socketio):
    """
    Combina todos los PDFs descargados en el día en un único archivo con:
      - Página de índice al inicio
      - Página separadora antes de cada expediente
      - PDFs originales a continuación

    IMPORTANTE:
    - Incluye TODOS los PDFs descargados, no solo proveídos.
    - El resumen refleja expedientes que tuvieron PDFs nuevos en esta corrida.
    - Si un expediente tuvo movimiento pero 0 PDFs nuevos, no entra al PDF unificado.
    """
    try:
        import fitz
        from datetime import date, datetime

        if not pdfs_del_dia:
            return

        # Incluir TODOS los PDFs descargados.
        # Antes se filtraban solo proveídos; eso hacía desaparecer expedientes
        # que tenían únicamente escritos de parte.
        pdfs_del_dia_filtrado = []
        for entry in pdfs_del_dia:
            paths = entry.get("paths") or []
            if not paths:
                continue

            entry_copia = dict(entry)
            entry_copia["paths"] = paths
            pdfs_del_dia_filtrado.append(entry_copia)

        pdfs_del_dia = pdfs_del_dia_filtrado

        if not pdfs_del_dia:
            socketio.emit('bot_status', {'msg': '📋 Sin PDFs nuevos para unificar'})
            return

        socketio.emit('bot_status', {'msg': '📎 Generando PDF resumen diario...'})

        fecha_label = fecha_str if fecha_str else date.today().strftime("%Y-%m-%d")
        fecha_display = datetime.strptime(fecha_label, "%Y-%m-%d").strftime("%d/%m/%Y")
        nombre_archivo = f"resumen_{fecha_label.replace('-', '')}.pdf"
        ruta_salida = os.path.join(config.RESUMEN_DIARIO_PATH, nombre_archivo)

        os.makedirs(config.RESUMEN_DIARIO_PATH, exist_ok=True)

        total_pdfs = sum(len(e.get("paths", [])) for e in pdfs_del_dia)

        def _nueva_pagina(doc, ancho=595, alto=842):
            return doc.new_page(width=ancho, height=alto)

        def _rect_fill(page, x0, y0, x1, y1, color):
            page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=color, fill=color)

        AZUL = (0.18, 0.33, 0.55)
        GRIS = (0.5, 0.5, 0.5)
        NEGRO = (0.1, 0.1, 0.1)
        BLANCO = (1.0, 1.0, 1.0)

        merger = fitz.open()

        # ── 1. Página de índice ───────────────────────────────────────────────
        pag = _nueva_pagina(merger)

        _rect_fill(pag, 0, 0, 595, 60, AZUL)

        pag.insert_text(
            fitz.Point(30, 38),
            "RESUMEN DIARIO DE NOTIFICACIONES",
            fontname="helv",
            fontsize=18,
            color=BLANCO
        )

        pag.insert_text(
            fitz.Point(30, 55),
            f"Fecha: {fecha_display}",
            fontname="helv",
            fontsize=10,
            color=BLANCO
        )

        y = 90

        _rect_fill(pag, 30, y, 565, y + 18, AZUL)

        pag.insert_text(fitz.Point(34, y + 13), "#", fontname="helv", fontsize=9, color=BLANCO)
        pag.insert_text(fitz.Point(55, y + 13), "Expediente", fontname="helv", fontsize=9, color=BLANCO)
        pag.insert_text(fitz.Point(170, y + 13), "Caratula", fontname="helv", fontsize=9, color=BLANCO)
        pag.insert_text(fitz.Point(500, y + 13), "PDFs", fontname="helv", fontsize=9, color=BLANCO)

        y += 20

        for i, entry in enumerate(pdfs_del_dia):
            bg = (0.94, 0.96, 1.0) if i % 2 == 0 else BLANCO

            if y > 780:
                pag = _nueva_pagina(merger)
                y = 40
                _rect_fill(pag, 30, y, 565, y + 18, AZUL)
                pag.insert_text(fitz.Point(34, y + 13), "#", fontname="helv", fontsize=9, color=BLANCO)
                pag.insert_text(fitz.Point(55, y + 13), "Expediente", fontname="helv", fontsize=9, color=BLANCO)
                pag.insert_text(fitz.Point(170, y + 13), "Caratula", fontname="helv", fontsize=9, color=BLANCO)
                pag.insert_text(fitz.Point(500, y + 13), "PDFs", fontname="helv", fontsize=9, color=BLANCO)
                y += 20

            _rect_fill(pag, 30, y, 565, y + 16, bg)

            nro_txt = f"{entry.get('tipo', '')} {entry.get('nro', '')}".strip()
            car_txt = entry.get("caratula", "")[:50]
            cant_txt = str(len(entry.get("paths", [])))

            pag.insert_text(fitz.Point(34, y + 11), str(i + 1), fontname="helv", fontsize=8, color=NEGRO)
            pag.insert_text(fitz.Point(55, y + 11), nro_txt, fontname="helv", fontsize=8, color=NEGRO)
            pag.insert_text(fitz.Point(170, y + 11), car_txt, fontname="helv", fontsize=8, color=NEGRO)
            pag.insert_text(fitz.Point(500, y + 11), cant_txt, fontname="helv", fontsize=8, color=NEGRO)

            y += 17

        y += 10

        if y > 790:
            pag = _nueva_pagina(merger)
            y = 40

        pag.insert_text(
            fitz.Point(30, y),
            f"Total: {len(pdfs_del_dia)} expediente(s) - {total_pdfs} PDF(s)",
            fontname="helv",
            fontsize=10,
            color=AZUL
        )

        # ── 2. Por cada expediente: separador + PDFs ──────────────────────────
        for entry in pdfs_del_dia:
            sep = _nueva_pagina(merger)

            _rect_fill(sep, 0, 0, 595, 70, AZUL)

            nro_titulo = f"EXPEDIENTE {entry.get('tipo', '')} N {entry.get('nro', '')}".strip()

            sep.insert_text(
                fitz.Point(30, 42),
                nro_titulo,
                fontname="helv",
                fontsize=16,
                color=BLANCO
            )

            y = 95

            sep.insert_text(fitz.Point(30, y), "Caratula:", fontname="helv", fontsize=11, color=NEGRO)
            y += 18

            caratula_txt = entry.get("caratula", "")
            palabras = caratula_txt.split()
            linea = ""

            for palabra in palabras:
                if len(linea) + len(palabra) + 1 > 80:
                    sep.insert_text(fitz.Point(30, y), linea, fontname="helv", fontsize=10, color=GRIS)
                    y += 15
                    linea = palabra
                else:
                    linea = (linea + " " + palabra).strip()

            if linea:
                sep.insert_text(fitz.Point(30, y), linea, fontname="helv", fontsize=10, color=GRIS)
                y += 20

            sep.insert_text(fitz.Point(30, y), "Juzgado:", fontname="helv", fontsize=11, color=NEGRO)
            sep.insert_text(fitz.Point(110, y), entry.get("juzgado", ""), fontname="helv", fontsize=10, color=GRIS)
            y += 20

            sep.insert_text(fitz.Point(30, y), "Secretaria:", fontname="helv", fontsize=11, color=NEGRO)
            sep.insert_text(fitz.Point(110, y), entry.get("secretaria", ""), fontname="helv", fontsize=10, color=GRIS)
            y += 20

            sep.insert_text(fitz.Point(30, y), f"Fecha notif.: {fecha_display}", fontname="helv", fontsize=10, color=NEGRO)
            y += 25

            sep.insert_text(
                fitz.Point(30, y),
                f"Archivos incluidos ({len(entry['paths'])}):",
                fontname="helv",
                fontsize=10,
                color=NEGRO
            )

            y += 18

            for path in entry["paths"]:
                if y > 800:
                    break

                sep.insert_text(
                    fitz.Point(40, y),
                    f"- {os.path.basename(path)}",
                    fontname="helv",
                    fontsize=9,
                    color=GRIS
                )

                y += 14

            for pdf_path in entry["paths"]:
                try:
                    with fitz.open(pdf_path) as pdf_doc:
                        merger.insert_pdf(pdf_doc)
                except Exception as e:
                    print(f"⚠️ No se pudo incluir {pdf_path}: {e}")

        merger.save(ruta_salida)
        merger.close()

        socketio.emit('bot_status', {
            'msg': f'📎 PDF resumen guardado: RESUMEN_DIARIO/{nombre_archivo}'
        })

    except Exception as e:
        traceback.print_exc()
        socketio.emit('bot_status', {'msg': f'⚠️ No se pudo generar PDF resumen: {str(e)}'})

def separar_juzgado_secretaria(texto_juzgado, texto_sec=""):
    texto_juzgado = (texto_juzgado or "").strip()
    texto_sec = (texto_sec or "").strip()

    if texto_sec and "SECRETARIA" in texto_sec.upper():
        return texto_juzgado, texto_sec.upper()

    m = re.search(
        r"(SECRETAR[ÍI]A\s*(?:NRO\.?|Nº|NO\.?)?\s*\d+)",
        texto_juzgado,
        re.IGNORECASE
    )

    if m:
        secretaria = m.group(1).upper().replace("Í", "I")
        juzgado = texto_juzgado[:m.start()].strip(" -")
        return juzgado, secretaria

    return texto_juzgado, "SECRETARIA UNICA"

def obtener_expedientes_con_movimiento(driver, matricula, socketio, fecha=None, alcance='capital'):

    wait = WebDriverWait(driver, 20)
    wait_corto = WebDriverWait(driver, 3)

    expedientes = []
    vistos = set()

    LOCALIDADES_PROVINCIAL = [
        'Capital', 'Alvear', 'Bella Vista', 'Beron de Astrada', 'Caa Cati',
        'Colonia Liebig', 'Concepcion', 'Curuzú Cuatiá', 'Empedrado', 'Esquina',
        'Gdor. Martinez', 'Gdor. Virasoro', 'Goya', 'Ita Ibate', 'Itati',
        'Ituzaingo', 'La Cruz', 'Loreto', 'Mburucuya', 'Mercedes', 'Mocoreta',
        'Monte Caseros', 'Paso de la Patria', 'Paso de los Libres', 'Perugorria',
        'Saladas', 'San Carlos', 'San Cosme', 'San Luis del Palmar', 'San Miguel',
        'San Roque', 'Santa Lucia', 'Santa Rosa', 'Santo Tome', 'Sauce', 'Yapeyu'
    ]

    localidades = (
        LOCALIDADES_PROVINCIAL
        if alcance == 'provincial'
        else ['Capital']
    )

    try:

        # =========================
        # ABRIR UNA SOLA VEZ
        # =========================
        driver.get(
            "https://forumna.juscorrientes.gov.ar/com.forumna.notificaciones"
        )

        wait.until(
            EC.presence_of_element_located(
                (By.ID, "vMATRICULA")
            )
        )

        for idx_loc, localidad in enumerate(localidades):

            t_ciclo = time.time()

            socketio.emit('bot_status', {
                'msg': (
                    f'🔍 Buscando en {localidad} '
                    f'({idx_loc+1}/{len(localidades)})...'
                ),
                'progreso': 15 + int(
                    (idx_loc / len(localidades)) * 10
                )
            })

            try:

                # =========================
                # SELECCIONAR LOCALIDAD
                # =========================
                combo = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.ID,
                            "COMBO_ID_LOCALIDADContainer_btnGroupDrop"
                        )
                    )
                )

                combo.click()

                opcion = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            f"//a[contains(., '{localidad}')]"
                        )
                    )
                )

                opcion.click()

                # =========================
                # MATRÍCULA
                # =========================
                input_mat = wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "vMATRICULA")
                    )
                )

                input_mat.click()
                input_mat.send_keys(Keys.CONTROL + "a")
                input_mat.send_keys(Keys.DELETE)

                driver.execute_script(
                    "arguments[0].value = arguments[1];",
                    input_mat,
                    str(matricula)
                )

                driver.execute_script("""
                    arguments[0].dispatchEvent(
                        new Event('change', { bubbles: true })
                    );
                """, input_mat)

                # =========================
                # FECHA
                # =========================
                if fecha:

                    try:

                        fecha_dt = datetime.strptime(
                            fecha,
                            "%Y-%m-%d"
                        )

                        fecha_forum = fecha_dt.strftime(
                            "%d/%m/%Y"
                        )

                        campo_fecha = driver.find_element(
                            By.ID,
                            "vFECHADATE"
                        )

                        campo_fecha.click()

                        campo_fecha.send_keys(
                            Keys.CONTROL + "a"
                        )

                        campo_fecha.send_keys(Keys.DELETE)

                        campo_fecha.send_keys(fecha_forum)

                        campo_fecha.send_keys(Keys.ESCAPE)

                    except Exception as e:

                        print(
                            f"⚠ No se pudo setear fecha "
                            f"en {localidad}: {e}"
                        )

                # =========================
                # GUARDAR GRID VIEJO
                # =========================
                try:
                    grid_viejo = driver.find_element(
                        By.XPATH,
                        "//table[contains(@class, 'Grid')]"
                    )
                except:
                    grid_viejo = None

                # =========================
                # CLICK BUSCAR
                # =========================
                btn = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//input[@value='Buscar']"
                        )
                    )
                )

                btn.click()

                # =========================
                # ESPERAR QUE MUERA GRID VIEJO
                # =========================
                if grid_viejo:

                    try:
                        wait.until(
                            EC.staleness_of(grid_viejo)
                        )

                    except TimeoutException:
                        pass

                # =========================
                # ESPERAR RESPUESTA NUEVA
                # =========================
                try:

                    wait_corto.until(
                        EC.any_of(

                            EC.presence_of_element_located(
                                (
                                    By.XPATH,
                                    "//*[contains(text(),'Cantidad')]"
                                )
                            ),

                            EC.presence_of_element_located(
                                (
                                    By.XPATH,
                                    "//table[contains(@class, 'Grid')]//tr[td]"
                                )
                            )
                        )
                    )

                except TimeoutException:

                    print(
                        f"⏱ {localidad}: "
                        f"{time.time()-t_ciclo:.1f}s "
                        f"→ timeout"
                    )

                    continue

                # =========================
                # HTML ACTUAL
                # =========================
                source = driver.page_source

                # =========================
                # SIN RESULTADOS
                # =========================
                if (
                    "Cantidad: 0" in source
                    or "No se encontraron registros" in source
                ):

                    print(
                        f"⏱ {localidad}: "
                        f"{time.time()-t_ciclo:.1f}s "
                        f"→ sin notificaciones"
                    )

                    continue

                # =========================
                # FILAS
                # =========================
                filas = driver.find_elements(
                    By.XPATH,
                    "//table[contains(@class, 'Grid')]//tr[td]"
                )

                if not filas:

                    print(
                        f"⏱ {localidad}: "
                        f"{time.time()-t_ciclo:.1f}s "
                        f"→ sin filas"
                    )

                    continue

                # =========================
                # HEADERS
                # =========================
                headers = driver.find_elements(
                    By.XPATH,
                    "//table[contains(@class, 'Grid')]//tr[1]/th"
                )

                idx_map = {}

                for i, h in enumerate(headers):

                    texto = h.text.strip().upper()

                    if 'EXPEDIENTES' in texto:
                        idx_map['exptes'] = i

                    elif 'ORGANISMO' in texto:
                        idx_map['juzgado'] = i

                    elif 'SECRETAR' in texto:
                        idx_map['secretaria'] = i

                if (
                    'exptes' not in idx_map
                    or 'juzgado' not in idx_map
                ):

                    print(
                        f"⏱ {localidad}: "
                        f"{time.time()-t_ciclo:.1f}s "
                        f"→ columnas inválidas"
                    )

                    continue

                socketio.emit('bot_status', {
                    'msg': (
                        f'📄 {localidad}: '
                        f'{len(filas)} notificaciones encontradas'
                    )
                })

                # =========================
                # PARSEAR FILAS
                # =========================
                for fila in filas:

                    try:

                        celdas = fila.find_elements(
                            By.TAG_NAME,
                            "td"
                        )

                        texto_exptes = celdas[
                            idx_map['exptes']
                        ].text.strip()

                        texto_juzgado_raw = celdas[
                            idx_map['juzgado']
                        ].text.strip()

                        texto_sec_raw = (
                            celdas[idx_map['secretaria']].text.strip()
                            if 'secretaria' in idx_map
                            else ""
                        )

                        texto_juzgado, texto_sec = separar_juzgado_secretaria(
                            texto_juzgado_raw,
                            texto_sec_raw
                        )

                        if (
                            not texto_exptes
                            or not texto_juzgado
                        ):
                            continue

                        juzgado_limpio = re.sub(
                            r'^JUZGADO\s+',
                            '',
                            texto_juzgado,
                            flags=re.IGNORECASE
                        ).strip().upper().replace("/", "-")

                        partes = texto_exptes.split(" - ")

                        for parte in partes:

                            parte = parte.strip()

                            match = re.match(
                                r'^([A-Z]+\d*)\s*(\d{4,6})(?:\s*/\s*(\d+))?$',
                                parte
                            )

                            if match:

                                tipo_code = match.group(1)
                                nro = match.group(2)
                                anio = match.group(3)

                                nro_completo = (
                                    f"{nro}-{anio}"
                                    if anio
                                    else nro
                                )

                                key = (
                                    f"{tipo_code}-"
                                    f"{nro_completo}-"
                                    f"{juzgado_limpio}"
                                )

                                if key not in vistos:

                                    expedientes.append({
                                        "tipo": tipo_code,
                                        "nro": nro_completo,
                                        "juzgado": juzgado_limpio,
                                        "secretaria": texto_sec.upper(),
                                        "localidad": localidad,
                                        "fecha_lista": (
                                            fecha if fecha else ""
                                        )
                                    })

                                    vistos.add(key)

                    except Exception:
                        continue

                print(
                    f"⏱ {localidad}: "
                    f"{time.time()-t_ciclo:.1f}s → "
                    f"{len(filas)} notificaciones"
                )

            except Exception as e:

                print(f"❌ Error en {localidad}: {e}")

                continue

        socketio.emit('bot_status', {
            'msg': (
                f'✅ Total: '
                f'{len(expedientes)} expedientes con movimiento'
            )
        })

        return expedientes

    except Exception as e:

        traceback.print_exc()

        socketio.emit('bot_error', {
            'msg': (
                f'❌ Error en notificaciones: {str(e)}'
            )
        })

        return []
def actualizar_estado_desde_tabla(driver, causa_id, app, socketio, fecha_notif=None):
    try:
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.XPATH, "//table//tbody")))
        time.sleep(1)

        headers = driver.find_elements(
            By.XPATH, "//table[contains(@class, 'Grid')]//tr[1]/th"
        )
        idx_fecha    = None
        idx_extracto = None
        for i, h in enumerate(headers):
            texto = h.text.strip().upper()
            if 'FECHA' in texto:
                idx_fecha = i
            elif any(x in texto for x in ['EXTRACTO', 'DETALLE', 'DESCRIPCION']):
                idx_extracto = i

        if idx_fecha is None or idx_extracto is None:
            return

        filas = driver.find_elements(By.XPATH, "//table//tbody/tr")
        for fila in filas:
            try:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) <= max(idx_fecha, idx_extracto):
                    continue
                fecha_str    = celdas[idx_fecha].text.strip()
                extracto_str = celdas[idx_extracto].text.strip()

                if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', fecha_str) and extracto_str:
                    with app.app_context():
                        c = CausaInfo.query.get(causa_id)
                        if c:
                            c.estado = extracto_str[:200]
                            if fecha_notif:
                                try:
                                    dt = datetime.strptime(fecha_notif, "%Y-%m-%d")
                                    c.ultima_notificacion = dt.strftime("%d/%m/%Y")
                                except Exception:
                                    c.ultima_notificacion = fecha_notif
                            else:
                                c.ultima_notificacion = fecha_str
                            db.session.commit()
                    socketio.emit('bot_status', {'msg': f'📋 Estado: {extracto_str[:60]}'})
                    break
            except Exception:
                continue

    except Exception as e:
        print(f"Error actualizando estado: {e}")


def _entrar_a_expediente_actualizador(driver, nro_expte, tipo_codigo=None, localidad='Capital'):
    nro_solo = nro_expte.split('-')[0]
    anio = nro_expte.split('-')[1] if '-' in nro_expte else ""
    tipo_normalizado = tipo_codigo.upper().replace(" ", "") if tipo_codigo else None

    driver.get(config.FORUM_URL_CAUSAS)
    wait = WebDriverWait(driver, 25)

    try:
        wait.until(EC.presence_of_element_located(
            (By.ID, "COMBO_CAUSA_LOCALIDADIDContainer_btnGroupDrop")
        ))
        time.sleep(0.5)
        wait.until(EC.element_to_be_clickable(
            (By.ID, "COMBO_CAUSA_LOCALIDADIDContainer_btnGroupDrop")
        )).click()
    except Exception:
        print("⚠️ Timeout en combo localidad, recargando...")
        driver.get(config.FORUM_URL_CAUSAS)
        time.sleep(3)
        wait.until(EC.element_to_be_clickable(
            (By.ID, "COMBO_CAUSA_LOCALIDADIDContainer_btnGroupDrop")
        )).click()

    wait.until(EC.element_to_be_clickable(
        (By.XPATH, f"//span[contains(text(), '{localidad}')]")
    )).click()

    input_nro = wait.until(EC.element_to_be_clickable((By.ID, "vCAUSANRO")))
    input_nro.clear()
    input_nro.send_keys(nro_solo)

    driver.find_element(By.ID, "BTN_SEARCH").click()

    pagina = 1

    while True:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//table[contains(@class,'Grid')]//tbody/tr")
        ))
        time.sleep(0.8)

        filas = driver.find_elements(
            By.XPATH, "//table[contains(@class,'Grid')]//tbody/tr"
        )

        hubo_mismo_numero = False
        hubo_mismo_numero_distinto_anio_o_tipo = False

        for fila in filas:
            try:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) < 4:
                    continue

                tipo_fila = celdas[1].text.strip().upper().replace(" ", "")
                nro_fila = celdas[2].text.strip()
                anio_fila = celdas[3].text.strip()

                if nro_fila != nro_solo:
                    continue

                hubo_mismo_numero = True

                if anio and anio_fila != anio:
                    hubo_mismo_numero_distinto_anio_o_tipo = True
                    continue

                if tipo_normalizado and tipo_fila != tipo_normalizado:
                    hubo_mismo_numero_distinto_anio_o_tipo = True
                    continue

                celda_nro = celdas[2]
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    celda_nro
                )
                time.sleep(0.3)
                ActionChains(driver).double_click(celda_nro).perform()

                try:
                    esperar_tabla_actuaciones(driver, timeout=20)
                    return True
                except Exception as e:
                    print(f"❌ Doble click no abrió actuaciones para {tipo_codigo} {nro_expte}: {e}")
                    return False

            except Exception:
                continue

        if hubo_mismo_numero and hubo_mismo_numero_distinto_anio_o_tipo:
            print(
                f"❌ Encontré nro={nro_solo}, pero no coincide tipo/año. "
                f"Buscado tipo={tipo_normalizado} año={anio}. No se pagina más."
            )
            return False

        print(f"🔄 entrar_actualizador: no encontrado en página {pagina}, paginando...")

        try:
            btn_sig = driver.find_element(
                By.XPATH,
                "//a[contains(text(),'Sig') or contains(@class,'next')][not(contains(@class,'disabled'))]"
            )
            driver.execute_script("arguments[0].click();", btn_sig)
            time.sleep(2)
            pagina += 1
        except Exception:
            break

    print(f"❌ No se encontró tipo={tipo_codigo} nro={nro_expte} en {pagina} páginas")
    return False
def detectar_total_paginas_forum(driver):

    try:

        import re
        from selenium.webdriver.common.by import By

        body = driver.find_element(By.TAG_NAME, "body")

        texto = body.text

        # ============================================================
        # CASO 1 — Página X de Y
        # ============================================================

        match = re.search(
            r"p[aá]gina\s+\d+\s+de\s+(\d+)",
            texto,
            re.IGNORECASE
        )

        if match:

            total = int(match.group(1))

            return total

        # ============================================================
        # CASO 2 — botones
        # ============================================================

        elementos = driver.find_elements(
            By.XPATH,
            "//a|//button|//span"
        )

        nums = []

        for e in elementos:

            try:

                t = e.text.strip()

                if t.isdigit():
                    nums.append(int(t))

            except:
                pass

        if nums:
            return max(nums)

        return 1

    except Exception as e:

        return 1

def guardar_reporte_ultima_ejecucion(
    usuario_nombre,
    fecha_str,
    total_movimiento,
    acumulador_pdfs,
    pdfs_descargados,
    exptes_sin_pdfs,
    exptes_error,
    tiempo_str,
):
    os.makedirs(config.RESUMEN_DIARIO_PATH, exist_ok=True)

    fecha_ejecucion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    fecha_notificacion = fecha_str or date.today().strftime("%Y-%m-%d")

    expedientes_con_pdfs = [
        e for e in acumulador_pdfs
        if e.get("paths")
    ]

    total_pdfs_resumen = sum(
        len(e.get("paths", []))
        for e in expedientes_con_pdfs
    )

    # PDFs físicos reales detectados en disco para ESTA ejecución.
    # Se cuentan los paths que el propio actualizador detectó como nuevos.
    pdfs_fisicos_detectados = 0
    archivos_faltantes = []

    for e in expedientes_con_pdfs:
        for p in e.get("paths", []):
            if os.path.exists(p):
                pdfs_fisicos_detectados += 1
            else:
                archivos_faltantes.append(p)

    detalle = []

    for e in acumulador_pdfs:
        detalle.append({
            "tipo": e.get("tipo", ""),
            "nro": e.get("nro", ""),
            "juzgado": e.get("juzgado", ""),
            "secretaria": e.get("secretaria", ""),
            "localidad": e.get("localidad", ""),
            "caratula": e.get("caratula", ""),
            "pdfs_nuevos": len(e.get("paths", [])),
            "archivos": [os.path.basename(p) for p in e.get("paths", [])],
        })

    coincide_resumen = pdfs_descargados == total_pdfs_resumen
    coincide_disco = total_pdfs_resumen == pdfs_fisicos_detectados
    coincide_general = coincide_resumen and coincide_disco

    reporte = {
        "fecha_ejecucion": fecha_ejecucion,
        "fecha_notificacion": fecha_notificacion,
        "usuario": usuario_nombre,

        "expedientes_con_movimiento": total_movimiento,
        "expedientes_con_pdfs_nuevos": len(expedientes_con_pdfs),

        "pdfs_descargados_reales": pdfs_descargados,
        "pdfs_incluidos_resumen": total_pdfs_resumen,
        "pdfs_fisicos_detectados": pdfs_fisicos_detectados,

        "coincide_resumen": coincide_resumen,
        "coincide_disco": coincide_disco,
        "coincide": coincide_general,

        "sin_pdfs_nuevos": exptes_sin_pdfs,
        "expedientes_error": exptes_error,
        "archivos_faltantes": archivos_faltantes,
        "tiempo_total": tiempo_str,
        "detalle": detalle,
    }

    ruta_json = os.path.join(config.RESUMEN_DIARIO_PATH, "ultima_ejecucion.json")
    ruta_txt = os.path.join(config.RESUMEN_DIARIO_PATH, "ultima_ejecucion.txt")

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)

    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write("RESUMEN DE ÚLTIMA EJECUCIÓN\n")
        f.write("=" * 40 + "\n")
        f.write(f"Fecha ejecución: {fecha_ejecucion}\n")
        f.write(f"Fecha notificación: {fecha_notificacion}\n")
        f.write(f"Usuario: {usuario_nombre}\n\n")

        f.write(f"Expedientes con movimiento: {total_movimiento}\n")
        f.write(f"Expedientes con PDFs nuevos: {len(expedientes_con_pdfs)}\n\n")

        f.write(f"PDFs descargados reales: {pdfs_descargados}\n")
        f.write(f"PDFs incluidos en resumen: {total_pdfs_resumen}\n")
        f.write(f"PDFs físicos detectados en disco: {pdfs_fisicos_detectados}\n\n")

        f.write(f"Coincide resumen: {'SI' if coincide_resumen else 'NO'}\n")
        f.write(f"Coincide disco: {'SI' if coincide_disco else 'NO'}\n")
        f.write(f"Coincide general: {'SI' if coincide_general else 'NO'}\n\n")

        f.write(f"Sin PDFs nuevos: {exptes_sin_pdfs}\n")
        f.write(f"Expedientes con error: {exptes_error}\n")
        f.write(f"Tiempo total: {tiempo_str}\n\n")

        if archivos_faltantes:
            f.write("ARCHIVOS INFORMADOS PERO NO ENCONTRADOS EN DISCO\n")
            f.write("=" * 40 + "\n")
            for p in archivos_faltantes:
                f.write(f"- {p}\n")
            f.write("\n")

        f.write("DETALLE\n")
        f.write("=" * 40 + "\n")

        for item in detalle:
            f.write(
                f"{item['tipo']} {item['nro']} | "
                f"{item['juzgado']} | {item['secretaria']} | "
                f"PDFs nuevos: {item['pdfs_nuevos']}\n"
            )

            if item["archivos"]:
                for archivo in item["archivos"]:
                    f.write(f"  - {archivo}\n")
            else:
                f.write("  - Sin PDFs nuevos\n")

            f.write("\n")

    return reporte


def ejecutar_actualizacion(usuario_id, usuario_nombre, socketio, app, fecha_str=None, max_exptes=None, matricula_override=None):
    try:
        socketio.emit('bot_status', {'msg': '🔧 Iniciando...'})

        with app.app_context():
            usuario = db.session.get(Usuario, usuario_id)

        forum_user = usuario.forum_user
        forum_pass = usuario.forum_pass
        matricula = matricula_override if matricula_override else (usuario.matricula if usuario.matricula else "")
        alcance = usuario.alcance or 'capital'

        socketio.emit('bot_status', {'msg': '🌐 Obteniendo Chrome...'})
        driver = get_driver(temp_download_path=config.TEMP_DOWNLOAD_PATH)
        marcar_ocupado()
        socketio.emit('bot_status', {'msg': '✅ Chrome listo'})

    except Exception as e:
        err = traceback.format_exc()
        print(f"❌ Error iniciando actualización: {e}\n{err}")
        socketio.emit('bot_status', {'msg': f'❌ Error: {str(e)}'})
        socketio.emit('bot_status', {'msg': err[:500]})
        return

    t0 = time.time()

    exptes_actualizados = 0
    exptes_nuevos = 0
    pdfs_descargados = 0
    exptes_sin_pdfs = 0
    exptes_error = 0

    acumulador_pdfs: list[dict] = []

    try:
        if not is_logged_in():
            socketio.emit('bot_status', {'msg': '🔑 Abriendo Forum...', 'progreso': 5})
            socketio.emit('bot_status', {'msg': '⚠️ Resolvé el Captcha e iniciá sesión', 'progreso': 10})
            if not login_forum(driver, forum_user, forum_pass):
                socketio.emit('bot_status', {'msg': '❌ No se pudo hacer login'})
                return
        else:
            socketio.emit('bot_status', {'msg': '✅ Sesión activa, reutilizando...', 'progreso': 10})

        expedientes = obtener_expedientes_con_movimiento(
            driver,
            matricula,
            socketio,
            fecha=fecha_str,
            alcance=alcance
        )

        if not expedientes:
            label = f"del {fecha_str}" if fecha_str else "de hoy"
            socketio.emit('bot_status', {'msg': f'📭 Sin notificaciones {label}', 'progreso': 100})
            socketio.emit('bot_finished', {})
            return

        if max_exptes and len(expedientes) > max_exptes:
            socketio.emit('bot_status', {
                'msg': f'⚠️ MODO TRIAL: procesando {max_exptes} de {len(expedientes)} expedientes',
                'progreso': 30
            })
            expedientes = expedientes[:max_exptes]

        total = len(expedientes)
        socketio.emit('bot_status', {'msg': f'📋 {total} expedientes con movimiento', 'progreso': 30})

        for idx, exp in enumerate(expedientes):
            nro = exp["nro"]
            nro_solo = nro.split('-')[0]
            tipo_code = exp.get("tipo", "")
            juzgado_forum = exp["juzgado"]
            secretaria_forum = exp["secretaria"]
            localidad_forum = exp.get("localidad", "Capital")
            progreso = int(((idx + 1) / total) * 65) + 30

            socketio.emit('bot_status', {
                'msg': f'📥 Actualizando {tipo_code} {nro} ({idx+1}/{total})',
                'progreso': progreso
            })

            entrada_resumen = {
                "nro": nro,
                "tipo": tipo_code,
                "caratula": "",
                "juzgado": juzgado_forum,
                "secretaria": secretaria_forum,
                "paths": [],
                "localidad": localidad_forum,
            }

            causa_id = None
            causa_juzgado = None
            causa_secretaria = ""
            causa_caratula = ""
            causa_encontrada = False

            with app.app_context():
                causa = CausaInfo.query.filter(
                    CausaInfo.numero == nro,
                    CausaInfo.usuario_id == usuario_id
                ).first()

                if not causa and tipo_code:
                    causa = CausaInfo.query.filter(
                        CausaInfo.numero.contains(nro_solo),
                        CausaInfo.tipo == "",
                        CausaInfo.usuario_id == usuario_id
                    ).first()
                    if causa:
                        causa.tipo = tipo_code
                        db.session.commit()

                if causa:
                    causa_encontrada = True
                    causa_id = causa.id
                    causa_juzgado = causa.juzgado
                    causa_secretaria = causa.secretaria or ""
                    causa_caratula = causa.demandado or ""

            if not causa_encontrada:
                with app.app_context():
                    ya_existe = CausaInfo.query.filter(
                        CausaInfo.numero == nro,
                        CausaInfo.usuario_id == usuario_id
                    ).first()

                    if not ya_existe:
                        ya_existe = CausaInfo.query.filter(
                            CausaInfo.numero.contains(nro_solo),
                            CausaInfo.usuario_id == usuario_id
                        ).first()

                if ya_existe:
                    socketio.emit('bot_status', {
                        'msg': f'⚠️ {tipo_code} {nro} ya existe en DB, actualizando...',
                        'progreso': progreso
                    })

                    causa_encontrada = True
                    causa_id = ya_existe.id
                    causa_juzgado = ya_existe.juzgado
                    causa_secretaria = ya_existe.secretaria or ""
                    causa_caratula = ya_existe.demandado or ""

                else:
                    socketio.emit('bot_status', {
                        'msg': f'🆕 {tipo_code} {nro} no estaba en DB, creando...',
                        'progreso': progreso
                    })

                    exptes_nuevos += 1
                    nueva_id = None
                    caratula_real = "SIN CARATULAR"

                    datos_busqueda = buscar_expediente(
                        driver,
                        nro_solo,
                        tipo_codigo=tipo_code,
                        localidad=localidad_forum
                    )

                    if datos_busqueda:
                        if datos_busqueda.get('caratula'):
                            caratula_real = datos_busqueda['caratula']
                        if datos_busqueda.get('juzgado'):
                            juzgado_forum = datos_busqueda['juzgado']

                        # La secretaría de la lista de notificaciones manda.
                        # No pisar con SECRETARIA UNICA.
                        if (
                            (not secretaria_forum or secretaria_forum.upper() == "SECRETARIA UNICA")
                            and datos_busqueda.get('secretaria')
                            and datos_busqueda['secretaria'].upper() != "SECRETARIA UNICA"
                        ):
                            secretaria_forum = datos_busqueda['secretaria']

                    entrada_resumen["caratula"] = caratula_real
                    entrada_resumen["juzgado"] = juzgado_forum
                    entrada_resumen["secretaria"] = secretaria_forum

                    ruta = os.path.join(
                        "expedientes_clientes",
                        usuario_nombre,
                        juzgado_forum,
                        secretaria_forum,
                        nro
                    )

                    os.makedirs(ruta, exist_ok=True)

                    if _entrar_a_expediente_actualizador(
                        driver,
                        nro,
                        tipo_codigo=tipo_code,
                        localidad=localidad_forum
                    ):
                        total_paginas = detectar_total_paginas_forum(driver)

                        socketio.emit('bot_status', {
                            'msg': f'📚 {tipo_code} {nro}: {total_paginas} páginas en Forum'
                        })

                        with app.app_context():
                            nueva = CausaInfo(
                                numero=nro,
                                tipo=tipo_code,
                                juzgado=juzgado_forum,
                                secretaria=secretaria_forum,
                                demandado=caratula_real,
                                estado="En Trámite",
                                usuario_id=usuario_id,
                                necesita_sync=True,
                                estado_sync="parcial",
                                ultima_sync=datetime.utcnow(),
                                error_sync=None,
                                paginas_forum_total=total_paginas,
                                paginas_descargadas_total=0
                            )

                            db.session.add(nueva)
                            db.session.commit()
                            nueva_id = nueva.id

                        actualizar_estado_desde_tabla(
                            driver,
                            nueva_id,
                            app,
                            socketio,
                            fecha_notif=fecha_str
                        )

                        pdfs_antes = set(_listar_pdfs(ruta))

                        resultado_descarga = descargar_pdfs_nuevos(
                            driver,
                            ruta,
                            config.TEMP_DOWNLOAD_PATH
                        )

                        if isinstance(resultado_descarga, tuple):
                            nuevos, total_paginas = resultado_descarga
                        else:
                            nuevos = resultado_descarga
                            total_paginas = getattr(driver, "paginas_forum_total", 0) or 0

                        pdfs_despues = set(_listar_pdfs(ruta))
                        pdfs_nuevos_paths = list(pdfs_despues - pdfs_antes)
                        cantidad_real_nueva = len(pdfs_nuevos_paths)

                        pdfs_descargados += cantidad_real_nueva
                        entrada_resumen["paths"] = pdfs_nuevos_paths

                        print(
                            f"[CONTROL RESUMEN] {tipo_code} {nro} | "
                            f"driver={nuevos} | fisicos_nuevos={cantidad_real_nueva}"
                        )

                        with app.app_context():
                            c = CausaInfo.query.get(nueva_id)

                            if c:
                                total_local = len(_listar_pdfs(ruta))
                                c.paginas_forum_total = total_paginas
                                c.paginas_descargadas_total = total_local

                                if total_local >= total_paginas:
                                    c.estado_sync = "sincronizado"
                                    c.necesita_sync = False
                                    c.error_sync = None
                                else:
                                    c.estado_sync = "parcial"
                                    c.necesita_sync = True
                                    c.error_sync = "Actualizado parcialmente; falta sincronización completa"

                                c.ultima_sync = datetime.utcnow()
                                db.session.commit()

                        if cantidad_real_nueva > 0:
                            socketio.emit('bot_status', {
                                'msg': f'✅ {tipo_code} {nro}: {cantidad_real_nueva} PDFs nuevos',
                                'progreso': progreso
                            })
                        else:
                            exptes_sin_pdfs += 1
                            socketio.emit('bot_status', {
                                'msg': f'📭 {tipo_code} {nro}: Sin PDFs nuevos',
                                'progreso': progreso
                            })

                        driver.switch_to.default_content()

                    else:
                        exptes_error += 1

                        with app.app_context():
                            nueva = CausaInfo(
                                numero=nro,
                                tipo=tipo_code,
                                juzgado=juzgado_forum,
                                secretaria=secretaria_forum,
                                demandado=caratula_real,
                                estado="En Trámite",
                                usuario_id=usuario_id,
                                necesita_sync=True,
                                estado_sync="error",
                                ultima_sync=datetime.utcnow(),
                                error_sync="No se pudo entrar al expediente",
                                paginas_forum_total=0,
                                paginas_descargadas_total=0
                            )

                            db.session.add(nueva)
                            db.session.commit()

                        socketio.emit('bot_status', {
                            'msg': f'⚠️ No se pudo entrar a {tipo_code} {nro}',
                            'progreso': progreso
                        })

                    acumulador_pdfs.append(entrada_resumen)
                    continue

            # ── CASO 2: Está en la DB ────────────────────────────────────────
            entrada_resumen["caratula"] = causa_caratula

            with app.app_context():
                c = CausaInfo.query.get(causa_id)
                if c and c.demandado in (None, "", "SIN CARATULAR", "CARATULA NO ENCONTRADA"):
                    datos = buscar_expediente(driver, nro_solo, tipo_codigo=tipo_code, localidad=localidad_forum)
                    if datos and datos.get('caratula'):
                        c.demandado = datos['caratula']
                        db.session.commit()
                        entrada_resumen["caratula"] = datos['caratula']
                        socketio.emit('bot_log', {'msg': f'📝 Carátula actualizada: {nro}'})

            ruta_vieja = os.path.join(
                "expedientes_clientes",
                usuario_nombre,
                causa_juzgado or juzgado_forum,
                causa_secretaria,
                nro
            )

            ruta_nueva = os.path.join(
                "expedientes_clientes",
                usuario_nombre,
                juzgado_forum,
                secretaria_forum,
                nro
            )

            if causa_secretaria.upper() != secretaria_forum.upper() and os.path.exists(ruta_vieja):
                try:
                    os.makedirs(os.path.dirname(ruta_nueva), exist_ok=True)
                    shutil.move(ruta_vieja, ruta_nueva)

                    socketio.emit('bot_status', {
                        'msg': f'📦 {nro}: {causa_secretaria} → {secretaria_forum}'
                    })

                    with app.app_context():
                        c = CausaInfo.query.get(causa_id)
                        if c:
                            c.secretaria = secretaria_forum
                            c.juzgado = juzgado_forum
                            db.session.commit()

                    causa_secretaria = secretaria_forum
                    causa_juzgado = juzgado_forum

                except Exception as e:
                    socketio.emit('bot_status', {'msg': f'⚠️ Error moviendo: {str(e)}'})

            ruta_final = ruta_nueva if os.path.exists(ruta_nueva) else ruta_vieja
            os.makedirs(ruta_final, exist_ok=True)

            if _entrar_a_expediente_actualizador(
                driver,
                nro,
                tipo_codigo=tipo_code,
                localidad=localidad_forum
            ):
                total_paginas = detectar_total_paginas_forum(driver)

                socketio.emit('bot_status', {
                    'msg': f'📚 {tipo_code} {nro}: {total_paginas} páginas en Forum'
                })

                actualizar_estado_desde_tabla(
                    driver,
                    causa_id,
                    app,
                    socketio,
                    fecha_notif=fecha_str
                )

                pdfs_antes = set(_listar_pdfs(ruta_final))

                resultado_descarga = descargar_pdfs_nuevos(
                    driver,
                    ruta_final,
                    config.TEMP_DOWNLOAD_PATH
                )

                if isinstance(resultado_descarga, tuple):
                    nuevos, total_paginas = resultado_descarga
                else:
                    nuevos = resultado_descarga
                    total_paginas = getattr(driver, "paginas_forum_total", 0) or 0

                pdfs_despues = set(_listar_pdfs(ruta_final))
                pdfs_nuevos_paths = list(pdfs_despues - pdfs_antes)
                cantidad_real_nueva = len(pdfs_nuevos_paths)

                pdfs_descargados += cantidad_real_nueva
                entrada_resumen["paths"] = pdfs_nuevos_paths

                print(
                    f"[CONTROL RESUMEN] {tipo_code} {nro} | "
                    f"driver={nuevos} | fisicos_nuevos={cantidad_real_nueva}"
                )

                with app.app_context():
                    c = CausaInfo.query.get(causa_id)

                    if c:
                        total_local = len(_listar_pdfs(ruta_final))
                        c.paginas_forum_total = total_paginas
                        c.paginas_descargadas_total = total_local

                        if total_local >= total_paginas:
                            c.estado_sync = "sincronizado"
                            c.necesita_sync = False
                            c.error_sync = None
                        else:
                            c.estado_sync = "parcial"
                            c.necesita_sync = True
                            c.error_sync = "Actualizado parcialmente; falta sincronización completa"

                        c.ultima_sync = datetime.utcnow()
                        db.session.commit()

                exptes_actualizados += 1

                if cantidad_real_nueva > 0:
                    socketio.emit('bot_status', {
                        'msg': f'✅ {tipo_code} {nro}: {cantidad_real_nueva} PDFs nuevos',
                        'progreso': progreso
                    })
                else:
                    exptes_sin_pdfs += 1
                    socketio.emit('bot_status', {
                        'msg': f'📭 {tipo_code} {nro}: Sin PDFs nuevos',
                        'progreso': progreso
                    })

                driver.switch_to.default_content()

            else:
                exptes_error += 1

                with app.app_context():
                    c = CausaInfo.query.get(causa_id)

                    if c:
                        c.estado_sync = "error"
                        c.necesita_sync = True
                        c.error_sync = "No se pudo entrar al expediente"
                        c.ultima_sync = datetime.utcnow()
                        db.session.commit()

                socketio.emit('bot_status', {
                    'msg': f'⚠️ No se pudo entrar a {tipo_code} {nro}',
                    'progreso': progreso
                })

            acumulador_pdfs.append(entrada_resumen)

        generar_pdf_resumen(acumulador_pdfs, fecha_str, socketio)

        tiempo_total = int(time.time() - t0)
        mins = tiempo_total // 60
        segs = tiempo_total % 60
        tiempo_str = f"{mins}m {segs}s" if mins > 0 else f"{segs}s"

        exptes_con_pdfs_resumen = len([
            e for e in acumulador_pdfs
            if e.get("paths")
        ])

        reporte_ultima = guardar_reporte_ultima_ejecucion(
            usuario_nombre=usuario_nombre,
            fecha_str=fecha_str,
            total_movimiento=total,
            acumulador_pdfs=acumulador_pdfs,
            pdfs_descargados=pdfs_descargados,
            exptes_sin_pdfs=exptes_sin_pdfs,
            exptes_error=exptes_error,
            tiempo_str=tiempo_str,
        )

        socketio.emit('bot_status', {
            'msg': (
                '🧾 Reporte última ejecución: '
                f"{'OK coincide' if reporte_ultima.get('coincide') else '⚠️ no coincide'}"
            )
        })

        socketio.emit('bot_status', {'msg': '🏁 Actualización finalizada', 'progreso': 100})
        socketio.emit('bot_status', {'msg': '━' * 40})
        socketio.emit('bot_status', {'msg': '📊 RESUMEN ACTUALIZACIÓN'})
        socketio.emit('bot_status', {'msg': f'🔔 Expedientes con movimiento: {total}'})
        socketio.emit('bot_status', {'msg': f'📎 Expedientes con PDFs nuevos: {exptes_con_pdfs_resumen}'})
        socketio.emit('bot_status', {'msg': f'✅ Actualizados: {exptes_actualizados}'})

        if exptes_nuevos > 0:
            socketio.emit('bot_status', {'msg': f'🆕 Nuevos creados: {exptes_nuevos}'})

        if exptes_error > 0:
            socketio.emit('bot_status', {'msg': f'❌ Expedientes con error: {exptes_error}'})

        socketio.emit('bot_status', {'msg': f'📄 PDFs descargados reales: {pdfs_descargados}'})
        socketio.emit('bot_status', {'msg': f'📭 Sin PDFs nuevos: {exptes_sin_pdfs}'})
        socketio.emit('bot_status', {'msg': f'⏱️ Tiempo total: {tiempo_str}'})
        socketio.emit('bot_status', {'msg': '━' * 40})

        expedientes_parciales = []

        numeros_actualizados = {
            str(e.get('nro', e.get('numero', ''))).strip()
            for e in acumulador_pdfs
            if str(e.get('nro', e.get('numero', ''))).strip()
        }

        actualizados_por_numero = {
            str(e.get('nro', e.get('numero', ''))).strip(): e
            for e in acumulador_pdfs
            if str(e.get('nro', e.get('numero', ''))).strip()
        }

        with app.app_context():
            causas_parciales = CausaInfo.query.filter(
                CausaInfo.usuario_id == usuario_id,
                CausaInfo.estado_sync == "parcial"
            ).all()

            for c in causas_parciales:
                nro_c = str(c.numero or "").strip()

                if nro_c not in numeros_actualizados:
                    continue

                fuente = actualizados_por_numero.get(nro_c, {})

                faltan = max(
                    (c.paginas_forum_total or 0) -
                    (c.paginas_descargadas_total or 0),
                    0
                )

                expedientes_parciales.append({
                    "nro": c.numero,
                    "numero": c.numero,
                    "forum_total": c.paginas_forum_total or 0,
                    "descargadas": c.paginas_descargadas_total or 0,
                    "faltan": faltan,
                    "juzgado": fuente.get("juzgado") or c.juzgado or "",
                    "secretaria": fuente.get("secretaria") or c.secretaria or "",
                    "tipo": fuente.get("tipo") or c.tipo or "",
                    "localidad": fuente.get("localidad") or c.localidad or "Capital",
                })

        socketio.emit('actualizacion_completa', {
            'total': total,
            'pdfs': pdfs_descargados,
            'expedientes': [
                {
                    'nro': e.get('nro', e.get('numero', '')),
                    'tipo': e.get('tipo', ''),
                    'juzgado': e.get('juzgado', ''),
                    'secretaria': e.get('secretaria', ''),
                    'localidad': e.get('localidad', 'Capital')
                }
                for e in acumulador_pdfs
            ],
            'expedientes_parciales': expedientes_parciales,
            'tiempo': tiempo_str
        })

    except Exception as e:
        traceback.print_exc()
        socketio.emit('bot_status', {'msg': f'❌ Error crítico: {str(e)}'})

    finally:
        marcar_libre()
        release_driver()


# ── Helper interno ───────────────────────────────────────────────────────────

def _listar_pdfs(carpeta: str) -> list[str]:
    """Devuelve lista absoluta y recursiva de todos los PDFs en una carpeta."""
    encontrados = []

    if not os.path.isdir(carpeta):
        return encontrados

    for root, dirs, files in os.walk(carpeta):
        for f in files:
            if f.lower().endswith(".pdf"):
                encontrados.append(os.path.join(root, f))

    return encontrados