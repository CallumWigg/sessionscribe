from datetime import datetime
import os
import re
import csv
from collections import defaultdict
import wn
import tempfile

from rapidfuzz import fuzz, process
from phonetics import metaphone
from spellchecker import SpellChecker

from . import utils, database_management as db

_spell_checker = None

def get_global_spell_checker():
    """
    Returns a globally shared spell checker populated with standard English words.
    Campaign-specific words are handled separately by the CampaignContext.
    """
    global _spell_checker
    if _spell_checker is not None:
        return _spell_checker
    
    print("Initializing global spell checker (one-time setup)...")
    spell_checker = SpellChecker()
    # Add common contractions and possessives that spellchecker might miss.
    contractions_possessives = [
        "i'll", "i've", "he's", "she's", "it's", "we're", "they're", "i'm", "you're", "can't", "don't",
        "won't", "shouldn't", "couldn't", "wouldn't", "isn't", "aren't", "wasn't", "weren't",
        "that's", "what's", "who's", "where's", "when's", "why's", "how's", "here's", "there's"
    ]
    spell_checker.word_frequency.load_words(contractions_possessives)
    
    # Attempt to load WordNet for a more comprehensive dictionary
    try:
        wn.download('oewn:2023')
        en = wn.Wordnet('oewn:2023')
        wordnet_words = [form for word_obj in en.words() for form in word_obj.forms()]
        spell_checker.word_frequency.load_words(wordnet_words)
        print("WordNet dictionary loaded successfully.")
    except Exception:
        print("Could not download or load WordNet 'oewn:2023'. Spell checking will be less comprehensive.")
        
    _spell_checker = spell_checker
    return _spell_checker


def process_text(text, context: utils.CampaignContext, case_insensitive=True):
    """
    Applies all correction steps to the input text in a single pass, using a CampaignContext.
    """
    if not text or not context:
        return ""

    corrections = context.corrections_dict
    phonetic_dict = context.phonetic_dict
    custom_words_set = set(word.lower() for word in context.custom_words) # Lowercase for matching

    corrected_words_list = []
    # Regex to split text into words and non-words (punctuation, spaces)
    tokens = re.findall(r"(\b[\w'-]+\b|[\W_]+)", text)

    for token in tokens:
        is_word = bool(re.fullmatch(r"[\w'-]+", token))
        
        if not is_word:
            corrected_words_list.append(token)
            continue
        
        # Preserve original case for replacement if no correction is found
        original_token = token
        word_to_check = token.lower()

        # 1. Direct match in custom dictionary (fastest check)
        if word_to_check in custom_words_set:
            corrected_words_list.append(original_token)
            continue

        # 2. Direct match in corrections dictionary
        if word_to_check in corrections:
            corrected_words_list.append(corrections[word_to_check])
            continue
            
        # 3. Phonetic match for custom words (handles sound-alike errors)
        phonetic_word = metaphone(word_to_check)
        if phonetic_word in phonetic_dict:
            corrected_words_list.append(phonetic_dict[phonetic_word])
            continue

        # 4. If no corrections apply, append the original token
        corrected_words_list.append(original_token)

    return "".join(corrected_words_list)


