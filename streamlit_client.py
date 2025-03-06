#!/usr/bin/env python3
"""
Cliente Streamlit que se conecta al servidor FastAPI a través de WebSockets.
Proporciona una interfaz de usuario para interactuar con el asistente de voz.
"""

import streamlit as st
import tempfile
import os
import json
import time
import hashlib
import torch
import websocket
import threading
import queue
from gtts import gTTS
from gtts.lang import tts_langs
from audio_recorder_streamlit import audio_recorder

# Forzar una inicialización vacía para evitar problemas con torch
torch.classes.__path__ = []

# Configurar la página
st.set_page_config(
    page_title="Simple Speech Assistant (WebSocket Client)",
    page_icon="🎤",
    layout="wide",
)

# Estilos
st.markdown("""
<style>
    .main {background-color: #f5f7f9;}
    .stButton button {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 24px;
    }
    .response-box {
        background-color: #333;
        color: #fff;
        border-radius: 8px;
        padding: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar el estado de la sesión
if 'conversation' not in st.session_state:
    st.session_state.conversation = []
if 'whisper_model' not in st.session_state:
    st.session_state.whisper_model = None
if 'tts_cache' not in st.session_state:
    st.session_state.tts_cache = {}
if 'tts_enabled' not in st.session_state:
    st.session_state.tts_enabled = True
if 'tts_last_request' not in st.session_state:
    st.session_state.tts_last_request = 0
if 'ws_queue' not in st.session_state:
    st.session_state.ws_queue = queue.Queue()
if 'ws_connected' not in st.session_state:
    st.session_state.ws_connected = False
if 'ws_client' not in st.session_state:
    st.session_state.ws_client = None

# Título
st.title("🎤 Simple Speech Assistant (WebSocket Client)")

# Sidebar con configuraciones
with st.sidebar:
    st.header("Settings")
    
    # WebSocket Settings
    st.subheader("WebSocket Connection")
    websocket_url = st.text_input("WebSocket URL", value="ws://localhost:8000/ws/agent")
    
    if st.button("Connect to WebSocket"):
        try:
            # Función para manejar mensajes WebSocket en un hilo separado
            def on_message(ws, message):
                st.session_state.ws_queue.put(json.loads(message))
            
            def on_error(ws, error):
                st.session_state.ws_queue.put({"status": "error", "error": str(error)})
            
            def on_close(ws, close_status_code, close_msg):
                st.session_state.ws_connected = False
                st.session_state.ws_queue.put({"status": "disconnected"})
            
            def on_open(ws):
                st.session_state.ws_connected = True
                st.session_state.ws_queue.put({"status": "connected"})
            
            # Crear cliente WebSocket
            ws = websocket.WebSocketApp(
                websocket_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # Ejecutar WebSocket en un hilo separado
            def run_websocket():
                ws.run_forever()
            
            ws_thread = threading.Thread(target=run_websocket, daemon=True)
            ws_thread.start()
            
            st.session_state.ws_client = ws
            
            with st.spinner("Connecting to WebSocket..."):
                # Esperar a que se conecte o falle
                for _ in range(30):  # 3 segundos máximo
                    if not st.session_state.ws_queue.empty():
                        msg = st.session_state.ws_queue.get()
                        if msg.get("status") == "connected":
                            st.success("Connected to WebSocket server!")
                            break
                        elif msg.get("status") == "error":
                            st.error(f"Connection error: {msg.get('error')}")
                            break
                    time.sleep(0.1)
                else:
                    st.warning("Connection timeout. Check if the server is running.")
        
        except Exception as e:
            st.error(f"Error connecting to WebSocket: {e}")
    
    # Estado de conexión
    if st.session_state.ws_connected:
        st.success("WebSocket Connected")
    else:
        st.warning("WebSocket Disconnected")
    
    st.divider()
    
    # Configuración de Text-to-Speech
    st.subheader("Text-to-Speech")
    st.session_state.tts_enabled = st.checkbox("Enable Text-to-Speech", value=st.session_state.tts_enabled)
    
    # Selección de idioma para TTS
    available_langs = tts_langs()
    tts_lang = st.selectbox(
        "TTS Language",
        options=list(available_langs.keys()),
        index=list(available_langs.keys()).index("es") if "es" in available_langs else 0,
        format_func=lambda x: f"{x} - {available_langs[x]}"
    )
    
    st.divider()
    
    # Selección de modelo Whisper
    st.subheader("Speech Recognition")
    whisper_model = st.selectbox(
        "Whisper Model",
        ["tiny", "base", "small", "medium"],
        index=1  # Default a "base"
    )
    
    # Botón para cargar Whisper
    if st.button("Load Whisper Model"):
        with st.spinner("Loading Whisper model..."):
            try:
                import whisper
                st.session_state.whisper_model = whisper.load_model(whisper_model)
                st.success("Whisper model loaded!")
            except Exception as e:
                st.error(f"Error loading model: {e}")

# Función para transcribir audio usando Whisper
def transcribe_audio(audio_file):
    if st.session_state.whisper_model is None:
        st.error("Please load the Whisper model first")
        return None
    try:
        result = st.session_state.whisper_model.transcribe(audio_file)
        return result["text"].strip()
    except Exception as e:
        st.error(f"Transcription error: {e}")
        return None

# Función para convertir texto a voz con caché y límite de velocidad
def text_to_speech(text, lang="es"):
    if not st.session_state.tts_enabled:
        return None
    
    try:
        # Crear un hash del texto y el idioma para usar como clave de caché
        text_hash = hashlib.md5((text + lang).encode()).hexdigest()
        
        # Verificar si ya tenemos este audio en caché
        if text_hash in st.session_state.tts_cache:
            return st.session_state.tts_cache[text_hash]
        
        # Limitar velocidad - asegurar al menos 1 segundo entre solicitudes
        current_time = time.time()
        time_since_last = current_time - st.session_state.tts_last_request
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)
        
        # Actualizar tiempo de última solicitud
        st.session_state.tts_last_request = time.time()
        
        # Generar el archivo de audio
        audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(audio_file.name)
        
        # Almacenar en caché
        st.session_state.tts_cache[text_hash] = audio_file.name
        
        return audio_file.name
    except Exception as e:
        # Si encontramos un límite de velocidad, esperar e intentar nuevamente una vez
        if "429" in str(e):
            st.warning("Rate limit encountered, waiting 5 seconds before retrying...")
            time.sleep(5)
            try:
                audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tts = gTTS(text=text, lang=lang, slow=False)
                tts.save(audio_file.name)
                
                # Almacenar en caché
                text_hash = hashlib.md5((text + lang).encode()).hexdigest()
                st.session_state.tts_cache[text_hash] = audio_file.name
                
                return audio_file.name
            except Exception as retry_e:
                st.error(f"Text-to-speech retry error: {retry_e}")
                return None
        else:
            st.error(f"Text-to-speech error: {e}")
            return None

# Función para enviar mensajes a través de WebSocket
def send_message_to_agent(text):
    if not st.session_state.ws_connected or st.session_state.ws_client is None:
        st.error("WebSocket is not connected. Please connect to the server first.")
        return None
    
    try:
        message = {"text": text}
        st.session_state.ws_client.send(json.dumps(message))
        
        # Esperar respuesta (con timeout)
        timeout = 30  # segundos
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not st.session_state.ws_queue.empty():
                response = st.session_state.ws_queue.get()
                return response
            time.sleep(0.1)
        
        return {"status": "error", "error": "Timeout waiting for response"}
    
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Layout: dos columnas - una para entrada de voz y otra para transcripción de conversación
col1, col2 = st.columns([1, 1])

with col1:
    st.header("Voice Input")
    
    # Advertir al usuario si el modelo Whisper no está cargado
    if st.session_state.whisper_model is None:
        st.warning("Please load the Whisper model from the sidebar first")
    
    # Advertir si WebSocket no está conectado
    if not st.session_state.ws_connected:
        st.warning("WebSocket is not connected. Please connect from the sidebar first.")
    
    st.markdown("**Record your message:**")
    audio_bytes = audio_recorder()
    
    if audio_bytes is not None:
        st.audio(audio_bytes, format="audio/wav")
        if st.button("Process Recorded Audio"):
            # Verificar conexión WebSocket
            if not st.session_state.ws_connected:
                st.error("WebSocket is not connected. Please connect to the server first.")
            else:
                # Guardar los bytes de audio grabados en un archivo temporal
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio_file:
                    temp_audio_file.write(audio_bytes)
                    temp_filename = temp_audio_file.name
                
                with st.spinner("Transcribing..."):
                    transcription = transcribe_audio(temp_filename)
                
                if transcription:
                    st.success("Transcription complete!")
                    
                    with st.spinner("Getting response from Agents via WebSocket..."):
                        response_data = send_message_to_agent(transcription)
                    
                    if response_data:
                        if response_data.get("status") == "success":
                            assistant_response = response_data.get("response", "")
                            st.session_state.conversation.append({
                                "user": transcription,
                                "assistant": assistant_response
                            })
                            
                            if st.session_state.tts_enabled:
                                with st.spinner("Generating speech..."):
                                    speech_file = text_to_speech(assistant_response, lang=tts_lang)
                                    if speech_file:
                                        st.audio(speech_file)
                                    else:
                                        st.warning("Text-to-speech unavailable. Continuing without audio.")
                        else:
                            st.error(f"Error: {response_data.get('error', 'Unknown error')}")
    
    # Opción de carga de archivo
    st.subheader("Or upload audio")
    uploaded_file = st.file_uploader("Upload audio file", type=["wav", "mp3"])
    
    if uploaded_file and st.button("Process Uploaded File"):
        # Verificar conexión WebSocket
        if not st.session_state.ws_connected:
            st.error("WebSocket is not connected. Please connect to the server first.")
        elif st.session_state.whisper_model is None:
            st.error("Please load the Whisper model first")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_file_name = temp_file.name
            
            with st.spinner("Transcribing..."):
                transcription = transcribe_audio(temp_file_name)
            
            if transcription:
                st.success("Transcription complete!")
                
                with st.spinner("Getting response from Agents via WebSocket..."):
                    response_data = send_message_to_agent(transcription)
                
                if response_data:
                    if response_data.get("status") == "success":
                        assistant_response = response_data.get("response", "")
                        st.session_state.conversation.append({
                            "user": transcription,
                            "assistant": assistant_response
                        })
                        
                        if st.session_state.tts_enabled:
                            with st.spinner("Generating speech..."):
                                speech_file = text_to_speech(assistant_response, lang=tts_lang)
                                if speech_file:
                                    st.audio(speech_file)
                                else:
                                    st.warning("Text-to-speech unavailable. Continuing without audio.")
                    else:
                        st.error(f"Error: {response_data.get('error', 'Unknown error')}")
    
    # Entrada de texto como fallback
    st.subheader("Or type your message")
    text_input = st.text_input("Type and press Enter")
    
    if text_input:
        # Verificar conexión WebSocket
        if not st.session_state.ws_connected:
            st.error("WebSocket is not connected. Please connect to the server first.")
        else:
            with st.spinner("Getting response from Agents via WebSocket..."):
                response_data = send_message_to_agent(text_input)
            
            if response_data:
                if response_data.get("status") == "success":
                    assistant_response = response_data.get("response", "")
                    st.session_state.conversation.append({
                        "user": text_input,
                        "assistant": assistant_response
                    })
                    
                    if st.session_state.tts_enabled:
                        with st.spinner("Generating speech..."):
                            speech_file = text_to_speech(assistant_response, lang=tts_lang)
                            if speech_file:
                                st.audio(speech_file)
                            else:
                                st.warning("Text-to-speech unavailable. Continuing without audio.")
                else:
                    st.error(f"Error: {response_data.get('error', 'Unknown error')}")

with col2:
    st.header("Conversation Transcript")
    
    if not st.session_state.conversation:
        st.info("Your conversation will appear here")
    else:
        for i, exchange in enumerate(st.session_state.conversation):
            st.markdown(f"**You:** {exchange['user']}")
            st.markdown(f'<div class="response-box"><strong>Assistant:</strong> {exchange["assistant"]}</div>',
                        unsafe_allow_html=True)
            if i < len(st.session_state.conversation) - 1:
                st.divider()
    
    if st.session_state.conversation and st.button("Clear Conversation"):
        st.session_state.conversation = []
        st.rerun()