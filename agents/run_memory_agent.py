# agents.py
from tools import store_fact
# WORKING!
def run_memory_agent(ui_context, tool_name, func_args):
    """
    Specialist agent managing context ingestion and memory retention.
    """
    if tool_name == "store_fact":
        fact_text = func_args.get("fact_text")
        category = func_args.get("category", "general")
        
        if not fact_text:
            return "MEMORY WRITE CRITICAL // Missing payload data vector."
            
        # Execute the ChromaDB logic from your ava_memory.py file
        db_confirmation = store_fact(fact_text=fact_text, category=category)
        return db_confirmation
        
    return f"MEMORY FAILURE // Agent cannot parse operation target: {tool_name}"