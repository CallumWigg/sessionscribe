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

from . import utils, database_management as db # Assuming utils.py and db are in the same package

# Caches are now dictionaries keyed by campaign_path
_phonetic_dict_cache = {}
_spell_checker_cache = {}

def get_phonetic_dict(campaign_path):
    """
    Generates or retrieves a cached phonetic dictionary for a specific campaign.
    """
    global _phonetic_dict_cache
    if campaign_path in _phonetic_dict_cache:
        return _phonetic_dict_cache[campaign_path]
    
    phonetic_dict = {metaphone(word): word for word in utils.load_custom_words(campaign_path)}
    _phonetic_dict_cache[campaign_path] = phonetic_dict
    return phonetic_dict

def get_spell_checker(campaign_path):
    """
    Returns a spell checker populated with the campaign's custom word list and WordNet.
    """
    global _spell_checker_cache
    if campaign_path in _spell_checker_cache:
        return _spell_checker_cache[campaign_path]
        
    spell_checker = SpellChecker()
    # Add custom words from the campaign's wack_dictionary.txt
    spell_checker.word_frequency.load_words(utils.load_custom_words(campaign_path))
    
    contractions_possessives = [
        "i'll", "i've", "he's", "she's", "it's", "we're", "they're", "i'm", "you're", 
        "aren't", "can't", "couldn't", "didn't", "doesn't", "don't", "hadn't", 
        "hasn't", "haven't", "isn't", "mustn't", "shan't", "shouldn't", "wasn't", 
        "weren't", "won't", "wouldn't", "he'll", "she'll", "it'll", "we'll", 
        "they'll", "i'd", "you'd", "he'd", "she'd", "we'd", "they'd", "that's", 
        "what's", "who's", "where's", "when's", "why's", "how's", "here's", "there's"
    ]
    spell_checker.word_frequency.load_words(contractions_possessives)
        
    try:
        try:
            en = wn.Wordnet('oewn:2023')
        except wn.lexicon.LexiconError:
            try:
                print("WordNet 'oewn:2023' not found, trying default 'oewn'...")
                wn.download('oewn')
                en = wn.Wordnet('oewn')
            except Exception as e_wn_download:
                print(f"Could not download/load WordNet 'oewn': {e_wn_download}.")
                en = None
        if en:
            wordnet_words = [form for word_obj in en.words() for form in word_obj.forms()]
            spell_checker.word_frequency.load_words(wordnet_words)
    except Exception as e:
        print(f"Error loading WordNet words: {e}.")

    _spell_checker_cache[campaign_path] = spell_checker
    return spell_checker


def process_text(text, campaign_path, case_insensitive=True):
    """
    Applies all correction steps to the input text in a single pass, using campaign-specific dictionaries.
    """
    if not text:
        return ""

    custom_words_set = set(utils.load_custom_words(campaign_path))
    replacements_dict = load_corrections_as_dict(campaign_path)
    spell_checker = get_spell_checker(campaign_path)
    current_phonetic_dict = get_phonetic_dict(campaign_path)

    corrected_words_list = []
    words_and_delimiters = re.findall(r"(\b[\w'-]+\b|[\W_]+)", text)
    if not words_and_delimiters and text:
        words_and_delimiters = [text]

    for token in words_and_delimiters:
        original_token = token
        is_word = bool(re.fullmatch(r"\b[\w'-]+\b", token))

        if not is_word:
            corrected_words_list.append(original_token)
            continue

        word_to_check = token.lower() if case_insensitive else token

        if word_to_check in custom_words_set or token in custom_words_set:
            corrected_words_list.append(original_token)
            continue

        if spell_checker.known([word_to_check]):
            corrected_words_list.append(original_token)
            continue
        
        replacement_found = False
        if token in replacements_dict:
             corrected_words_list.append(replacements_dict[token])
             replacement_found = True
        elif case_insensitive and word_to_check in replacements_dict:
            corrected_words_list.append(replacements_dict[word_to_check])
            replacement_found = True
        if replacement_found:
            continue

        phonetic_word = metaphone(word_to_check)
        if phonetic_word in current_phonetic_dict:
            corrected_words_list.append(current_phonetic_dict[phonetic_word])
            continue

        corrected_words_list.append(original_token)

    return "".join(corrected_words_list)

