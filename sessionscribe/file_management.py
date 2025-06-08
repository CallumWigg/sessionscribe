import os
import re

from .summarisation import collate_summaries, generate_summary_and_chapters
from .transcription import transcribe_and_revise_audio

from . import user_interaction # Assuming user_interaction.py is in the same package
from .utils import get_working_directory # Assuming utils.py is in the same package

def find_audio_files_folder(campaign_folder_path):
    """Find a folder within the campaign folder that contains 'Audio Files' in its name.
    campaign_folder_path should be an absolute path.
    Returns absolute path to the audio files folder or None.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None

    audio_folders = [
        os.path.join(campaign_folder_path, folder_name) # Store absolute path
        for folder_name in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, folder_name)) and "Audio Files" in folder_name
    ]
    if not audio_folders:
        return None
    elif len(audio_folders) == 1:
        return audio_folders[0]
    else:
        # Let user choose if multiple are found
        folder_basenames = [os.path.basename(f) for f in audio_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Audio Files' found. Please select one:",
            "Enter the number of the folder:",
            default=folder_basenames[0]
        )
        return os.path.join(campaign_folder_path, chosen_basename) # Construct absolute path

def find_transcriptions_folder(campaign_folder_path):
    """Find a folder within the campaign folder that contains 'Transcriptions' in its name.
    campaign_folder_path should be an absolute path.
    Returns absolute path to the transcriptions folder or None.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None
        
    transcriptions_folders = [
        os.path.join(campaign_folder_path, folder_name) # Store absolute path
        for folder_name in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, folder_name)) and "Transcriptions" in folder_name
    ]
    if not transcriptions_folders:
        return None
    elif len(transcriptions_folders) == 1:
        return transcriptions_folders[0]
    else:
        folder_basenames = [os.path.basename(f) for f in transcriptions_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Transcriptions' found. Please select one:",
            "Enter the number of the folder:",
            default=folder_basenames[0]
        )
        return os.path.join(campaign_folder_path, chosen_basename) # Construct absolute path

def generate_new_campaign(campaign_name, abbreviation, base_directory):
    """Generates a new campaign directory structure.
    Returns absolute paths: (campaign_folder, audio_files_folder, transcriptions_folder)
    """
    campaign_folder_abs = os.path.join(base_directory, campaign_name)
    audio_files_folder_abs = os.path.join(campaign_folder_abs, f"{abbreviation} Audio Files")
    transcriptions_folder_abs = os.path.join(campaign_folder_abs, f"{abbreviation} Transcriptions")

    try:
        os.makedirs(campaign_folder_abs, exist_ok=True)
        os.makedirs(audio_files_folder_abs, exist_ok=True)
        os.makedirs(transcriptions_folder_abs, exist_ok=True)
        print(f"Campaign '{campaign_name}' structure created successfully in '{base_directory}'.")
    except OSError as e:
        print(f"Error creating campaign structure for '{campaign_name}': {e}")
        # Return None or raise exception if creation fails critically
        return None, None, None

    return campaign_folder_abs, audio_files_folder_abs, transcriptions_folder_abs


def get_sort_key_from_content_and_filename(file_path):
    """
    Generates a sort key for transcription files.
    Primary sort: Date from filename (YYYY_MM_DD).
    Secondary sort: Track number from the first line of file content.
    """
    # Date from filename (e.g., "2023_01_15_...")
    filename_date_match = re.match(r'(\d{4}_\d{2}_\d{2})', os.path.basename(file_path))
    date_int = 0
    if filename_date_match:
        date_str_filename = filename_date_match.group(1)
        try:
            date_int = int(date_str_filename.replace("_", "")) # YYYYMMDD as integer
        except ValueError:
            pass # Keep date_int as 0

    # Track number from content (e.g., "... - #123 - DD/MM/YYYY")
    track_number = 0 
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
        # Regex looks for " - #NUMBER - DD/MM/YYYY" at the end of the line.
        match_content = re.search(r' - #(\d+)\s*-\s*\d{2}/\d{2}/\d{4}\s*$', first_line)
        if match_content:
            try:
                track_number = int(match_content.group(1))
            except ValueError:
                pass # Keep track_number as 0
    except IOError:
        pass # Keep track_number as 0 if file can't be read

    return (date_int, track_number) # Sort by date, then track number


