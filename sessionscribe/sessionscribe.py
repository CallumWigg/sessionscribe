import os
import re
import sys
import subprocess
from datetime import datetime
from tqdm import tqdm

try:
    from tkinter import Tk, filedialog
except ImportError:
    Tk, filedialog = None, None
    print("Warning: tkinter not found. File dialog functionality will be disabled.")

from .audio_processing import convert_to_m4a, search_audio_files, bulk_normalize_audio
from .transcription import transcribe_and_revise_audio
from .summarisation import generate_summary_and_chapters, collate_summaries, bulk_summarize_transcripts
from .file_management import (
    retranscribe_single_file, resummarise_single_file, generate_new_campaign, 
    transcribe_combine, find_audio_files_folder, dictionary_update_wrapper
)
from .user_interaction import choose_from_list, get_yes_no_input
from .utils import get_working_directory, config
from . import database_management as db
from . import data_migration


def display_menu(menu_title, menu_options):
    """
    Displays a consistently formatted menu and returns the user's choice.
    menu_options is a list of tuples: (key, description).
    """
    print("\n" + "="*80)
    print(f"| {menu_title:^76} |")
    print("="*80)
    
    for key, description in menu_options:
        print(f"  {key}. {description}")
    print("  x. Back / Exit")
    print("-"*80)
    
    choice = input("Enter your choice: ").lower().strip()
    return choice

def select_campaign():
    """Handles campaign selection."""
    base_dir = get_working_directory()
    campaign_folders = sorted([
        d for d in os.listdir(base_dir) 
        if os.path.isdir(os.path.join(base_dir, d)) and not d.startswith(('.', '_', 'x '))]
    )
    
    if not campaign_folders:
        print("No campaign folders found in the working directory.")
        return None

    chosen_campaign = choose_from_list(campaign_folders, "Select Campaign")
    if chosen_campaign:
        return os.path.join(base_dir, chosen_campaign)
    return None

def select_episode(campaign_path, header_text="Select an Episode", return_index=False):
    """
    Displays a list of episodes and prompts the user to select one.
    Returns the selected episode object, and optionally its index in the list.
    """
    episodes = db.get_episodes_for_campaign(campaign_path)
    if not episodes:
        print("No episodes found in this campaign's database.")
        return (None, -1) if return_index else None

    episode_choices = [f"#{ep['episode_number']} (S{ep['season_number'] or '?'}) - {ep['episode_title']}" for ep in episodes]
    
    chosen_str = choose_from_list(episode_choices, header_text)
    if not chosen_str:
        return (None, -1) if return_index else None
        
    choice_index = episode_choices.index(chosen_str)
    selected_episode = episodes[choice_index]
    
    return (selected_episode, choice_index) if return_index else selected_episode


def open_file(file_path):
    """Opens a file using the default system application."""
    abs_file_path = os.path.abspath(file_path)
    if not os.path.exists(abs_file_path):
        print(f"Error: File not found: {abs_file_path}")
        return
    try:
        if sys.platform == "win32":
            os.startfile(abs_file_path)
        elif sys.platform == "darwin": # macOS
            subprocess.call(('open', abs_file_path))
        else: # linux
            subprocess.call(('xdg-open', abs_file_path))
    except Exception as e:
        print(f"Error opening file '{abs_file_path}': {e}")


def move_file_to_campaign(file_path, campaign_path):
    """Moves a file to a campaign's 'Audio Files' folder."""
    audio_files_folder = find_audio_files_folder(campaign_path)
    if not audio_files_folder: return None

    new_file_path = os.path.join(audio_files_folder, os.path.basename(file_path))
    if os.path.abspath(file_path) == os.path.abspath(new_file_path):
        print("File is already in the target campaign's audio folder.")
        return file_path

    if os.path.exists(new_file_path):
        if not get_yes_no_input(f"File '{os.path.basename(file_path)}' already exists in destination. Overwrite?"):
            return None
        os.remove(new_file_path)
        
    try:
        os.rename(file_path, new_file_path)
        print(f"File moved to {os.path.relpath(new_file_path, get_working_directory())}")
        return new_file_path
    except Exception as e:
        print(f"Error moving file: {e}")
        return None

