#!/usr/bin/env python3
"""
Servidor FastAPI con WebSockets para el Simple Speech Assistant.
Proporciona endpoints para la comunicación en tiempo real con los agentes.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
import subprocess
import sys
import os
import asyncio
import logging
from typing import List, Dict, Any

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear la aplicación FastAPI
app = FastAPI(title="Simple Speech Assistant API")

# Asegurarse de que el runner existe
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

# Clase para gestionar las conexiones WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Nueva conexión WebSocket. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Conexión WebSocket cerrada. Restantes: {len(self.active_connections)}")

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

# Instanciar el gestor de conexiones
manager = ConnectionManager()

# Función para obtener respuesta del agente
async def get_agent_response(text):
    try:
        # Escape single quotes in the input text
        escaped_text = text.replace("'", "\\'")
        
        # Run the agent_runner.py script as a separate process
        result = await asyncio.create_subprocess_exec(
            sys.executable, agent_runner_path, escaped_text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        if result.returncode != 0:
            logger.error(f"Agent execution error: {stderr.decode()}")
            return {"status": "error", "error": f"Process exited with {result.returncode}"}
            
        # Parse the JSON output
        try:
            response_json = json.loads(stdout.decode())
            return response_json
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"status": "error", "error": "Could not parse agent response"}
            
    except Exception as e:
        logger.error(f"Agent execution error: {e}")
        return {"status": "error", "error": str(e)}

# Endpoint WebSocket para la comunicación con el agente
@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Recibir mensaje del cliente
            data = await websocket.receive_text()
            
            # Analizar el mensaje recibido
            try:
                message = json.loads(data)
                text = message.get("text", "")
                
                if not text:
                    await manager.send_message(json.dumps({"status": "error", "error": "No text provided"}), websocket)
                    continue
                
                # Enviar confirmación de recepción
                await manager.send_message(json.dumps({"status": "processing", "message": "Processing your request..."}), websocket)
                
                # Obtener respuesta del agente
                response = await get_agent_response(text)
                
                # Enviar respuesta al cliente
                await manager.send_message(json.dumps(response), websocket)
                
            except json.JSONDecodeError:
                await manager.send_message(json.dumps({"status": "error", "error": "Invalid JSON format"}), websocket)
            except Exception as e:
                await manager.send_message(json.dumps({"status": "error", "error": str(e)}), websocket)
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Endpoint para verificar el estado del servidor
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Endpoint para probar la conexión con el agente
@app.get("/test-agent")
async def test_agent():
    response = await get_agent_response("test connection")
    return response

# HTML simple para pruebas de WebSocket
@app.get("/", response_class=HTMLResponse)
async def get():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>WebSocket Test</title>
        </head>
        <body>
            <h1>WebSocket Test</h1>
            <form action="" onsubmit="sendMessage(event)">
                <input type="text" id="messageText" autocomplete="off"/>
                <button>Send</button>
            </form>
            <ul id="messages"></ul>
            <script>
                var ws = new WebSocket("ws://" + window.location.host + "/ws/agent");
                ws.onmessage = function(event) {
                    var messages = document.getElementById('messages');
                    var message = document.createElement('li');
                    var content = document.createTextNode(event.data);
                    message.appendChild(content);
                    messages.appendChild(message);
                };
                function sendMessage(event) {
                    var input = document.getElementById("messageText");
                    var message = {
                        "text": input.value
                    };
                    ws.send(JSON.stringify(message));
                    input.value = '';
                    event.preventDefault();
                }
            </script>
        </body>
    </html>
    """

# Iniciar el servidor
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)