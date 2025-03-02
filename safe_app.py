import streamlit as st
import tempfile
import os
import requests
import json
from gtts import gTTS

# Import the audio recorder component from the correct library
from audio_recorder_streamlit import audio_recorder

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

# Title
st.title("🎤 Simple Speech Assistant")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    
    # Whisper model selection
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
    
    # Ollama settings
    ollama_model = st.text_input("Ollama Model", value="llama3.2:3b")
    ollama_url = st.text_input("Ollama API URL", value="http://localhost:11434/api/generate")
    
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

# Function to get response from Ollama
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

# Function to convert text to speech
def text_to_speech(text):
    try:
        audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts = gTTS(text=text, lang="es", slow=False)
        tts.save(audio_file.name)
        return audio_file.name
    except Exception as e:
        st.error(f"Text-to-speech error: {e}")
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
                
                with st.spinner("Getting response from Ollama..."):
                    response = get_ollama_response(
                        transcription,
                        ollama_model,
                        ollama_url
                    )
                
                if response:
                    st.session_state.conversation.append({
                        "user": transcription,
                        "assistant": response
                    })
                    
                    speech_file = text_to_speech(response)
                    if speech_file:
                        st.audio(speech_file)
    
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
                
                with st.spinner("Getting response from Ollama..."):
                    response = get_ollama_response(
                        transcription,
                        ollama_model,
                        ollama_url
                    )
                
                if response:
                    st.session_state.conversation.append({
                        "user": transcription,
                        "assistant": response
                    })
                    
                    speech_file = text_to_speech(response)
                    if speech_file:
                        st.audio(speech_file)
    
    # Fallback text input
    st.subheader("Or type your message")
    text_input = st.text_input("Type and press Enter")
    
    if text_input:
        with st.spinner("Getting response from Ollama..."):
            response = get_ollama_response(
                text_input,
                ollama_model,
                ollama_url
            )
        
        if response:
            st.session_state.conversation.append({
                "user": text_input,
                "assistant": response
            })
            
            speech_file = text_to_speech(response)
            if speech_file:
                st.audio(speech_file)

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
