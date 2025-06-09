import os
import re
import subprocess
import json
from datetime import datetime

try:
    from tkinter import Tk, filedialog
except ImportError:
    Tk, filedialog = None, None
    print("Warning: tkinter not found. File dialog functionality will be disabled.")

# Import functions from modules
from .audio_processing import convert_to_m4a, search_audio_files, bulk_normalize_audio, apply_metadata
from .transcription import transcribe_and_revise_audio
from .summarisation import generate_summary_and_chapters, collate_summaries, bulk_summarize_transcripts
from .file_management import retranscribe_single_file, resummarise_single_file, generate_new_campaign, transcribe_combine, find_transcriptions_folder, find_audio_files_folder
from .user_interaction import choose_from_list, get_yes_no_input, get_user_input
from .utils import get_working_directory, config
from . import database_management as db


def display_menu(menu_title, menu_options):
    """Displays a menu, gets user input, and returns the selected option tuple."""
    while True:
        padding_char = "*"
        title_padding_len = (80 - len(menu_title) - 2) // 2
        title_padding_str = ' ' * title_padding_len
        
        print("\n" + padding_char * 80)
        print(f"{padding_char}{title_padding_str}{menu_title}{title_padding_str}{padding_char if (len(menu_title) % 2 == 0) else ' '+padding_char}")
        print(padding_char * 80)

        for _, label, *_ in menu_options:
            print(label)
        print("x. Back / Exit")
        print(padding_char * 80)

        choice = input("Enter your choice: ").lower().strip()
        if choice == "x":
            return None
        
        # Match by leading number or letter
        matched_options = [opt for opt in menu_options if opt[1].lower().startswith(choice)]
        if len(matched_options) == 1:
            return matched_options[0]
        else:
            print("Invalid or ambiguous choice. Please try again.")

def select_campaign():
    """Handles campaign selection from the database."""
    base_dir = get_working_directory()
    campaign_folders = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and not d.startswith(('.', 'x '))]
    
    if not campaign_folders:
        print("No campaign folders found in the working directory.")
        return None

    campaign_menu_options = [(os.path.join(base_dir, p), f"{i + 1}. {p}") for i, p in enumerate(campaign_folders)]
    
    selected_option = display_menu("Select Campaign", campaign_menu_options)
    return selected_option[0] if selected_option else None


def process_full_pipeline_wrapper():
    """Wrapper for the full file processing pipeline."""
    # Step 1: Select or create a campaign
    campaign_path = select_campaign()
    if not campaign_path:
        if get_yes_no_input("No campaign selected. Create a new one?"):
            name = input("Enter new campaign name: ")
            abbrev = input(f"Enter abbreviation for '{name}': ")
            if name and abbrev:
                campaign_path, _, _ = generate_new_campaign(name, abbrev, get_working_directory())
            if not campaign_path:
                print("Campaign creation failed. Aborting.")
                return
        else:
            return

    # Step 2: Select an audio file to process
    file_path = select_file(campaign_path) # Select file, which can come from outside campaign
    if not file_path:
        return

    # Step 3: Ensure file is in the campaign's audio folder
    audio_folder = find_audio_files_folder(campaign_path)
    if os.path.dirname(file_path) != audio_folder:
        file_path = move_file_to_campaign(file_path, campaign_path)
        if not file_path:
            print("File move failed. Aborting pipeline.")
            return

    # Step 4: Get title and run pipeline
    title_from_filename = os.path.splitext(os.path.basename(file_path))[0]
    title_from_filename = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", title_from_filename).replace("_", " ").strip()
    title = input(f"Enter the title for the episode (default: '{title_from_filename}'): ") or title_from_filename
    
    process_full_pipeline(campaign_path, file_path, title)

def process_full_pipeline(campaign_path, file_path, title):
    """Processes a single file through the full pipeline, updating the database."""
    print(f"\n--- Starting Full Pipeline for: {os.path.basename(file_path)} ---")
    
    print("\nStep 1: Converting to M4A and Normalizing...")
    episode_id = convert_to_m4a(campaign_path, file_path, title)
    if not episode_id:
        print("Normalization/conversion failed. Aborting pipeline.")
        return
    episode = db.get_episode_by_id(campaign_path, episode_id)
    print(f"Normalized audio and created Episode #{episode['episode_number']}.")

    print("\nStep 2: Transcribing Audio...")
    revised_txt_file_path = transcribe_and_revise_audio(campaign_path, episode_id)
    if not revised_txt_file_path:
        print("Transcription failed. Aborting pipeline.")
        return
    print(f"Revised transcription created: {os.path.basename(revised_txt_file_path)}")

    print("\nStep 3: Generating Summary and Chapters...")
    generate_summary_and_chapters(campaign_path, episode_id)

    print("\nStep 4: Updating Combined Campaign Files...")
    transcribe_combine(campaign_path)
    collate_summaries(campaign_path)
    
    print(f"\n--- Full Pipeline Completed for: {episode['episode_title']} ---")

