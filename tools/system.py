import sys
import subprocess
import time
import pyautogui
import easyocr
import os
import platform

def run_system_maintenance() -> str:
    """
    Safely initiates native OS maintenance chores by prompting the official 
    system cleanup dashboard, keeping all file permissions 100% secure.
    """
    try:
        if sys.platform == "win32":
            # Safely opens the built-in Windows Disk Cleanup configuration selector
            subprocess.Popen(["cleanmgr.exe"], shell=False)
            return "MAINTENANCE ACTIVE // Initializing native Windows Disk Cleanup terminal interface."
            
        elif sys.platform == "darwin":
            # Opens the native macOS Storage Management utility panel
            subprocess.Popen(["open", "/System/Library/CoreServices/Applications/Storage Management.app"])
            return "MAINTENANCE ACTIVE // Mapping macOS Storage Optimization matrix."
            
        else:
            return "MAINTENANCE ABORTED // Target platform architecture unrecognized by security layer."
            
    except Exception as e:
        return f"MAINTENANCE ERROR // Failed to route interface protocols: {str(e)}"

def get_visual_context() -> str:
    """Invisibly snaps the user screen, parsing character metrics via low-overhead OCR."""
    print("[VISION PIPELINE ACTIVE]: Analyzing screen buffer matrix...")
    screenshot_name = f"scan_{int(time.time())}.png"
    
    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_name)
        
        # Performance trick: Initialize inside the function call so it 
        # doesn't continuously sit inside your RAM background space.
        reader = easyocr.Reader(['en'], gpu=False) 
        result = reader.readtext(screenshot_name, detail=0)
        
        if os.path.exists(screenshot_name):
            os.remove(screenshot_name)
            
        extracted_text = " ".join(result)
        
        # Explicit garbage collection reference tip to drop memory overhead
        del reader
        
        if not extracted_text.strip():
            return "Scan executed. No text coordinates parsed on workspace display."
            
        return f"SCAN COMPLETE. Workspace text payload: {extracted_text}"
    except Exception as err:
        return f"VISION ENGINE PROCESS HALTED // {str(err)}"

def launch_system_application(app_name: str) -> str:
    """
    Dynamically launches an application by passing its name 
    directly to the host operating system shell execution engine.
    """
    try:
        clean_app = app_name.lower().strip()
        current_os = platform.system()

        if current_os == "Windows":
            # --- WINDOWS APP STORE PROTOCOL INTERCEPT ---
            # We map the common app name to its native Windows URI protocol
            WINDOWS_STORE_APPS = {
                "spotify": "spotify:",
                "whatsapp": "whatsapp:",
                "teams": "msteams:",
                "obsidian": "obsidian:"
            }
            
            if clean_app in WINDOWS_STORE_APPS:
                target_command = WINDOWS_STORE_APPS[clean_app]
            else:
                target_command = clean_app

            # shell=True lets us use built-in shell commands like 'start'
            # We pass a dummy title string "" because 'start' treats the first quoted argument as a title
            subprocess.Popen(f'start "" "{target_command}"', shell=True)
            return f"SUCCESS // System signal sent to launch application: '{target_command}'."

        elif current_os == "Darwin":  # macOS
            # 'open -a' targets an application by its registered display name
            subprocess.Popen(["open", "-a", app_name])
            return f"SUCCESS // System signal sent to launch application: '{app_name}'."

        else:
            return f"SYSTEM ERROR // Host OS environment '{current_os}' is currently unsupported."

    except Exception as e:
        return f"LAUNCH FAILURE // Operating system rejected execution parameters: {str(e)}"