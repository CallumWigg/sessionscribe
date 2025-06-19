import os
import json
from phonetics import metaphone

# Load configuration
CONFIG_FILE_PATH = 'config.json'
config = {}

## C-IMPROVEMENT: The CampaignContext class centralizes all campaign-specific data loading and caching.
## This avoids passing 'campaign_path' everywhere and managing multiple global caches.
class CampaignContext:
    def __init__(self, campaign_path):
        if not os.path.isdir(campaign_path):
            raise FileNotFoundError(f"Campaign path does not exist: {campaign_path}")
        self.campaign_path = campaign_path
        self.campaign_name = os.path.basename(campaign_path)
        
        # These will be loaded lazily (on first access)
        self._custom_words = None
        self._corrections_dict = None
        self._phonetic_dict = None

    @property
    def custom_words(self):
        if self._custom_words is None:
            self._custom_words = self._load_custom_words()
        return self._custom_words

    @property
    def corrections_dict(self):
        if self._corrections_dict is None:
            self._corrections_dict = self._load_corrections_as_dict()
        return self._corrections_dict
        
    @property
    def phonetic_dict(self):
        if self._phonetic_dict is None:
            self._phonetic_dict = {metaphone(word): word for word in self.custom_words}
        return self._phonetic_dict

    def _load_custom_words(self):
        """Loads words from the campaign's wack_dictionary.txt."""
        dictionary_file_path = os.path.join(self.campaign_path, "wack_dictionary.txt")
        words = []
        if os.path.exists(dictionary_file_path):
            try:
                with open(dictionary_file_path, "r", encoding="utf-8") as f:
                    words = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            except IOError as e:
                print(f"Error reading custom dictionary {dictionary_file_path}: {e}")
        else:
            # Create it if it doesn't exist
            try:
                with open(dictionary_file_path, 'w', encoding='utf-8') as f:
                    f.write("# Add campaign-specific proper nouns, one per line (e.g., character names, locations)\n")
            except IOError as e:
                print(f"Error creating custom dictionary {dictionary_file_path}: {e}")
        return words

    def _load_corrections_as_dict(self):
        """Loads the campaign-specific corrections list from file into a dictionary."""
        replacements_dict = {}
        corrections_file = get_corrections_list_file(self.campaign_path)
        if not os.path.exists(corrections_file):
            try:
                with open(corrections_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Campaign: {self.campaign_name}\n")
                    f.write("# Add corrections in the format: misspelled -> corrected\n")
                return {}
            except IOError as e:
                print(f"Error creating corrections file: {e}")
                return {}

        try:
            with open(corrections_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ' -> ' in line:
                        original, replacement = line.split(' -> ', 1)
                        if original.strip() and replacement.strip():
                            replacements_dict[original.strip()] = replacement.strip()
        except Exception as e:
            print(f"Error loading corrections file '{corrections_file}': {e}")
        return replacements_dict

def load_config():
    global config
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as config_file:
                loaded_config = json.load(config_file)
                # C-IMPROVEMENT: Fix potential typo from old config files automatically
                if "podcasts" in loaded_config and "samping_rate" in loaded_config["podcasts"]:
                    loaded_config["podcasts"]["sampling_rate"] = loaded_config["podcasts"].pop("samping_rate")
                config = loaded_config
        except json.JSONDecodeError as e:
            print(f"Error: Could not decode {CONFIG_FILE_PATH}. Invalid JSON: {e}")
            config = {}
        except Exception as e:
            print(f"Error loading {CONFIG_FILE_PATH}: {e}")
            config = {}
    else:
        print(f"Warning: {CONFIG_FILE_PATH} not found. Creating a default config file.")
        config = {
            "general": {
                "working_directory": ".", "ffmpeg_path": "ffmpeg", "ffmpeg_target_size_mb": 50,
                "minimum_bitrate_kbps": 64, "summary_skip_minutes": 0,
                "supported_audio_extensions": [".wav", ".m4a", ".flac", ".mp3"],
                "recent_files_scan_days": 100,
            },
            "podcasts": {
                "artist_name": "Unknown Artist", "genre": "Speech", "audio_channels": 1, "sampling_rate": 44100,
            },
            "transcription": {
                "model": "base.en", "device": "cpu", "compute": "int8", "language": "en",
                "condition_on_previous_text": False, "repetition_penalty": 1.1,
                "beam_size": 5, "vad_filter": True, "vad_parameters": {"threshold": 0.5}
            },
            "gemini": {
                "api_key": "YOUR_GEMINI_API_KEY_HERE", "model_name": "gemini-1.5-flash",
                "temperature": 0.7, "safety_settings": "BLOCK_NONE"
            },
            "dictionaries":{ "correction_threshold": 90 }
        }
        try:
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f_out:
                json.dump(config, f_out, indent=4)
            print(f"A default {CONFIG_FILE_PATH} has been created. Please review it, especially the API keys and paths.")
        except IOError as e:
            print(f"Error creating default config file: {e}")

load_config()

def get_working_directory():
    wd = config.get("general", {}).get("working_directory", ".")
    abs_wd = os.path.abspath(os.path.expanduser(wd))
    if not os.path.isdir(abs_wd):
        print(f"Warning: Configured working directory '{abs_wd}' does not exist.")
        try:
            os.makedirs(abs_wd, exist_ok=True)
            print(f"Created working directory: {abs_wd}")
        except OSError as e:
            print(f"Could not create working directory: {e}. Defaulting to '.'")
            return os.path.abspath(".")
    return abs_wd

def get_corrections_list_file(campaign_path):
    return os.path.join(campaign_path, "corrections.txt")

def format_time(time_str, timestamp_format='seconds'):
    try:
        total_seconds = float(time_str)
    except (ValueError, TypeError):
        return "00:00:00"

    if total_seconds < 0: total_seconds = 0
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"