def process_full_pipeline(campaign_path, file_path, title):
    """Processes a single file through the full pipeline."""
    print(f"\n--- Starting Full Pipeline for: {os.path.basename(file_path)} ---")
    
    print("\n[Step 1/4] Converting to M4A and Normalizing...")
    episode_id = convert_to_m4a(campaign_path, file_path, title)
    if not episode_id:
        print("Normalization/conversion failed. Aborting pipeline.")
        return

    # Refetch episode data to ensure all fields are current
    episode = db.get_episode_by_id(campaign_path, episode_id)
    print(f"Normalized audio and created Episode #{episode['episode_number']}.")

    print("\n[Step 2/4] Transcribing Audio...")
    revised_txt_file_path = transcribe_and_revise_audio(campaign_path, episode_id)
    if not revised_txt_file_path:
        print("Transcription failed. Aborting pipeline.")
        return
    print(f"Revised transcription created.")

    print("\n[Step 3/4] Generating Summary and Chapters...")
    generate_summary_and_chapters(campaign_path, episode_id)

    print("\n[Step 4/4] Updating Combined Campaign Files...")
    transcribe_combine(campaign_path)
    collate_summaries(campaign_path)
    
    print(f"\n--- Full Pipeline Completed for: {episode['episode_title']} ---")

def process_file_from_command_line(file_path):
    """Handles processing a file passed via command line or drag-and-drop."""
    print(f"File detected: {os.path.basename(file_path)}")
    if not os.path.exists(file_path):
        print("Error: File not found.")
        return

    campaign_path = select_campaign()
    if not campaign_path:
        if get_yes_no_input("No campaign selected. Create a new one?"):
            name = input("Enter new campaign name: ")
            abbrev = input(f"Enter abbreviation for '{name}': ")
            if name and abbrev:
                campaign_path = generate_new_campaign(name, abbrev, get_working_directory())
            if not campaign_path:
                print("Campaign creation failed. Aborting.")
                return
        else:
            return
    
    final_file_path = move_file_to_campaign(file_path, campaign_path)
    if not final_file_path:
        print("File move failed. Aborting.")
        return

    title_from_filename = re.sub(r"^\d{4}[_-]\d{2}[_-]\d{2}_?", "", os.path.splitext(os.path.basename(final_file_path))[0]).replace("_", " ").strip()
    title = input(f"Enter episode title (default: '{title_from_filename}'): ") or title_from_filename
    
    process_full_pipeline(campaign_path, final_file_path, title)
    input("\nProcessing complete. Press Enter to exit.")

#==============================================================================
# MENU WRAPPER FUNCTIONS
#==============================================================================

def process_new_file_wrapper():
    """Wrapper for the full file processing pipeline."""
    campaign_path = select_campaign()
    if not campaign_path: return

    recent_files = search_audio_files()
    file_to_process = None

    if recent_files:
        options = [os.path.basename(fp) for fp in recent_files]
        if filedialog:
            options.append("Browse for file...")
        
        chosen_option = choose_from_list(options, "Select a recent untracked file, or browse")
        if not chosen_option: return

        if chosen_option == "Browse for file...":
            file_to_process = filedialog.askopenfilename(title="Select audio file to process")
        else:
            file_to_process = recent_files[options.index(chosen_option)]
    elif filedialog:
        file_to_process = filedialog.askopenfilename(title="Select audio file to process")
    else:
        print("No recent untracked files found and file dialog is unavailable.")
        return

    if not file_to_process or not os.path.exists(file_to_process):
        print("No file selected or file does not exist.")
        return

    final_file_path = move_file_to_campaign(file_to_process, campaign_path)
    if not final_file_path: return

    title_from_filename = re.sub(r"^\d{4}[_-]\d{2}[_-]\d{2}_?", "", os.path.splitext(os.path.basename(final_file_path))[0]).replace("_", " ").strip()
    title = input(f"Enter episode title (default: '{title_from_filename}'): ") or title_from_filename
    
    process_full_pipeline(campaign_path, final_file_path, title)

