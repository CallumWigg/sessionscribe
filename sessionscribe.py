import os
import sys
import json
import enchant
import re
import subprocess
import math
from typing import List, Tuple
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from faster_whisper import WhisperModel

DEFAULT_CONFIG = {
    "wack_dictionary": "path/to/wack_word_dictionary.txt",
    "correction_list_file": "path/to/correct_dictionary.txt",
    "campaigns": [
        {
            "name": "Campaign 1",
            "members": ["John, Alice, Bob"],
            "queue": [],
            "folder_path": "path/to/campaign1_folder"
        }
    ]
}

def setup_config():
    config_path = "config.json"
    if os.path.isfile(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = DEFAULT_CONFIG
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
    return config

config = setup_config()
wack_dictionary = config['wack_dictionary']
correction_list_file = config['correction_list_file']
campaigns = config['campaigns']

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def prepare_recording():
    clear_screen()
    campaign_folders = config['campaign_folders']
    for folder in campaign_folders:
        unprepped_audio = search_audio(os.path.join(folder, 'i campaign'), 'un_norm')
        print(f"Un-normalised audio files {len(unprepped_audio)}")
        print("List of files, their campaign, with number 1-8 in front of each:")
        for i, (path, filename) in enumerate(unprepped_audio[:8]):
            print(f"{i+1}. {filename} ({os.path.basename(folder)})")
        print("9. Prepare all files")
        file_num = input("Please select a file to prepare (1-9): ")
        if file_num.isdigit():
            file_num = int(file_num)
            if file_num in range(1, 9):
                path, filename = unprepped_audio[file_num - 1]
                metadata = {}
                answer = input("Would you like to fill out metadata for this file? (y/n): ")
                if answer.lower() == 'y':
                    metadata['track'] = input("Track number: ")
                    metadata['album'] = input("Album name: ")
                    metadata['year'] = input("Year: ")
                    metadata['genre'] = input("Genre: ")
                    metadata = {k: v if v != '-' else None for k, v in metadata.items()}
                else:
                    answer = input("Would you like to transcribe this file? (y/n): ")
                    metadata = None
                mp3_file = convert_to_mp3(path)
                if answer.lower() == 'y':
                    transcribe_audio(mp3_file)
                    transcription_combine(folder)
                    corrections_replace(folder)
                    update_dictionary(folder)
                    print(f"{filename} normalized, transcribed, transcription library collated (and corrected), dictionary updated.")
                else:
                    print(f"{filename} normalized.")
            elif file_num == 9:
                for path, filename in unprepped_audio:
                    mp3_file = convert_to_mp3(path)
                    print(f"{filename} normalized.")
        else:
            print("Invalid input.")

def search_audio(directory, norm_type):
    if norm_type == 'un_norm':
        audio_files = [(os.path.join(root, filename), filename)
                       for root, dirs, files in os.walk(directory)
                       for filename in files
                       if filename.lower().endswith(('.wav', '.mp3', '.m4a'))]
    elif norm_type == 'norm':
        audio_files = [(os.path.join(root, filename), filename)
                       for root, dirs, files in os.walk(directory)
                       for filename in files
                       if filename.lower().endswith(('.wav', '.mp3', '.m4a'))]
    else:
        raise ValueError(f"Invalid normalization type: {norm_type}.")
    
    # Sort the audio files by modification time (most recent first).
    audio_files.sort(key=lambda file: os.path.getmtime(file[0]), reverse=True)
    
    return audio_files

def convert_to_mp3(input_path):
    # get the file name and directory separately
    input_dir, input_file = os.path.split(input_path)
    cmd = ['ffprobe', '-i', input_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
    output = subprocess.check_output(cmd, universal_newlines=True)
    input_duration = float(output.strip())

    # Calculate required bitrate for 145MB output file size
    target_size = 145 * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))

    # Convert to MP3 with calculated bitrate
    file_name = os.path.splitext(input_file)[0]
    fil_date = file_name[:10]
    output_file = f"{fil_date}_norm_{file_name[11:]}.mp3"
    output_path = os.path.join(input_dir, output_file)
    cmd = ['ffmpeg', '-i', input_path, '-af', 'loudnorm', '-c:a', 'libmp3lame', '-b:a', str(target_bitrate)+'k', output_path]
    subprocess.run(cmd, check=True)

    print(f'Successfully converted {input_path} to {output_path} with {target_bitrate} kbps bitrate.')

def prepare_transcription():
    with open(config, "r") as f:
        config = json.load(f)

    for campaign in config["campaigns"]:
        audio_folder = campaign["folder_path"]
        audio_files = os.listdir(audio_folder)
        for file_name in audio_files:
            if "_norm" in file_name and ".md" not in file_name:
                transcription_path = os.path.join(audio_folder, file_name[:-4] + ".md")
                if not os.path.exists(transcription_path):
                    choice = input(f"Would you like to transcribe {file_name}? [y/n/q]")
                    if choice == "n":
                        continue
                    elif choice == "q":
                        return
                    model_size = "tiny.en"
                    model = WhisperModel(model_size, device="auto")
                    audio_path = os.path.join(audio_folder, file_name)
                    segments, info = model.transcribe(audio_path, beam_size=5)
                    with open(transcription_path, "w") as f:
                        f.write("# Transcription\n")
                        for segment in segments:
                            f.write(f"{segment.text}\n")

    print("All audio files transcribed.")