def load_corrections_as_dict(campaign_path):
    """Loads the campaign-specific corrections list from file into a dictionary."""
    replacements_dict = {}
    corrections_file = utils.get_corrections_list_file(campaign_path)
    if not os.path.exists(corrections_file):
        try:
            with open(corrections_file, 'w', encoding='utf-8') as f:
                f.write(f"# Campaign: {os.path.basename(campaign_path)}\n")
                f.write("# Add corrections in the format: mispelled -> corrected\n")
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
                    replacements_dict[original.strip()] = replacement.strip()
    except Exception as e:
        print(f"Error loading corrections file '{corrections_file}': {e}")
    return replacements_dict


def apply_corrections_and_formatting(campaign_path, episode_id, input_tsv_path, output_txt_path):
    """
    Applies corrections and formatting. Now requires campaign_path and episode_id.
    """
    episode = db.get_episode_by_id(campaign_path, episode_id)
    if not episode:
        print(f"Error: Could not find episode {episode_id} in database for formatting.")
        return None

    title = episode['episode_title']
    track_num = episode['episode_number']
    
    try:
        recorded_date = datetime.strptime(episode['recorded_date'], '%Y-%m-%d')
        formatted_date = recorded_date.strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        formatted_date = "Unknown Date"

    try:
        with open(input_tsv_path, 'r', encoding='utf-8', newline='') as f_in, \
             open(output_txt_path, 'w', encoding='utf-8') as f_out:

            f_out.write(f"{title} - #{track_num} - {formatted_date}\n\n")

            tsv_reader = csv.reader(f_in, delimiter='\t')
            header = next(tsv_reader, None)

            for row in tsv_reader:
                if len(row) >= 3:
                    start_time_str, _, caption = row[:3]
                    formatted_start_time = utils.format_time(start_time_str, 'seconds')
                    # Pass campaign_path to process_text
                    corrected_caption = process_text(caption, campaign_path)
                    f_out.write(f"{formatted_start_time}   |   {corrected_caption}\n")
                elif len(row) > 0:
                    print(f"Warning: Skipping malformed row in {input_tsv_path}: {row}")
        
        # Update DB
        db.update_episode_path(campaign_path, episode_id, "transcription_file", output_txt_path)
        db.update_processing_status(campaign_path, episode_id, text_processed=True)
        return output_txt_path

    except Exception as e:
        print(f"Error during apply_corrections_and_formatting for {input_tsv_path}: {e}")
        return None


def dictionary_update(campaign_path, txt_path):
    """
    Updates the campaign's dictionary (corrections.txt) with unknown words.
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

    words_to_check = set()
    for line in text_content.splitlines():
        if "|" in line:
            caption_part = line.split("|", 1)[1]
            words_to_check.update(re.findall(r"\b[\w'-]+\b", caption_part.lower()))

    spell_checker = get_spell_checker(campaign_path)
    custom_words_set = set(word.lower() for word in utils.load_custom_words(campaign_path))
    existing_corrections = load_corrections_as_dict(campaign_path)
    words_to_add_to_corrections = []

    for word in sorted(list(words_to_check)):
        if not word: continue

        is_known_by_spellchecker = bool(spell_checker.known([word]))
        is_in_custom_dict = word in custom_words_set
        is_in_corrections_keys = word in existing_corrections 

        if not is_known_by_spellchecker and not is_in_custom_dict and not is_in_corrections_keys:
            if custom_words_set:
                best_match_custom, score_custom, _ = process.extractOne(word, custom_words_set, scorer=fuzz.WRatio)
                if score_custom < utils.config["dictionaries"]["correction_threshold"]:
                    words_to_add_to_corrections.append(word)
            else:
                 words_to_add_to_corrections.append(word)

    if words_to_add_to_corrections:
        print(f"\nFound {len(words_to_add_to_corrections)} potential new words for corrections.txt for this campaign:")
        corrections_file_path = utils.get_corrections_list_file(campaign_path)
        try:
            with open(corrections_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n# Potential additions from {os.path.basename(txt_path)} ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
                for word in sorted(list(set(words_to_add_to_corrections))):
                    print(f"  - {word}")
                    f.write(f"{word} -> \n")
            print(f"Appended suggestions to {corrections_file_path}. Please review and complete the corrections.")
        except Exception as e:
            print(f"Error writing to corrections file {corrections_file_path}: {e}")
    else:
        print(f"No new unknown words found in {os.path.basename(txt_path)} for dictionary update.")