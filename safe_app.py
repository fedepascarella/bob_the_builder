import streamlit as st
import tempfile
import os
import requests
import json
import subprocess
import sys
import time
import hashlib
import torch
from gtts import gTTS
from gtts.lang import tts_langs
import base64

# Import the audio recorder component
from audio_recorder_streamlit import audio_recorder

torch.classes.__path__ = [] # add this line to manually set it to empty. 

# Set page configuration
st.set_page_config(
    page_title="Simple Speech Assistant",
    page_icon="🎤",
    layout="wide",
)

# Simple styling with updated assistant response box style
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
        background-color: #333;  /* Dark background */
        color: #fff;             /* White text for contrast */
        border-radius: 8px;
        padding: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
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

# Create the agent_runner.py file if it doesn't exist
def ensure_agent_runner_exists():
    agent_runner_path = os.path.join(os.getcwd(), "agent_runner.py")
    if not os.path.exists(agent_runner_path):
        with open(agent_runner_path, "w") as f:
            f.write("""#!/usr/bin/env python3
\"\"\"
Script auxiliar para ejecutar los agentes sin interferencia con Streamlit.
Este script se ejecuta como un proceso separado.
\"\"\"

import sys
import json

def run_agent(input_text):
    \"\"\"Ejecuta el equipo de agentes con el texto proporcionado y devuelve la respuesta.\"\"\"
    try:
        from agents import bob_team
        
        # Capturar la salida del equipo de agentes
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            bob_team.print_response(input_text, stream=False)
        
        response = f.getvalue()
        
        # Devolver un resultado exitoso
        return {
            "status": "success",
            "response": response
        }
    except Exception as e:
        # Devolver error si algo salió mal
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    # Si no hay argumentos, mostrar ayuda
    if len(sys.argv) < 2:
        print("Uso: python agent_runner.py 'texto de entrada'")
        sys.exit(1)
    
    # El primer argumento es el texto a procesar
    input_text = sys.argv[1]
    
    # Ejecutar el agente y obtener la respuesta
    result = run_agent(input_text)
    
    # Imprimir el resultado como JSON para que el llamador pueda analizarlo
    print(json.dumps(result))
""")
        # Hacerlo ejecutable
        os.chmod(agent_runner_path, 0o755)
    return agent_runner_path

# Asegurarse de que el runner existe al inicio
agent_runner_path = ensure_agent_runner_exists()

# Title
st.title("🎤 Simple Speech Assistant")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    
    # Text-to-Speech settings
    st.subheader("Text-to-Speech")
    st.session_state.tts_enabled = st.checkbox("Enable Text-to-Speech", value=st.session_state.tts_enabled)
    
    # Language selection for TTS
    available_langs = tts_langs()
    tts_lang = st.selectbox(
        "TTS Language",
        options=list(available_langs.keys()),
        index=list(available_langs.keys()).index("es") if "es" in available_langs else 0,
        format_func=lambda x: f"{x} - {available_langs[x]}"
    )
    
    st.divider()
    
    # Whisper model selection
    st.subheader("Speech Recognition")
    whisper_model = st.selectbox(
        "Whisper Model",
        ["tiny", "base", "small", "medium"],
        index=1  # Default to "base"
    )
    
    # Load Whisper button
    if st.button("Load Whisper Model"):
        with st.spinner("Loading Whisper model..."):
            try:
                import whisper
                st.session_state.whisper_model = whisper.load_model(whisper_model)
                st.success("Whisper model loaded!")
            except Exception as e:
                st.error(f"Error loading model: {e}")
    
    st.divider()
    
    # Test Agent button
    if st.button("Test Agent Connection"):
        with st.spinner("Testing Agent connection..."):
            try:
                # Ejecutar una prueba simple con el runner
                result = subprocess.run(
                    [sys.executable, agent_runner_path, "test connection"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                response_json = json.loads(result.stdout)
                if response_json["status"] == "success":
                    st.success("Agent connection successful!")
                else:
                    st.error(f"Agent connection error: {response_json.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"Error testing agent: {e}")
    
    st.divider()
    
    # Ollama settings (kept for fallback)
    ollama_model = st.text_input("Ollama Model (Fallback)", value="llama3.2:3b")
    ollama_url = st.text_input("Ollama API URL (Fallback)", value="http://localhost:11434/api/generate")
    
    st.divider()
    
    st.info("Audio is captured via the browser using audio-recorder-streamlit.")

# Function to transcribe audio using Whisper
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

# Function to get response from Ollama (fallback)
def get_ollama_response(text, model, api_url):
    try:
        response = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "prompt": text,
                "stream": False
            })
        )
        if response.status_code == 200:
            return response.json()["response"]
        else:
            st.error(f"Ollama error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None

# Function to get response from the agent team via the separate runner script
def get_agent_response(text):
    try:
        # Escape single quotes in the input text
        escaped_text = text.replace("'", "\\'")
        
        # Run the agent_runner.py script as a separate process
        result = subprocess.run(
            [sys.executable, agent_runner_path, escaped_text],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the JSON output
        try:
            response_json = json.loads(result.stdout)
            if response_json["status"] == "success":
                return response_json["response"]
            else:
                st.warning(f"Agent error: {response_json.get('error', 'Unknown error')}")
                st.info("Falling back to direct Ollama call")
                return get_ollama_response(text, ollama_model, ollama_url)
        except json.JSONDecodeError:
            st.warning("Could not parse agent response. Falling back to direct Ollama call.")
            return get_ollama_response(text, ollama_model, ollama_url)
            
    except Exception as e:
        st.error(f"Agent execution error: {e}")
        st.info("Falling back to direct Ollama call")
        return get_ollama_response(text, ollama_model, ollama_url)

# Function to convert text to speech with caching and rate limiting
def text_to_speech(text, lang="es"):
    if not st.session_state.tts_enabled:
        return None
    
    try:
        # Create a hash of the text and language to use as a cache key
        text_hash = hashlib.md5((text + lang).encode()).hexdigest()
        
        # Check if we already have this audio in cache
        if text_hash in st.session_state.tts_cache:
            return st.session_state.tts_cache[text_hash]
        
        # Rate limiting - ensure at least 1 second between requests
        current_time = time.time()
        time_since_last = current_time - st.session_state.tts_last_request
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)
        
        # Update last request time
        st.session_state.tts_last_request = time.time()
        
        # Generate the audio file
        audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(audio_file.name)
        
        # Store in cache
        st.session_state.tts_cache[text_hash] = audio_file.name
        
        return audio_file.name
    except Exception as e:
        # If we encounter a rate limit, wait and try again once
        if "429" in str(e):
            st.warning("Rate limit encountered, waiting 5 seconds before retrying...")
            time.sleep(5)
            try:
                audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tts = gTTS(text=text, lang=lang, slow=False)
                tts.save(audio_file.name)
                
                # Store in cache
                text_hash = hashlib.md5((text + lang).encode()).hexdigest()
                st.session_state.tts_cache[text_hash] = audio_file.name
                
                return audio_file.name
            except Exception as retry_e:
                st.error(f"Text-to-speech retry error: {retry_e}")
                # Fall back to a note about TTS being unavailable
                return None
        else:
            st.error(f"Text-to-speech error: {e}")
            return None

# Fallback function to generate silent audio
def create_silent_audio():
    # Generate a short silent MP3 file
    silent_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    silent_file_path = silent_file.name
    silent_file.close()
    
    # Use subprocess to create a silent MP3
    try:
        import subprocess
        # Try using ffmpeg if available
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", 
            "-t", "0.1", "-q:a", "9", "-acodec", "libmp3lame", silent_file_path
        ], check=True, capture_output=True)
        return silent_file_path
    except:
        # If ffmpeg fails, return None
        return None

