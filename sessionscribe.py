import datetime
import math
import os
import re
import subprocess
import sys
import unicodedata

import taglib
from faster_whisper import WhisperModel
from fuzzywuzzy import fuzz, process
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from spellchecker import SpellChecker

# File locations
working_directory = os.path.dirname(os.getcwd()) # Working directory for trawling
dictionary_file = os.path.join(working_directory, "sessionscribe\\wack_dictionary.txt")  # Dictionary file location
correction_list_file = os.path.join(working_directory, "sessionscribe\\corrections.txt") # Correction list file location

# Trawl through working directory and grab the all the audio files in the last 3 days
def search_audio_files():
    audio_files = []
    current_time = datetime.datetime.now()
    three_days_ago = current_time - datetime.timedelta(days=7)

    # Recursively search for audio files in the directory and its subdirectories
    for root, dirs, files in os.walk(working_directory):
        for file in files:
            if file.endswith((".wav",".m4a",".flac")):
                file_path = os.path.join(root, file)
                file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_modified_time >= three_days_ago:
                    audio_files.append(file_path)
    return audio_files

# Print em all to the screen awaiting user input.
def print_options(audio_files):
    for i, file_path in enumerate(audio_files):
        print(f"{i+1}. {file_path}")

# Grab user input
def get_user_input():
    while True:
        try:
            option = int(input("Enter the number of the file you want to process: "))
            return option
        except ValueError:
            print("Invalid input. Please enter a number.")

# Function to convert an audio file to m4a format and apply metadata
def convert_to_m4a(file_path, title):
    # Get the file name and directory separately
    input_dir, input_file = os.path.split(file_path)
    cmd = ['ffprobe', '-i', file_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
    output = subprocess.check_output(cmd, universal_newlines=True)
    input_duration = float(output.strip())
    year = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).year

    # Calculate required bitrate for 145MB output file size
    target_size = 140 * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))

    # Convert to M4a with calculated bitrate
    file_name = os.path.splitext(input_file)[0]
    fil_date = file_name[:10]
    output_file = f"{fil_date}_{file_name[11:]}_norm.m4a"
    output_path = os.path.join(input_dir, output_file)
    cmd = ['ffmpeg', '-i', file_path, '-af', 'loudnorm', '-ac', '1', '-ar', '44100','-c:a', 'aac', '-b:a', str(target_bitrate)+'k', output_path]
    subprocess.run(cmd, check=True)

    # Find the highest track number in existing files
    existing_files = [f for f in os.listdir(input_dir) if f.endswith('.m4a') and f != output_file]
    existing_track_numbers = []
    for f in existing_files:
        audio = MP4(os.path.join(input_dir, f))
        track_num = str(audio.get('trkn', [(0,0)])[0][0])
        if track_num:
            existing_track_numbers.append(int(track_num))
    highest_track_number = max(existing_track_numbers) if existing_track_numbers else 0

    # Increment the track number for the new file
    new_track_number = highest_track_number + 1

    # Apply metadata to the audio files, original then new
    with taglib.File(file_path, save_on_exit=True) as song:
        song.tags["TITLE"] = [str(title)]
        song.tags["TRACKNUMBER"] = [str(new_track_number)]
        song.tags["ARTIST"] = ["Snek Podcasts"]
        song.tags["GENRE"] = ["Podcast"]
        song.tags["DATE"] = [str(year)]
        song.tags["ALBUM"] = [str(os.path.basename(os.path.dirname(input_dir)))]
        song.save()

    with taglib.File(output_path, save_on_exit=True) as song:
        song.tags["TITLE"] = [str(title)]
        song.tags["TRACKNUMBER"] = [str(new_track_number)]
        song.tags["ARTIST"] = ["Snek Podcasts"]
        song.tags["GENRE"] = ["Podcast"]
        song.tags["DATE"] = [str(year)]
        song.tags["ALBUM"] = [str(os.path.basename(os.path.dirname(input_dir)))]
        song.save()

    print(f'\n\nSuccessfully converted {file_path} to {output_path} with {target_bitrate} kbps bitrate and applied metadata.\n\n')
    return output_path

