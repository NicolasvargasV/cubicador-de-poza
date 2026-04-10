"""
setup_admin.py — Crea el usuario administrador inicial en Firebase Auth + Firestore
Uso: python setup_admin.py

Edita las variables ADMIN_* antes de correr.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

# ── CONFIGURA AQUÍ EL ADMIN ───────────────────────────────────────────────────
ADMIN_EMAIL    = "admin@vmetric.cl"       # ← cambia al email real
ADMIN_PASSWORD = "Admin123!"              # ← cambia a contraseña segura
ADMIN_NOMBRE   = "Administrador"
# ─────────────────────────────────────────────────────────────────────────────

DATABASE_ID = "v-metric"
ROOT = Path(__file__).parent

try:
    import firebase_admin
    from firebase_admin import credentials, auth, firestore
except ImportError:
    print("❌ Instala firebase-admin: pip install firebase-admin")
    sys.exit(1)

key_file = ROOT / "firebase-key.json"
if not key_file.exists():
    print(f"❌ No se encontró {key_file}")
    sys.exit(1)

# Inicializar
cred = credentials.Certificate(str(key_file))
firebase_admin.initialize_app(cred)
db = firestore.client(database=DATABASE_ID)

print(f"\n🔧 Configurando usuario admin en Firebase...")
print(f"   Email:    {ADMIN_EMAIL}")
print(f"   Nombre:   {ADMIN_NOMBRE}")
print(f"   Database: {DATABASE_ID}\n")

# ── 1. Crear usuario en Firebase Auth ─────────────────────────────────────────
try:
    user = auth.get_user_by_email(ADMIN_EMAIL)
    print(f"⚠️  Usuario ya existe en Auth (uid: {user.uid}) — actualizando...")
    auth.update_user(user.uid, password=ADMIN_PASSWORD, display_name=ADMIN_NOMBRE)
    uid = user.uid
    print(f"✅ Auth actualizado")
except auth.UserNotFoundError:
    user = auth.create_user(
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        display_name=ADMIN_NOMBRE,
    )
    uid = user.uid
    print(f"✅ Usuario creado en Firebase Auth (uid: {uid})")
except Exception as e:
    print(f"❌ Error en Firebase Auth: {e}")
    sys.exit(1)

# ── 2. Crear perfil en Firestore users/{uid} ──────────────────────────────────
try:
    doc_ref = db.collection("users").document(uid)
    doc_ref.set({
        "email":           ADMIN_EMAIL,
        "nombre_completo": ADMIN_NOMBRE,
        "rol":             "admin",
        "activo":          True,
        "created_at":      datetime.now(timezone.utc).isoformat(),
    }, merge=True)
    print(f"✅ Perfil creado en Firestore (users/{uid})")
except Exception as e:
    print(f"❌ Error en Firestore: {e}")
    sys.exit(1)

print(f"""
════════════════════════════════════════
  ✅ Admin configurado correctamente
════════════════════════════════════════
  Email:      {ADMIN_EMAIL}
  Contraseña: {ADMIN_PASSWORD}
  uid:        {uid}

  ⚠️  Cambia la contraseña en el primer login.
════════════════════════════════════════
""")