def search_transcribe(directory: str, transcr_type: str) -> List[Tuple[str, str]]:
    if transcr_type == 'un_transcr':
        audio_files = [(os.path.join(directory, f), f) for f in os.listdir(directory) if f.endswith('.mp3')]
        sorted_audio_files = sorted(audio_files, key=lambda x: os.path.getmtime(x[0]), reverse=True)
        return sorted_audio_files
    elif transcr_type == 'transcr':
        audio_files = [(os.path.join(directory, f), f) for f in os.listdir(directory) if f.endswith('.txt')]
        sorted_audio_files = sorted(audio_files, key=lambda x: os.path.getmtime(x[0]), reverse=True)
        return sorted_audio_files
    else:
        raise ValueError("Invalid transcription type.")

def update_dictionary(input_file, dictionary_file):
    # Create a dictionary object using the 'en_US' dictionary
    dictionary = enchant.Dict("en_US")

    # Open the input file
    with open(input_file , "r", encoding="utf-8", errors="ignore") as file:
        text = file.read()

    # Define regex pattern for words
    words_pattern = r"\b\w+\b"

    # Find all matches for words
    words = sorted(set(re.findall(words_pattern, text)))

    # Filter out words that are in the standard dictionary
    non_dict_words = [word for word in words if not dictionary.check(word)]

    # Check if output file already exists
    try:
        with open(dictionary_file, "r", encoding="utf-8", errors="ignore") as file:
            # Read the contents of the file
            lines = file.readlines()

        # Create a set of words that already have corrections
        corrected_words = set(line.split(" -> ")[0] for line in lines if "->" in line)

        # Append new words to the end of the file
        with open(dictionary_file, "a", encoding="utf-8", errors="ignore") as file:
            for word in sorted(non_dict_words, key=lambda x: x.lower()):
                # Only write the word to the file if it does not already have a correction
                if word not in corrected_words:
                    file.write(f"{word} -> \n")
    except FileNotFoundError:
        # Write the results to a new output file with empty columns for corrections
        with open(dictionary_file, "w", encoding="utf-8", errors="ignore") as file:
            for word in sorted(non_dict_words, key=lambda x: x.lower()):
                file.write(f"{word} -> \n")\

def open_dictionary():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("Opening dictionary...")
    os.open(config_json['wack_dictionary_location'])
    sys.exit()

def sort_dictionary():
    # Open the input file and read the lines
    with open(wack_dictionary, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Sort the lines in alphabetical order, regardless of case
    lines.sort(key=str.lower)

    # Write the sorted lines to the output file
    with open("sorted_lines.txt", "w", encoding="utf-8", errors="ignore") as f:
        for line in lines:
            f.write(line)

def correct_dictionary():
    with open(wack_dictionary, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    incorrect_words = {}
    for line in lines:
        if "->" in line:
            incorrect, correction = line.split("->")
            incorrect_words[incorrect.strip()] = correction.strip()

    with open(correction_list_file, 'r', encoding='utf-8') as f:
        all_words = f.read().splitlines()

    for incorrect in incorrect_words.keys():
        if not incorrect_words[incorrect]:
            best_match, score = process.extractOne(incorrect, all_words, scorer=fuzz.ratio)
            if score >= 90:
                correction = best_match
                print(f"Correcting {incorrect} -> {correction} ({score}% score)")
                incorrect_words[incorrect] = correction

    with open(wack_dictionary, 'w', encoding='utf-8') as f:
        for incorrect, correction in incorrect_words.items():
            f.write(f"{incorrect} -> {correction}\n")

'''
def batch_operations():
    clear_screen()
    print("WARNING, this will take a long time....")
    if queue != empty
        print('continue with previous queue?')
    else if
        print('input top level folder location')
        input()
        # SET UP CORRECT FOLDER STRUCTURE
        print('queue initialised')
        # begin normalizigin
        # begin transcribing
    print('queue complete. return?')
    input()
    clear_screen()
'''

def exit_program():
    clear_screen()
    print("Exiting program...")
    sys.exit()

# dictionary to map options to functions
main_menu_options = {
    "1": prepare_recording,
    "2": prepare_transcription,
    "3": update_dictionary,
    "4": open_dictionary,
    "5": sort_dictionary,
    "6": correct_dictionary,
    #"7": batch_operations,
    "x": exit_program
}

while True:
    clear_screen()
    print("\t__________________________________________________\n")
    print("\t  Sessionscribe - An RPG podcast management tool")
    print("\t__________________________________________________\n")
    print("\t[1] Prepare Recordings")
    print("\t[2] Prepare Transcriptions")
    print("\t[3] Open Dictionary")
    print("\t[4] Update Dictionary")
    print("\t[5] Sort Dictionary")
    print("\t[6] Perform Dictionary Corrections")
    print("\t__________________________________________________\n")
    print("\t\t\tCampaign Functions")
    print("\t__________________________________________________\n")
    for i, campaign in enumerate(config['campaigns']):
        print(f'\t[{7+i}] {campaign["name"]} Transcription Library')
    print("\t[x] Exit")
    print("\t__________________________________________________\n")
    main_menu_choice = input("\tEnter a menu option in the Keyboard [1,2,3, ...x]: ")
    if main_menu_choice in main_menu_options:
        main_menu_options[main_menu_choice]()
    else:
        print("Invalid choice. Please enter a valid option.")
    input("Press Enter continuuueuedd")