# Function to transcribe an audio file
def transcribe_audio(input_dir):
    parent_dir = os.path.dirname(os.path.dirname(input_dir))
    transcriptions_folder = next((folder for folder in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder), None)
    output_dir = os.path.join(parent_dir, transcriptions_folder) if transcriptions_folder else None
    subprocess.run(["whisper-ctranslate2", input_dir, "--compute_type int8 --model", "distil-large-v3", "--language", "en", "--condition_on_previous_text", "False", "--output_dir", output_dir])    
    return os.path.dirname(output_dir)

# Function to combine individual transcriptions into a single mass transcription file
def transcribe_combine(directory):
    # Create a list of all VTT files in the current directory and its subdirectories
    vtt_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".vtt"):
                vtt_files.append(os.path.join(root, file))

    # Sort the list in descending order by filename
    vtt_files.sort(reverse=True)

    campaign = os.path.basename(directory)

    # Create a new text file to write to
    file_name = campaign + " - Transcriptions.txt"
    output_file = open(os.path.join(directory, file_name), 'w', encoding='utf-8')

    # Write the campaign information to the output file
    output_file.write('# ' + campaign + '\n\n')
    output_file.write('Sessions: ' + str(len(vtt_files)) + '\n\n')

    # Create a list to store the relevant information for each VTT file
    vtt_info = []

    # Loop through each VTT file and store the relevant information in the list
    for vtt_file in vtt_files:
        # Extract the date and title from the VTT filename
        file_name = os.path.basename(vtt_file)
        day_str = file_name.split('_')[2].replace('-', '_')
        mon_str = file_name.split('_')[1].replace('-', '_')
        year_str = file_name.split('_')[0].replace('-', '_')
        date_str = year_str + '_' + mon_str + '_' + day_str
        date = datetime.datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')

        # Get the title and track number metadata from the m4a file using mutagen
        audio_files_folder = next((folder for folder in os.listdir(directory) if os.path.isdir(os.path.join(directory, folder)) and "Audio Files" in folder), None)
        m4a_file = os.path.basename(vtt_file.replace('.vtt', '.m4a'))
        audio = MP4(os.path.join(directory, audio_files_folder, m4a_file))
        title = str(audio.get('\xa9nam', [''])[0])
        track_num = str(audio.get('trkn', [(0, 0)])[0][0])

        # Store the relevant information in a dictionary and append it to the list
        vtt_info.append({
            'date': date,
            'title': title,
            'track_num': track_num
        })

    # Loop through the list of VTT file information and write the lines to the output file
    for info in vtt_info:
        date = info['date']
        title = info['title']
        track_num = info['track_num']
        output_file.write(date + ' - #' + track_num + ' - ' + title + '\n')

    # Write a newline to separate the campaign info from the VTT file contents
    output_file.write('\n\n')

    # Loop through each VTT file and write the contents to the output file
    for vtt_file, info in zip(vtt_files, vtt_info):
        # Extract metadata as before
        date = info['date']
        title = info['title']
        track_num = info['track_num']

        # Read the contents of the VTT file and write to the output file
        output_file.write('## ' + date + ' - #' + track_num + ' - ' + title + '\n')

        with open(vtt_file, 'r', encoding='utf-8') as f:
            # Skip the first two lines of the VTT file
            lines = f.readlines()[2:]

            # Write the remaining lines to the output file, indented with 4 spaces
            for j, line in enumerate(lines):
                line = ''.join(c for c in line if unicodedata.category(c)[0] != 'C')
                if '-->' in line:
                    times = line.strip().split(' --> ')
                    if len(times) >= 2:
                        start_time = times[0]
                        end_time = times[1]
                        caption = lines[j + 1].strip()
                        if caption:
                            output_file.write(start_time + ' --> ' + end_time + '    |    ' + caption + '\n')
                else:
                    continue

            output_file.write('\n')

    # Close the output file
    output_file.close()
    return output_file.name

