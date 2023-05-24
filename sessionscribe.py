import os
import subprocess
import math
import datetime
import taglib
from mutagen.mp3 import MP3
import enchant
import re
import unicodedata
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from faster_whisper import WhisperModel

# File locations
working_directory = os.path.dirname(os.getcwd())  # Working directory for trawling
dictionary_file = os.path.join(working_directory, "sessionscribe\\wack_dictionary.txt")  # Dictionary file location
correction_list_file = os.path.join(working_directory, "sessionscribe\\corrections.txt") # Correction list file location

# Trawl through working directory and grab the all the audio files in the last 3 days
def search_audio_files():
    audio_files = []
    current_time = datetime.datetime.now()
    three_days_ago = current_time - datetime.timedelta(days=3)

    # Recursively search for audio files in the directory and its subdirectories
    for root, dirs, files in os.walk(working_directory):
        for file in files:
            if file.endswith(".wav"):
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

# Function to convert an audio file to MP3 format and apply metadata
def convert_to_mp3(file_path, title, track_number):
    # Get the file name and directory separately
    #print(str(file_path))
    input_dir, input_file = os.path.split(file_path)
    cmd = ['ffprobe', '-i', file_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
    output = subprocess.check_output(cmd, universal_newlines=True)
    input_duration = float(output.strip())
    year = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).year

    # Calculate required bitrate for 145MB output file size
    target_size = 145 * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))

    # Convert to MP3 with calculated bitrate
    file_name = os.path.splitext(input_file)[0]
    fil_date = file_name[:10]
    output_file = f"{fil_date}_norm_{file_name[11:]}.mp3"
    output_path = os.path.join(input_dir, output_file)
    cmd = ['ffmpeg', '-i', file_path, '-af', 'loudnorm', '-c:a', 'libmp3lame', '-b:a', str(target_bitrate)+'k', output_path]
    subprocess.run(cmd, check=True)

    # Apply metadata to the audio files, original then new
    with taglib.File(file_path, save_on_exit=True) as song:
        song.tags["TITLE"] = [str(title)]
        song.tags["TRACKNUMBER"] = [str(track_number)]
        song.tags["ARTIST"] = ["Snek Podcasts"]
        song.tags["GENRE"] = ["Podcast"]
        song.tags["DATE"] = [str(year)]
        song.tags["ALBUM"] = [str(os.path.basename(os.path.dirname(input_dir)))]

    with taglib.File(output_path, save_on_exit=True) as song:
        song.tags["TITLE"] = [str(title)]
        song.tags["TRACKNUMBER"] = [str(track_number)]
        song.tags["ARTIST"] = ["Snek Podcasts"]
        song.tags["GENRE"] = ["Podcast"]
        song.tags["DATE"] = [str(year)]
        song.tags["ALBUM"] = [str(os.path.basename(os.path.dirname(input_dir)))]

    print(f'\n\nSuccessfully converted {file_path} to {output_path} with {target_bitrate} kbps bitrate and applied metadata.\n\n')
    return output_path

# Function to transcribe an audio file
def transcribe_audio(input_dir):
    parent_dir = os.path.dirname(os.path.dirname(input_dir))
    transcriptions_folder = next((folder for folder in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder), None)
    output_dir = os.path.join(parent_dir, transcriptions_folder) if transcriptions_folder else None
    subprocess.run(["whisper-ctranslate2", input_dir, "--model", "medium.en", "--language", "en", "--condition_on_previous_text", "False", "--output_dir", output_dir])    
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

    # Create a new Markdown file to write to
    file_name = campaign + " - Transcriptions.md"
    output_file = open(os.path.join(directory,file_name), 'w', encoding='utf-8')

    # Write the campaign information to the output file
    output_file.write('# ' + campaign + '\n\n')
    output_file.write('**Sessions:** ' + str(len(vtt_files)) + '\n\n')

    # Loop through each VTT file and write the contents to the output file
    for i, vtt_file in enumerate(vtt_files):
        # Extract the date and title from the VTT filename
        file_name = os.path.basename(vtt_file)
        day_str = file_name.split('_')[2].replace('-', '_')
        mon_str = file_name.split('_')[1].replace('-', '_')
        year_str = file_name.split('_')[0].replace('-', '_')
        date_str = year_str + '_' + mon_str + '_' + day_str
        date = datetime.datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')

        # Get the title and track number metadata from the MP3 file using mutagen
        audio_files_folder = next((folder for folder in os.listdir(directory) if os.path.isdir(os.path.join(directory, folder)) and "Audio Files" in folder), None)
        mp3_file = os.path.basename(vtt_file.replace('.vtt', '.mp3'))
        audio = MP3(os.path.join(directory,audio_files_folder,mp3_file))
        title = str(audio.get('TIT2', ''))
        track_num = str(audio.get('TRCK', ''))
        print(date + ' - #' + track_num + ' - ' + title)
        # Write the header for this section, including track number
        output_file.write('## ' + title + ' - Session ' + str(track_num) + ' - ' + date + '\n\n')

        # Read the contents of the VTT file and write to the output file
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

