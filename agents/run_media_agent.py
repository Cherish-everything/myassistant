from tools import play_spotify
# WORKING!
def run_media_agent(ui_context, tool_name, args):
    """The Media Agent handles all music and audio playback requests."""

    if tool_name == "play_spotify":
        song_or_artist = args.get("song_or_artist")
        # We log this so you can see A.V.A "thinking" in the terminal
        print(f"Media Agent: Processing audio request for '{song_or_artist}'...")
        
        # Execute the tool
        results = play_spotify(song_or_artist)
    return f"Media command executed. Status: {results}"