def dictionary_update(md_path):
    # Create a SpellChecker object
    spell = SpellChecker()

    # Open the input file
    with open(md_path, "r", encoding="utf-8") as file:
        text = file.read()

    # Define regex pattern for words
    words_pattern = r"\b\w+\b"

    # Find all matches for words
    words = sorted(set(re.findall(words_pattern, text)))

    # Filter out words that are in the standard dictionary
    non_dict_words = [word for word in words if not spell.word_frequency[word]]

    try:
        with open(correction_list_file, "r", encoding="utf-8") as file:
            lines = file.readlines()
            corrected_words = {line.split(" -> ")[0] for line in lines if "->" in line}
    except FileNotFoundError:
        corrected_words = set()

    with open(correction_list_file, "a", encoding="utf-8") as file:
        for word in sorted(non_dict_words, key=lambda x: x.lower()):
            if word not in corrected_words:
                file.write(f"{word} -> \n")

### Function to perform fuzzy matching and correction on words in the wack_words file
def fuzzy_fix():
    # Load the list of incorrect words
    with open(correction_list_file, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    incorrect_words = {}
    for line in lines:
        if "->" in line:
            incorrect, correction = line.split("->")
            incorrect_words[incorrect.strip()] = correction.strip()

    # Load the list of all known words
    with open(dictionary_file, 'r', encoding='utf-8') as f:
        all_words = f.read().splitlines()

    # Correct the incorrect words
    for incorrect in incorrect_words.keys():
        if not incorrect_words[incorrect]:
            # If there is no known correction, try to find a correction based on fuzzy matching
            best_match, score = process.extractOne(incorrect, all_words, scorer=fuzz.ratio)
            if score >= 90:
                correction = best_match
                print(f"Correcting {incorrect} -> {correction} ({score}% score)")
                incorrect_words[incorrect] = correction

    # Write the corrected words back to the file
    with open(correction_list_file, 'w', encoding='utf-8') as f:
        for incorrect, correction in incorrect_words.items():
            f.write(f"{incorrect} -> {correction}\n")


#Function to replace incorrect words in the mass transcription file with corrected versions
def corrections_replace(file_path):
    # Load dictionary
    replacements = {}
    with open(correction_list_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ' -> ' in line:
                original, replacement = line.split(' -> ')
                if replacement:
                    replacements[original] = replacement


    # Perform replacements
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
        for original, replacement in replacements.items():
            pattern = r'\b' + re.escape(original) + r'\b'
            text = re.sub(pattern, replacement, text)

    # Save output
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)

# Define the split functions
def process_arguments():
    if "--update" in sys.argv and len(sys.argv) >= 3:
        campaign = sys.argv[sys.argv.index("--update") + 1]
        campaign_folder = os.path.join(working_directory,campaign)
        txt_location = transcribe_combine(campaign_folder)
        print(f'\nstarting dictionary_update at {txt_location}')
        dictionary_update(txt_location)
        print('\nstarting fuzzy_fix')
        fuzzy_fix()
        print(f'\nstarting corrections_replace at {txt_location}')
        corrections_replace(txt_location)
        print('\ndone')
    else:
        main()

def main():
    # Search for audio files created in the last 3 days in the current and lower directories
    # Print the names of the audio files with corresponding numbers
    audio_files = search_audio_files()
    print_options(audio_files)
    
    # Prompt the user for input to select a file using the number
    selected_file = audio_files[get_user_input()-1]

    # Prompt the user for metadata: Title, Track Number
    title = input("Enter the title: ")

    # Run the selected file through the convert_to_m4a function and apply metadata
    normalised_path = convert_to_m4a(selected_file, title)

    # Run the converted file through the transcribe_audio function
    campaign_folder = transcribe_audio(normalised_path)

    # Run the transcribe_combine function on the folder containing the file
    md_location = transcribe_combine(campaign_folder)

    # Run the dictionary_update function on the mass transcription file
    dictionary_update(md_location)

    # Run the fuzzywuzzy0 function on the wack_words and correction_list files
    fuzzy_fix()

    # Run the corrections_replace function on the mass transcription file
    corrections_replace(md_location)

# Call the process_arguments function to check command line arguments and execute the appropriate functions
if __name__ == "__main__":
    process_arguments()
