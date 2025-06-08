from datetime import datetime
import os
import re
import csv
from collections import defaultdict
import wn

import ffmpeg
from phonetics import metaphone
from rapidfuzz import fuzz, process
from spellchecker import SpellChecker

from . import utils # Assuming utils.py is in the same package directory

# Generate phonetic dictionary once (outside process_text)
# Moved _phonetic_dict initialization to a getter function for robustness against utils not being fully loaded.
_phonetic_dict_cache = None

def get_phonetic_dict():
    global _phonetic_dict_cache
    if _phonetic_dict_cache is None:
        _phonetic_dict_cache = {metaphone(word): word for word in utils.load_custom_words()}
    return _phonetic_dict_cache

def process_text(text, case_insensitive=True):
    """
    Applies all correction steps to the input text in a single pass.

    Args:
        text (str): The text to be processed.
        case_insensitive (bool): Whether corrections should be applied in a
                                 case-insensitive manner (default: True).

    Returns:
        str: The corrected text.
    """
    if not text: # Handle empty or None text
        return ""

    custom_words_set = set(utils.load_custom_words()) # Load fresh in case it changed
    replacements_dict = load_corrections_as_dict()
    spell_checker = get_spell_checker()
    current_phonetic_dict = get_phonetic_dict() # Load fresh

    corrected_words_list = []
    # Using a regex that handles punctuation better by splitting on non-word chars but keeping them if needed
    # This regex splits by spaces and punctuation, keeping words.
    # For more sophisticated tokenization, consider nltk.word_tokenize
    
    # A simpler approach: find words, process them, then rebuild the string.
    # This might lose some original spacing nuances if not careful.
    # For now, sticking to word-by-word replacement on identified word tokens.
    
    words_and_delimiters = re.findall(r"(\b[\w'-]+\b|[\W_]+)", text)
    if not words_and_delimiters and text: # If regex fails but text exists, treat whole text as one word (edge case)
        words_and_delimiters = [text]


    for token in words_and_delimiters:
        original_token = token
        is_word = bool(re.fullmatch(r"\b[\w'-]+\b", token))

        if not is_word:
            corrected_words_list.append(original_token)
            continue

        # Process as a word
        word_to_check = token.lower() if case_insensitive else token

        # 1. Check Custom Dictionary:
        if word_to_check in custom_words_set or token in custom_words_set: # check original case too
            corrected_words_list.append(original_token)
            continue

        # 2. Check Standard Dictionary (SpellChecker's known words):
        # spell_checker.known([word_to_check]) returns a set, check if word_to_check is in it.
        if spell_checker.known([word_to_check]):
            corrected_words_list.append(original_token)
            continue
        
        # 3. Apply Corrections List:
        # Check both original and lowercased form in replacements_dict
        # Prioritize original form if exists, then lowercased
        replacement_found = False
        if token in replacements_dict:
             corrected_words_list.append(replacements_dict[token])
             replacement_found = True
        elif case_insensitive and word_to_check in replacements_dict:
            # If original was e.g. "Teh", and corrections has "teh" -> "the"
            # We need to respect original capitalization if possible.
            # This is complex. For now, just use the replacement as is.
            corrected_words_list.append(replacements_dict[word_to_check])
            replacement_found = True
        if replacement_found:
            continue

        # 4. Apply Phonetic Correction (only if not found in dictionaries):
        phonetic_word = metaphone(word_to_check)
        if phonetic_word in current_phonetic_dict:
            # Preserve original casing if the phonetic match is for a lowercased version
            # This is tricky. If original "Exampel" matches "example" phonetically.
            # A simple approach:
            # if original_token[0].isupper() and current_phonetic_dict[phonetic_word][0].islower():
            #     corrected_words_list.append(current_phonetic_dict[phonetic_word].capitalize())
            # else:
            #     corrected_words_list.append(current_phonetic_dict[phonetic_word])
            # Simpler: just use the dictionary form for now
            corrected_words_list.append(current_phonetic_dict[phonetic_word])
            continue

        # 5. If not found anywhere, keep original
        corrected_words_list.append(original_token)
        # unknown_words handling can be done elsewhere if needed

    return "".join(corrected_words_list)


