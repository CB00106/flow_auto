import time
import requests
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client
from flask import Flask, jsonify
import os

# ==================== Configuración de Gravity Forms ====================
CLIENT_KEY = "ck_f331db5cb252dd93aae1a08a90719f4f74a618b6"
CLIENT_SECRET = "cs_0a164f2c61cc4fef512259ecdd41b1e751edd731"
BASE_URL_GF = "https://www.poweractivezone.com/wp-json/gf/v2"
FORM_ID = "1"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ==================== Configuración de Supabase ====================
SUPABASE_URL = "https://hcdlnkiqyvwhnxvobgjm.supabase.co"
# Para operaciones de escritura se recomienda usar la llave service_role
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhjZGxua2lxeXZ3aG54dm9iZ2ptIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczOTMwMjkxNCwiZXhwIjoyMDU0ODc4OTE0fQ.Sj797d3lCXLJsN0FC-UXAPJjyxH44pDX20A6LF0RnTQ"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== Funciones ====================

def get_latest_entry():
    """
    Consulta la última entrada del formulario en Gravity Forms.
    """
    url = f"{BASE_URL_GF}/forms/{FORM_ID}/entries"
    response = requests.get(url, auth=HTTPBasicAuth(CLIENT_KEY, CLIENT_SECRET), headers=headers)
    if response.status_code == 200:
        data = response.json()
        entries = data.get("entries", [])
        return entries[0] if entries else None
    else:
        print(f"Error al obtener entradas (código {response.status_code})")
        return None

def update_supabase(entry):
    """
    Transforma los datos de la entrada y los inserta en la tabla 'clientes_form' de Supabase.
    Se usan las claves reales devueltas por Gravity Forms.
    """
    # Extraer y mapear los campos según el debug de Gravity Forms
    nombre = entry.get("1.3", "")
    apellido = entry.get("1.6", "")
    correo = entry.get("2", "")  # Email en la clave "2"
    genero = entry.get("21", "")
    try:
        edad = int(entry.get("22", 0))
    except ValueError:
        edad = 0
    try:
        peso = float(entry.get("24", 0))
    except ValueError:
        peso = 0.0
    try:
        altura = float(entry.get("18", 0))
    except ValueError:
        altura = 0.0
    objetivo = entry.get("27", "")
    nivel_actividad = entry.get("26", "sedentario")
    
    # Procesar preferencias y restricciones (ajusta las claves según tu formulario)
    preferencias = []
    # Por ejemplo, si usas "32.9" y "32.11" para preferencias:
    for key in ["32.9", "32.11"]:
        val = entry.get(key, "").strip()
        if val:
            preferencias.append(val)
            
    restricciones = []
    # Por ejemplo, si usas "33.11" para restricciones:
    for key in ["33.11"]:
        val = entry.get(key, "").strip()
        if val and val.lower() != "ninguna":
            restricciones.append(val)
            
    # Comentarios (por ejemplo, en la clave "34")
    comentarios = entry.get("34", "")
    
    # Preparar el registro de acuerdo a la estructura de la tabla clientes_form
    record = {
        "nombre": nombre,
        "apellido": apellido,
        "email": correo,
        "genero": genero,
        "edad": edad,
        "peso": peso,
        "altura": altura,
        "objetivo": objetivo,
        "nivel_actividad": nivel_actividad,
        "grasa_corporal": None,  # o 0.0, según prefieras
        "masa_muscular": None,   # o 0.0
        "preferencias": preferencias,
        "restricciones": restricciones,
        "comentarios": comentarios,
        # "job_id" se actualizará posteriormente
    }
    
    print("Record a insertar en Supabase:", record)
    
    try:
        response = supabase.table("clientes_form").insert(record).execute()
        print("Respuesta de Supabase:", response)
    except Exception as e:
        print("Excepción durante la inserción en Supabase:", e)


# ==================== Ciclo Principal ====================

def main():
    last_entry_id = None
    while True:
        entry = get_latest_entry()
        if entry:
            entry_id = entry.get("id")
            if entry_id != last_entry_id:
                last_entry_id = entry_id
                print(f"Nueva entrada detectada (ID: {entry_id}). Actualizando Supabase...")
                update_supabase(entry)
            else:
                print("No hay nuevas entradas.")
        else:
            print("No se pudo obtener la última entrada.")
        time.sleep(60)  # Espera 60 segundos antes de volver a consultar

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"message": "La aplicación Flask se está ejecutando correctamente en Render."})

# Puedes agregar otros endpoints según lo requieras, por ejemplo, para forzar una actualización:
@app.route('/update')
def update():
    entry = get_latest_entry()
    if entry:
        update_supabase(entry)
        return jsonify({"message": "Supabase actualizado con la entrada más reciente."})
    else:
        return jsonify({"error": "No se pudo obtener la entrada."}), 500

if __name__ == '__main__':
        main()
