import serial
import time
import threading
from functools import wraps
# =====================================================================
# CORE TRANSMISSION CONFIGURATION
# =====================================================================

# Master switch for the Arduino/LCD/button hardware. Set to False when you're
# not connected to the Arduino (e.g. working away from your desk) - this
# skips the serial connection attempt entirely, so there's nothing to time
# out or error on, and listen_for_button below just no-ops.
HARDWARE_ENABLED = False

# 1. Open the USB serial port to your Arduino
# Replace 'COM3' with your actual Arduino port (e.g., '/dev/ttyUSB0' on Mac/Linux)
if HARDWARE_ENABLED:
    try:
        arduino = serial.Serial(port='COM3', baudrate=9600, timeout=1)
        time.sleep(2) # Give Arduino a moment to reset
    except Exception as e:
        print(f"Could not connect to LCD: {e}")
        arduino = None
else:
    print("[System] Hardware disabled (HARDWARE_ENABLED = False) - skipping Arduino connection.")
    arduino = None

# Guards every write to the Arduino so overlapping calls (e.g. an AI reply
# landing on the LCD while another trigger is being written) can't collide
# and cause "Write timeout" errors.
serial_lock = threading.Lock()

# Minimum time between accepted button triggers. The Arduino side is firing
# TRIGGER_AVA multiple times per physical press (contact bounce), so this
# debounce collapses a burst of triggers into a single one.
DEBOUNCE_SECONDS = 3.0
_last_trigger_time = 0.0

def listen_for_button(on_trigger, prompt="Hi"):
    """Blocks forever, watching the serial line for a TRIGGER_AVA message from
    the Arduino. Every time it sees one (debounced), it calls on_trigger(prompt).

    This function does NOT talk to the AI itself anymore - it's purely a
    hardware-event loop. Whoever calls it (app.py) decides what happens with
    the trigger, e.g. routing it into the real AI pipeline so the response
    reaches both the LCD and the on-screen UI.

    Run this in its own daemon thread, e.g.:
        threading.Thread(target=listen_for_button, args=(callback,), daemon=True).start()
    """
    global _last_trigger_time

    if not HARDWARE_ENABLED or arduino is None:
        print("[System] Hardware button listener not started (no Arduino / HARDWARE_ENABLED = False).")
        return

    print("[System] Listening for hardware button triggers...")
    while True:
        if arduino.in_waiting > 0:
            try:
                # Read incoming serial message from Arduino
                line = arduino.readline().decode('utf-8').strip()

                if line == "TRIGGER_AVA":
                    now = time.time()
                    if now - _last_trigger_time < DEBOUNCE_SECONDS:
                        # Bounce from the same physical press - ignore it
                        continue
                    _last_trigger_time = now

                    print("\n[Hardware Event] Button pressed! Launching A.V.A...")
                    on_trigger(prompt)
            except Exception as e:
                print(f"[Serial Error] {e}")

        time.sleep(0.01)

# 2. The Decorator that intercepts return statements
def send_to_lcd(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Run your original code seamlessly
        result = func(*args, **kwargs)
        cleaned_result = clean_for_lcd(result) if isinstance(result, str) else result

        # If the function returns a string, intercept it and send it to the LCD
        if arduino and isinstance(cleaned_result, str):
            # Clean it up: keep it short for the tiny screen, encode to bytes, add a newline
            lcd_message = cleaned_result[:120] + "\n"
            with serial_lock:
                try:
                    arduino.write(lcd_message.encode('utf-8'))
                except Exception as e:
                    print(f"[LCD Write Error] {e}")

        return result
    return wrapper


def clean_for_lcd(text: str) -> str:
    # Replace smart punctuation with standard ASCII
    replacements = {
        '—': '-',  # Em-dash
        '–': '-',  # En-dash
        '’': "'",  # Right curly single quote
        '‘': "'",  # Left curly single quote
        '”': '"',  # Right curly double quote
        '“': '"',  # Left curly double quote
    }
    
    for target, replacement in replacements.items():
        text = text.replace(target, replacement)
        
    # Strip out any remaining non-ASCII characters to prevent weird artifacts
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text