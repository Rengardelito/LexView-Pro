# helpers/features.py
"""
Control de funcionalidades por plan en LexView Pro.

Planes comerciales definitivos:

  prueba       → prueba gratuita / demo, 1 matrícula, 1 dispositivo
  profesional → abogado independiente, 1 matrícula, 1 dispositivo
  estudio     → estudio jurídico, 3 matrículas, 2 dispositivos
  dev         → desarrollo / soporte, sin límites prácticos

Regla comercial:
  Todas las funciones están disponibles en todos los planes activos.
  La diferencia comercial está en:
    - cantidad de matrículas
    - cantidad de dispositivos
"""

from datetime import date
from functools import wraps
from flask import jsonify
from flask_login import current_user


PLANES_VALIDOS = {
    "prueba",
    "profesional",
    "estudio",
    "dev",
}


PLAN_LIMITS = {
    "prueba": {
        "max_matriculas": 1,
        "max_dispositivos": 1,
        "max_exptes_actualizacion": 5,
    },
    "profesional": {
        "max_matriculas": 1,
        "max_dispositivos": 1,
        "max_exptes_actualizacion": None,
    },
    "estudio": {
        "max_matriculas": 3,
        "max_dispositivos": 2,
        "max_exptes_actualizacion": None,
    },
    "dev": {
        "max_matriculas": 999,
        "max_dispositivos": 999,
        "max_exptes_actualizacion": None,
    },
}


# Todas las funciones principales quedan habilitadas.
# No se mutila el producto por plan.
FEATURES = {
    "clasificar": ["prueba", "profesional", "estudio", "dev"],
    "sincronizar": ["prueba", "profesional", "estudio", "dev"],
    "actualizar": ["prueba", "profesional", "estudio", "dev"],
    "migrar": ["prueba", "profesional", "estudio", "dev"],
    "auditoria": ["prueba", "profesional", "estudio", "dev"],
    "cedulas": ["prueba", "profesional", "estudio", "dev"],
    "resumen_pdf": ["prueba", "profesional", "estudio", "dev"],
}


LEGACY_PLAN_MAP = {
    "trial": "prueba",
    "basic": "profesional",
    "pro": "profesional",
    "premium": "estudio",
    "piloto": "prueba",
    "PRUEBA": "prueba",
    "PROFESIONAL": "profesional",
    "ESTUDIO": "estudio",
    "DEV": "dev",
}


def normalizar_plan(plan: str | None) -> str:
    plan_raw = (plan or "prueba").strip()
    return LEGACY_PLAN_MAP.get(plan_raw, plan_raw.lower())


def get_plan(usuario) -> str:
    """Devuelve el plan normalizado del usuario."""
    plan = normalizar_plan(getattr(usuario, "plan", None))

    if plan not in PLANES_VALIDOS:
        return "prueba"

    return plan


def plan_activo(usuario) -> bool:
    """Verifica que la licencia no esté vencida."""
    vence = getattr(usuario, "licencia_vence", None)

    if vence is None:
        return True

    return vence >= date.today()


def tiene_feature(usuario, feature: str) -> bool:
    """
    Devuelve True si el usuario tiene acceso a la feature.
    También verifica que la licencia no esté vencida.
    """
    if not plan_activo(usuario):
        return False

    plan = get_plan(usuario)
    planes_permitidos = FEATURES.get(feature, [])

    return plan in planes_permitidos


def es_prueba(usuario) -> bool:
    return get_plan(usuario) == "prueba"


def es_trial(usuario) -> bool:
    """
    Compatibilidad con código viejo.
    Desde ahora trial = prueba.
    """
    return es_prueba(usuario)


def get_plan_limits(usuario) -> dict:
    plan = get_plan(usuario)
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["prueba"])


def max_exptes_trial(usuario) -> int | None:
    """
    Compatibilidad con código existente.

    En el nuevo esquema:
    prueba tiene límite de expedientes por actualización.
    profesional / estudio / dev no tienen límite.
    """
    limits = get_plan_limits(usuario)
    return limits.get("max_exptes_actualizacion")


def max_matriculas_plan(usuario) -> int:
    return get_plan_limits(usuario).get("max_matriculas", 1)


def max_dispositivos_plan(usuario) -> int:
    return get_plan_limits(usuario).get("max_dispositivos", 1)


def requiere_feature(feature: str):
    """
    Decorador para rutas Flask.
    Devuelve 403 si el usuario no tiene acceso a la feature.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not tiene_feature(current_user, feature):
                plan = get_plan(current_user)
                return jsonify({
                    "error": "plan_insuficiente",
                    "mensaje": f'Tu plan "{plan}" no incluye esta funcionalidad.',
                    "feature": feature
                }), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator