import os
import json
from phonetics import metaphone

from phonetics import metaphone

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

def get_working_directory():
    """Return the base directory all working files are stored in."""
    
    return config["general"]["working_directory"]

def get_corrections_list_file():
    """Return path of corrections list. Not used any more."""

    return os.path.join(get_working_directory(), "corrections.txt")

_custom_words = None
def load_custom_words():
    """Return a cached list of custom words from the dictionary."""

    DICTIONARY_FILE_NAME = "wack_dictionary.txt"

    global _custom_words
    if _custom_words is not None:
        return _custom_words

    dictionary_file = os.path.join(get_working_directory(), DICTIONARY_FILE_NAME)

    # Load the custom dictionary and cache in global
    with open(dictionary_file, "r", encoding="utf-8") as f:
        _custom_words = f.read().splitlines()
        
    return _custom_words

_phonetic_dict = None
def phonetic_dict():
    """Return a dictionary of phonetic representations for faster lookup."""

    global _phonetic_dict
    if _phonetic_dict == None:
        _phonetic_dict = {
            metaphone(word): word for word in load_custom_words()
        }
    return _phonetic_dict

def format_time(time_str, timestamp_format='seconds'):
    """Convert time to hh:mm:ss format."""

    if timestamp_format == 'seconds':
        seconds = float(time_str)
    elif timestamp_format == 'milliseconds':
        seconds = float(time_str) / 1000
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp_format}")

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"