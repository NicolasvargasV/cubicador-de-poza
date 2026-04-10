"""
poza/firebase_auth.py
─────────────────────
Autenticación de usuarios vía Firebase Authentication REST API.

Las credenciales NO se almacenan en disco — se mantienen únicamente en
memoria durante la sesión activa.  Al cerrar la app, la sesión se pierde.

Estructura de Firestore para perfiles de usuario:
    users/{uid}/
        email:          str
        nombre_completo: str
        rol:            "admin" | "operador"
        activo:         bool
        created_at:     ISO timestamp

Requiere:
    - poza/firebase-auth-config.json  (contiene {"apiKey": "...", "projectId": "..."})
    - firebase_admin ya inicializado (FirebaseSync lo hace al arrancar)

Instalación de dependencias:
    pip install requests
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests  # tipo: ignorar si no está instalado

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG_CANDIDATES: list[Path] = [
    Path(__file__).parent.parent / "firebase-auth-config.json",
    Path(__file__).parent / "firebase-auth-config.json",
]

_SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
_SIGN_UP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"


def _load_config() -> Dict[str, str]:
    for p in _CONFIG_CANDIDATES:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


_CONFIG: Dict[str, str] = _load_config()
_API_KEY: str = _CONFIG.get("apiKey", "")


# ─────────────────────────────────────────────────────────────────────────────
# Errores
# ─────────────────────────────────────────────────────────────────────────────

class FirebaseAuthError(Exception):
    """Error de autenticación con Firebase."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code


# ─────────────────────────────────────────────────────────────────────────────
# Sesión en memoria
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UserSession:
    """Información de la sesión activa. Se destruye al cerrar la app."""
    uid:             str
    email:           str
    id_token:        str          # JWT de Firebase Auth (expira en 1h)
    refresh_token:   str          # Para renovar el id_token si se necesita
    nombre_completo: str = ""
    rol:             str = "operador"
    activo:          bool = True
    # extra data del perfil Firestore
    extra:           Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def sign_in(email: str, password: str) -> UserSession:
    """
    Autentica al usuario contra Firebase Authentication.

    Retorna un UserSession con toda la información de la sesión.
    Lanza FirebaseAuthError si las credenciales son incorrectas.
    Los datos NO se escriben en disco.
    """
    if not _API_KEY:
        raise FirebaseAuthError(
            "API key de Firebase no encontrada.\n"
            "Crea el archivo firebase-auth-config.json en la raíz del proyecto.",
            code="NO_API_KEY",
        )

    try:
        resp = requests.post(
            f"{_SIGN_IN_URL}?key={_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        raise FirebaseAuthError(
            "Sin conexión a internet. Verifica la red e intenta de nuevo.",
            code="NETWORK_ERROR",
        )
    except requests.exceptions.Timeout:
        raise FirebaseAuthError(
            "El servidor tardó demasiado en responder. Intenta de nuevo.",
            code="TIMEOUT",
        )

    if not resp.ok:
        err = resp.json().get("error", {})
        code = err.get("message", "UNKNOWN_ERROR")
        msg = _translate_error(code)
        raise FirebaseAuthError(msg, code=code)

    data = resp.json()
    session = UserSession(
        uid=data["localId"],
        email=data["email"],
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        nombre_completo=data.get("displayName", email.split("@")[0]),
    )

    # Obtener perfil extendido desde Firestore (rol, nombre completo real)
    _enrich_session_from_firestore(session)

    return session


