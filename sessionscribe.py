import datetime
import math
import os
import re
import subprocess
import sys
import unicodedata
import csv

import taglib
from fuzzywuzzy import fuzz, process
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from spellchecker import SpellChecker
from phonetics import metaphone 
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import whisperx

from keys import gemini_key
genai.configure(api_key=gemini_key)

generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 1000,
  "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
  model_name="gemini-1.5-flash",
  generation_config=generation_config,
  safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,        
    }
)

# File locations
working_directory = "C:\\Users\\callu\\OneDrive - Monash University\\DnD\\Session Recordings"
dictionary_file = os.path.join(working_directory, "wack_dictionary.txt")
correction_list_file = os.path.join(working_directory, "corrections.txt")  # Not used anymore 

# Load the custom dictionary globally
with open(dictionary_file, 'r', encoding='utf-8') as f:
    custom_words = f.read().splitlines()

# Create a dictionary of phonetic representations for faster lookup
phonetic_dict = {metaphone(word): word for word in custom_words}

# Create a SpellChecker object with the custom dictionary
spell = SpellChecker()
spell.word_frequency.load_words(custom_words)  

# Trawl through working directory and grab the all the audio files in the last 3 days
def search_audio_files():
    audio_files = []
    current_time = datetime.datetime.now()
    three_days_ago = current_time - datetime.timedelta(days=7)

    for root, dirs, files in os.walk(working_directory):
        for file in files:
            if file.endswith((".wav", ".m4a", ".flac")):
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
    cmd = ['ffprobe', '-i', file_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of',
           'csv=p=0']
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
    cmd = ['ffmpeg', '-i', file_path, '-af', 'loudnorm', '-ac', '1', '-ar', '44100', '-c:a', 'aac',
           '-b:a', str(target_bitrate) + 'k', output_path]
    subprocess.run(cmd, check=True)

    # Find the highest track number in existing files
    existing_files = [f for f in os.listdir(input_dir) if f.endswith('.m4a') and f != output_file]
    existing_track_numbers = []
    for f in existing_files:
        audio = MP4(os.path.join(input_dir, f))
        track_num = str(audio.get('trkn', [(0, 0)])[0][0])
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

    print(
        f'\n\nSuccessfully converted {file_path} to {output_path} with {target_bitrate} kbps bitrate and applied metadata.\n\n')
    return output_path

def format_time(time_str):
    # Convert time from milliseconds to hh:mm:ss format
    milliseconds = int(time_str)  # Convert milliseconds to an integer
    seconds = milliseconds // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# Transcribe and revise audio
def transcribe_and_revise_audio(input_audio_file):
    # Additional settings
    model = "distil-large-v2"
    device = "auto"
    output_format = "tsv"
    language = "en"
    align_model = "en"
    print_progress = True

    # Transcription with WhisperX
    model = whisperx.load_model(model, device=device)
    audio = whisperx.load_audio(input_audio_file)
    result = model.transcribe(audio, language=language, print_progress=print_progress)
    segments = result["segments"]

    # Align whisper output
    model_a, metadata = whisperx.load_align_model(language_code=language, device=device)
    segments = whisperx.align(segments, model_a, metadata, audio, device, return_char_alignments=False)["segments"]

    # Save the aligned segments to a TSV file
    output_dir = os.path.dirname(input_audio_file)
    output_tsv_file = os.path.join(output_dir, os.path.splitext(os.path.basename(input_audio_file))[0] + "_revised.tsv")
    with open(output_tsv_file, "w", encoding="utf-8") as f:
        for segment in segments:
            f.write(f"{segment['start_time']}\t{segment['end_time']}\t{segment['text']}\n")

    # Apply corrections and formatting to the TSV file
    revised_tsv_file = output_tsv_file.replace(".tsv", "_revised.md")
    # Assuming apply_corrections_and_formatting is a placeholder for your actual function
    apply_corrections_and_formatting(output_tsv_file, revised_tsv_file)

    return output_dir, revised_tsv_file