def select_file(campaign_path=None):
    """Handles file selection, preferring recent un-tracked files or file explorer."""
    recent_files = search_audio_files() # Returns absolute paths of untracked files
    options = []
    if recent_files:
        print("\nRecent Untracked Audio Files:")
        for i, file_abs_path in enumerate(recent_files):
            display_path = os.path.relpath(file_abs_path, get_working_directory())
            options.append((file_abs_path, f"{i+1}. {display_path}"))
    
    if filedialog:
        options.append(("f_explorer_sentinel", "f. Open File Explorer"))
    
    if not options:
        print("No recent untracked files found and file explorer is not available.")
        return None

    selected = display_menu("Select a File to Process", options)
    if not selected: return None

    if selected[0] == "f_explorer_sentinel":
        return handle_file_explorer()
    else:
        return selected[0]

def move_file_to_campaign(file_path, campaign_folder_path):
    """Moves a file to a campaign's 'Audio Files' folder."""
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print("Could not find or create audio folder. Cannot move file.")
        return None

    new_file_path_abs = os.path.join(audio_files_folder, os.path.basename(file_path))
    if os.path.exists(new_file_path_abs):
        if not get_yes_no_input(f"File '{os.path.basename(file_path)}' already exists in destination. Overwrite?"):
            return None
    try:
        os.rename(file_path, new_file_path_abs)
        print(f"File moved to {new_file_path_abs}")
        return new_file_path_abs
    except Exception as e:
        print(f"Error moving file: {e}")
        return None

def handle_file_explorer():
    if not filedialog: return None
    root = Tk(); root.withdraw()
    file_path = filedialog.askopenfilename(
        initialdir=get_working_directory(),
        title="Select Audio File",
        filetypes=(("Audio Files", "*.wav *.m4a *.flac *.mp3"), ("all files", "*.*"))
    )
    root.destroy()
    return file_path

def bulk_operations_wrapper():
    """Handles the 'Bulk Operations' menu option."""
    campaign_path = select_campaign()
    if not campaign_path: return

    bulk_op_menu_options = [
        (bulk_normalize_audio, "1. Normalize All New Audio"),
        (bulk_transcribe_audio, "2. Transcribe All Un-transcribed Episodes"),
        (bulk_summarize_transcripts, "3. Summarize All Un-summarized Transcripts"),
        (lambda p: (transcribe_combine(p), collate_summaries(p)), "4. Update All Combined Campaign Files"),
    ]

    selected_option = display_menu(f"Bulk Operations for {os.path.basename(campaign_path)}", bulk_op_menu_options)
    if not selected_option: return
    
    operation_func = selected_option[0]
    print(f"\nStarting bulk operation: {selected_option[1]}...")
    operation_func(campaign_path)
    print("Bulk operation finished.")

def campaign_tools_wrapper():
    """Menu for campaign-specific tools like re-transcribe, re-summarise."""
    campaign_path = select_campaign()
    if not campaign_path: return

    tools_menu_options = [
        (retranscribe_single_file, "1. Re-Transcribe a Single Episode"),
        (resummarise_single_file, "2. Re-Summarise a Single Episode"),
        (open_campaign_files, "3. Open Campaign Files"),
    ]
    
    while True:
        selected_option = display_menu(f"Tools for {os.path.basename(campaign_path)}", tools_menu_options)
        if selected_option is None: break
        
        # Pass campaign_path to the selected function
        selected_option[0](campaign_path)

def open_campaign_files(campaign_path):
    """Opens campaign-specific files by reading from the DB."""
    episodes = db.get_episodes_for_campaign(campaign_path)
    if not episodes:
        print("No episodes found in this campaign's database.")
        return

    file_choices = []
    for ep in episodes:
        if ep['normalized_audio_file']: file_choices.append((os.path.join(campaign_path, ep['normalized_audio_file']), f"Episode {ep['episode_number']} - Audio"))
        if ep['transcription_file']: file_choices.append((os.path.join(campaign_path, ep['transcription_file']), f"Episode {ep['episode_number']} - Transcript"))
        if ep['summary_file']: file_choices.append((os.path.join(campaign_path, ep['summary_file']), f"Episode {ep['episode_number']} - Summary"))
        if ep['chapters_file']: file_choices.append((os.path.join(campaign_path, ep['chapters_file']), f"Episode {ep['episode_number']} - Chapters"))
    
    combined_trans_path = os.path.join(campaign_path, f"{os.path.basename(campaign_path)} - Transcriptions Combined.txt")
    if os.path.exists(combined_trans_path):
        file_choices.append((combined_trans_path, "Combined Campaign Transcript"))

    collated_summary_path = os.path.join(campaign_path, f"{os.path.basename(campaign_path)} - Collated Summaries.txt")
    if os.path.exists(collated_summary_path):
        file_choices.append((collated_summary_path, "Collated Campaign Summaries"))

    selected_file = display_menu(f"Files for {os.path.basename(campaign_path)}", file_choices)
    if selected_file:
        open_file(selected_file[0])

def open_file(file_path):
    """Opens a file using the default system application."""
    abs_file_path = os.path.abspath(file_path)
    if not os.path.exists(abs_file_path):
        print(