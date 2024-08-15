import streamlit as st
import pandas as pd
import re
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from io import BytesIO
from PIL import Image
import requests
import os
from geopy.distance import geodesic  # Para calcular la distancia entre dos coordenadas

# Configuración de Azure Form Recognizer
endpoint = "https://demoocr.cognitiveservices.azure.com/"
key = "125c4bac6511481290029459b6cf96c2"

# Clave de API de Google Maps
API_KEY = 'AIzaSyAup1kQpy0W1gyaWOY2IoUl9VAHP_7pxYI'

# URL de la API de Geocoding
GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# URL de la API de Static Maps
STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"

# URL de la API de Places para buscar tipos de lugares cercanos
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Función para eliminar palabras clave no deseadas y normalizar la dirección
def clean_and_normalize_address(address):
    # Paso 1: Eliminar palabras clave no deseadas
    address = re.sub(r'\b(OFICINA|APT|APARTAMENTO|PISO|DEPTO|INTERIOR)\b\s*\d*', '', address, flags=re.IGNORECASE)
    
    # Paso 2: Normalizar la dirección y eliminar referencias duplicadas
    # Convertir diferentes abreviaciones de "Carrera" a "Carrera"
    address = re.sub(r'\b(CRA|CRR|CR|CARR)\b', 'Carrera', address, flags=re.IGNORECASE)
    # Convertir diferentes abreviaciones de "Calle" a "Calle"
    address = re.sub(r'\b(CLL|CL|CALLE)\b', 'Calle', address, flags=re.IGNORECASE)
    # Convertir diferentes abreviaciones de "Diagonal" a "Diagonal"
    address = re.sub(r'\b(DG|DIAG|DIAGONAL)\b', 'Diagonal', address, flags=re.IGNORECASE)

    # Paso 3: Eliminar referencias duplicadas (solo dejar la primera ocurrencia)
    address_parts = address.split()
    primary_type = None
    normalized_address = []
    for part in address_parts:
        if part.lower() in ["carrera", "calle", "diagonal"]:
            if not primary_type:
                primary_type = part.lower()
                normalized_address.append(part)
        else:
            normalized_address.append(part)

    # Convertir todo a minúsculas para comparación uniforme
    normalized_address = " ".join(normalized_address).lower()
    
    # Eliminar espacios extra
    normalized_address = re.sub(r'\s+', ' ', normalized_address).strip()

    return normalized_address

def obtener_coordenadas(direccion):
    parametros = {
        'address': direccion,
        'key': API_KEY
    }
    respuesta = requests.get(GEOCODING_URL, params=parametros)
    if respuesta.status_code == 200:
        datos = respuesta.json()
        if datos['status'] == 'OK':
            ubicacion = datos['results'][0]['geometry']['location']
            return ubicacion['lat'], ubicacion['lng']
    return None, None

def obtener_imagen_mapa(latitud, longitud):
    parametros = {
        'center': f"{latitud},{longitud}",
        'zoom': 17,
        'size': "600x300",
        'markers': f"color:red|label:A|{latitud},{longitud}",
        'maptype': 'satellite',
        'key': API_KEY
    }
    respuesta = requests.get(STATIC_MAP_URL, params=parametros)
    return Image.open(BytesIO(respuesta.content))

def obtener_lugares_cercanos(latitud, longitud, tipo, radio=50):
    parametros = {
        'location': f"{latitud},{longitud}",
        'radius': radio,  # Radio de búsqueda en metros
        'type': tipo,
        'key': API_KEY
    }
    respuesta = requests.get(PLACES_API_URL, params=parametros)
    if respuesta.status_code == 200:
        datos = respuesta.json()
        return datos.get('results', [])
    return []

def categorizar_zona(latitud, longitud):
    tipos = {
        "residencial": "neighborhood",
        "portuaria": "point_of_interest|establishment",
        "bodegas": "storage"
    }
    radio_busqueda = 201  # Radio en metros
    lugares_residenciales = obtener_lugares_cercanos(latitud, longitud, tipos['residencial'], radio_busqueda)
    lugares_portuarios = obtener_lugares_cercanos(latitud, longitud, tipos['portuaria'], radio_busqueda)
    lugares_bodegas = obtener_lugares_cercanos(latitud, longitud, tipos['bodegas'], radio_busqueda)

    if lugares_residenciales:
        return "Zona residencial"
    elif lugares_portuarios:
        return "Zona de bodegas"
    elif lugares_bodegas:
        return "Zona portuaria"
    else:
        return "Zona desconocida"

# Función para analizar el documento
def analyze_document(file_path, doc_type):
    document_analysis_client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    with open(file_path, "rb") as f:
        if doc_type == "Cámara de Comercio":
            poller = document_analysis_client.begin_analyze_document("prebuilt-layout", f)
        else:
            poller = document_analysis_client.begin_analyze_document("prebuilt-invoice", f)
        result = poller.result()

    document_data = {}
    if doc_type == "Cámara de Comercio":
        # Buscar la frase y extraer la dirección
        target_text = "Dirección del domicilio principal:"
        for page in result.pages:
            for line in page.lines:
                if target_text in line.content:
                    direccion_line = line.content.replace(target_text, "").strip()
                    document_data["CustomerAddress"] = direccion_line
                    break
    else:
        for field_name, field in result.documents[0].fields.items():
            document_data[field_name] = field.value if field else "0"
    return document_data

# Función para extraer la dirección completa
def extract_full_address(address_value):
    if isinstance(address_value, dict):
        road = address_value.get("road", "")
        house_number = address_value.get("house_number", "")
        city = address_value.get("city", "")
        state = address_value.get("state", "")
    elif hasattr(address_value, 'road') and hasattr(address_value, 'house_number'):
        road = address_value.road if address_value.road else ""
        house_number = address_value.house_number if address_value.house_number else ""
        city = address_value.city if address_value.city else ""
        state = address_value.state if address_value.state else ""
    else:
        return "No address found"
    
    address_parts = [f"{road} {house_number}".strip()]
    if city:
        address_parts.append(city)
    if state:
        address_parts.append(state)
    return ", ".join(address_parts)