def chained_processing_wrapper():
    """
    Wrapper for processing a chain of episodes from a selected start point.
    This is the re-introduced missing feature.
    """
    campaign_path = select_campaign()
    if not campaign_path: return

    episodes = db.get_episodes_for_campaign(campaign_path)
    if not episodes:
        print("No episodes in this campaign to process.")
        return

    selected_episode, start_index = select_episode(campaign_path, "Select the STARTING episode for the chain", return_index=True)
    if not selected_episode: return
    
    episodes_to_process = episodes[start_index:]
    if get_yes_no_input(f"Process episode #{selected_episode['episode_number']} and all {len(episodes_to_process)-1} subsequent episodes?", "y"):
        print(f"\nStarting chained processing for {len(episodes_to_process)} episodes...")

        for episode in tqdm(episodes_to_process, desc="Chained Processing Progress"):
            print(f"\n>>> Processing Episode #{episode['episode_number']}: {episode['episode_title']} <<<")
            
            # We need to refresh the episode's status inside the loop
            current_status = db.get_episode_by_id(campaign_path, episode['episode_id'])
            
            if not current_status['normalized']:
                print("Episode is not normalized. Cannot continue chain. Please run normalization first.")
                continue # or break, depending on desired behavior
            
            if not current_status['transcribed']:
                print("  - Transcribing audio...")
                transcribe_and_revise_audio(campaign_path, episode['episode_id'])
            
            # Refresh status again after transcription
            current_status = db.get_episode_by_id(campaign_path, episode['episode_id'])
            if current_status['text_processed'] and not current_status['summarized']:
                print("  - Generating summary and chapters...")
                generate_summary_and_chapters(campaign_path, episode['episode_id'])
        
        print("\nChained processing complete. Updating combined campaign files...")
        transcribe_combine(campaign_path)
        collate_summaries(campaign_path)


def bulk_operations_wrapper():
    """Handles the 'Bulk Operations' menu option."""
    campaign_path = select_campaign()
    if not campaign_path: return

    menu_map = {
        "1": ("Normalize All New Audio", bulk_normalize_audio),
        "2": ("Transcribe All Un-transcribed Episodes", bulk_transcribe_audio),
        "3": ("Summarize All Un-summarized Transcripts", bulk_summarize_transcripts),
        "4": ("Update All Combined Campaign Files", lambda p: (transcribe_combine(p), collate_summaries(p))),
    }
    menu_options = [(k, v[0]) for k, v in menu_map.items()]

    choice = display_menu(f"Bulk Operations for {os.path.basename(campaign_path)}", menu_options)
    if choice in menu_map:
        operation_name, operation_func = menu_map[choice]
        print(f"\nStarting bulk operation: {operation_name}...")
        operation_func(campaign_path)
        print("Bulk operation finished.")
    elif choice is not None and choice != 'x':
        print("Invalid choice.")

def episode_management_wrapper():
    """Menu for editing individual episode data."""
    campaign_path = select_campaign()
    if not campaign_path: return

    while True:
        selected_episode = select_episode(campaign_path, "Select Episode to Manage")
        if not selected_episode: break

        current_episode = db.get_episode_by_id(campaign_path, selected_episode['episode_id'])
        print(f"\n--- Managing Episode #{current_episode['episode_number']}: {current_episode['episode_title']} ---")
        
        menu_map = {
            "1": ("Edit Title", "episode_title"),
            "2": ("Edit Season Number", "season_number"),
            "3": ("Edit Recorded Date (YYYY-MM-DD)", "recorded_date"),
            "4": ("Re-transcribe this episode", "retranscribe"),
            "5": ("Re-summarise this episode", "resummarise"),
            "c": ("Clear All Processing Flags", "clear_status"),
        }
        menu_options = [(k, v[0]) for k, v in menu_map.items()]
        
        choice = display_menu(f"Edit options for '{current_episode['episode_title']}'", menu_options)
        if choice == 'x': break
        if choice not in menu_map: 
            print("Invalid choice.")
            continue
            
        action = menu_map[choice][1]
        episode_id = current_episode['episode_id']
        
        if action == "retranscribe":
            retranscribe_single_file(campaign_path)
            break # Exit to main menu after this complex action
        elif action == "resummarise":
            resummarise_single_file(campaign_path)
            break # Exit to main menu
        elif action == "clear_status":
            if get_yes_no_input("This will reset all processing flags for this episode. Are you sure?", "n"):
                db.clear_processing_status(campaign_path, episode_id)
        else:
            new_value = input(f"Enter new value for {action.replace('_', ' ')}: ")
            if new_value:
                try:
                    if action == 'season_number':
                        new_value = int(new_value)
                    elif action == 'recorded_date':
                        datetime.strptime(new_value, '%Y-%m-%d')
                    db.update_episode_data(campaign_path, episode_id, {action: new_value})
                    print("Update successful.")
                except ValueError:
                    print("Invalid format. Please check your input (e.g., season must be a number, date must be YYYY-MM-DD).")

