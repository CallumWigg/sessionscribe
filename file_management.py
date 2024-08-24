import os
import re
from datetime import datetime

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