# Función para comparar coordenadas con un umbral de distancia
def comparar_coordenadas(coord1, coord2, umbral_metros=200):
    if None in coord1 or None in coord2:
        return False
    distancia = geodesic(coord1, coord2).meters
    st.write(f"Distancia calculada entre coordenadas: {distancia} metros")  # Mostrar la distancia calculada
    return distancia <= umbral_metros

# Función para guardar los resultados
def save_results(results, file_name="historico_documentos.xlsx"):
    df = pd.DataFrame(results)
    if os.path.exists(file_name):
        existing_df = pd.read_excel(file_name)
        df = pd.concat([existing_df, df], ignore_index=True)
    with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Documentos')

def main():
    st.set_page_config(layout="centered")
    col1, col2 = st.columns([2, 1.5])
    col1.title("Analizador de Documentos")
    image_path = os.path.join(os.path.dirname(__file__), 'LOGOTIPO IAC-02 1.png')  # Usar ruta relativa
    image = Image.open(image_path)
    col2.image(image, width=300)

    st.write("Carga documentos RUT, Cámara de Comercio y Cotizaciones para ser analizados.")

    # Cargar documentos
    rut_file = st.file_uploader("Carga RUT", type=["pdf", "jpg", "jpeg"])
    cc_file = st.file_uploader("Carga Cámara de Comercio", type=["pdf", "jpg", "jpeg"])
    cotizacion_file = st.file_uploader("Carga Cotización", type=["pdf", "jpg", "jpeg"])

    if st.button("Analizar documentos"):
        all_results = []
        base_addresses = []
        coordenadas_base = []
        direccion_rut = ""
        with st.spinner("Analizando..."):
            for uploaded_file, doc_type in [(rut_file, "RUT"), (cc_file, "Cámara de Comercio"), (cotizacion_file, "Cotizacion")]:
                if uploaded_file is not None:
                    file_path = f"temp_{uploaded_file.name}"
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    try:
                        data = analyze_document(file_path, doc_type)
                        if doc_type == "Cámara de Comercio":
                            street_address = data.get("CustomerAddress", "No encontrado")
                        else:
                            address_value = data.get("CustomerAddress", "No encontrado")
                            street_address = extract_full_address(address_value)
                            if doc_type == "RUT":
                                # Normalizar la dirección del RUT para categorizar
                                direccion_rut = clean_and_normalize_address(street_address)

                        # Normalizar la dirección antes de obtener las coordenadas
                        normalized_address = clean_and_normalize_address(street_address)
                        lat, lng = obtener_coordenadas(normalized_address)
                        
                        if lat and lng:
                            coordenadas_base.append((lat, lng))
                        
                        formatted_data = {
                            "Document Type": doc_type,
                            "Vendor Name": data.get("VendorName", "No encontrado") if 'data' in locals() else "No encontrado",
                            "Customer Name": data.get("CustomerName", "No encontrado") if 'data' in locals() else "No encontrado",
                            "Dirección": normalized_address,  # Mostrar la dirección normalizada
                            "Coordenadas": f"{lat}, {lng}" if lat and lng else "Coordenadas no encontradas"
                        }
                    except Exception as e:
                        formatted_data = {
                            "Document Type": doc_type,
                            "Vendor Name": "No encontrado",
                            "Customer Name": "No encontrado",
                            "Dirección": "Error normalizando dirección",
                            "Coordenadas": "Error obteniendo coordenadas"
                        }
                        st.error(f"Error procesando el archivo {uploaded_file.name}: {e}")

                    all_results.append(formatted_data)
                    base_addresses.append(normalized_address)

        # Mostrar resultados
        df_results = pd.DataFrame(all_results)
        st.write(df_results)

        # Verificar similitud de coordenadas si hay más de una dirección base
        if len(coordenadas_base) > 1:
            if comparar_coordenadas(coordenadas_base[0], coordenadas_base[1]):
                st.success("Direcciones similares según las coordenadas.")
            else:
                st.warning("Direcciones diferentes según coordenadas.")
        elif len(coordenadas_base) == 1:
            st.info("Sólo una dirección base encontrada.")

        # Guardar y permitir descarga
        save_results(all_results)
        excel_data = BytesIO()
        with pd.ExcelWriter(excel_data, engine='openpyxl') as writer:
            df_results.to_excel(writer, index=False, sheet_name='Documentos')
        excel_data.seek(0)
        st.download_button(label="Descargar Excel", data=excel_data, file_name="documentos_combinados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Guardar la dirección en session_state para categorizar después
        st.session_state.direccion_rut = direccion_rut

    if "direccion_rut" in st.session_state:
        st.title("Categorización de Dirección")
        direccion_editada = st.text_input("Edita la dirección para categorizar", value=st.session_state.direccion_rut)

        if st.button("Confirmar y Categorizar"):
            direccion_editada_normalizada = clean_and_normalize_address(direccion_editada)
            lat, lng = obtener_coordenadas(direccion_editada_normalizada)
            if lat and lng:
                st.write(f"Coordenadas: {lat}, {lng}")
                imagen = obtener_imagen_mapa(lat, lng)
                st.image(imagen, caption="Vista de la zona con marcador", use_column_width=True)
                categoria = categorizar_zona(lat, lng)
                st.write(f"Categoría: {categoria}")
            else:
                st.error("No se pudieron obtener las coordenadas de la dirección.")

if __name__ == "__main__":
    main()