def create_firebase_user(
    email: str,
    password: str,
    nombre_completo: str,
    rol: str = "operador",
    admin_session: Optional[UserSession] = None,
) -> str:
    """
    Crea un usuario en Firebase Auth y su perfil en Firestore.

    Solo los admins pueden crear usuarios. Retorna el uid del nuevo usuario.
    Requiere que firebase_admin esté inicializado (FirebaseSync).
    """
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth, firestore
        from datetime import datetime, timezone

        # Crear en Firebase Auth via Admin SDK
        user_record = fb_auth.create_user(
            email=email,
            password=password,
            display_name=nombre_completo,
        )
        uid = user_record.uid

        # Crear perfil en Firestore
        try:
            app = firebase_admin.get_app()
            db = firestore.client(app=app)
            db.collection("users").document(uid).set({
                "email": email,
                "nombre_completo": nombre_completo,
                "rol": rol,
                "activo": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error("Error al crear perfil Firestore para %s: %s", email, e)

        return uid

    except ImportError:
        raise FirebaseAuthError(
            "firebase_admin no está instalado. Instala con: pip install firebase-admin",
            code="SDK_NOT_AVAILABLE",
        )
    except Exception as e:
        code = getattr(e, "code", "UNKNOWN")
        raise FirebaseAuthError(str(e), code=str(code))


def list_firebase_users(limit: int = 100) -> list[Dict[str, Any]]:
    """
    Lista todos los usuarios registrados en Firestore (no en Firebase Auth directamente).
    Retorna lista de dicts con uid, email, nombre_completo, rol, activo.
    """
    try:
        import firebase_admin
        from firebase_admin import firestore

        app = firebase_admin.get_app()
        db = firestore.client(app=app)
        docs = db.collection("users").limit(limit).stream()
        result = []
        for doc in docs:
            d = doc.to_dict()
            d["uid"] = doc.id
            result.append(d)
        return result
    except Exception as e:
        logger.error("Error al listar usuarios Firebase: %s", e)
        return []


def set_user_active_firebase(uid: str, activo: bool) -> None:
    """Activa o desactiva un usuario en Firestore y Firebase Auth."""
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth, firestore

        app = firebase_admin.get_app()
        db = firestore.client(app=app)
        db.collection("users").document(uid).update({"activo": activo})
        fb_auth.update_user(uid, disabled=not activo)
    except Exception as e:
        logger.error("Error al cambiar estado de usuario %s: %s", uid, e)


def update_user_role_firebase(uid: str, rol: str) -> None:
    """Actualiza el rol de un usuario en Firestore."""
    try:
        import firebase_admin
        from firebase_admin import firestore

        app = firebase_admin.get_app()
        db = firestore.client(app=app)
        db.collection("users").document(uid).update({"rol": rol})
    except Exception as e:
        logger.error("Error al actualizar rol de usuario %s: %s", uid, e)


# ─────────────────────────────────────────────────────────────────────────────
# Interno
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_session_from_firestore(session: UserSession) -> None:
    """
    Obtiene el perfil de usuario desde Firestore y lo agrega a la sesión.
    Se ejecuta en un hilo background — la sesión se enriquece de forma asíncrona.
    """
    def _fetch():
        try:
            import firebase_admin
            from firebase_admin import firestore

            app = firebase_admin.get_app()
            db = firestore.client(app=app)
            doc = db.collection("users").document(session.uid).get()
            if doc.exists:
                data = doc.to_dict()
                session.nombre_completo = data.get("nombre_completo", session.nombre_completo)
                session.rol = data.get("rol", "operador")
                session.activo = data.get("activo", True)
                session.extra = {k: v for k, v in data.items()
                                 if k not in ("nombre_completo", "rol", "activo", "email")}
                logger.debug("Perfil Firestore cargado para uid=%s rol=%s", session.uid, session.rol)
            else:
                # Primer login: crear perfil básico en Firestore
                _create_default_profile(session)
        except Exception as e:
            logger.warning("No se pudo enriquecer sesión desde Firestore: %s", e)

    threading.Thread(target=_fetch, name="fb-profile-fetch", daemon=True).start()


def _create_default_profile(session: UserSession) -> None:
    """Crea un perfil básico en Firestore si no existe (primer login)."""
    try:
        import firebase_admin
        from firebase_admin import firestore
        from datetime import datetime, timezone

        app = firebase_admin.get_app()
        db = firestore.client(app=app)
        db.collection("users").document(session.uid).set({
            "email": session.email,
            "nombre_completo": session.nombre_completo,
            "rol": "operador",  # rol mínimo por defecto
            "activo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, merge=True)
    except Exception as e:
        logger.error("Error al crear perfil por defecto: %s", e)


def _translate_error(code: str) -> str:
    """Traduce los códigos de error de Firebase Auth a mensajes en español."""
    translations = {
        "EMAIL_NOT_FOUND":     "Correo no registrado.",
        "INVALID_PASSWORD":    "Contraseña incorrecta.",
        "USER_DISABLED":       "Esta cuenta está desactivada.",
        "INVALID_EMAIL":       "El correo electrónico no es válido.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos. Espera unos minutos.",
        "INVALID_LOGIN_CREDENTIALS": "Correo o contraseña incorrectos.",
        "EMAIL_EXISTS":        "Ya existe una cuenta con este correo.",
        "WEAK_PASSWORD":       "La contraseña debe tener al menos 6 caracteres.",
    }
    # Buscar coincidencia parcial (Firebase a veces agrega detalles al código)
    for key, msg in translations.items():
        if key in code:
            return msg
    return f"Error de autenticación: {code}"


# ─────────────────────────────────────────────────────────────────────────────
# Disponibilidad
# ─────────────────────────────────────────────────────────────────────────────

def is_available() -> bool:
    """True si el módulo está configurado (tiene API key)."""
    return bool(_API_KEY)
