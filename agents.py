from agno.agent import Agent
from agno.models.ollama import Ollama


constructor_de_recetas = Agent(
    name="Bob",
    model=Ollama(id="llama3.2:3b"),
    role="Eres un experto que crea indicaciones paso a paso para poder ejecutar una tarea de renovacion dentro de un hogar."
)

sql_master = Agent(
    name="Buscador Base de Datos",
    model=Ollama(id="HridaAI/hrida-t2sql-128k:latest"),
    role="Eres un experto en convertir el input del usuario al lenguaje SQL y generar una consulta que pueda ser ejecuta en una base de datos." 
)

rag_master = Agent(
    name="Rag Master",
    model=Ollama(id="llama3.2:3b"),
    role="Eres un experto en realizar busquedas semanticas en una base de datos vectorial si te preguntar por realizar una busqueda en una base de conocimiento"
)

recomendador_master = Agent(
    name="Recomendador Master",
    model=Ollama(id="llama3.2:3b"),
    role="Eres un experto decorador de interiores que realizaras recomendaciones de renovacion si un el usuario te pregunta."
)

team_lider = Agent(
    name="Team Lider",
    model=Ollama(id="llama3.2:3b"),
    role="Lider del equipo de Agentes, decide que agente tiene que actuar frente al input del usuario"
)

bob_team = Agent(
    name="Equipo Bob",
    model=Ollama(id="llama3.2:3b"),
    team=[constructor_de_recetas, sql_master, rag_master, recomendador_master, team_lider],
    instructions=[
        "Primero, el agente team lider decidira en relacion al input del usuario que agente tiene que actuar.",
        "Segundo, una vez que el agente elegido entra en accion, completara su tarea.",
        "Finalmente, se dara la respuesta final al usuario.",
    ],
    show_tool_calls=False,
    markdown=False,
    debug_mode=False,
)
# bob_team.print_response(
#     "Quiero generar una consulta sql para saber cuantas unidades de stock quedan de los muebles de cocina", stream=True
# )