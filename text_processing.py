import re
import os
from spellchecker import SpellChecker
from phonetics import metaphone

from .utils import config, get_corrections_list_file, load_custom_words, phonetic_dict

def apply_corrections(text):
    """Apply corrections to the given text."""
    corrected_text = []
    for word in text.split():
        if word.lower() in [w.lower() for w in load_custom_words()]:
            corrected_text.append(word)  # Keep original case
            continue

        phonetic_word = metaphone(word)
        if phonetic_word in phonetic_dict():
            corrected_text.append(phonetic_dict()[phonetic_word])
            continue

        corrected_text.append(word)

    return " ".join(corrected_text)


def apply_corrections_and_formatting(input_tsv, output_txt):
    """Apply corrections and formatting to the transcribed text."""
    tsv_dir = os.path.dirname(input_tsv)
    parent_dir = os.path.dirname(tsv_dir)  # (Campaign Folder)

    transcriptions_folder = next(
        (folder for folder in os.listdir(parent_dir)
         if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder),
        None
    )
    abbreviation = transcriptions_folder.split()[0] if transcriptions_folder else ""

    audio_files_folder = os.path.join(parent_dir, f"{abbreviation} Audio Files")

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
    date = datetime.datetime.strptime(date_str, '%Y_%m_%d').strftime('%Y_%m_%d')

    with open(input_tsv, 'r', encoding='utf-8', newline='') as f_in, \
            open(output_txt, 'w', encoding='utf-8') as f_out:

        date_obj = datetime.strptime(date_str, '%Y_%m_%d')
        formatted_date = date_obj.strftime('%d / %m / %Y')  # Format date
        f_out.write(f"{title} - #{track_num} - {formatted_date}\n\n")

        tsv_reader = csv.reader(f_in, delimiter='\t')  # Create a TSV reader
        next(tsv_reader, None)  # Skip the header row

        for row in tsv_reader:
            if len(row) == 3:
                start_time, _, caption = row  # Unpack the row
                start_time = format_time(start_time)
                f_out.write(f"{start_time}   |   {caption}\n")
            else:
                print(f"Warning: Skipping row with incorrect format in {input_tsv}: {row}")

def corrections_replace(file_path):
    """Replace incorrect words with correct words in the given file."""
    replacements = {}
    with open(get_corrections_list_file(), 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ' -> ' in line:
                original, replacement = line.split(' -> ')
                if replacement:
                    replacements[original] = replacement

    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
        for original, replacement in replacements.items():
            pattern = r'\b' + re.escape(original) + r'\b'
            text = re.sub(pattern, replacement, text)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)

def dictionary_update(txt_path):
    """Update the dictionary with non-dictionary words."""
    with open(txt_path, "r", encoding="utf-8") as file:
        text = file.read()
    words = sorted(set(re.findall(r"\b\w+\b", text)))
    non_dict_words = [word for word in words if not get_spell_checker().word_frequency[word]]

    try:
        with open(get_corrections_list_file(), "r", encoding="utf-8") as file:
            lines = file.readlines()
            corrected_words = {line.split(" -> ")[0] for line in lines if "->" in line}
    except FileNotFoundError:
        corrected_words = set()

    with open(get_corrections_list_file(), "a", encoding="utf-8") as file:
        for word in sorted(non_dict_words, key=lambda x: x.lower()):
            if word not in corrected_words:
                file.write(f"{word} -> \n")

def fuzzy_fix():
    """Fuzzy fix incorrect words in the dictionary."""
    with open(get_corrections_list_file(), 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    incorrect_words = {}
    for line in lines:
        if "->" in line:
            incorrect, correction = line.split("->")
            incorrect_words[incorrect.strip()] = correction.strip()

    for incorrect in list(incorrect_words.keys()):
        if not incorrect_words[incorrect]:
            best_match, score = process.extractOne(incorrect, load_custom_words(), scorer=fuzz.ratio)
            if score >= config["dictionaries"]["correction_threshold"]:
                correction = best_match
                print(f"Correcting {incorrect} -> {correction} ({score}% score)")
                incorrect_words[incorrect] = correction

    with open(get_corrections_list_file(), 'w', encoding='utf-8') as f:
        for incorrect, correction in incorrect_words.items():
            f.write(f"{incorrect} -> {correction}\n")

def get_spell_checker():
    """Return spell checker populated with custom word list."""
    global _spell_checker 
    if _spell_checker is None:
        # Create a SpellChecker object with the custom dictionary
        _spell_checker = SpellChecker()
        _spell_checker.word_frequency.load_words(load_custom_words())
    return _spell_checker


_spell_checker = None # Initialize the global variable