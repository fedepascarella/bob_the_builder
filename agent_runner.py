#!/usr/bin/env python3
"""
Script auxiliar para ejecutar los agentes sin interferencia con Streamlit.
Este script se ejecuta como un proceso separado.
"""

import sys
import json

def run_agent(input_text):
    """Ejecuta el equipo de agentes con el texto proporcionado y devuelve la respuesta."""
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