# Function to update a dictionary file with new words from the mass transcription file
def dictionary_update(md_path, dictionary_file):
    # Create a dictionary object using the 'en_US' dictionary
    dictionary = enchant.Dict("en_US")

    # Open the input file
    with open(md_path, "r", encoding="utf-8", errors="ignore") as file:
        text = file.read()

    # Define regex pattern for words
    words_pattern = r"\b\w+\b"

    # Find all matches for words
    words = sorted(set(re.findall(words_pattern, text)))

    # Filter out words that are in the standard dictionary
    non_dict_words = [word for word in words if not dictionary.check(word)]

    # Check if the dictionary file already exists
    try:
        with open(correction_list_file, "r", encoding="utf-8", errors="ignore") as file:
            # Read the contents of the file
            lines = file.readlines()

        # Create a set of words that already have corrections
        corrected_words = set(line.split(" -> ")[0] for line in lines if "->" in line)

        # Append new words to the end of the file
        with open(correction_list_file, "a", encoding="utf-8", errors="ignore") as file:
            for word in sorted(non_dict_words, key=lambda x: x.lower()):
                # Only write the word to the file if it does not already have a correction
                if word not in corrected_words:
                    file.write(f"{word} -> \n")
    except FileNotFoundError:
        # Write the results to a new output file with empty columns for corrections
        with open(correction_list_file, "w", encoding="utf-8", errors="ignore") as file:
            for word in sorted(non_dict_words, key=lambda x: x.lower()):
                file.write(f"{word} -> \n")

# Function to perform fuzzy matching and correction on words in the wack_words file
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

# Function to replace incorrect words in the mass transcription file with corrected versions
def corrections_replace(file_path):
    # Load dictionary
    replacements = {}
    with open(dictionary_file, 'r') as f:
        for line in f:
            line = line.strip()
            if ' -> ' in line:
                original, replacement = line.split(' -> ')
                if replacement:
                    replacements[original] = replacement

    # Perform replacements
    with open(file_path, 'r') as f:
        text = f.read()
        for original, replacement in replacements.items():
            text = text.replace(original, replacement)

    # Save output
    with open(file_path, 'w') as f:
        f.write(text)

# Main script logic
def main():
    # Search for audio files created in the last 3 days in the current and lower directories
    # Print the names of the audio files with corresponding numbers
    audio_files = search_audio_files()
    print_options(audio_files)
    # Prompt the user for input to select a file using the number
    selected_file = audio_files[get_user_input()-1]

    # Prompt the user for metadata: Title, Track Number
    title = input("Enter the title: ")
    track_number = input("Enter the track number: ")

    # Run the selected file through the convert_to_mp3 function and apply metadata
    normalised_path = convert_to_mp3(selected_file, title, track_number)

    # Run the converted file through the transcribe_audio function
    campaign_folder = transcribe_audio(normalised_path)

    # Run the transcribe_combine function on the folder containing the file
    md_location = transcribe_combine(campaign_folder)

    # Run the dictionary_update function on the mass transcription file
    dictionary_update(md_location, dictionary_file)

    # Run the fuzzywuzzy0 function on the wack_words and correction_list files
    fuzzy_fix()

    # Run the corrections_replace function on the mass transcription file
    corrections_replace(md_location)

# Call the main function to start the script
if __name__ == "__main__":
    main()
