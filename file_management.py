import os
import re

from summarisation import collate_summaries, generate_summary_and_chapters
from transcription import transcribe_and_revise_audio


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

def generate_new_campaign(campaign_name, abbreviation, base_directory):
    """Generates a new campaign directory structure."""
    campaign_folder = os.path.join(base_directory, campaign_name)
    audio_files_folder = os.path.join(campaign_folder, f"{abbreviation} Audio Files")
    transcriptions_folder = os.path.join(campaign_folder, f"{abbreviation} Transcriptions")

    os.makedirs(campaign_folder, exist_ok=True)
    os.makedirs(audio_files_folder, exist_ok=True)
    os.makedirs(transcriptions_folder, exist_ok=True)

    return campaign_folder, audio_files_folder, transcriptions_folder

def transcribe_combine(directory):
    """Combine individual revised transcriptions into a single text file."""
    txt_files = [os.path.join(root, file)
                for root, _, files in os.walk(directory)
                for file in files if file.endswith("_revised.txt")]

    # Sort by track number in descending order (highest first)
    def get_sort_key(file_path):
        match = re.search(r'#(\d+) - (\d{4}_\d{2}_\d{2})', file_path)  # Capture date as well
        if match:
            track_number = int(match.group(1))
            date_str = match.group(2)
            date_int = int(date_str.replace("_", ""))
            return track_number, date_int  # Sort by track number descending, then date ascending
        else:
            return 0, 0  # Handle cases without a track number

    txt_files.sort(key=get_sort_key)
    txt_files.reverse()  # Reverse the list after sorting!

    campaign = os.path.basename(directory)
    output_file_name = os.path.join(directory, f"{campaign} - Transcriptions.txt")

    with open(output_file_name, 'w', encoding='utf-8') as output_file:
        output_file.write(f"# {campaign}\n\n")
        output_file.write(f"Sessions: {len(txt_files)}\n\n")

        # Write track summary
        for txt_file in txt_files:
            with open(txt_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()  # Read the first line
                match = re.search(r'^(.*) - #(\d+) - (\d{4}_\d{2}_\d{2})$', first_line)
                if match:
                    title, track_number, date_str = match.groups()
                    date_str = date_str.replace("_", "/")  # Format date as DD/MM/YYYY
                    output_file.write(f"{date_str} - #{track_number} - {title}\n")

        output_file.write("\n")  # Add extra newline before session content

        # Write session content
        for txt_file in txt_files:
            with open(txt_file, 'r', encoding='utf-8') as f:
                # Read and write the entire content, including the modified first line
                output_file.write(f.read())
                output_file.write('\n')  # Add a separator between sessions

    return output_file_name

def extract_track_number(file_path):
    """Extracts the track number from a file path using regex."""
    match = re.search(r'- #(\d+) -', file_path)
    return match.group(1) if match else "0"  # Default to 0 if not found

def retranscribe_single_file(campaign_folder):
    """Retranscribe a single audio file and update related files."""
    try:
        # 1. Construct the path to the "Audio Files" subdirectory
        audio_files_folder = find_audio_files_folder(campaign_folder)

        # 2. Get the list of _norm.m4a files in the "Audio Files" subdirectory
        audio_files = [
            f for f in os.listdir(audio_files_folder)
            if f.endswith("_norm.m4a")
        ]

        if not audio_files:
            print(f"No normalised audio files (_norm.m4a) found in {audio_files_folder}")
            return

        print("\nNormalised Audio Files:")
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
        txt_location = transcribe_combine(campaign_folder) # This should still point to the main campaign folder

        print("Generating updated summary and chapters...")
        generate_summary_and_chapters(revised_tsv_file)
        collate_summaries(campaign_folder)  # This should also point to the main campaign folder

        print(f"Retranscription complete. Combined transcription saved to: {txt_location}")

    except Exception as e:
        print(f"An error occurred: {e}")

def resummarise_single_file(campaign_folder):
    """Resummarise a single revised transcription file."""
    transcriptions_folder = find_transcriptions_folder(campaign_folder)
    
    if not transcriptions_folder:
        print(f"No folder containing 'Transcriptions' found in {campaign_folder}")
        return
    
    # Get list of ALL revised transcription files (or create if not existing)
    revised_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith("_revised.txt") and "_norm" in f
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

    print(f"Generating summary and chapters for: {selected_file}")
    generate_summary_and_chapters(selected_file)
    collate_summaries(campaign_folder)
    print(f"Resummarisation complete for file: {selected_file}")
