import os
import json
from phonetics import metaphone # Keep for phonetic_dict, though text_processing.py also imports

# Load configuration
CONFIG_FILE_PATH = 'config.json'
config = {}

def load_config():
    global config
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as config_file:
                config = json.load(config_file)
        except json.JSONDecodeError as e:
            print(f"Error: Could not decode {CONFIG_FILE_PATH}. Invalid JSON: {e}")
            print("Please fix config.json or sessionscribe may not work correctly.")
            config = {} # Reset to empty to avoid errors with malformed config
        except Exception as e:
            print(f"Error loading {CONFIG_FILE_PATH}: {e}")
            config = {}
    else:
        print(f"Warning: {CONFIG_FILE_PATH} not found. Using default settings where available.")
        # Define minimal default structure if config is critical
        config = {
            "general": {
                "working_directory": ".",
                "ffmpeg_path": "ffmpeg",
                "ffmpeg_target_size_mb": 50,
                "minimum_bitrate_kbps": 64,
                "summary_skip_minutes": 0,
                "supported_audio_extensions": [".wav", ".m4a", ".flac", ".mp3"],
                "recent_files_scan_days": 100,
            },
            "podcasts": {
                "artist_name": "Unknown Artist",
                "genre": "Speech",
                "audio_channels": 1, # Mono
                "sampling_rate": 44100,
            },
            "transcription": {
                "model": "base.en", # Example model
                "device": "cpu",
                "compute": "int8",
                "language": "en",
                "condition_on_previous_text": False,
                "repetition_penalty": 1.1,
                "beam_size": 5,
                "vad_filter": True,
                "vad_parameters": {"threshold": 0.5}
            },
            "gemini": {
                "api_key": "YOUR_GEMINI_API_KEY_HERE", # Placeholder
                "model_name": "gemini-pro", # Example model
                "temperature": 0.7,
                "safety_settings": "BLOCK_MEDIUM_AND_ABOVE" # Example
            },
            "dictionaries":{
                "correction_threshold": 70 # For fuzzy match in dictionary_update
            }
        }
        try:
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f_out:
                json.dump(config, f_out, indent=4)
            print(f"A default {CONFIG_FILE_PATH} has been created. Please review it, especially the API keys and paths.")
        except IOError as e:
            print(f"Error creating default config file: {e}")


load_config() # Load config when module is imported

def get_working_directory():
    """Return the base directory all working files are stored in.
    Ensures the path is absolute and normalized.
    """
    wd = config.get("general", {}).get("working_directory", ".")
    abs_wd = os.path.abspath(os.path.expanduser(wd)) # Expand ~ if used
    if not os.path.isdir(abs_wd):
        print(f"Warning: Configured working directory '{abs_wd}' (from '{wd}') does not exist or is not a directory.")
        # Fallback to current directory if configured one is bad, or could raise error
        # For now, let's try to create it if it's a reasonable subpath of CWD or user home
        # This is risky. Better to just warn and default to "."
        if wd != ".": # If it was something specific and bad
             print("Defaulting working directory to the current script location's parent or '.'")
             # Attempt to use script's parent dir or CWD as a last resort
             try:
                script_dir_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if os.path.isdir(script_dir_parent): return script_dir_parent
             except: pass
             return os.path.abspath(".") # Fallback to current execution directory
    return abs_wd


def get_corrections_list_file():
    """Return absolute path of corrections list file."""
    return os.path.join(get_working_directory(), "corrections.txt")

_custom_words_cache = None
def load_custom_words():
    """Return a cached list of custom words from the wack_dictionary.txt.
    Loads from file only once unless cache is cleared (e.g. for refresh).
    """
    global _custom_words_cache
    # Allow forced reload if needed, e.g. by setting _custom_words_cache to None externally
    if _custom_words_cache is not None:
        return _custom_words_cache

    dictionary_file_name = "wack_dictionary.txt"
    dictionary_file_path = os.path.join(get_working_directory(), dictionary_file_name)

    custom_words = []
    if os.path.exists(dictionary_file_path):
        try:
            with open(dictionary_file_path, "r", encoding="utf-8") as f:
                custom_words = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except IOError as e:
            print(f"Error reading custom dictionary {dictionary_file_path}: {e}")
    else:
        print(f"Custom dictionary '{dictionary_file_name}' not found in working directory.")
        # Optionally create a default one here too, like in sessionscribe.py main()
        
    _custom_words_cache = custom_words
    return _custom_words_cache

_phonetic_dict_cache = None
def phonetic_dict(): # This function is also in text_processing.py. Consolidate or ensure consistency.
    """Return a dictionary of phonetic representations of custom words for faster lookup."""
    global _phonetic_dict_cache
    if _phonetic_dict_cache is None:
        _phonetic_dict_cache = {
            metaphone(word.lower()): word for word in load_custom_words() # Store original case, key on lower's metaphone
        }
    return _phonetic_dict_cache

def format_time(time_str, timestamp_format='seconds'):
    """Convert time string (seconds or milliseconds) to hh:mm:ss format."""
    try:
        if timestamp_format == 'seconds':
            total_seconds = float(time_str)
        elif timestamp_format == 'milliseconds':
            total_seconds = float(time_str) / 1000.0
        else:
            # Attempt to infer if it's a number
            val = float(time_str)
            # Heuristic: if it's a large number without decimal, assume ms. Otherwise, seconds.
            if '.' in time_str or val < 100000: # Arbitrary threshold for assuming seconds unless very large int
                total_seconds = val
            else:
                total_seconds = val / 1000.0
            print(f"Warning: Unknown timestamp_format '{timestamp_format}', inferred based on value.")
            
    except ValueError:
        print(f"Warning: Could not parse time string '{time_str}' as float. Returning original.")
        return time_str # Return original if unparseable

    if total_seconds < 0: total_seconds = 0 # Handle negative times if they occur

    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"