def dictionary_update(md_path):
    with open(md_path, "r", encoding="utf-8") as file:
        text = file.read()
    words = sorted(set(re.findall(r"\b\w+\b", text)))
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

def fuzzy_fix():
    with open(correction_list_file, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    incorrect_words = {}
    for line in lines:
        if "->" in line:
            incorrect, correction = line.split("->")
            incorrect_words[incorrect.strip()] = correction.strip()

    for incorrect in incorrect_words.keys():
        if not incorrect_words[incorrect]:
            best_match, score = process.extractOne(incorrect, custom_words, scorer=fuzz.ratio)
            if score >= 90:
                correction = best_match
                print(f"Correcting {incorrect} -> {correction} ({score}% score)")
                incorrect_words[incorrect] = correction

    with open(correction_list_file, 'w', encoding='utf-8') as f:
        for incorrect, correction in incorrect_words.items():
            f.write(f"{incorrect} -> {correction}\n")

def corrections_replace(file_path):
    replacements = {}
    with open(correction_list_file, 'r', encoding='utf-8') as f:
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

def combine_summaries_and_chapters(directory):
    """Combines summaries and chapters from individual sessions into a single file."""

    # 1. Find Summary and Chapter files
    summary_files = [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files if file.endswith("_summary.txt")
    ]

    chapter_files = [
        os.path.join(root, file)
        for root, _, files in os.walk(directory)
        for file in files if file.endswith("_chapters.txt")
    ]

    # 2. Sort Files (using the same logic as in transcribe_combine)
    def get_sort_key(file_path):
        match = re.search(r'#(\d+) - (\d{4}_\d{2}_\d{2})', file_path)
        if match:
            track_number = int(match.group(1))
            date_str = match.group(2)
            date_int = int(date_str.replace("_", ""))
            return track_number, date_int  # Sort by track number descending, then date ascending
        else:
            return 0, 0  # Handle cases without a track number 

    summary_files.sort(key=get_sort_key)
    summary_files.reverse()  # Reverse to get newest to oldest

    chapter_files.sort(key=get_sort_key)
    chapter_files.reverse()  # Reverse to get newest to oldest

    # 3. Combine content into a single file
    campaign = os.path.basename(directory)
    output_file_name = os.path.join(directory, f"{campaign} - Summaries and Chapters.txt")

    with open(output_file_name, "w", encoding="utf-8") as f:
        f.write(f"# {campaign}\n\n")

        # Write Summaries
        for summary_file in summary_files:
            with open(summary_file, "r", encoding="utf-8") as sf:
                f.write(sf.read())
                f.write("\n\n")

        # Write Chapters 
        for chapter_file in chapter_files:
            with open(chapter_file, "r", encoding="utf-8") as cf:
                f.write(cf.read())
                f.write("\n\n") 

    print(f"Combined summaries and chapters saved to: {output_file_name}")

# Function to apply corrections to a single caption (word by word)
def apply_corrections(text):
    corrected_text = []
    for word in text.split():
        # 1. Check custom dictionary (case-insensitive)
        if word.lower() in [w.lower() for w in custom_words]:
            corrected_text.append(word) # Keep original case
            continue

        # 2. Phonetic Matching
        phonetic_word = metaphone(word)
        if phonetic_word in phonetic_dict:
            corrected_text.append(phonetic_dict[phonetic_word])
            continue

        # 3. If no match, keep the original word
        corrected_text.append(word)

    return " ".join(corrected_text)

def apply_corrections_and_formatting(input_tsv, output_md):
    # Get metadata from the corresponding m4a file
    tsv_dir = os.path.dirname(input_tsv)  # Directory of the TSV file
    parent_dir = os.path.dirname(tsv_dir)  # Parent directory (Campaign Folder)

    # Extract the subfolder abbreviation (e.g., "CoS" from "CoS Transcriptions")
    transcriptions_folder = next(
        (folder for folder in os.listdir(parent_dir)
         if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder),
        None
    )
    abbreviation = transcriptions_folder.split()[0] if transcriptions_folder else ""

    # Construct the path to the "Audio Files" folder
    audio_files_folder = os.path.join(parent_dir, f"{abbreviation} Audio Files")

    if not os.path.exists(audio_files_folder):
        print(f"Warning: Could not find 'Audio Files' folder: {audio_files_folder}")
        return

    m4a_file = os.path.join(audio_files_folder, os.path.basename(input_tsv).replace(".tsv", ".m4a"))

    if not os.path.exists(m4a_file):
        print(f"Warning: Could not find corresponding m4a file: {m4a_file}")
        return

    audio = MP4(m4a_file)
    title = str(audio.get('\xa9nam', [''])[0])
    track_num = str(audio.get('trkn', [(0, 0)])[0][0])
    date_str = os.path.basename(m4a_file)[:10]  # Extract date from filename
    date = datetime.datetime.strptime(date_str, '%Y_%m_%d').strftime('%Y_%m_%d')

    with open(input_tsv, 'r', encoding='utf-8', newline='') as f_in, \
            open(output_md, 'w', encoding='utf-8') as f_out:
        f_out.write(f"{title} - #{track_num} - {date}\n\n")  # New format for revised Markdown

        tsv_reader = csv.reader(f_in, delimiter='\t')  # Create a TSV reader
        next(tsv_reader, None)  # Skip the header row

        for row in tsv_reader:
            if len(row) == 3:
                start_time, _, caption = row  # Unpack the row
                start_time = format_time(start_time)
                f_out.write(f"{start_time}   |   {caption}\n")
            else:
                print(f"Warning: Skipping row with incorrect format in {input_tsv}: {row}")

        generate_summary_and_chapters(output_md)  # Generate after creating revised transcript

# Function to generate revised transcripts for existing TSVs
def generate_revised_transcripts(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".tsv"):
                tsv_file = os.path.join(root, file)
                revised_tsv_file = tsv_file.replace(".tsv", "_revised.md")
                apply_corrections_and_formatting(tsv_file, revised_tsv_file)

    combine_summaries_and_chapters(directory)  # Combine after generating all transcripts

# Function to combine individual revised transcriptions into a single text file 
def transcribe_combine(directory):
    md_files = [os.path.join(root, file)
                for root, _, files in os.walk(directory)
                for file in files if file.endswith("_revised.md")]

    # Sort by track number in descending order (highest first)
    def get_sort_key(file_path):
        match = re.search(r'#(\d+) - (\d{4}_\d{2}_\d{2})', file_path) # Capture date as well
        if match:
            track_number = int(match.group(1))
            date_str = match.group(2)
            # Convert date to a sortable format (YYYYMMDD as integer)
            date_int = int(date_str.replace("_", ""))
            return track_number, date_int  # Sort by track number descending, then date ascending
        else:
            return 0, 0  # Handle cases without a track number 

    md_files.sort(key=get_sort_key)
    md_files.reverse() # Reverse the list after sorting!

    campaign = os.path.basename(directory)
    output_file_name = os.path.join(directory, f"{campaign} - Transcriptions.txt")

    with open(output_file_name, 'w', encoding='utf-8') as output_file:
        output_file.write(f"# {campaign}\n\n")
        output_file.write(f"Sessions: {len(md_files)}\n\n")

        # Write track summary
        for md_file in md_files:
            with open(md_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()  # Read the first line
                match = re.search(r'^(.*) - #(\d+) - (\d{4}_\d{2}_\d{2})$', first_line)
                if match:
                    title, track_number, date_str = match.groups()
                    date_str = date_str.replace("_", "/")  # Format date as DD/MM/YYYY
                    output_file.write(f"{date_str} - #{track_number} - {title}\n")

        output_file.write("\n") # Add extra newline before session content

        # Write session content
        for md_file in md_files:
            with open(md_file, 'r', encoding='utf-8') as f:
                # Read and write the entire content, including the modified first line
                output_file.write(f.read())
                output_file.write('\n')  # Add a separator between sessions

    return output_file_name

def extract_track_number(file_path):
    """Extracts the track number from a file path using regex."""
    match = re.search(r'- #(\d+) -', file_path)
    return match.group(1) if match else "0"  # Default to 0 if not found

# Function to generate revised transcripts for existing TSVs
def generate_revised_transcripts(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".tsv"):
                tsv_file = os.path.join(root, file)
                revised_tsv_file = tsv_file.replace(".tsv", "_revised.md")
                apply_corrections_and_formatting(tsv_file, revised_tsv_file)

def generate_summary_and_chapters(transcript_path):
    """Generates a summary and timestamped chapters using the Gemini API."""
    summary = None
    chapters = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    # 1. Generate Summary (without timestamps)
    text_without_timestamps = re.sub(r'^\d{2}:\d{2}:\d{2}   \|   ', '', transcript_text, flags=re.MULTILINE)

    # Create a temporary file for the summary input
    temp_summary_file = transcript_path.replace("_revised.md", "_temp_summary.txt")
    with open(temp_summary_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(text_without_timestamps)

    file_summary = genai.upload_file(temp_summary_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.md", "_summary.txt"))
    #print(f"Uploaded file '{file_summary.display_name}' as: {file_summary.uri}")
    while file_summary.state.name == "PROCESSING":
      #rint(".", end="", flush=True)
      time.sleep(10)
      file_summary = genai.get_file(file_summary.name)
    if file_summary.state.name != "ACTIVE":
      raise Exception(f"File {file_summary.name} failed to process")
    #print("...all files ready")
    #print()

    summary_response = model.generate_content([file_summary, "Generate a short 200-word summary of this dungeons and dragons session transcript. Write as a synopsis of the events, assuming the reader understands the context of the campaign."])
    if summary_response.prompt_feedback:
        print(f"Prompt Feedback: {summary_response.prompt_feedback}", end='')
    else: 
        summary = summary_response.text

    # --- Create and write to summary file --- 
    if summary is not None:
        summary_file_path = transcript_path.replace(".md", "_summary.md") # Create summary filename

        with open(summary_file_path, 'w', encoding='utf-8') as f:
            f.write(summary)
            desired_part = '_'.join(os.path.splitext(os.path.basename(summary_file_path))[0].split('_')[:4])
            print(f"Summary saved to: {desired_part}")
    else:
        print(f"Warning: Could not generate summary for {transcript_path}. Skipping...")

    # 2. Generate Timestamped Chapters (with timestamps)
    # Create a temporary file for the chapters input
    temp_chapters_file = transcript_path.replace("_revised.md", "_temp_chapters.txt")
    with open(temp_chapters_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(transcript_text)

    file_chapters = genai.upload_file(temp_chapters_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.md", "_chapters.txt"))
    #print(f"Uploaded file '{file_chapters.display_name}' as: {file_chapters.uri}")
    while file_chapters.state.name == "PROCESSING":
      #print(".", end="", flush=True)
      time.sleep(10)
      file_chapters = genai.get_file(file_chapters.name)
    if file_chapters.state.name != "ACTIVE":
      raise Exception(f"File {file_chapters.name} failed to process")
    #print("...all files ready")
    #print()

    prompt_text = """
    Generate timestamps for main chapter/topics in a Dungeons and Dragons podcast session transcript.
    Given text segments with their time, generate timestamps for main topics discussed in the session. Format timestamps as hh:mm:ss and provide clear and concise topic titles, with a short one sentence description.  

    IMPORTANT:
    1. Ensure that the chapters are an accurate representation of the entire session, and that the chapters are distributed evenly. The session is often 6 hours long, so they should be well distributed.
    2. There should aim to be 5 chapters TOTAL for the whole transcript.

    List only topic titles and timestamps, and a short description.
    Example for output:
    [hh:mm:ss] **Topic Title One** - Topic 1 brief description
    [hh:mm:ss] **Topic Title Two** - Topic 2 brief description
    - and so on 

    Transcript is provided below, in the format of hh:mm:ss   |   "text":
    """

    chapters_response = model.generate_content([file_chapters, prompt_text]) 
    if chapters_response.prompt_feedback:
        print(f"Prompt Feedback: {chapters_response.prompt_feedback}", end='')
    else: 
        chapters = chapters_response.text

    # --- Create and write to chapters file --- 
    if chapters is not None:
        chapters_file_path = transcript_path.replace(".md", "_chapters.md") # Create chapter filename

        with open(chapters_file_path, 'w', encoding='utf-8') as f:
            f.write(chapters)
            desired_part = '_'.join(os.path.splitext(os.path.basename(chapters_file_path))[0].split('_')[:4])
            print(f"Chapters saved to: {desired_part}")
    else:
        print(f"    Warning: Could not generate chapters for {transcript_path}. Skipping...")


    # Delete the temporary files
    os.remove(temp_chapters_file)
    os.remove(temp_summary_file) 

def find_audio_files_folder(campaign_folder):
    """Find a folder within the campaign folder that contains 'Audio Files' in its name."""
    audio_folders = [
        folder for folder in os.listdir(campaign_folder)
        if os.path.isdir(os.path.join(campaign_folder, folder)) and "Audio Files" in folder
    ]
    if not audio_folders:
        return None
    elif len(audio_folders) == 1:
        return os.path.join(campaign_folder, audio_folders[0])
    else:
        print("Multiple folders with 'Audio Files' found. Please select one:")
        for i, folder in enumerate(audio_folders):
            print(f"{i + 1}. {folder}")
        try:
            choice = int(input("\nEnter the number of the folder: ")) - 1
            if 0 <= choice < len(audio_folders):
                return os.path.join(campaign_folder, audio_folders[choice])
            else:
                print("Invalid choice. Using the first folder.")
                return os.path.join(campaign_folder, audio_folders[0])
        except ValueError:
            print("Invalid input. Using the first folder.")
            return os.path.join(campaign_folder, audio_folders[0])

def find_transcriptions_folder(campaign_folder):
    """Find a folder within the campaign folder that contains 'Transcriptions' in its name."""
    transcriptions_folders = [
        folder for folder in os.listdir(campaign_folder)
        if os.path.isdir(os.path.join(campaign_folder, folder)) and "Transcriptions" in folder
    ]
    if not transcriptions_folders:
        return None
    elif len(transcriptions_folders) == 1:
        return os.path.join(campaign_folder, transcriptions_folders[0])
    else:
        print("Multiple folders with 'Transcriptions' found. Please select one:")
        for i, folder in enumerate(transcriptions_folders):
            print(f"{i + 1}. {folder}")
        try:
            choice = int(input("\nEnter the number of the folder: ")) - 1
            if 0 <= choice < len(transcriptions_folders):
                return os.path.join(campaign_folder, transcriptions_folders[choice])
            else:
                print("Invalid choice. Using the first folder.")
                return os.path.join(campaign_folder, transcriptions_folders[0])
        except ValueError:
            print("Invalid input. Using the first folder.")
            return os.path.join(campaign_folder, transcriptions_folders[0])

def retranscribe_single_file(campaign_folder):
    try:
        # 1. Construct the path to the "Audio Files" subdirectory
        audio_files_folder = find_audio_files_folder(campaign_folder)

        # 2. Get the list of _norm.m4a files in the "Audio Files" subdirectory
        audio_files = [
            f for f in os.listdir(audio_files_folder)
            if f.endswith("_norm.m4a")
        ]

        if not audio_files:
            print(f"No normalized audio files (_norm.m4a) found in {audio_files_folder}")
            return

        print("\nNormalized Audio Files:")
        for i, file in enumerate(audio_files):
            print(f"{i+1}. {file}")

        while True:
            try:
                file_choice = int(input("\nEnter the number of the file to retranscribe: ")) - 1
                if 0 <= file_choice < len(audio_files):
                    selected_file = os.path.join(audio_files_folder, audio_files[file_choice])
                    break
                else:
                    print("Invalid choice. Please enter a number from the list.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        # 3. Transcribe and revise the selected file
        print(f"Retranscribing: {selected_file}")
        _, revised_tsv_file = transcribe_and_revise_audio(selected_file)

        # 4.  Update, combine, and generate summaries/chapters
        print("Updating and combining transcriptions...")
        md_location = transcribe_combine(campaign_folder) # This should still point to the main campaign folder

        print("Generating updated summary and chapters...")
        generate_summary_and_chapters(revised_tsv_file)
        combine_summaries_and_chapters(campaign_folder)  # This should also point to the main campaign folder

        print(f"Retranscription complete. Combined transcription saved to: {md_location}")

    except Exception as e:
        print(f"An error occurred: {e}")

def resummarise_single_file(campaign_folder):
    # Find the folder with "Transcriptions" in its name
    transcriptions_folder = find_transcriptions_folder(campaign_folder)
    
    if not transcriptions_folder:
        print(f"No folder containing 'Transcriptions' found in {campaign_folder}")
        return
    
    # Get list of ALL revised transcription files (or create if not existing)
    revised_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith("_revised.md") and "_norm" in f
    ]

    if not revised_files:
        print("No revised transcription files found with '_norm' in their names.")
        return

    print("\nRevised Transcription Files:")
    for i, file in enumerate(revised_files):
        print(f"{i + 1}. {file}")

    while True:
        try:
            file_choice = int(input("\nEnter the number of the file to resummarise: ")) - 1
            if 0 <= file_choice < len(revised_files):
                selected_file = os.path.join(transcriptions_folder, revised_files[file_choice])
                break
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    # Generate summary and chapters for the selected revised file
    print(f"Generating summary and chapters for: {selected_file}")
    generate_summary_and_chapters(selected_file)

    # Combine summaries and chapters for the campaign folder
    combine_summaries_and_chapters(campaign_folder)

    print(f"Resummarisation complete for file: {selected_file}")


# Function to generate a new campaign folder structure
def generate_new_campaign(campaign_name, abbreviation, working_directory):
    # Create campaign folder structure
    campaign_folder = os.path.join(working_directory, campaign_name)
    os.makedirs(campaign_folder, exist_ok=True)

    # Create "Audio Files" and "Transcriptions" folders
    audio_files_folder = os.path.join(campaign_folder, f"{abbreviation} Audio Files")
    transcriptions_folder = os.path.join(campaign_folder, f"{abbreviation} Transcriptions")
    os.makedirs(audio_files_folder, exist_ok=True)
    os.makedirs(transcriptions_folder, exist_ok=True)

    return campaign_folder, audio_files_folder, transcriptions_folder

# Function to find and select a campaign folder
def select_campaign_folder(working_directory):
    campaigns = [folder for folder in os.listdir(working_directory)
                 if os.path.isdir(os.path.join(working_directory, folder))]
    
    if not campaigns:
        print("No campaigns found in the specified directory.")
        return None
    
    print("Available campaigns:")
    for i, campaign in enumerate(campaigns, start=1):
        print(f"{i}. {campaign}")
    
    while True:
        try:
            choice = int(input("Enter the number corresponding to the campaign: "))
            if 1 <= choice <= len(campaigns):
                campaign_name = campaigns[choice - 1]
                abbreviation = input(f"Enter the abbreviation for '{campaign_name}': ").strip()
                return campaign_name, abbreviation
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")

# Function to normalize audio files in a specified folder
def bulk_normalize_audio(audio_files_folder):
    audio_files = [
        os.path.join(audio_files_folder, f)
        for f in os.listdir(audio_files_folder)
        if f.endswith(".wav") or f.endswith(".m4a") or f.endswith(".flac")
    ]
    
    for audio_file in audio_files:
        normalized_file = os.path.join(audio_files_folder, os.path.splitext(os.path.basename(audio_file))[0] + "_norm.m4a")
        subprocess.run(["ffmpeg", "-i", audio_file, "-af", "loudnorm", normalized_file])

    print("Bulk normalization complete.")

# Function to bulk transcribe audio files in a campaign
def bulk_transcribe_audio(working_directory):
    campaign_name, abbreviation = select_campaign_folder(working_directory)
    if not campaign_name:
        return
    
    audio_files_folder = os.path.join(working_directory, campaign_name, f"{abbreviation} Audio Files")
    for file_name in os.listdir(audio_files_folder):
        if file_name.endswith("_norm.m4a"):
            audio_file = os.path.join(audio_files_folder, file_name)
            transcribe_and_revise_audio(audio_file)

    print("Bulk transcription complete.")

# Function to display the interactive menu
def display_menu():
    print("\nDnD Session Transcription Menu:")
    print("1. Transcribe and process new audio file")
    print("2. Update existing transcriptions (corrections, combining)")
    print("3. Generate revised transcripts from TSVs")
    print("4. Retranscribe a single file")
    print("5. Resummarise a single file")
    print("6. Generate a new campaign")
    print("7. Exit")

def main():
    while True:
        display_menu()
        choice = input("\nEnter your choice (1-6): ")

        if choice == '1':       # Transcribe and process new audio file
            # Search for audio files created in the last 3 days
            # Print the names of the audio files with corresponding numbers
            audio_files = search_audio_files()
            print_options(audio_files)
            
            # Prompt the user for input to select a file using the number
            selected_file = audio_files[get_user_input() - 1]

            # Prompt the user for metadata: Title
            title = input("Enter the title: ")

            # Run the selected file through the convert_to_m4a function and apply metadata
            normalised_path = convert_to_m4a(selected_file, title)

            # Transcribe and create revised version
            campaign_folder, revised_tsv_file = transcribe_and_revise_audio(normalised_path)

            # Combine revised transcriptions
            md_location = transcribe_combine(campaign_folder)

            generate_summary_and_chapters(revised_tsv_file)
            combine_summaries_and_chapters(campaign_folder)

            print(f"Combined transcription saved to: {md_location}")

        elif choice == '2':     # Update existing revised transcriptions
            
            campaigns = [
                f for f in os.listdir(working_directory) 
                if os.path.isdir(os.path.join(working_directory, f)) and not f.startswith("x ")
            ]

            if not campaigns:
                print("No campaign folders found in the working directory.")
            else:
                print("\nAvailable Campaigns:")
                for i, campaign in enumerate(campaigns):
                    print(f"{i+1}. {campaign}")

                while True:
                    try:
                        campaign_choice = int(input("\nEnter the number of the campaign: ")) - 1
                        if 0 <= campaign_choice < len(campaigns):
                            campaign_folder = os.path.join(working_directory, campaigns[campaign_choice])
                            break
                        else:
                            print("Invalid choice. Please enter a number from the list.")
                    except ValueError:
                        print("Invalid input. Please enter a number.") 

            # Find ALL revised Markdown files
            revised_md_files = [
                os.path.join(dirpath, f)
                for dirpath, dirnames, filenames in os.walk(campaign_folder)
                for f in filenames
                if f.endswith("_revised.md")
            ]
            if not revised_md_files:
                print("No revised Markdown files found for update.")
            else:
                # Update ALL revised Markdown files
                for md_file in revised_md_files:
                    print(f'Starting dictionary_update on {md_file}')
                    dictionary_update(md_file)
                    print('Starting fuzzy_fix')
                    fuzzy_fix()
                    print(f'Starting corrections_replace on {md_file}')
                    corrections_replace(md_file)
                    print(f'Done updating {md_file}') 

                # Combine revised transcriptions 
                md_location = transcribe_combine(campaign_folder)  # Call directly 
                print(f"Combined transcriptions (text) saved to: {md_location}")

        elif choice == '3':     # Generate revised transcriptions
            
            campaigns = [
                f for f in os.listdir(working_directory) 
                if os.path.isdir(os.path.join(working_directory, f)) and not f.startswith("x ")
            ]

            if not campaigns:
                print("No campaign folders found in the working directory.")
            else:
                print("\nAvailable Campaigns:")
                for i, campaign in enumerate(campaigns):
                    print(f"{i+1}. {campaign}")

                while True:
                    try:
                        campaign_crehoice = int(input("\nEnter the number of the campaign: ")) - 1
                        if 0 <= campaign_choice < len(campaigns):
                            campaign_folder = os.path.join(working_directory, campaigns[campaign_choice])
                            break
                        else:
                            print("Invalid choice. Please enter a number from the list.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
            generate_revised_transcripts(campaign_folder)
            combine_summaries_and_chapters(campaign_folder)  # Combine after generating all transcripts
            print(f"Generated revised transcripts in: {campaign_folder}")

        elif choice == '4':     # Retranscribe single file
            # Get a list of existing campaign folders (same logic as before) 
            campaigns = [
                f for f in os.listdir(working_directory)
                if os.path.isdir(os.path.join(working_directory, f)) and 
                any("Audio Files" in d for d in os.listdir(os.path.join(working_directory, f))) 
            ]
            if not campaigns:
                print("No campaign folders found in the working directory.")
            else:
                print("\nAvailable Campaigns:")
                for i, campaign in enumerate(campaigns):
                    print(f"{i+1}. {campaign}")

                while True:
                    try:
                        campaign_choice = int(input("\nEnter the number of the campaign: ")) - 1
                        if 0 <= campaign_choice < len(campaigns):
                            campaign_folder = os.path.join(working_directory, campaigns[campaign_choice])
                            break
                        else:
                            print("Invalid choice. Please enter a number from the list.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
            retranscribe_single_file(campaign_folder)

        elif choice == '5':     # Resummarise single file
            # Get a list of existing campaign folders (same logic as before) 
            campaigns = [
                f for f in os.listdir(working_directory) 
                if os.path.isdir(os.path.join(working_directory, f)) and not f.startswith("x ")
            ]
            if not campaigns:
                print("No campaign folders found in the working directory.")
            else:
                print("\nAvailable Campaigns:")
                for i, campaign in enumerate(campaigns):
                    print(f"{i+1}. {campaign}")

                while True:
                    try:
                        campaign_choice = int(input("\nEnter the number of the campaign: ")) - 1
                        if 0 <= campaign_choice < len(campaigns):
                            campaign_folder = os.path.join(working_directory, campaigns[campaign_choice])
                            break
                        else:
                            print("Invalid choice. Please enter a number from the list.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
            resummarise_single_file(campaign_folder)     

        elif choice == '6':
            # Option 6: Generate a new campaign
            campaign_name = input("Enter the name of the new campaign: ")
            abbreviation = input(f"Enter the abbreviation for '{campaign_name}': ")
            campaign_folder, audio_files_folder, transcriptions_folder = generate_new_campaign(campaign_name, abbreviation, working_directory)
            print(f"New campaign '{campaign_name}' created at:")
            print(f"Campaign Folder: {campaign_folder}")
            print(f"Audio Files Folder: {audio_files_folder}")
            print(f"Transcriptions Folder: {transcriptions_folder}")

        elif choice == '7':
            # Option 7: Bulk normalize audio files in a campaign
            bulk_transcribe_audio(working_directory)

        elif choice == '8':
            # Option 8: Bulk transcribe audio files in a campaign
            bulk_summarize_tsv_files(working_directory)

        elif choice == '9':
            print("Exiting...")
            break

        else:
            print("Invalid choice. Please try again.")

# Call the main function to start the interactive menu
if __name__ == "__main__":
    main()