# Layout: two columns – one for voice input and one for conversation transcript
col1, col2 = st.columns([1, 1])

with col1:
    st.header("Voice Input")
    
    # Warn user if Whisper model is not loaded
    if st.session_state.whisper_model is None:
        st.warning("Please load the Whisper model from the sidebar first")
    
    st.markdown("**Record your message:**")
    audio_bytes = audio_recorder()
    
    if audio_bytes is not None:
        st.audio(audio_bytes, format="audio/wav")
        if st.button("Process Recorded Audio"):
            # Save the recorded audio bytes to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio_file:
                temp_audio_file.write(audio_bytes)
                temp_filename = temp_audio_file.name
            
            with st.spinner("Transcribing..."):
                transcription = transcribe_audio(temp_filename)
            
            if transcription:
                st.success("Transcription complete!")
                
                with st.spinner("Getting response from Agents..."):
                    response = get_agent_response(transcription)
                
                if response:
                    st.session_state.conversation.append({
                        "user": transcription,
                        "assistant": response
                    })
                    
                    if st.session_state.tts_enabled:
                        with st.spinner("Generating speech..."):
                            speech_file = text_to_speech(response, lang=tts_lang)
                            if speech_file:
                                st.audio(speech_file)
                            else:
                                st.warning("Text-to-speech unavailable. Continuing without audio.")
    
    # File upload option
    st.subheader("Or upload audio")
    uploaded_file = st.file_uploader("Upload audio file", type=["wav", "mp3"])
    
    if uploaded_file and st.button("Process Uploaded File"):
        if st.session_state.whisper_model is None:
            st.error("Please load the Whisper model first")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_file_name = temp_file.name
            
            with st.spinner("Transcribing..."):
                transcription = transcribe_audio(temp_file_name)
            
            if transcription:
                st.success("Transcription complete!")
                
                with st.spinner("Getting response from Agents..."):
                    response = get_agent_response(transcription)
                
                if response:
                    st.session_state.conversation.append({
                        "user": transcription,
                        "assistant": response
                    })
                    
                    if st.session_state.tts_enabled:
                        with st.spinner("Generating speech..."):
                            speech_file = text_to_speech(response, lang=tts_lang)
                            if speech_file:
                                st.audio(speech_file)
                            else:
                                st.warning("Text-to-speech unavailable. Continuing without audio.")
    
    # Fallback text input
    st.subheader("Or type your message")
    text_input = st.text_input("Type and press Enter")
    
    if text_input:
        with st.spinner("Getting response from Agents..."):
            response = get_agent_response(text_input)
        
        if response:
            st.session_state.conversation.append({
                "user": text_input,
                "assistant": response
            })
            
            if st.session_state.tts_enabled:
                with st.spinner("Generating speech..."):
                    speech_file = text_to_speech(response, lang=tts_lang)
                    if speech_file:
                        st.audio(speech_file)
                    else:
                        st.warning("Text-to-speech unavailable. Continuing without audio.")

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
        st.rerun()  # For older versions, use st.experimental_rerun()