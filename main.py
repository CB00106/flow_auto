import os
import time
import json
import threading
import requests
from time import sleep
from flask import Flask, request, jsonify
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client
from openai import OpenAI, OpenAIError  # Usamos DeepSeek vía la API de OpenAI

# ==================== Configuración de variables y clientes ====================

# Variables de entorno para APIs y Supabase
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
EDAMAM_APP_ID = os.environ.get('EDAMAM_APP_ID')
EDAMAM_APP_KEY = os.environ.get('EDAMAM_APP_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
PORT = int(os.environ.get('PORT', 5000))
EDAMAM_BASE_URL = "https://api.edamam.com"
EDAMAM_PARSER_ENDPOINT = "/api/food-database/v2/parser"
EDAMAM_NUTRIENTS_ENDPOINT = "/api/food-database/v2/nutrients"

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
        return entries[-1] if entries else None  # Retorna la última entrada
    else:
        print(f"Error obteniendo respuestas: {response.status_code}")
        return None

# ==================== Funciones para el procesamiento del menú ====================

def calcular_imc(peso, altura):
    """Calcula el IMC y su clasificación."""
    altura_m = altura / 100  # Convertir cm a metros
    imc = peso / (altura_m ** 2)
    if imc < 18.5:
        clasificacion = "Bajo peso"
    elif 18.5 <= imc < 24.9:
        clasificacion = "Peso normal"
    elif 25 <= imc < 29.9:
        clasificacion = "Sobrepeso"
    elif 30 <= imc < 34.9:
        clasificacion = "Obesidad grado I"
    elif 35 <= imc < 39.9:
        clasificacion = "Obesidad grado II"
    else:
        clasificacion = "Obesidad grado III (mórbida)"
    return round(imc, 2), clasificacion

def calcular_calorias_totales(peso, altura, edad, sexo, nivel_actividad, metas):
    """Calcula las calorías totales recomendadas."""
    if sexo.lower() == "masculino":
        tmb = 10 * peso + 6.25 * altura - 5 * edad + 5
    else:
        tmb = 10 * peso + 6.25 * altura - 5 * edad - 161

    nivel_actividad_factor = {
        "sedentario": 1.2,
        "ligeramente activo": 1.375,
        "moderadamente activo": 1.55,
        "muy activo": 1.725,
        "extremadamente activo": 1.9
    }
    factor = nivel_actividad_factor.get(nivel_actividad.lower(), 1.2)
    calorias_totales = tmb * factor
    if metas.lower() == "perder peso":
        calorias_totales -= 500
    elif metas.lower() == "ganar peso":
        calorias_totales += 500
    return round(calorias_totales)

def buscar_alimentos_edamam(query):
    response = requests.get(
        f"{EDAMAM_BASE_URL}{EDAMAM_PARSER_ENDPOINT}",
        params = {
        "app_id": EDAMAM_APP_ID,
        "app_key": EDAMAM_APP_KEY,
        "ingr": query,
        "category": "generic-foods",
        "calories": "50-500",
        "nutrients[PROCNT]": "5+",
        "nutrients[CHOCDF]": "0-50",
        "nutrients[FAT]": "0-20",
        }, 
    timeout=10
    )
    if response.status_code == 200:
        data = response.json()
        alimentos = []
        if "parsed" in data and data["parsed"]:
            alimentos.extend([item["food"] for item in data["parsed"]])
        if "hints" in data:
            alimentos.extend([hint["food"] for hint in data["hints"]])
        return alimentos[:28]
    else:
        print(f"Error al consultar Edamam: {response.status_code}, {response.text}")
    return []
def obtener_nutrientes_edamam(ingredientes):
    ingredientes = [ing for ing in ingredientes if "foodId" in ing][:5]  # Filtrar y limitar explícitamente a 5 ingredientes

    if not ingredientes:
        print("No hay ingredientes válidos para enviar a Edamam.")
        return {}

    payload = {
        "ingredients": [
            {
                "quantity": 1,
                "measureURI": "http://www.edamam.com/ontologies/edamam.owl#Measure_gram",
                "foodId": ing["foodId"]
            } for ing in ingredientes
        ]
    }
    response = requests.post(
        f"{EDAMAM_BASE_URL}{EDAMAM_NUTRIENTS_ENDPOINT}",
        json=payload,
        params={
            "app_id": EDAMAM_APP_ID,
            "app_key": EDAMAM_APP_KEY
        }
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error al consultar nutrientes en Edamam: {response.status_code}, {response.text}")
    return {}

# Función para ajustar porciones según calorías
def ajustar_porciones(nutrientes, calorias_totales):
    alimentos_ajustados = []
    calorias_acumuladas = 0

    for alimento in nutrientes.get("ingredients", []):
        detalles_nutrientes = alimento.get("parsed", {}).get("nutrients", {})
        calorias_porcion = detalles_nutrientes.get("ENERC_KCAL", {}).get("quantity", 0)
        proteina = detalles_nutrientes.get("PROCNT", {}).get("quantity", 0)
        carbohidratos = detalles_nutrientes.get("CHOCDF", {}).get("quantity", 0)
        grasa = detalles_nutrientes.get("FAT", {}).get("quantity", 0)

        if calorias_acumuladas + calorias_porcion <= calorias_totales:
            alimentos_ajustados.append({
                "nombre": alimento.get("parsed", {}).get("food", {}).get("label", ""),
                "cantidad": alimento.get("parsed", {}).get("quantity", 0),
                "calorias": calorias_porcion,
                "proteina": proteina,
                "carbohidratos": carbohidratos,
                "grasa": grasa
            })
            calorias_acumuladas += calorias_porcion


    return alimentos_ajustados

# Generar menú utilizando la API de OpenAI
def generar_menu_con_chatgpt(alimentos_ajustados, calorias, preferencias, restricciones, restricciones_explicitas):
    pref_texto = ", ".join(preferencias) if preferencias else "sin preferencias específicas"
    restr_texto = "sin restricciones" if not restricciones or restricciones == ["ninguna"] else ", ".join(restricciones)
    restr_expl_texto = "sin restricciones explícitas" if not restricciones_explicitas else ", ".join(restricciones_explicitas)

    messages = [
        {"role": "system", "content": "Eres un asistente experto en nutrición."},
        {"role": "user", "content": f"Genera un plan de comidas basado en las siguientes especificaciones:\n"
                                     f"- Calorías diarias totales: {calorias}\n"
                                     f"- Preferencias: {pref_texto}\n"
                                     f"- Restricciones: {restr_texto}\n"
                                     f"- Restricciones explícitas (alimentos que deben ser excluidos): {restr_expl_texto}\n"
                                     f"- Usa los siguientes alimentos y cantidades para el menú:\n"
                                     f"{json.dumps(alimentos_ajustados, indent=2)}\n"
                                     f"- Las {calorias} deben distribuirse en 3 comidas principales, desayuno, almuerzo y cena, y 2 snacks, a esta distribucion de comidas le llamaras menu\n"
                                     f"  - el desayuno debe tener 20% de las calorías totales\n"
                                     f"  - el almuerzo debe tener 30% de las calorías totales\n"
                                     f"  - la cena debe tener 30% de las calorías totales\n"
                                     f"  - los snacks deben tener 20% de las calorías totales\n"
                                     f"- Cada comida debe incluir alimentos variados y balanceados.\n"
                                     f"  - 40% de las calorías deben provenir de proteína.\n"
                                     f"  - 40% de las calorías deben provenir de carbohidratos.\n"
                                     f"  - 20% de las calorías deben provenir de grasas.\n"
                                     f"- Usa opciones saludables y accesibles.\n"
                                     f"- Debes generar dos menus con el total de {calorias} cada uno.\n"
                                     f"  - Opcion 1 = {calorias}.\n"
                                     f"  - Opcion 2 = {calorias}.\n"
                                     f"  - Dos opciones diferentes para almuerzo.\n"
                                     f"  - Dos opciones diferentes para cena.\n"
                                     f"  - Dos opciones diferentes para snacks.\n"
                                     f"  - Cada opcion debe priorizar ingredientes americanos, mexicanos, italianos\n"
                                     f"- Acompaña cada opción con una breve descripción o instrucciones sobre cómo prepararla o consumirla.\n"
                                     f"- Por favor, estructura el menú en Opcion 1 = desayuno, almuerzo, cena y snacks y posteriormente Opcion 2 = desayuno, almuerzo, cena y snacks\n"
                                     f"- incluye siempre las porciones de cada alimento y las calorías totales de cada comida\n"
                                     f"- Por favor, estructura el menú con el siguiente formato:\n"
                                     f"  - Título de la Opción\n"
                                     f"  - Texto generado con el menú y las instrucciones breves\n"
                                     f"  - Macronutrientes (proteínas, carbohidratos netos y grasas) y sus contribuciones calóricas.\n"
                                     f"- el resultado debe venir en una estrucutra que cumpla con, Titulo, calorias, instrucciones y macronutrientes totales.\n"
                                     f"- evita añadir caracteristicas especiales o simbolos tiporgrafios en la respuesta, esto es para evitar removerlos en una fase posterior" 
                                     f"- por favor evita saludos o despedidas, para ahorrar tokens, gracias"}
    ]

    for _ in range(3):
        try:
            response = client.chat.completions.create(
                model="deepseek-reasoner",
                messages=messages,
            )
            return response.choices[0].message.content.strip()
        except OpenAIError as e:
            print(f"Error de deepseek: {e}")
            sleep(2)

    return "No se pudo generar un menú en este momento. Inténtalo más tarde."

# ==================== Configuración de Flask y endpoints ====================

app = Flask(__name__)
jobs = {}  # Diccionario para almacenar el estado de los trabajos

@app.route('/generar-menu', methods=['POST'])
def generar_menu_route():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Formato JSON inválido o datos faltantes"}), 400

    job_id = f"job_{int(time.time())}"
    jobs[job_id] = {"status": "processing"}
    # Se inicia el procesamiento en un hilo separado
    threading.Thread(target=procesar_menu, args=(job_id, data), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "processing"}), 202

@app.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job ID no encontrado"}), 404
    return jsonify(job)

def procesar_menu(job_id, data):
    try:
        # Transformar "Nombre Completo" en "nombre" y "apellido"
        full_name = data.get("Nombre Completo", "")
        tokens = full_name.split()
        nombre = tokens[0] if tokens else ""
        apellido = " ".join(tokens[1:]) if len(tokens) > 1 else ""
        email = data.get("Email")  # Se asume que el formulario incluye Email
        sexo = data.get("Sexo")
        edad = int(data.get("Edad", 0))
        peso = float(data.get("Peso", 0))
        altura = float(data.get("Altura", 0))
        metas = data.get("Metas")
        preferencias = data.get("Selecciona tus preferencias", [])
        restricciones = data.get("Restrictions Alimenticias o Alérgicas", [])
        restricciones_explicitas = data.get("restricciones_explicitas", [])
        nivel_actividad = data.get("Nivel de Actividad Física Actual", "sedentario")

        # Calcular datos nutricionales
        calorias = calcular_calorias_totales(peso, altura, edad, sexo, nivel_actividad, metas)
        imc, clasificacion_imc = calcular_imc(peso, altura)

        # Buscar alimentos (se puede ajustar o filtrar según requerimientos)
        alimentos = buscar_alimentos_edamam("comida saludable")
        # Generar menú usando ChatGPT/DeepSeek
        menu = generar_menu_con_chatgpt(alimentos, calorias, preferencias, restricciones, restricciones_explicitas)

        # Actualizar el trabajo en memoria
        jobs[job_id] = {
            "status": "completed",
            "result": {
                "nombre": full_name,
                "calorias_recomendadas": calorias,
                "IMC": imc,
                "Clasificación IMC": clasificacion_imc,
                "menu": menu
            }
        }

        # Actualizar el registro en Supabase con el job_id (se usa el email como identificador único)
        update_response = supabase.table("clientes_form").update({"job_id": job_id}).eq("email", email).execute()
        if hasattr (update_response, "error") and update_response.error:
            print("Error actualizando job_id en Supabase:", update_response.error)
        else:
            print("job_id actualizado en Supabase:", update_response.data)
    except Exception as e:
        jobs[job_id] = {"status": "failed", "error": str(e)}

# ==================== Función de consulta periódica a Gravity Forms ====================

last_entry_id = None  # Variable global para almacenar el último ID procesado

def check_for_new_entries():
    """Consulta cada minuto Gravity Forms y, al detectar una nueva entrada, la procesa."""
    global last_entry_id
    # Se espera un poco para que el servidor Flask inicie
    sleep(5)
    while True:
        entry = get_latest_entry()
        if entry:
            entry_id = entry.get("id")
            if entry_id != last_entry_id:
                last_entry_id = entry_id
                print(f"Nueva entrada detectada: {entry_id}")
                # Transformar datos del formulario para adecuarlos al registro de Supabase
                # Se espera que la entrada incluya los siguientes campos:
                # "Nombre Completo", "Email", "Sexo", "Edad", "Peso", "Altura",
                # "Metas", "Selecciona tus preferencias", "Restrictions Alimenticias o Alérgicas",
                # "restricciones_explicitas", "Nivel de Actividad Física Actual", "Comentarios"
                data = entry

                # Transformar "Nombre Completo"
                full_name = data.get("Nombre Completo", "")
                tokens = full_name.split()
                nombre = tokens[0] if tokens else ""
                apellido = " ".join(tokens[1:]) if len(tokens) > 1 else ""
                record = {
                    "nombre": nombre,
                    "apellido": apellido,
                    "email": data.get("Email"),
                    "genero": data.get("Sexo"),
                    "edad": int(data.get("Edad", 0)),
                    "peso": float(data.get("Peso", 0)),
                    "altura": float(data.get("Altura", 0)),
                    "objetivo": data.get("Metas"),
                    "nivel_actividad": data.get("Nivel de Actividad Física Actual", "sedentario"),
                    "preferencias": data.get("Selecciona tus preferencias", []),
                    "restricciones": data.get("Restrictions Alimenticias o Alérgicas", []),
                    "comentarios": data.get("Comentarios", "")
                    # Los campos grasa_corporal y masa_muscular se dejan como NULL
                }
                # Insertar el registro en Supabase inmediatamente
                insert_response = supabase.table("clientes_form").insert(record).execute()
                if insert_response.error:
                    print("Error insertando en Supabase:", insert_response.error)
                else:
                    print("Registro insertado en Supabase:", insert_response.data)

                # Invocar el endpoint POST /generar-menu con la data obtenida
                try:
                    url = f"http://127.0.0.1:{PORT}/generar-menu"
                    response = requests.post(url, json=data)
                    if response.status_code in [200, 202]:
                        job_info = response.json()
                        print("Menú generado, job_id:", job_info.get("job_id"))
                    else:
                        print("Error al invocar /generar-menu:", response.text)
                except Exception as e:
                    print("Error al invocar /generar-menu:", e)
        else:
            print("No se encontraron entradas en Gravity Forms.")
        time.sleep(60)  # Espera 60 segundos antes de la siguiente consulta

# ==================== Inicio del servidor y del proceso de consulta periódica ====================

if __name__ == '__main__':
    # Iniciar el hilo que consulta Gravity Forms cada minuto
    threading.Thread(target=check_for_new_entries, daemon=True).start()
    print(f"Servidor iniciado en el puerto {PORT} y monitoreando nuevas entradas en Gravity Forms...")
    app.run(host='0.0.0.0', port=PORT)
