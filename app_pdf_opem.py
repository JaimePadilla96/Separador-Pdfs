import os
import re
import zipfile
import io
import base64
import streamlit as st
from pypdf import PdfReader, PdfWriter
from pdf2image import convert_from_path
from openai import OpenAI

# Configuración inicial de la página
st.set_page_config(page_title="Separador de PDFs (OpenAI)", page_icon="🤖")

# Inicializa el cliente de OpenAI (Buscará la variable OPENAI_API_KEY automáticamente)
try:
    client = OpenAI()
except Exception as e:
    st.error("Error: No se encontró la OPENAI_API_KEY en las variables de entorno.")

# Campos que la IA buscará siempre
CAMPO_FIJO_1 = "Nombres y apellidos"
CAMPO_FIJO_2 = "Tipo y No de documento"

def pil_a_base64(imagen_pil):
    """Convierte la imagen a texto (base64) para poder enviarla a OpenAI."""
    buffered = io.BytesIO()
    imagen_pil.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extraer_multiples_campos(imagen_pil):
    """Envía la imagen a GPT-4o-mini para leer la caligrafía."""
    
    prompt = (
        f"Analiza este documento y busca los campos '{CAMPO_FIJO_1}' y '{CAMPO_FIJO_2}', "
        f"los cuales están llenados a mano. "
        f"Devuelve SOLO los valores encontrados separados por un guion bajo (_). "
        f"Ejemplo: Juan Perez_123456. "
        f"No escribas NADA MÁS. Si algún dato es ilegible o falta, usa la sigla ND."
    )
    
    try:
        base64_image = pil_a_base64(imagen_pil)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            "type": "image_url"
                        }
                    ]
                }
            ],
            max_tokens=30,
            temperature=0.1
        )
        
        texto = response.choices[0].message.content.strip()

        nombre_valido = re.sub(r'[\\/*?:"<>|.\n\r]', '', texto)
        
        # Limpiamos guiones bajos duplicados y espacios sobrantes
        nombre_limpio = re.sub(r'_+', '_', nombre_valido).strip('_')
        
        return nombre_limpio if nombre_limpio else "sin_datos"
        
    except Exception as e:
        st.error(f"Error de conexión con OpenAI: {e}")
        return "error_IA"

def crear_zip_desde_pdf(archivo_subido):
    ruta_temporal = "temp_upload.pdf"
    with open(ruta_temporal, "wb") as f:
        f.write(archivo_subido.getbuffer())

    reader = PdfReader(ruta_temporal)
    total_paginas = len(reader.pages)
    
    zip_buffer = io.BytesIO()
    barra_progreso = st.progress(0)
    estado_texto = st.empty()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        estado_texto.text("Convirtiendo PDF a imágenes...")
        imagenes = convert_from_path(ruta_temporal)
        
        for i, (pagina_pdf, imagen_pil) in enumerate(zip(reader.pages, imagenes)):
            numero_hoja = i + 1
            estado_texto.text(f"Analizando hoja {numero_hoja} de {total_paginas} (GPT-4o-mini)...")
            
            # IA en acción
            valores_extraidos = extraer_multiples_campos(imagen_pil)
            
            # Armamos el nombre
            nombre_pdf = f"{valores_extraidos}.pdf"
            
            # Guardamos la hoja
            writer = PdfWriter()
            writer.add_page(pagina_pdf)
            pdf_en_memoria = io.BytesIO()
            writer.write(pdf_en_memoria)
            
            zip_file.writestr(nombre_pdf, pdf_en_memoria.getvalue())
            
            # Actualiza la barra
            barra_progreso.progress((i + 1) / total_paginas)

    if os.path.exists(ruta_temporal):
        os.remove(ruta_temporal)
    
    estado_texto.success("¡Proceso finalizado con éxito!")
    return zip_buffer.getvalue()

# ==========================================
# INTERFAZ WEB
# ==========================================

st.title("🤖 Separador Inteligente de PDFs (OpenAI)")
st.write(f"Sube un archivo PDF. El sistema extraerá de forma rápida y precisa los campos **{CAMPO_FIJO_1}** y **{CAMPO_FIJO_2}** de cada hoja usando GPT-4o-mini.")

archivo_pdf = st.file_uploader("Sube tu archivo PDF aquí", type=["pdf"])

if archivo_pdf is not None and st.button("Iniciar Procesamiento"):
    with st.spinner("Procesando con IA..."):
        zip_resultado = crear_zip_desde_pdf(archivo_pdf)
        
        st.write("---")
        st.subheader("¡Todo listo!")
        
        st.download_button(
            label="⬇️ Descargar PDFs Separados (.zip)",
            data=zip_resultado,
            file_name="documentos_separados.zip",
            mime="application/zip"
        )