def load_corrections_as_dict():
    """
    Loads the corrections list from file into a dictionary.
    """
    replacements_dict = {}
    corrections_file = utils.get_corrections_list_file()
    if not os.path.exists(corrections_file):
        print(f"Warning: Corrections list file not found at {corrections_file}. Creating an empty one.")
        try:
            with open(corrections_file, 'w', encoding='utf-8') as f:
                f.write("# Add corrections in the format: mispelled -> corrected\n")
            return {} # Return empty dict as it's just created
        except IOError as e:
            print(f"Error creating corrections file: {e}")
            return {}


    try:
        with open(corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): # Skip empty lines and comments
                    continue
                if ' -> ' in line:
                    original, replacement = line.split(' -> ', 1) # Split only on first occurrence
                    replacements_dict[original.strip()] = replacement.strip()
                else:
                    print(f"Warning: Malformed line in corrections file: {line}")
    except FileNotFoundError:
        # This case should be handled by the os.path.exists check above, but as a fallback:
        print(f"Warning: Corrections list file '{corrections_file}' not found. Skipping corrections.")
    except Exception as e:
        print(f"Error loading corrections file '{corrections_file}': {e}")
    return replacements_dict


def apply_corrections_and_formatting(input_tsv_path, output_txt_path):
    """Applies corrections and formatting to the transcribed text.
    Reads from input_tsv_path, writes to output_txt_path.
    Returns the output_txt_path if successful, else None.
    """
    
    from .file_management import find_audio_files_folder # Local import to avoid circular dependency at module load time

    # input_tsv_path is absolute. Example: .../Campaign/Transcriptions/YYYY_MM_DD_title_norm.tsv
    # We need to find the corresponding audio file to get metadata like title and track number.
    # The audio file would be in .../Campaign/Audio Files/YYYY_MM_DD_title_norm.m4a

    transcriptions_dir = os.path.dirname(input_tsv_path) # .../Campaign/Transcriptions
    campaign_folder_path = os.path.dirname(transcriptions_dir) # .../Campaign

    audio_files_folder = find_audio_files_folder(campaign_folder_path)

    # Derive m4a filename from tsv filename
    base_tsv_name = os.path.splitext(os.path.basename(input_tsv_path))[0] # YYYY_MM_DD_title_norm
    m4a_filename = f"{base_tsv_name}.m4a"
    
    # Construct full path to m4a file
    # It might not be in audio_files_folder if processing was started from elsewhere
    # Let's first check relative to the tsv's campaign structure
    prospective_m4a_path = None
    if audio_files_folder:
        prospective_m4a_path = os.path.join(audio_files_folder, m4a_filename)

    if not prospective_m4a_path or not os.path.exists(prospective_m4a_path):
        # Fallback: assume m4a might be named similarly but without _norm, or different extension
        # This part is tricky if the link between TSV and original audio is not strict.
        # For now, we rely on the _norm.m4a existing.
        print(f"Warning: Could not find corresponding m4a file '{m4a_filename}' in '{audio_files_folder}'. Metadata might be incomplete.")
        # Try to get at least date from filename for the header
        date_match_from_tsv = re.match(r"(\d{4}_\d{2}_\d{2})", os.path.basename(input_tsv_path))
        if date_match_from_tsv:
            date_str = date_match_from_tsv.group(1)
            formatted_date = datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')
        else:
            formatted_date = "Unknown Date"
        
        # Use a generic title if m4a metadata is unavailable
        title = os.path.splitext(os.path.basename(input_tsv_path))[0].replace("_norm", "").replace("_", " ")
        track_num = "N/A" # No track number if m4a not found
    else: # m4a file found
        try:
            probe_data = ffmpeg.probe(prospective_m4a_path)
            metadata = probe_data.get('format', {}).get('tags', {})
            title = metadata.get('title', os.path.splitext(os.path.basename(prospective_m4a_path))[0].replace("_norm", ""))
            track_num_full = metadata.get('track', '0')
            track_num = track_num_full.split('/')[0] if '/' in track_num_full else track_num_full
            
            # Date from m4a filename is more reliable for YYYY_MM_DD format
            date_match_from_m4a = re.match(r"(\d{4}_\d{2}_\d{2})", os.path.basename(prospective_m4a_path))
            if date_match_from_m4a:
                date_str = date_match_from_m4a.group(1)
            else: # Fallback to TSV filename for date
                date_match_from_tsv = re.match(r"(\d{4}_\d{2}_\d{2})", os.path.basename(input_tsv_path))
                date_str = date_match_from_tsv.group(1) if date_match_from_tsv else datetime.now().strftime('%Y_%m_%d')
            
            formatted_date = datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')
        except ffmpeg.Error as e:
            print(f"Error probing m4a file {prospective_m4a_path}: {e}. Using fallback metadata.")
            # Fallback metadata if probe fails
            date_match_from_tsv = re.match(r"(\d{4}_\d{2}_\d{2})", os.path.basename(input_tsv_path))
            date_str = date_match_from_tsv.group(1) if date_match_from_tsv else datetime.now().strftime('%Y_%m_%d')
            formatted_date = datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')
            title = os.path.splitext(os.path.basename(input_tsv_path))[0].replace("_norm", "").replace("_", " ")
            track_num = "N/A"


    try:
        with open(input_tsv_path, 'r', encoding='utf-8', newline='') as f_in, \
             open(output_txt_path, 'w', encoding='utf-8') as f_out:

            f_out.write(f"{title} - #{track_num} - {formatted_date}\n\n")

            tsv_reader = csv.reader(f_in, delimiter='\t')
            header = next(tsv_reader, None) # Skip header: ['start', 'end', 'text'] or similar

            # Determine timestamp format from the first data row
            first_data_row_for_check = next(tsv_reader, None)
            timestamp_format = 'seconds' # Default
            
            if first_data_row_for_check:
                # Check if first_data_row_for_check[0] looks like milliseconds or seconds.milliseconds
                # Whisper typically outputs seconds.milliseconds (e.g., "2.345" or "120.000")
                # Milliseconds as pure integers (e.g. "2345") would also need handling if that's a format.
                # Assuming Whisper's float seconds format for now.
                # If timestamps are large integers (e.g. > 1,000,000 for a multi-hour session in ms), it's ms.
                try:
                    # If it's a float, it's likely seconds. If it's a large int, could be ms.
                    # This heuristic is not perfect.
                    # Let's assume Whisper output is always float seconds.
                    # If pure integer milliseconds were a possibility:
                    # if '.' not in first_data_row_for_check[0] and len(first_data_row_for_check[0]) > 5: # Heuristic for large integer ms
                    #     timestamp_format = 'milliseconds'
                    pass # Sticking to 'seconds' as Whisper default
                except (IndexError, ValueError):
                     print(f"Warning: Could not determine timestamp format from row: {first_data_row_for_check}")


            # Rewind or re-open if needed to process the first data row
            # For simplicity, let's just process it now if we have it
            if first_data_row_for_check:
                if len(first_data_row_for_check) >= 3:
                    start_time_str, _, caption = first_data_row_for_check[:3]
                    formatted_start_time = utils.format_time(start_time_str, timestamp_format)
                    corrected_caption = process_text(caption)
                    f_out.write(f"{formatted_start_time}   |   {corrected_caption}\n")
                elif len(first_data_row_for_check) > 0 : # If row exists but malformed
                     print(f"Warning: Skipping malformed row in {input_tsv_path}: {first_data_row_for_check}")


            # Process the remaining rows
            for row in tsv_reader:
                if len(row) >= 3: # Ensure at least 3 columns (start, end, text)
                    start_time_str, _, caption = row[:3] # Take first 3, ignore extras
                    formatted_start_time = utils.format_time(start_time_str, timestamp_format)
                    corrected_caption = process_text(caption)
                    f_out.write(f"{formatted_start_time}   |   {corrected_caption}\n")
                elif len(row) > 0: # If row exists but malformed
                    print(f"Warning: Skipping malformed row in {input_tsv_path}: {row}")
        
        return output_txt_path

    except Exception as e:
        print(f"Error during apply_corrections_and_formatting for {input_tsv_path}: {e}")
        return None


