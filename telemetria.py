import json
import sqlite3
import time
import uuid
import socket
import getpass
import logging
from pathlib import Path
from datetime import datetime

import requests

from config import get_hardware_id

TELEMETRIA_URL = "https://lexviewpro.com.ar/api/evento"
HEARTBEAT_URL = "https://lexviewpro.com.ar/api/heartbeat"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "telemetria.db"

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _get_version() -> str:
    try:
        version_path = BASE_DIR / "version.txt"
        if version_path.exists():
            return version_path.read_text(encoding="utf-8").strip()

        internal_version = BASE_DIR / "_internal" / "version.txt"
        if internal_version.exists():
            return internal_version.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    return "0.0.0"


def _base_payload() -> dict:
    return {
        "hardware_id": get_hardware_id(),
        "version": _get_version(),
        "hostname": socket.gethostname(),
        "usuario_windows": getpass.getuser(),
    }


def _conn():
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS telemetria_pendiente (
            id TEXT PRIMARY KEY,
            fecha TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            evento TEXT NOT NULL,
            prioridad INTEGER DEFAULT 5,
            payload_json TEXT NOT NULL,
            intentos INTEGER DEFAULT 0,
            ultimo_error TEXT
        )
    """)
    con.commit()
    return con


def guardar_pendiente(endpoint: str, evento: str, payload: dict, prioridad: int = 5, error: str = "") -> None:
    try:
        con = _conn()
        con.execute(
            """
            INSERT OR REPLACE INTO telemetria_pendiente
            (id, fecha, endpoint, evento, prioridad, payload_json, intentos, ultimo_error)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                str(uuid.uuid4()),
                _now(),
                endpoint,
                evento,
                prioridad,
                json.dumps(payload, ensure_ascii=False),
                error[:500],
            )
        )
        con.commit()
        con.close()
    except Exception as e:
        log.debug(f"No se pudo guardar evento pendiente: {e}")


def _post(endpoint: str, payload: dict, timeout: int = 3) -> bool:
    try:
        r = requests.post(endpoint, json=payload, timeout=timeout)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def flush_pendientes(max_items: int = 20) -> int:
    enviados = 0

    try:
        con = _conn()
        rows = con.execute(
            """
            SELECT id, endpoint, evento, payload_json, intentos
            FROM telemetria_pendiente
            ORDER BY prioridad ASC, fecha ASC
            LIMIT ?
            """,
            (max_items,)
        ).fetchall()

        for row_id, endpoint, evento, payload_json, intentos in rows:
            try:
                payload = json.loads(payload_json)
                ok = _post(endpoint, payload)

                if ok:
                    con.execute("DELETE FROM telemetria_pendiente WHERE id = ?", (row_id,))
                    enviados += 1
                else:
                    con.execute(
                        """
                        UPDATE telemetria_pendiente
                        SET intentos = ?, ultimo_error = ?
                        WHERE id = ?
                        """,
                        (intentos + 1, "No enviado", row_id)
                    )

            except Exception as e:
                con.execute(
                    """
                    UPDATE telemetria_pendiente
                    SET intentos = ?, ultimo_error = ?
                    WHERE id = ?
                    """,
                    (intentos + 1, str(e)[:500], row_id)
                )

        con.commit()
        con.close()

    except Exception as e:
        log.debug(f"No se pudo flush telemetría: {e}")

    return enviados


def enviar_evento(
    evento: str,
    detalle: str = "",
    datos: dict | None = None,
    prioridad: int = 5,
    modulo: str | None = None,
    nivel: str | None = None,
    duracion_segundos: float | None = None,
    usuario_id: int | None = None,
) -> bool:
    payload = _base_payload()

    payload.update({
        "evento": evento,
        "detalle": detalle,
        "datos": datos or {},
        "fecha_cliente": _now(),
    })

    if modulo is not None:
        payload["modulo"] = modulo

    if nivel is not None:
        payload["nivel"] = nivel

    if duracion_segundos is not None:
        payload["duracion_segundos"] = duracion_segundos

    if usuario_id is not None:
        payload["usuario_id"] = usuario_id

    flush_pendientes(max_items=10)

    ok = _post(TELEMETRIA_URL, payload)

    if not ok:
        guardar_pendiente(
            TELEMETRIA_URL,
            evento,
            payload,
            prioridad=prioridad,
            error="Servidor no disponible"
        )

    return ok


def heartbeat(evento: str = "HEARTBEAT", detalle: str = "Cliente activo") -> bool:
    payload = _base_payload()
    payload.update({
        "evento": evento,
        "detalle": detalle,
        "fecha_cliente": _now(),
    })

    flush_pendientes(max_items=10)

    ok = _post(HEARTBEAT_URL, payload)

    if not ok:
        guardar_pendiente(
            HEARTBEAT_URL,
            evento,
            payload,
            prioridad=9,
            error="Heartbeat no enviado"
        )

    return ok


class EventoDuracion:
    def __init__(
        self,
        evento: str,
        detalle: str = "",
        datos: dict | None = None,
        prioridad: int = 5,
        modulo: str | None = None,
        nivel: str | None = None,
        usuario_id: int | None = None,
    ):
        self.evento = evento
        self.detalle = detalle
        self.datos = datos or {}
        self.prioridad = prioridad
        self.modulo = modulo
        self.nivel = nivel
        self.usuario_id = usuario_id
        self.inicio = time.time()

        enviar_evento(
            f"{evento}_START",
            detalle or "Inicio",
            self.datos,
            prioridad=prioridad,
            modulo=modulo,
            nivel=nivel or "info",
            usuario_id=usuario_id,
        )

    def finalizar(
        self,
        detalle: str = "",
        datos: dict | None = None,
        nivel: str | None = None,
    ):
        duracion = round(time.time() - self.inicio, 2)
        final_datos = dict(self.datos)
        final_datos.update(datos or {})
        final_datos["duracion_segundos"] = duracion

        return enviar_evento(
            f"{self.evento}_END",
            detalle or "Finalizado",
            final_datos,
            prioridad=self.prioridad,
            modulo=self.modulo,
            nivel=nivel or self.nivel or "success",
            duracion_segundos=duracion,
            usuario_id=self.usuario_id,
        )


def iniciar_evento(
    evento: str,
    detalle: str = "",
    datos: dict | None = None,
    prioridad: int = 5,
    modulo: str | None = None,
    nivel: str | None = None,
    usuario_id: int | None = None,
) -> EventoDuracion:
    return EventoDuracion(
        evento=evento,
        detalle=detalle,
        datos=datos,
        prioridad=prioridad,
        modulo=modulo,
        nivel=nivel,
        usuario_id=usuario_id,
    )