def apply_corrections_and_formatting(context: utils.CampaignContext, episode_id, input_tsv_path, output_txt_path):
    """
    Applies corrections and formatting using a safe, atomic write method.
    """
    episode = db.get_episode_by_id(context.campaign_path, episode_id)
    if not episode:
        print(f"Error: Could not find episode {episode_id} in database for formatting.")
        return None

    title = episode['episode_title']
    track_num = episode['episode_number']
    
    try:
        recorded_date = datetime.strptime(episode['recorded_date'], '%Y-%m-%d')
        formatted_date = recorded_date.strftime('%d %B %Y')
    except (TypeError, ValueError):
        formatted_date = "Unknown Date"

    # Write to a temporary file first.
    temp_file_handle, temp_file_path = tempfile.mkstemp(suffix=".txt", text=True)
    
    try:
        with os.fdopen(temp_file_handle, 'w', encoding='utf-8') as f_out:
            with open(input_tsv_path, 'r', encoding='utf-8', newline='') as f_in:
                f_out.write(f"{title} - Episode {track_num}\nRecorded on {formatted_date}\n\n")

                tsv_reader = csv.reader(f_in, delimiter='\t')
                next(tsv_reader, None) # Skip header

                for row in tsv_reader:
                    if len(row) >= 3:
                        start_time_str, _, caption = row[:3]
                        formatted_start_time = utils.format_time(start_time_str)
                        corrected_caption = process_text(caption, context)
                        f_out.write(f"{formatted_start_time} | {corrected_caption.strip()}\n")
        
        # If we get here, the temp file was written successfully. Now, replace the original.
        os.replace(temp_file_path, output_txt_path)
        
        db.update_episode_path(context.campaign_path, episode_id, "transcription_file", output_txt_path)
        db.update_processing_status(context.campaign_path, episode_id, text_processed=True)
        return output_txt_path

    except Exception as e:
        print(f"Error during apply_corrections_and_formatting for {input_tsv_path}: {e}")
        # Clean up the temp file on failure
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return None



def dictionary_update(context: utils.CampaignContext, txt_path):
    """
    Scans a processed transcript and AUTOMATICALLY adds high-confidence corrections
    to the campaign's corrections.txt file.
    """
    if not os.path.exists(txt_path):
        print(f"Error: Cannot update dictionary, file not found: {txt_path}")
        return

    print(f"\nRunning automated dictionary update for {os.path.basename(txt_path)}...")
    
    # 1. Gather all unique words from the transcript
    try:
        with open(txt_path, "r", encoding="utf-8") as file:
            text_content = file.read()
    except Exception as e:
        print(f"Error reading file {txt_path} for dictionary update: {e}")
        return

    words_in_transcript = set(re.findall(r"\b[a-zA-Z'-]+\b", text_content.lower()))

    # 2. Get all known words for this context
    spell_checker = get_global_spell_checker()
    known_global_words = spell_checker.known(words_in_transcript)
    known_custom_words = set(word.lower() for word in context.custom_words)
    already_corrected = set(context.corrections_dict.keys())
    
    # 3. Find all unknown words by removing all known words from the transcript set
    unknown_words = words_in_transcript - known_global_words - known_custom_words - already_corrected

    if not unknown_words:
        print("No new unknown words found. Dictionary is up to date for this file.")
        return
        
    if not context.custom_words:
        print("Warning: `wack_dictionary.txt` is empty. Cannot generate automatic corrections.")
        print("Please add proper nouns (character names, places) to the dictionary first.")
        return

    # 4. For each unknown word, find the best fuzzy match in the custom dictionary
    print(f"Found {len(unknown_words)} potential new words to correct. Analyzing...")
    new_corrections = {}
    
    # Use rapidfuzz to find the best match for each unknown word from the custom list
    # This is much faster than iterating one by one
    for unknown_word in unknown_words:
        # We find the best match from the list of correctly spelled custom words
        result = process.extractOne(unknown_word, context.custom_words, scorer=fuzz.WRatio, score_cutoff=utils.config["dictionaries"]["correction_threshold"])
        if result:
            best_match_word = result[0]
            score = result[1]
            # We check to make sure we aren't creating a circular correction
            if unknown_word != best_match_word.lower():
                new_corrections[unknown_word] = best_match_word
                print(f"  - Found correction: '{unknown_word}' -> '{best_match_word}' (Score: {score:.1f})")

    # 5. Append the new, high-confidence corrections to the file
    if new_corrections:
        corrections_file_path = utils.get_corrections_list_file(context.campaign_path)
        try:
            with open(corrections_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n# --- Automated additions from {os.path.basename(txt_path)} on {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n")
                for original, corrected in sorted(new_corrections.items()):
                    f.write(f"{original} -> {corrected}\n")
            print(f"\nSuccessfully added {len(new_corrections)} new rules to {os.path.basename(corrections_file_path)}.")
        except Exception as e:
            print(f"Error writing to corrections file {corrections_file_path}: {e}")
    else:
        print("No new high-confidence corrections were found.")