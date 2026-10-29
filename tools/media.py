import sys
import subprocess
import pyautogui
import time
import urllib

def play_spotify(song_or_artist: str) -> str:
    """Opens Spotify, searches for a song/artist, and automatically hits play."""
    # Convert spaces safely for Spotify's native protocol app router
    url_safe_song = urllib.parse.quote(song_or_artist)
    
    # Fire up the native desktop application URI
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", f"spotify:search:{url_safe_song}"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", f"spotify:search:{url_safe_song}"])
        
    # --- UI INTERACTION SEQUENCE ---
    # Give the heavy app frame enough breathing room to wake up and focus the window
    time.sleep(2.5) 
    
    # Hit Enter to search/select the top match result card
    pyautogui.press('enter') 
    time.sleep(0.5) 
    
    # Hit Enter a second time to execute the play routine on the selected track card
    pyautogui.press('enter') 
    
    return f"PLAYING // Initializing soundscape for: '{song_or_artist}'"