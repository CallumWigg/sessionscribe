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

from .summarisation import collate_summaries
from . import utils

# Generate phonetic dictionary once (outside process_text)
_phonetic_dict = {metaphone(word): word for word in utils.load_custom_words()}

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

    custom_words_set = set(utils.load_custom_words())
    replacements_dict = load_corrections_as_dict()
    spell_checker = get_spell_checker()  # Get the spell checker instance

    corrected_text = []
    unknown_words = set()

    for word in re.findall(r"\b[\w'-]+\b", text):
        original_word = word
        if case_insensitive:
            word = word.lower()

        # 1. Check Custom Dictionary:
        if word in custom_words_set:
            corrected_text.append(original_word)
            continue

        # 2. Check Standard Dictionary:
        if spell_checker.word_frequency[word.lower()]:  # Check if the word is in the dictionary
            corrected_text.append(original_word)
            continue

        # 3. Apply Corrections List:
        if word in replacements_dict:
            corrected_text.append(replacements_dict[word])
            continue

        # 4. Apply Phonetic Correction (only if not found in dictionaries):
        phonetic_word = metaphone(word)
        if phonetic_word in _phonetic_dict:
            corrected_text.append(_phonetic_dict[phonetic_word])
            continue

        # 5. Add to Unknown Words (if not found anywhere)
        corrected_text.append(original_word)
        unknown_words.add(original_word)

    #if unknown_words:
    #    print("Unknown words found:")
    #    for word in sorted(unknown_words):
    #        print(f"  - {word}")

    return " ".join(corrected_text)

def load_corrections_as_dict():
    """
    Loads the corrections list from file into a dictionary.
    """
    replacements_dict = {}
    try:
        with open(utils.get_corrections_list_file(), 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ' -> ' in line:
                    original, replacement = line.split(' -> ')
                    replacements_dict[original.strip()] = replacement.strip()
    except FileNotFoundError:
        print("Warning: Corrections list file not found. Skipping corrections.")
    return replacements_dict


def apply_corrections_and_formatting(input_tsv, output_txt):
    """
    Applies corrections and formatting to the transcribed text.

    NOTE: This function's timestamp logic and revised txt file
    construction are retained as requested.
    The text processing part is replaced with a call to `process_text`.
    """
    from .file_management import find_audio_files_folder, find_transcriptions_folder
    tsv_dir = os.path.dirname(input_tsv)
    parent_dir = os.path.dirname(tsv_dir)  # (Campaign Folder)

    audio_files_folder = find_audio_files_folder(parent_dir)

    if not os.path.exists(audio_files_folder):
        print(f"Warning: Could not find 'Audio Files' folder: {audio_files_folder}")
        return

    m4a_file = os.path.join(audio_files_folder, os.path.basename(input_tsv).replace(".tsv", ".m4a"))

    if not os.path.exists(m4a_file):
        print(f"Warning: Could not find corresponding m4a file: {m4a_file}")
        return

    metadata = ffmpeg.probe(m4a_file)['format']['tags']
    title = metadata.get('title', '')
    track_num = metadata.get('track', '0').split('/')[0]  # Extract the track number
    date_str = os.path.basename(m4a_file)[:10]  # Extract date from the filename and format it
    date = datetime.strptime(date_str, '%Y_%m_%d').strftime('%Y_%m_%d')

    with open(input_tsv, 'r', encoding='utf-8', newline='') as f_in, \
            open(output_txt, 'w', encoding='utf-8') as f_out:

        date_obj = datetime.strptime(date_str, '%Y_%m_%d')
        formatted_date = date_obj.strftime('%d / %m / %Y')  # Format date
        f_out.write(f"{title} - #{track_num} - {formatted_date}\n\n")

        tsv_reader = csv.reader(f_in, delimiter='\t')  # Create a TSV reader
        next(tsv_reader, None)  # Skip the header row

        # Determine timestamp format from the first row
        first_row = next(tsv_reader, None)
        if first_row and re.match(r'^\d+\.\d+$', first_row[0]):  # Check for digits.digits pattern
            timestamp_format = 'seconds'  # Format: seconds.milliseconds
        else:
            timestamp_format = 'milliseconds'  # Format: milliseconds

        # Process the first row (now that we know the format)
        if first_row:
            start_time, _, caption = first_row
            start_time = utils.format_time(start_time, timestamp_format)  # Pass the format
            corrected_caption = process_text(caption) # Process caption using process_text
            f_out.write(f"{start_time}   |   {corrected_caption}\n")

        # Process the remaining rows
        for row in tsv_reader:
            if len(row) == 3:
                start_time, _, caption = row
                start_time = utils.format_time(start_time, timestamp_format)  # Pass the format
                corrected_caption = process_text(caption) # Process caption using process_text
                f_out.write(f"{start_time}   |   {corrected_caption}\n")
            else:
                print(f"Warning: Skipping row with incorrect format in {input_tsv}: {row}")

def dictionary_update(txt_path):
    """
    Updates the dictionary with non-dictionary words
    that have a low fuzzy match score.
    """
    with open(txt_path, "r", encoding="utf-8") as file:
        text = file.read()
    words = sorted(set(re.findall(r"\b\w+\b", text)))
    spell_checker = get_spell_checker()
    custom_words_set = set(utils.load_custom_words()) # Load as set for faster lookup

    try:
        with open(utils.get_corrections_list_file(), "r", encoding="utf-8") as file:
            lines = file.readlines()
            corrected_words = {line.split(" -> ")[0] for line in lines if "->" in line}
    except FileNotFoundError:
        corrected_words = set()

    with open(utils.get_corrections_list_file(), "a", encoding="utf-8") as file:
        for word in sorted(words, key=lambda x: x.lower()):
            if not spell_checker.word_frequency[word] and word not in corrected_words:
                best_match, score, _ = process.extractOne(word, custom_words_set, scorer=fuzz.ratio)
                if score < utils.config["dictionaries"]["correction_threshold"]:
                    file.write(f"{word} -> \n")

_spell_checker = None # Initialize the global variable
def get_spell_checker():
    """Return spell checker populated with custom word list."""

    global _spell_checker
    if _spell_checker is None:
        _spell_checker = SpellChecker()
        _spell_checker.word_frequency.load_words(utils.load_custom_words())
        contractions_possessives = ["i'll", "i've", "he's", "she's", "it's", "we're", "they're", "i'm", "you're", "aren't", "can't", "couldn't", "didn't", "doesn't", "don't", "hadn't", "hasn't", "haven't", "isn't", "mustn't", "shan't", "shouldn't", "wasn't", "weren't", "won't", "wouldn't", "he'll", "she'll", "it'll", "we'll", "they'll", "i'd", "you'd", "he'd", "she'd", "we'd", "they'd", "that's", "what's", "who's", "where's", "when's", "why's", "how's", "here's", "there's"] 
        _spell_checker.word_frequency.load_words(contractions_possessives)
        wn.download("oewn:2023", quiet=True)
        en = wn.Wordnet('oewn:2023')
        wordnet_words = [synset.lemma().name() for synset in en.synsets()]
        _spell_checker.word_frequency.load_words(wordnet_words)

    return _spell_checker