def dictionary_update(txt_path):
    """
    Updates the dictionary (corrections.txt) with non-dictionary words
    that have a low fuzzy match score against the custom_words (wack_dictionary.txt).
    """
    if not os.path.exists(txt_path):
        print(f"Error: Cannot update dictionary, file not found: {txt_path}")
        return

    try:
        with open(txt_path, "r", encoding="utf-8") as file:
            text_content = file.read()
    except Exception as e:
        print(f"Error reading file {txt_path} for dictionary update: {e}")
        return

    # Extract words: typically, we only want to check words from the captions, not timestamps or speaker names.
    # Assuming txt_path is a _revised.txt file, format: HH:MM:SS | Caption
    words_to_check = set()
    for line in text_content.splitlines():
        if "|" in line:
            caption_part = line.split("|", 1)[1]
            words_to_check.update(re.findall(r"\b[\w'-]+\b", caption_part.lower())) # process lowercased words


    spell_checker = get_spell_checker()
    custom_words_set = set(word.lower() for word in utils.load_custom_words()) # Use lowercased custom words for comparison
    
    existing_corrections = load_corrections_as_dict()
    # We need the keys of corrections (the misspelled words) to avoid re-adding them
    # And also the values (corrected words) to avoid flagging correctly replaced words if they are not in dicts.
    # This becomes complex. Simpler: check if word is in custom_words or spell_checker.known.
    # If not, and not already a key in corrections.txt, then consider it.

    words_to_add_to_corrections = []

    for word in sorted(list(words_to_check)):
        if not word: continue # Skip empty strings

        is_known_by_spellchecker = bool(spell_checker.known([word]))
        is_in_custom_dict = word in custom_words_set
        is_in_corrections_keys = word in existing_corrections 
        # (it's okay if it's a *value* in corrections_dict and still unknown, e.g. a proper noun replacement)

        if not is_known_by_spellchecker and not is_in_custom_dict and not is_in_corrections_keys:
            # Word is unknown and not already in corrections_list as a source word.
            # Check phonetic match against custom_words (wack_dictionary)
            phonetic_word = metaphone(word)
            phonetic_dict_cache = get_phonetic_dict() # Ensure it's loaded

            if phonetic_word in phonetic_dict_cache: # Phonetically matches a custom word
                # Example: "githyanki" (custom) vs "gith'yanki" (in text, unknown to spellchecker)
                # If they are very similar, don't add to corrections.
                # fuzz.ratio(word, phonetic_dict_cache[phonetic_word])
                # If phonetic match is good, probably don't need to add to corrections.txt
                # This logic might be too aggressive. Let's use fuzzy match instead for adding.
                pass # Phonetic match found, probably okay or handled by process_text

            # Check fuzzy match against custom_words. If very different, suggest adding to corrections.
            # We only want to add words that are genuinely new/misspelled and NOT close to existing custom words.
            if custom_words_set: # Ensure custom_words_set is not empty for process.extractOne
                best_match_custom, score_custom, _ = process.extractOne(word, custom_words_set, scorer=fuzz.WRatio)
                # If score is low, it means it's NOT similar to any custom word.
                # utils.config["dictionaries"]["correction_threshold"] is a percentage, e.g., 70.
                # If score_custom < threshold, it's a candidate for corrections.txt.
                if score_custom < utils.config["dictionaries"]["correction_threshold"]:
                    words_to_add_to_corrections.append(word)
            else: # No custom words, so any unknown word is a candidate if not in spellchecker
                 words_to_add_to_corrections.append(word)


    if words_to_add_to_corrections:
        print(f"\nFound {len(words_to_add_to_corrections)} potential new words for corrections.txt from {os.path.basename(txt_path)}:")
        corrections_file_path = utils.get_corrections_list_file()
        try:
            with open(corrections_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n# Potential additions from {os.path.basename(txt_path)} ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
                for word in sorted(list(set(words_to_add_to_corrections))): # Ensure uniqueness
                    print(f"  - {word}")
                    f.write(f"{word} -> \n")
            print(f"Appended suggestions to {corrections_file_path}. Please review and complete the corrections.")
        except Exception as e:
            print(f"Error writing to corrections file {corrections_file_path}: {e}")
    else:
        print(f"No new unknown words (below threshold) found in {os.path.basename(txt_path)} for dictionary update.")


_spell_checker_cache = None # Initialize the global variable

def get_spell_checker():
    """Return spell checker populated with custom word list."""
    global _spell_checker_cache
    if _spell_checker_cache is None:
        _spell_checker_cache = SpellChecker()
        # Add custom words from wack_dictionary.txt
        _spell_checker_cache.word_frequency.load_words(utils.load_custom_words())
        
        # Add common contractions and possessives
        contractions_possessives = [
            "i'll", "i've", "he's", "she's", "it's", "we're", "they're", "i'm", "you're", 
            "aren't", "can't", "couldn't", "didn't", "doesn't", "don't", "hadn't", 
            "hasn't", "haven't", "isn't", "mustn't", "shan't", "shouldn't", "wasn't", 
            "weren't", "won't", "wouldn't", "he'll", "she'll", "it'll", "we'll", 
            "they'll", "i'd", "you'd", "he'd", "she'd", "we'd", "they'd", "that's", 
            "what's", "who's", "where's", "when's", "why's", "how's", "here's", "there's"
        ]
        _spell_checker_cache.word_frequency.load_words(contractions_possessives)
        
        # Add words from WordNet
        try:
            # Ensure WordNet resource is available
            # wn.download('oewn') # Using default oewn, 2023 version specified in backup seems too specific for general download
            # Check if 'oewn' is available, if not, try to download a commonly available one.
            try:
                en = wn.Wordnet('oewn:2023') # Try specific version if available
            except wn.lexicon.LexiconError:
                try:
                    print("WordNet 'oewn:2023' not found, trying default 'oewn'...")
                    wn.download('oewn') # Download Open English WordNet if not present
                    en = wn.Wordnet('oewn')
                except Exception as e_wn_download:
                    print(f"Could not download/load WordNet 'oewn': {e_wn_download}. WordNet words will not be added to spellchecker.")
                    en = None

            if en:
                wordnet_words = [form for word_obj in en.words() for form in word_obj.forms()]
                _spell_checker_cache.word_frequency.load_words(wordnet_words)
        except Exception as e:
            print(f"Error loading WordNet words: {e}. Spellchecker might be less effective.")

    return _spell_checker_cache