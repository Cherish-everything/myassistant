import os
import json
from groq import Groq

from agents.script import execute_python_code
from .run_comms_agent import run_comms_agent
from .run_media_agent import run_media_agent
from .run_memory_agent import run_memory_agent
from .run_research_agent import run_research_agent
from .run_system_agent import run_system_agent
from .run_task_agent import run_task_agent

# Mapping tool names to the specialist that handles them
DOMAIN_MAP = {
    "basic_web_search": run_research_agent,
    "get_weather_forecast": run_research_agent,
    "play_spotify": run_media_agent,
    "send_whatsapp_message": run_comms_agent,
    "get_visual_context": run_system_agent,
    "run_system_maintenance": run_system_agent,
    "store_fact" : run_memory_agent,
    "add_new_task": run_task_agent,
    "view_active_tasks": run_task_agent,
    "resolve_completed_task": run_task_agent,
    "launch_system_application": run_system_agent,
    "execute_deep_research": run_research_agent,
    "check_for_new_emails": run_comms_agent,
    "get_agenda_for_date": run_task_agent,
    "read_email_log": run_comms_agent
}

def analyze_argument_viability(tool_name: str, func_args: dict) -> dict:
    """
    Uses Llama to inspect tool arguments. If they are too vague or insufficient,
    it prompts the user for clarification instead of calling the tool.
    """
    # Only vet search/research tools for vagueness to avoid intercepting distinct actions
    if tool_name not in ["execute_deep_research", "basic_web_search"]:
        return {"viable": True, "clarification_prompt": ""}

    # Extract the query argument safely
    search_query = func_args.get("query", "")
    if not search_query:
        return {"viable": False, "clarification_prompt": "What specific topic or query would you like me to research?"}

    client = Groq()
    
    system_prompt = (
        "You are an AI system quality-assurance filter. Your job is to check if a user's research query "
        "is specific enough to yield high-quality academic or professional results without getting buried in web junk.\n\n"
        "CRITERIA FOR FAILURE (Vague):\n"
        "- Just a single broad word or generic phrase (e.g., 'productivity', 'graphic design', 'marketing').\n"
        "- Lacks context, specific angles, or defined objectives.\n\n"
        "CRITERIA FOR SUCCESS (Specific):\n"
        "- Mentions specific frameworks, strategies, demographics, or precise requirements (e.g., 'Pomodoro method benefits', 'UI design strategies for corporate clients').\n\n"
        "OUTPUT FORMAT:\n"
        "You must respond ONLY with a valid JSON block containing two keys: 'viable' (boolean) and 'clarification_prompt' (string).\n"
        "If 'viable' is false, write a brief, sharp, conversational question asking the user to specify their angle or context."
    )
    try:
        response = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Tool: {tool_name}\nArguments: {json.dumps(func_args)}"}
            ],
            response_format={"type": "json_object"}, # Forces Llama to reply in pure JSON
            temperature=0.1
        )
        
        # Parse the decision payload
        decision = json.loads(response.choices[0].message.content)
        return decision
    except Exception as e:
        print(f"[SYSTEM WARN] Router verification failed: {e}. Defaulting to execution.")
        return {"viable": True, "clarification_prompt": ""}


def route_to_agent(ui_context, tool_name, func_args, from_script=False):
    if func_args is None:
        func_args = {}

    if tool_name == "execute_python_code":
        if from_script:
            return "Error: scripts cannot launch other scripts."
        dispatch = lambda name, args: route_to_agent(ui_context, name, args, from_script=True)
        return execute_python_code(func_args.get("script", ""), dispatch=dispatch)

    agent_func = DOMAIN_MAP.get(tool_name)
    if agent_func is None:
        return f"Error: No domain registered for {tool_name}"

    # The vagueness check is for the human conversation, not for scripts
    if not from_script:
        validation = analyze_argument_viability(tool_name, func_args)
        if not validation.get("viable", True):
            print(f"[ROUTER HALT] Arguments for '{tool_name}' are too vague.")
            return f"A.V.A: {validation.get('clarification_prompt')}"

    print(f"Routing to agent: {tool_name} with args: {func_args}")
    return agent_func(ui_context, tool_name, func_args)