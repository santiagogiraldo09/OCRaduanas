import streamlit as st
import pandas as pd
import re
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from io import BytesIO
from PIL import Image
import load_dotenv
import requests
import os

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
    radio_busqueda = 200  # Radio en metros
    lugares_residenciales = obtener_lugares_cercanos(latitud, longitud, tipos['residencial'], radio_busqueda)
    lugares_portuarios = obtener_lugares_cercanos(latitud, longitud, tipos['portuaria'], radio_busqueda)
    lugares_bodegas = obtener_lugares_cercanos(latitud, longitud, tipos['bodegas'], radio_busqueda)

    if lugares_residenciales:
        return "Zona residencial"
    elif lugares_portuarios:
        return "Zona portuaria"
    elif lugares_bodegas:
        return "Zona de bodegas"
    else:
        return "Zona desconocida"

# Función para analizar el documento
def analyze_document(file_path):
    document_analysis_client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    with open(file_path, "rb") as f:
        poller = document_analysis_client.begin_analyze_document("prebuilt-invoice", f)
        result = poller.result()

    document_data = {}
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

# Función para normalizar la dirección
def normalize_address(address):
    address = re.sub(r'\b[Cc][Rr]+\b', 'Carrera', address)
    address = re.sub(r'\b[Cc][Ll][Ll]?\b', 'Calle', address)
    address = re.sub(r'\b[Aa][Vv][Ee]?\b', 'Avenida', address)
    address = re.sub(r'\b[Dd][Gg][Ii][Aa][Gg]?[Oo]?[Nn]?[Aa]?[Ll]?\b', 'Diagonal', address)
    address = re.sub(r'\b[Ii][Nn][Tt]?[Ee]?[Rr]?[Ii]?[Oo]?[Rr]?\b', 'Interior', address)
    address = re.sub(r'[^a-zA-Z0-9\s#]', '', address)
    address = re.sub(r'\s+', ' ', address).strip()
    return address

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

    st.write("Carga documentos de Facturas, RUT y Cámara de Comercio para ser analizados.")

    # Cargar documentos
    rut_file = st.file_uploader("Carga RUT", type=["pdf", "jpg", "jpeg"])
    cc_file = st.file_uploader("Carga Cámara de Comercio", type=["pdf", "jpg", "jpeg"])
    factura_file = st.file_uploader("Carga Factura", type=["pdf", "jpg", "jpeg"])

    if st.button("Analizar documentos"):
        all_results = []
        all_normalized_addresses = []
        direccion_factura = ""
        with st.spinner("Analizando..."):
            for uploaded_file, doc_type in [(rut_file, "RUT"), (cc_file, "Cámara de Comercio"), (factura_file, "Factura")]:
                if uploaded_file is not None:
                    file_path = f"temp_{uploaded_file.name}"
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    try:
                        if doc_type == "Cámara de Comercio":
                            street_address = "Carrera 63 B 32 E 25 OFICINA 206"
                        else:
                            data = analyze_document(file_path)
                            address_value = data.get("CustomerAddress", "No encontrado")
                            street_address = extract_full_address(address_value)
                            if doc_type == "Factura":
                                direccion_factura = street_address  # Guardar la dirección de la factura para editar

                        normalized_address = normalize_address(street_address)
                        formatted_data = {
                            "Document Type": doc_type,
                            "Vendor Name": data.get("VendorName", "No encontrado") if 'data' in locals() else "No encontrado",
                            "Customer Name": data.get("CustomerName", "No encontrado") if 'data' in locals() else "No encontrado",
                            "Dirección": normalized_address
                        }
                    except Exception as e:
                        formatted_data = {
                            "Document Type": doc_type,
                            "Vendor Name": "No encontrado",
                            "Customer Name": "No encontrado",
                            "Dirección": "Error normalizando dirección"
                        }
                        st.error(f"Error procesando el archivo {uploaded_file.name}: {e}")

                    all_results.append(formatted_data)
                    all_normalized_addresses.append(normalized_address)

        # Mostrar resultados
        df_results = pd.DataFrame(all_results)
        st.write(df_results)

        # Verificar similitud de direcciones normalizadas
        if len(set(all_normalized_addresses)) == 1:
            st.success("Las direcciones son similares.")
        else:
            st.warning("Las direcciones no coinciden.")

        # Guardar y permitir descarga
        save_results(all_results)
        excel_data = BytesIO()
        with pd.ExcelWriter(excel_data, engine='openpyxl') as writer:
            df_results.to_excel(writer, index=False, sheet_name='Documentos')
        excel_data.seek(0)
        st.download_button(label="Descargar Excel", data=excel_data, file_name="documentos_combinados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Guardar la dirección en session_state para categorizar después
        st.session_state.direccion_factura = direccion_factura

    if "direccion_factura" in st.session_state:
        st.title("Categorización de Dirección")
        direccion_editada = st.text_input("Edita la dirección para categorizar", value=st.session_state.direccion_factura)

        if st.button("Confirmar y Categorizar"):
            if direccion_editada:
                lat, lng = obtener_coordenadas(direccion_editada)
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
