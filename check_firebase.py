"""
check_firebase.py — Diagnóstico del estado de Firebase
Uso: python check_firebase.py
"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).parent

# ── Cargar firebase_admin ─────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, auth
except ImportError:
    print("❌ firebase-admin no instalado. Corre: pip install firebase-admin")
    sys.exit(1)

# ── Inicializar ───────────────────────────────────────────────────────────────
key_file = ROOT / "firebase-key.json"
if not key_file.exists():
    print(f"❌ No se encontró {key_file}")
    sys.exit(1)

cred = credentials.Certificate(str(key_file))
firebase_admin.initialize_app(cred)
db = firestore.client()

print("\n" + "="*60)
print("  DIAGNÓSTICO FIREBASE — V-Metric")
print("="*60)

# ── 1. Firebase Auth ──────────────────────────────────────────────────────────
print("\n📋 USUARIOS EN FIREBASE AUTH")
print("-"*60)
try:
    page = auth.list_users()
    users = list(page.users)
    if not users:
        print("  ⚠️  VACÍO — no hay usuarios registrados")
        print("  → Necesitas crear usuarios con el panel de Admin de la app")
    else:
        for u in users:
            estado = "🔴 desactivado" if u.disabled else "🟢 activo"
            print(f"  {estado} | {u.email} | uid: {u.uid[:20]}...")
except Exception as e:
    print(f"  ❌ Error al listar usuarios Auth: {e}")

# ── 2. Firestore users/ ───────────────────────────────────────────────────────
print("\n📋 PERFILES EN FIRESTORE (users/)")
print("-"*60)
try:
    fs_users = list(db.collection("users").stream())
    if not fs_users:
        print("  ⚠️  VACÍA — los perfiles se crean al primer login")
    else:
        for u in fs_users:
            d = u.to_dict()
            print(f"  uid: {u.id[:20]}... | email: {d.get('email')} | rol: {d.get('rol')} | activo: {d.get('activo')}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ── 3. Activity log ───────────────────────────────────────────────────────────
print("\n📋 ACTIVITY LOG (últimos 10)")
print("-"*60)
try:
    logs = list(
        db.collection("activity_log")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    if not logs:
        print("  ⚠️  VACÍA — ninguna acción registrada aún")
    else:
        for l in logs:
            d = l.to_dict()
            print(f"  {str(d.get('created_at',''))[:19]} | {d.get('accion','?'):30} | uid: {str(d.get('uid',''))[:15]}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ── 4. Reservorios / DEM history ──────────────────────────────────────────────
print("\n📋 HISTORIAL DE DEMs POR RESERVORIO")
print("-"*60)
try:
    reservorios = ["R1","R2","R3","R4","R5","R6","R7","R8","R9","R10"]
    alguno = False
    for cod in reservorios:
        dems = list(db.collection("reservorios").document(cod).collection("dem_history").limit(3).stream())
        if dems:
            alguno = True
            print(f"  {cod}: {len(dems)} DEM(s) registrados")
            for d in dems:
                dd = d.to_dict()
                print(f"       archivo: {dd.get('archivo')} | fecha_vuelo: {dd.get('fecha_vuelo')}")
    if not alguno:
        print("  ⚠️  Sin DEMs registrados en ningún reservorio")
except Exception as e:
    print(f"  ❌ Error: {e}")

# ── 5. Cubicaciones history ───────────────────────────────────────────────────
print("\n📋 HISTORIAL DE CUBICACIONES")
print("-"*60)
try:
    alguna = False
    for cod in reservorios:
        cubs = list(db.collection("reservorios").document(cod).collection("cubicaciones_history").limit(3).stream())
        if cubs:
            alguna = True
            print(f"  {cod}: {len(cubs)} cubicación(es)")
            for c in cubs:
                cd = c.to_dict()
                print(f"       {str(cd.get('created_at',''))[:19]} | vol_total: {cd.get('brine_total_m3')} m³")
    if not alguna:
        print("  ⚠️  Sin cubicaciones registradas aún")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "="*60)
print("  FIN DEL DIAGNÓSTICO")
print("="*60 + "\n")
