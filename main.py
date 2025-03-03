import os
import time
import json
import threading
import requests
from time import sleep
from flask import Flask, request, jsonify
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client
from openai import OpenAI, OpenAIError

# ==================== Configuración de variables y clientes ====================
# Variables de entorno para APIs y Supabase
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
EDAMAM_APP_ID = os.environ.get('EDAMAM_APP_ID')
EDAMAM_APP_KEY = os.environ.get('EDAMAM_APP_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
PORT = int(os.environ.get('PORT', 5000))

# En producción, BASE_URL debe ser el dominio asignado por Render (defínelo en las variables de entorno)
BASE_URL = os.environ.get('BASE_URL', f"http://localhost:{PORT}")

# Inicializar el cliente de Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuración para Gravity Forms
CLIENT_KEY = "ck_f331db5cb252dd93aae1a08a90719f4f74a618b6"
CLIENT_SECRET = "cs_0a164f2c61cc4fef512259ecdd41b1e751edd731"
BASE_URL_GF = "https://www.poweractivezone.com/wp-json/gf/v2"
FORM_ID = "1"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Inicializar cliente DeepSeek (usando la API de OpenAI configurada para deepseek)
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")

# ==================== Funciones de Gravity Forms ====================

def get_form_fields():
    """Obtiene la estructura del formulario y mapea los campos."""
    url = f"{BASE_URL_GF}/forms/{FORM_ID}"
    response = requests.get(url, auth=HTTPBasicAuth(CLIENT_KEY, CLIENT_SECRET), headers=headers)
    if response.status_code == 200:
        form_data = response.json()
        fields = form_data.get("fields", [])
        field_mapping = {str(field["id"]): field.get("label", f"Campo {field['id']}") for field in fields}
        return field_mapping
    else:
        print(f"Error obteniendo campos: {response.status_code}")
        return {}

def get_latest_entry():
    """Consulta la última respuesta del formulario de Gravity Forms."""
    url = f"{BASE_URL_GF}/forms/{FORM_ID}/entries"
    response = requests.get(url, auth=HTTPBasicAuth(CLIENT_KEY, CLIENT_SECRET), headers=headers)
    if response.status_code == 200:
        data = response.json()
        entries = data.get("entries", [])
        return entries[-1] if entries else None
    else:
        print(f"Error obteniendo respuestas: {response.status_code}")
        return None

# ==================== Función para actualizar Supabase ====================

def update_supabase(entry):
    """
    Transforma los datos de la entrada y los inserta en la tabla 'clientes_form' de Supabase.
    Mapea los campos de Gravity Forms a la estructura de la tabla.
    
    Mapeo según el debug:
      - "1.3": Nombre
      - "1.6": Apellido
      - "2": Email
      - "21": Género
      - "22": Edad
      - "24": Peso
      - "18": Altura
      - "27": Objetivo
      - "26": Nivel de Actividad
      - "32.9" y "32.11": Preferencias
      - "33.11": Restricciones
      - "34": Comentarios
    """
    nombre = entry.get("1.3", "")
    apellido = entry.get("1.6", "")
    correo = entry.get("2", "")
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
    
    preferencias = []
    for key in ["32.9", "32.11"]:
        val = entry.get(key, "").strip()
        if val:
            preferencias.append(val)
            
    restricciones = []
    for key in ["33.11"]:
        val = entry.get(key, "").strip()
        if val and val.lower() != "ninguna":
            restricciones.append(val)
            
    comentarios = entry.get("34", "")
    
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
        "grasa_corporal": None,  # Se puede actualizar posteriormente
        "masa_muscular": None,   # Se puede actualizar posteriormente
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

# ==================== Función de consulta periódica a Gravity Forms ====================

last_entry_id = None  # Almacena el último ID procesado

def check_for_new_entries():
    """Consulta cada minuto Gravity Forms y, al detectar una nueva entrada, actualiza Supabase."""
    global last_entry_id
    sleep(5)  # Espera inicial para asegurar que todo esté configurado
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
        time.sleep(60)

# ==================== Configuración de Flask y servidor ====================

app = Flask(__name__)
jobs = {}  # Diccionario para almacenar estados (si en el futuro se agregan endpoints)

# En este script se enfoca únicamente en la actualización a Supabase a partir de Gravity Forms.

# ==================== Inicio del servidor y del proceso de consulta ====================

if __name__ == '__main__':
    # En producción con gunicorn, se recomienda que el background checker se inicie solo en el worker principal.
    if os.environ.get("RUN_CHECKER", "true").lower() == "true":
        threading.Thread(target=check_for_new_entries, daemon=True).start()
        print("Background checker thread iniciado.")
    else:
        print("Background checker thread deshabilitado.")
        
    print(f"Servidor iniciado en el puerto {PORT} con BASE_URL={BASE_URL}...")
    app.run(host='0.0.0.0', port=PORT)
