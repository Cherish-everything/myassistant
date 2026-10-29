from tools import get_visual_context, run_system_maintenance, launch_system_application
# WORKING!
def run_system_agent(ui_context, tool_name, args):
    if tool_name == "get_visual_context":

        return get_visual_context()
    
    elif tool_name == "run_system_maintenance":
        return run_system_maintenance()
    
    elif tool_name == "launch_system_application":
        app_name = args.get("app_name")
        return launch_system_application(app_name)
    
    return f"System Agent: Tool'{tool_name}' completed!"