def transcribe_combine(campaign_folder_path):
    """Combine individual revised transcriptions into a single text file for the campaign.
    campaign_folder_path is the absolute path to the main campaign folder.
    """
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found for campaign '{os.path.basename(campaign_folder_path)}'. Cannot combine.")
        return None

    txt_files_abs_paths = []
    for root, _, files in os.walk(transcriptions_folder): # Walk only within specific transcriptions_folder
        for file_name in files:
            if file_name.endswith("_revised.txt") and "_norm" in file_name: # Ensure it's a processed file
                txt_files_abs_paths.append(os.path.join(root, file_name))

    if not txt_files_abs_paths:
        print(f"No revised transcription files found in '{transcriptions_folder}'.")
        return None

    # Sort files: by date (from filename, ascending), then track number (from content, ascending)
    txt_files_abs_paths.sort(key=get_sort_key_from_content_and_filename)
    # If you want newest first for the combined document, you might reverse after sorting,
    # or sort descending initially. The current sort is oldest first.
    # For typical combined documents, chronological (oldest first) is common.

    campaign_basename = os.path.basename(campaign_folder_path)
    output_file_name = os.path.join(campaign_folder_path, f"{campaign_basename} - Transcriptions Combined.txt")

    try:
        with open(output_file_name, 'w', encoding='utf-8') as output_file:
            output_file.write(f"# {campaign_basename} - Combined Transcriptions\n\n")
            output_file.write(f"Total Sessions: {len(txt_files_abs_paths)}\n\n")
            output_file.write("--- Session Index ---\n")
            
            session_details_for_index = []
            for txt_file_path in txt_files_abs_paths:
                with open(txt_file_path, 'r', encoding='utf-8') as f_in:
                    first_line = f_in.readline().strip() # e.g., "Title - #Track - DD/MM/YYYY"
                    session_details_for_index.append(first_line) # Store the header line
            
            for detail_line in session_details_for_index:
                 output_file.write(f"- {detail_line}\n")
            output_file.write("\n---\n\n")

            # Write session content
            for i, txt_file_path in enumerate(txt_files_abs_paths):
                with open(txt_file_path, 'r', encoding='utf-8') as f_in:
                    content = f_in.read()
                    # The first line is already part of content, good.
                    output_file.write(content)
                    if i < len(txt_files_abs_paths) - 1: # Add separator if not the last file
                        output_file.write('\n\n---\n\n') # Separator between sessions
        
        print(f"Combined transcription saved to: {output_file_name}")
        return output_file_name
    except IOError as e:
        print(f"Error writing combined transcription file '{output_file_name}': {e}")
        return None


def retranscribe_single_file(campaign_folder_path):
    """Retranscribe a single audio file and update related files."""
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in campaign '{os.path.basename(campaign_folder_path)}'.")
        return

    # List _norm.m4a files as these are the ones usually transcribed
    norm_audio_files = [
        f for f in os.listdir(audio_files_folder)
        if f.endswith("_norm.m4a")
    ]

    if not norm_audio_files:
        print(f"No normalized audio files (_norm.m4a) found in {audio_files_folder}.")
        return

    print("\nNormalized Audio Files available for retranscription:")
    # Present files with numbers for selection
    selected_filename = user_interaction.choose_from_list(norm_audio_files, None, "Enter the number of the file to retranscribe")
    if not selected_filename: # User cancelled
        return

    selected_audio_file_path = os.path.join(audio_files_folder, selected_filename)

    print(f"\nRetranscribing: {selected_filename}...")
    # transcribe_and_revise_audio returns (output_dir, revised_txt_file_path)
    # output_dir is the transcriptions folder for this campaign.
    # revised_txt_file_path is the path to the newly created/updated _revised.txt
    _, revised_txt_file_path = transcribe_and_revise_audio(selected_audio_file_path)

    if not revised_txt_file_path or not os.path.exists(revised_txt_file_path):
        print(f"Retranscription failed for {selected_filename}.")
        return

    print(f"Retranscription successful. Output: {os.path.basename(revised_txt_file_path)}")

    print("\nUpdating combined campaign transcription...")
    transcribe_combine(campaign_folder_path) # Path to main campaign folder

    print("\nGenerating updated summary and chapters for the retranscribed file...")
    generate_summary_and_chapters(revised_txt_file_path)
    
    print("\nCollating all campaign summaries...")
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if transcriptions_folder:
        collate_summaries(transcriptions_folder)
    else:
        print(f"Warning: Transcriptions folder not found for {os.path.basename(campaign_folder_path)}, cannot collate summaries.")

    print(f"\nRetranscription and update process complete for {selected_filename}.")


def resummarise_single_file(campaign_folder_path):
    """Resummarise a single revised transcription file."""
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found in campaign '{os.path.basename(campaign_folder_path)}'.")
        return
    
    revised_txt_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith("_norm_revised.txt")
    ]

    if not revised_txt_files:
        print(f"No revised transcription files (_norm_revised.txt) found in {transcriptions_folder}.")
        return

    print("\nRevised Transcription Files available for re-summarisation:")
    selected_filename = user_interaction.choose_from_list(revised_txt_files, None, "Enter the number of the file to re-summarise")
    if not selected_filename: # User cancelled
        return

    selected_txt_file_path = os.path.join(transcriptions_folder, selected_filename)

    print(f"\nGenerating summary and chapters for: {selected_filename}...")
    generate_summary_and_chapters(selected_txt_file_path)
    
    print("\nCollating all campaign summaries...")
    collate_summaries(transcriptions_folder) # Pass the transcriptions_folder path

    print(f"\nRe-summarisation process complete for {selected_filename}.")