import os
import json
from phonetics import metaphone

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
    """Return the base directory where campaign folders are stored."""
    wd = config.get("general", {}).get("working_directory", ".")
    abs_wd = os.path.abspath(os.path.expanduser(wd))
    if not os.path.isdir(abs_wd):
        print(f"Warning: Configured working directory '{abs_wd}' (from '{wd}') does not exist.")
        try:
            os.makedirs(abs_wd, exist_ok=True)
            print(f"Created working directory: {abs_wd}")
        except OSError as e:
            print(f"Could not create working directory: {e}. Defaulting to '.'")
            return os.path.abspath(".")
    return abs_wd

def get_corrections_list_file(campaign_path):
    """Return absolute path of the campaign-specific corrections list file."""
    return os.path.join(campaign_path, "corrections.txt")

_custom_words_cache = {} # Cache per campaign_path
def load_custom_words(campaign_path):
    """
    Return a cached list of custom words from the campaign's wack_dictionary.txt.
    """
    if campaign_path in _custom_words_cache:
        return _custom_words_cache[campaign_path]

    dictionary_file_name = "wack_dictionary.txt"
    dictionary_file_path = os.path.join(campaign_path, dictionary_file_name)

    custom_words = []
    if os.path.exists(dictionary_file_path):
        try:
            with open(dictionary_file_path, "r", encoding="utf-8") as f:
                custom_words = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except IOError as e:
            print(f"Error reading custom dictionary {dictionary_file_path}: {e}")
    else:
        print(f"Custom dictionary '{dictionary_file_name}' not found in '{campaign_path}'.")
        
    _custom_words_cache[campaign_path] = custom_words
    return custom_words

def format_time(time_str, timestamp_format='seconds'):
    """Convert time string (seconds or milliseconds) to hh:mm:ss format."""
    try:
        if timestamp_format == 'seconds':
            total_seconds = float(time_str)
        elif timestamp_format == 'milliseconds':
            total_seconds = float(time_str) / 1000.0
        else:
            val = float(time_str)
            if '.' in time_str or val < 100000:
                total_seconds = val
            else:
                total_seconds = val / 1000.0
            
    except (ValueError, TypeError):
        return "00:00:00" # Return a default for invalid input

    if total_seconds < 0: total_seconds = 0

    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"