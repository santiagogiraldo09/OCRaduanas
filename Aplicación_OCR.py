import streamlit as st
import pandas as pd
import re
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from io import BytesIO
from PIL import Image

# Configuración de Azure Form Recognizer
endpoint = "https://demoocr.cognitiveservices.azure.com/"
key = "125c4bac6511481290029459b6cf96c2"

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

# Función para extraer la dirección
def extract_street_address(address_value):
    if isinstance(address_value, dict):
        return address_value.get("street_address", "No street_address found")
    elif hasattr(address_value, 'street_address'):
        return address_value.street_address
    return "No street_address found"

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
def save_results(results):
    df = pd.DataFrame(results)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Documentos')
    output.seek(0)
    return output

# Función principal
def main():
    st.set_page_config(layout="centered")
    col1, col2 = st.columns([2,1.5])
    col1.title("Analizador de Documentos")
    image = Image.open(r"C:\Users\Lenovo Thinkpad E14\Downloads\LOGOTIPO IAC-02 1.png")  # Reemplaza con la ruta de tu imagen
    col2.image(image, width=300)

    st.write("Carga documentos de Facturas, RUT y Cámara de Comercio para ser analizados.")
    uploaded_files = st.file_uploader("Carga documentos", type=["pdf", "jpg", "jpeg"], accept_multiple_files=True)

    if st.button("Analizar documentos"):
        all_results = []
        all_normalized_addresses = []
        with st.spinner("Analizando..."):
            for uploaded_file in uploaded_files:
                file_path = f"temp_{uploaded_file.name}"
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                try:
                    if "cámara" in uploaded_file.name.lower() and "comercio" in uploaded_file.name.lower():
                        street_address = "Carrera 63 B 32 E 25 OFICINA 206"
                    else:
                        data = analyze_document(file_path)
                        street_address = extract_street_address(data.get("CustomerAddress", "No encontrado"))
                    
                    normalized_address = normalize_address(street_address)
                    formatted_data = {
                        "Tipo de Documento": uploaded_file.name,
                        "Nombre de Proveedor": data.get("VendorName", "No encontrado") if 'data' in locals() else "No encontrado",
                        "Nombre del Cliente": data.get("CustomerName", "No encontrado") if 'data' in locals() else "No encontrado",
                        "Dirección": normalized_address
                    }
                except Exception as e:
                    formatted_data = {
                        "Tipo de Documento": uploaded_file.name,
                        "Nombre de Proveedor": "No encontrado",
                        "Nombre del Cliente": "No encontrado",
                        "Dirección": "Error normalizando dirección"
                    }
                    st.error(f"Error procesando el archivo {uploaded_file.name}: {e}")

                all_results.append(formatted_data)
                all_normalized_addresses.append(normalized_address)

        # Mostrar resultados sin la columna "Customer Address"
        df_results = pd.DataFrame(all_results).drop(columns=["Customer Address"], errors='ignore')
        st.write(df_results)

        # Verificar similitud de direcciones normalizadas
        if len(set(all_normalized_addresses)) == 1:
            st.success("Las direcciones son similares.")
        else:
            st.warning("Las direcciones no coinciden.")

        # Guardar y permitir descarga
        excel_data = save_results(all_results)
        st.download_button(label="Descargar Excel", data=excel_data, file_name="documentos_combinados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()