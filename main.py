import time
import requests
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client
import os

# ==================== Configuración de Gravity Forms ====================
CLIENT_KEY = "ck_f331db5cb252dd93aae1a08a90719f4f74a618b6"
CLIENT_SECRET = "cs_0a164f2c61cc4fef512259ecdd41b1e751edd731"
BASE_URL_GF = "https://www.poweractivezone.com/wp-json/gf/v2"
FORM_ID = "1"

# ==================== Configuración de Supabase ====================
SUPABASE_URL = "https://hcdlnkiqyvwhnxvobgjm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhjZGxua2lxeXZ3aG54dm9iZ2ptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzkzMDI5MTQsImV4cCI6MjA1NDg3ODkxNH0.1w2xEbHnEC8K2ELljynxyXm98MXw-sLiRDpX_WmiAFE"  # Usa tu llave 'service_role'
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_latest_entry():
    """
    Consulta la última entrada del formulario en Gravity Forms.
    """
    url = f"{BASE_URL_GF}/forms/{FORM_ID}/entries"
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

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
    Inserta en la tabla clientes_form según:
    CREATE TABLE clientes_form (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        nombre TEXT NOT NULL,
        apellido TEXT NOT NULL,
        email TEXT NOT NULL,
        genero TEXT NOT NULL,
        edad INT NOT NULL,
        peso FLOAT NOT NULL,
        altura FLOAT NOT NULL,
        objetivo TEXT NOT NULL,
        nivel_actividad TEXT NOT NULL,
        masa_adiposa FLOAT NOT NULL,
        masa_muscular FLOAT NOT NULL,
        preferencias JSONB NOT NULL,
        restricciones JSONB NOT NULL,
        restricciones_explicitas TEXT NOT NULL,
        enfemedades TEXT NOT NULL,
        tipo_enfermedad TEXT,
        fecha_creacion TIMESTAMP DEFAULT NOW(),
        job_id TEXT UNIQUE,
        create_by TEXT NOT NULL
    );
    
    Se basa en los campos vistos en la última entrada. Ajusta si cambian.
    """

    def safe_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    def safe_float(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    # -------------------------------------------------
    # 1) Campos obligatorios del formulario
    # -------------------------------------------------
    nombre = entry.get("1.3", "").strip()       # 'César'
    apellido = entry.get("1.6", "").strip()     # 'Briones'
    email = entry.get("2", "").strip()          # 'cesar_106@hotmail.com'
    genero = entry.get("21", "").strip()        # 'Masculino'
    edad = safe_int(entry.get("22", 0))         # '25'
    peso = safe_float(entry.get("24", 0))       # '23'
    altura = safe_float(entry.get("18", 0))     # '23'
    objetivo = entry.get("27", "").strip()      # 'Perder Peso'
    nivel_actividad = entry.get("26", "").strip() or "sedentario"

    # -------------------------------------------------
    # 2) Masa adiposa y masa muscular
    #    Supongamos que:
    #       "29" => masa_adiposa
    #       "30" => masa_muscular
    # -------------------------------------------------
    masa_adiposa = safe_float(entry.get("29", 0))   # '23'
    masa_muscular = safe_float(entry.get("30", 0))  # '23'

    # -------------------------------------------------
    # 3) Preferencias y restricciones (JSONB)
    #    Observamos que:
    #      "32.3" => 'Keto'
    #      "33.5" => 'Libre de cacahuates (Peanuts-Free)'
    #    Ajustamos para meterlo en arrays:
    # -------------------------------------------------
    preferencias = []
    for i in range(1, 11):
        key = f"32.{i}"
        if entry.get(key, "").strip():
            preferencias.append(entry[key].strip())

    restricciones = []
    for i in range(1, 11):
        key = f"33.{i}"
        if entry.get(key, "").strip():
            restricciones.append(entry[key].strip())

    # -------------------------------------------------
    # 4) restricciones_explicitas, enfemedades, tipo_enfermedad
    #    Según tu ejemplo:
    #      "34" => '23' (quizá sea un comentario adicional)
    #      "40" => 'Second Choice' (podría ser tipo_enfermedad o enfermedad)
    #    Ajusta según tu lógica real:
    # -------------------------------------------------
    restricciones_explicitas = entry.get("34", "").strip() or "Sin comentarios"
    # Supongamos que "40" te indica el tipo de enfermedad
    tipo_enfermedad = entry.get("39", "").strip() or None

    # Si no definiste un campo específico en Gravity Forms para 'enfemedades'
    # y no hay un valor claro, deja 'Ninguna':
    enfemedades = entry.get("40", "").strip() or None

    # -------------------------------------------------
    # 5) job_id y create_by
    #    - 'created_by' => '2' (ID de usuario WP).
    #    - 'source_id' => '1967'
    #    Podrías guardar 'id' de la entrada GF como job_id,
    #    o 'source_id'; escoge uno. Aquí usaremos 'source_id'.
    # -------------------------------------------------
    job_id = entry.get("source_id", None)
    create_by = entry.get("created_by", "GravityForms").strip()

    # -------------------------------------------------
    # 6) Construcción del registro
    # -------------------------------------------------
    record = {
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
        "genero": genero,
        "edad": edad,
        "peso": peso,
        "altura": altura,
        "objetivo": objetivo,
        "nivel_actividad": nivel_actividad,
        "masa_adiposa": masa_adiposa,
        "masa_muscular": masa_muscular,
        "preferencias": preferencias,  # JSONB
        "restricciones": restricciones,  # JSONB
        "restricciones_explicitas": restricciones_explicitas,
        "enfemedades": enfemedades,
        "tipo_enfermedad": tipo_enfermedad,
        "job_id": job_id,
        "create_by": create_by
    }

    print("Insertando registro en Supabase:", record)
    try:
        response = supabase.table("clientes_form").insert(record).execute()
        print("Respuesta de Supabase:", response)
    except Exception as e:
        print("Error al insertar en Supabase:", e)

def main():
    """
    Bucle infinito que:
      1. Consulta la entrada más reciente de Gravity Forms.
      2. Si es nueva, la inserta en Supabase.
      3. Espera 60 segundos y repite.
    """
    last_entry_id = None
    print("Iniciando background worker de sincronización...")

    while True:
        entry = get_latest_entry()
        if entry:
            entry_id = entry.get("id")
            if entry_id and entry_id != last_entry_id:
                print(f"Nueva entrada detectada (ID: {entry_id}). Subiendo a Supabase...")
                update_supabase(entry)
                last_entry_id = entry_id
            else:
                print("No hay nuevas entradas o ID repetido.")
        else:
            print("No se obtuvo entrada válida de Gravity Forms.")
        
        time.sleep(60)  # Espera 60s antes de la siguiente consulta

if __name__ == "__main__":
    main()