def database_tools_wrapper():
    """Menu for DB-related tasks like migration and integrity checks."""
    campaign_path = select_campaign()
    if not campaign_path: return

    menu_map = {
        "1": ("Run Data Migration (Scan files to DB)", data_migration.run_migration_for_campaign),
        "2": ("Automated Dictionary Update", dictionary_update_wrapper),
        "3": ("Check Database Integrity (Find broken links)", "integrity"),
        "4": ("Open Database File (Advanced)", lambda p: open_file(os.path.join(p, db.DATABASE_NAME))),
    }
    menu_options = [(k, v[0]) for k, v in menu_map.items()]
    
    choice = display_menu(f"Database Tools for {os.path.basename(campaign_path)}", menu_options)
    
    if choice == "3": # Special handling for integrity check
        print("\nChecking database for broken file links...")
        problems = db.check_database_integrity(campaign_path)
        if not problems:
            print("Integrity check passed. No missing files found.")
        else:
            print(f"Found {len(problems)} issues:")
            for p in problems:
                print(f"  - Ep #{p['episode_id']} ({p['episode_title']}): Missing '{p['field']}' -> {p['path']}")
            
            if get_yes_no_input("\nDo you want to remove these broken links from the database records?", "n"):
                cleared_count = db.clear_invalid_paths(campaign_path, problems)
                print(f"Removed {cleared_count} invalid file links from the database.")
    elif choice in menu_map:
        menu_map[choice][1](campaign_path)

    if choice != 'x':
        input("\nPress Enter to continue...")

#==============================================================================
# MAIN EXECUTION BLOCK
#==============================================================================

def main():
    """Main function for the sessionscribe application."""
    if len(sys.argv) > 1:
        process_file_from_command_line(sys.argv[1])
        return

    working_directory = get_working_directory()
    print("Initializing campaign databases...")
    for campaign_name in os.listdir(working_directory):
        campaign_path = os.path.join(working_directory, campaign_name)
        if os.path.isdir(campaign_path) and not campaign_name.startswith('.'):
            db.init_campaign_db(campaign_path)

    # C-IMPROVEMENT: Main menu is now cleaner and includes Chained Processing
    menu_map = {
        "1": ("Process New Audio File (Full Pipeline)", process_new_file_wrapper),
        "2": ("Chained Processing (From an episode)", chained_processing_wrapper),
        "3": ("Bulk Operations (For a Campaign)", bulk_operations_wrapper),
        "4": ("Episode Management", episode_management_wrapper),
        "5": ("Database & Dictionary Tools", database_tools_wrapper),
        "6": ("Create New Campaign", lambda: generate_new_campaign(input("Enter new campaign name: "), input("Enter abbreviation: "), get_working_directory())),
    }
    menu_options = [(k, v[0]) for k, v in menu_map.items()]

    while True:
        choice = display_menu("sessionscribe - Main Menu", menu_options)
        if choice == 'x':
            print("Exiting...")
            break
        
        if choice in menu_map:
            menu_map[choice][1]()
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()