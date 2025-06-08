import os
import subprocess
from datetime import datetime

try:
    from tkinter import Tk, filedialog
except ImportError:
    Tk = None  # Tkinter is optional
    filedialog = None
    print("Warning: tkinter not found. File dialog functionality will be disabled.")


# Import functions from modules
from .audio_processing import convert_to_m4a, search_audio_files, bulk_normalize_audio, apply_metadata
from .transcription import transcribe_and_revise_audio, bulk_transcribe_audio
from .text_processing import apply_corrections_and_formatting, process_text as text_processing_process_text # Renamed to avoid conflict
from .summarisation import generate_summary_and_chapters, collate_summaries, bulk_summarize_transcripts
from .file_management import retranscribe_single_file, resummarise_single_file, generate_new_campaign, transcribe_combine, find_transcriptions_folder, find_audio_files_folder
from .user_interaction import choose_from_list, select_campaign_folder, get_yes_no_input
from .utils import get_working_directory

def display_menu(menu_title, menu_options):
    """Displays a menu, gets user input, and returns the selected option tuple."""
    while True:
        padding_char = "*"
        title_padding_len = (80 - len(menu_title) - 2) // 2 # -2 for the side asterisks
        title_padding_str = ' ' * title_padding_len
        
        print(padding_char * 80)
        # Ensure even padding if length is odd
        if (80 - len(menu_title) - 2) % 2 != 0:
            print(f"{padding_char}{title_padding_str}{menu_title}{title_padding_str} {padding_char}")
        else:
            print(f"{padding_char}{title_padding_str}{menu_title}{title_padding_str}{padding_char}")
        print(padding_char * 80)

        for _, label, *_ in menu_options:
            print(label)
        print(padding_char * 80)
        choice = input("Enter your choice: ").lower()
        if choice == "x":
            return None  # Indicates "back" or "exit"
        
        matched_options = [opt for opt in menu_options if opt[1].lower().startswith(choice)]
        if len(matched_options) == 1:
            return matched_options[0]
        elif len(matched_options) > 1:
            print("Ambiguous choice. Please be more specific.")
        else:
            print("Invalid choice. Please try again.")

def select_campaign():
    """Handles campaign selection. Returns campaign path string, or result of file explorer, or None."""
    base_dir = get_working_directory()
    campaigns = [
        os.path.join(base_dir, f) for f in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, f)) and not f.startswith(("x ", ".", "_", " ", "-"))
    ]
    if not campaigns:
        print("No campaign folders found in the working directory.")
        # Offer to create one or go to file explorer
        if get_yes_no_input("No campaigns found. Would you like to try selecting a file via File Explorer?"):
            return handle_file_explorer()
        return None

    # Use basename for display, but store full path in lambda
    campaign_menu_options = [
        (lambda path=p: path, f"{i + 1}. {os.path.basename(p)}") for i, p in enumerate(campaigns)
    ]
    if filedialog: # Only add if tkinter is available
        campaign_menu_options.append((lambda: "f_explorer_sentinel", "f. Open File Explorer"))

    selected_option = display_menu("Select Campaign", campaign_menu_options)

    if selected_option is None:  # User chose 'x'
        return None

    callback_result = selected_option[0]() # Execute the lambda

    if callback_result == "f_explorer_sentinel":
        return handle_file_explorer()
    else:
        return callback_result # This is the campaign_path string

def open_general_files():
    """Opens general files (dictionary, config, corrections list)."""
    while True:
        menu_options = [
            (lambda: open_file(os.path.join(get_working_directory(), "wack_dictionary.txt")), "1. Wack Dictionary"),
            (lambda: open_file(os.path.join(get_working_directory(), "config.json")), "2. Config"),
            (lambda: open_file(os.path.join(get_working_directory(), "corrections.txt")), "3. Corrections List"),
        ]
        selected_option = display_menu("General Files", menu_options)

        if selected_option is None: # 'x' to go back
            break
        selected_option[0]() # Execute the open_file lambda

def handle_file_explorer():
    """Handles file selection using the file explorer and campaign-less file logic."""
    if not filedialog:
        print("File Explorer functionality is not available because tkinter is missing.")
        return None
        
    root = Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        initialdir=get_working_directory(),
        title="Select Audio File",
        filetypes=(("Audio Files", "*.wav *.m4a *.flac *.mp3"), ("all files", "*.*"))
    )
    root.destroy()
    if not file_path:
        print("No file selected.")
        return None

    if not is_file_in_campaign(file_path):
        print(f"Selected file: {file_path}")
        choice = choose_from_list(
            ["Move File to Existing Campaign Folder", "Create New Campaign and Move File", "Process File in Current Location (Creates Subfolder)", "Cancel"],
            "File Not in a Recognized Campaign Folder - What to Do?",
            "Enter your choice: ",
        )
        if choice == "1":
            campaign_folder_path = select_campaign()
            if campaign_folder_path and campaign_folder_path != "f_explorer_sentinel": # Ensure it's a path
                moved_path = move_file_to_campaign(file_path, campaign_folder_path)
                return moved_path if moved_path != file_path else None # Return new path or None if failed/cancelled
            else:
                return None
        elif choice == "2":
            new_campaign_name = input("Enter name for the new campaign: ")
            new_campaign_abbrev = input(f"Enter abbreviation for '{new_campaign_name}': ")
            campaign_folder_path, _, _ = generate_new_campaign(new_campaign_name, new_campaign_abbrev, get_working_directory())
            moved_path = move_file_to_campaign(file_path, campaign_folder_path)
            return moved_path if moved_path != file_path else None
        elif choice == "3":
            parent_dir_of_file = os.path.dirname(file_path)
            new_folder_name = input(f"Enter a name for a new subfolder within '{parent_dir_of_file}' to process this file: ")
            if not new_folder_name.strip():
                print("Folder name cannot be empty. Cancelling.")
                return None
            # Create a campaign-like structure: NewFolder/Audio Files
            # The "campaign" becomes the new_folder_name itself relative to the file's original dir
            # This is a bit of a hack to make it fit the existing structure somewhat
            temp_campaign_path = os.path.join(parent_dir_of_file, new_folder_name)
            os.makedirs(temp_campaign_path, exist_ok=True)
            
            # Create "Audio Files" subfolder within this temp campaign
            audio_files_subfolder = os.path.join(temp_campaign_path, f"{new_folder_name} Audio Files")
            os.makedirs(audio_files_subfolder, exist_ok=True)

            # Move the file into this new "Audio Files" subfolder
            base_name = os.path.basename(file_path)
            new_file_location = os.path.join(audio_files_subfolder, base_name)
            try:
                os.rename(file_path, new_file_location)
                print(f"File moved to {new_file_location}")
                # Now, this new_file_location can be processed.
                # The 'campaign_folder' for processing purposes would be temp_campaign_path
                # This function is expected to return a file_path to process.
                return new_file_location 
            except Exception as e:
                print(f"Error moving file: {e}")
                return None
        else: # Cancel
            return None
    return file_path

def is_file_in_campaign(file_path):
    """Checks if a file is located within a recognized campaign folder structure."""
    working_dir = get_working_directory()
    try:
        relative_path_to_file = os.path.relpath(file_path, working_dir)
    except ValueError:
        return False # File is not within the working directory

    parts = relative_path_to_file.split(os.sep)
    # A file is in a campaign if:
    # working_dir / campaign_name / (campaign_name Audio Files) / audio_file.m4a
    # So, parts should be like: [campaign_name, (campaign_name Audio Files), audio_file.m4a]
    # Minimum length of parts is 3 for a file inside an "Audio Files" folder of a campaign
    if len(parts) >= 3:
        campaign_name_part = parts[0]
        # Check if campaign_name_part is a directory and is a direct child of working_dir
        if os.path.isdir(os.path.join(working_dir, campaign_name_part)):
             # Check if the second part is an "Audio Files" or "Transcriptions" like folder
            if "Audio Files" in parts[1] or "Transcriptions" in parts[1]:
                return True
    # Or, if it's directly in a campaign folder (e.g. summary files)
    # working_dir / campaign_name / summary.txt
    if len(parts) == 2:
        campaign_name_part = parts[0]
        if os.path.isdir(os.path.join(working_dir, campaign_name_part)):
            return True # File is directly in a campaign folder
            
    return False

def select_file(campaign_folder_path=None):
    """Handles file selection (recent files or file explorer if no campaign_folder_path).
    If campaign_folder_path is provided, lists audio files from its 'Audio Files' subdir.
    Returns an absolute file path or None.
    """
    if campaign_folder_path:
        audio_files_folder = find_audio_files_folder(campaign_folder_path)
        if not audio_files_folder:
            print(f"No 'Audio Files' folder found in {campaign_folder_path}")
            return None

        audio_files = [
            f for f in os.listdir(audio_files_folder)
            if f.endswith((".wav", ".m4a", ".flac", ".mp3"))
        ]

        if not audio_files:
            print(f"No audio files found in {audio_files_folder}")
            return None

        print("\nAvailable Audio Files:")
        for i, file in enumerate(audio_files):
            print(f"{i+1}. {file}")

        while True:
            try:
                choice = input("\nEnter the number of the file you want to process (or 'x' to cancel): ").lower()
                if choice == 'x':
                    return None
                file_choice_idx = int(choice) - 1
                if 0 <= file_choice_idx < len(audio_files):
                    selected_file = os.path.join(audio_files_folder, audio_files[file_choice_idx])
                    return selected_file
                else:
                    print("Invalid choice. Please enter a number from the list.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    else: # No campaign folder, show recent files or explorer
        recent_files = search_audio_files() # Returns absolute paths
        print("\nRecent Audio Files (not yet normalized):")
        if recent_files:
            for i, file_abs_path in enumerate(recent_files):
                # Show relative path for brevity if it's within working dir
                try:
                    display_path = os.path.relpath(file_abs_path, get_working_directory())
                except ValueError:
                    display_path = file_abs_path # If not in working_dir, show full path
                print(f"{i+1}. {display_path}")
            if filedialog:
                print("\nf. Open File Explorer")
        else:
            print("No recent audio files found.")
            if filedialog:
                print("\nf. Open File Explorer to select a file.")

        while True:
            choice = input("\nEnter the number of the file or 'f' to open File Explorer (or 'x' to cancel): ").lower()
            if choice == "x":
                return None
            elif choice == "f" and filedialog:
                return handle_file_explorer()
            elif choice.isdigit():
                try:
                    file_index = int(choice) - 1
                    if 0 <= file_index < len(recent_files):
                        return recent_files[file_index] # This is an absolute path
                    else:
                        print("Invalid file number. Please try again.")
                except (ValueError, IndexError):
                    print("Invalid input. Please try again.")
            else:
                print("Invalid choice. Please try again.")

def move_file_to_campaign(file_path, campaign_folder_path):
    """Moves a file to a campaign's 'Audio Files' folder and renames it if desired by user.
    Returns the new file path, or original file_path if move failed/cancelled.
    """
    audio_files_folder = find_audio_files_folder(campaign_folder_path) # campaign_folder_path is absolute
    if not audio_files_folder:
        # Attempt to create it
        campaign_abbrev = os.path.basename(campaign_folder_path) # Or prompt user for abbrev
        audio_files_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Audio Files")
        try:
            os.makedirs(audio_files_folder, exist_ok=True)
            print(f"Created 'Audio Files' folder: {audio_files_folder}")
        except OSError as e:
            print(f"Error creating 'Audio Files' folder in {campaign_folder_path}: {e}. Cannot move file.")
            return file_path


    original_file_name = os.path.basename(file_path)
    original_file_ext = os.path.splitext(original_file_name)[1]

    # Try to get date from filename (e.g., YYYY_MM_DD_...) or use file's modification time
    name_match = re.match(r"(\d{4}_\d{2}_\d{2})", original_file_name)
    if name_match:
        file_date_str = name_match.group(1)
    else:
        try:
            file_mtime = os.path.getmtime(file_path)
            file_date_str = datetime.fromtimestamp(file_mtime).strftime("%Y_%m_%d")
        except OSError:
            file_date_str = datetime.now().strftime("%Y_%m_%d") # Fallback to current date

    # Suggest a new name
    default_new_name_base = f"{file_date_str}_{os.path.splitext(original_file_name)[0]}"
    
    if get_yes_no_input(f"Original name: {original_file_name}. Rename file? (Default new name: {default_new_name_base}{original_file_ext})"):
        custom_name_base = input(f"Enter new base name for the file (default: '{default_new_name_base}', extension '{original_file_ext}' will be kept): ")
        if not custom_name_base.strip():
            new_file_name_final = f"{default_new_name_base}{original_file_ext}"
        else:
            new_file_name_final = f"{custom_name_base}{original_file_ext}"
    else:
        new_file_name_final = original_file_name

    new_file_path_abs = os.path.join(audio_files_folder, new_file_name_final)

    if os.path.exists(new_file_path_abs) and new_file_path_abs != file_path:
        print(f"Warning: A file named '{new_file_name_final}' already exists in {audio_files_folder}.")
        if not get_yes_no_input("Overwrite existing file?"):
            print("File not moved.")
            return file_path

    try:
        os.rename(file_path, new_file_path_abs)
        print(f"File moved and/or renamed to {new_file_path_abs}")
        return new_file_path_abs
    except Exception as e:
        print(f"Error moving/renaming file: {e}")
        return file_path

def process_full_pipeline_wrapper():
    """Handles the "Process Full Pipeline" menu option."""
    file_path = select_file() # Returns absolute path or None
    if file_path is None:
        return

    # Determine campaign folder. If file is already in a campaign structure, use that.
    # Otherwise, prompt for campaign or create new.
    current_campaign_folder = None
    working_dir = get_working_directory()
    try:
        rel_path = os.path.relpath(os.path.dirname(file_path), working_dir)
        path_parts = rel_path.split(os.sep)
        if len(path_parts) >= 1 and ("Audio Files" in path_parts[-1] or "Transcriptions" in path_parts[-1]):
            # Assuming path is like .../CampaignName/CampaignName Audio Files/file.mp3
            # Then path_parts[-2] is CampaignName
            current_campaign_folder = os.path.join(working_dir, path_parts[-2] if len(path_parts) > 1 else path_parts[0])

            # Verify this is a campaign folder
            if not (os.path.isdir(current_campaign_folder) and os.path.basename(current_campaign_folder) == (path_parts[-2] if len(path_parts) > 1 else path_parts[0])):
                 current_campaign_folder = None # Invalid structure
        elif len(path_parts) >=1 and os.path.isdir(os.path.join(working_dir, path_parts[0])): # File is directly in a campaign-like folder
             current_campaign_folder = os.path.join(working_dir, path_parts[0])


    except ValueError: # File not in working directory
        pass


    if current_campaign_folder:
        print(f"File seems to be part of campaign: {os.path.basename(current_campaign_folder)}")
        if not get_yes_no_input("Process with this campaign context?", default="y"):
            current_campaign_folder = None # User wants to choose/create new

    if not current_campaign_folder:
        print("Select or create a campaign for this file:")
        # Simplified: always ask to select/create if not auto-detected or user overrides
        campaign_choice_action = choose_from_list(
            ["Select Existing Campaign", "Create New Campaign"],
            "Choose campaign action:", "Enter choice: "
        )
        if campaign_choice_action == "1":
            current_campaign_folder = select_campaign()
            if current_campaign_folder and current_campaign_folder == "f_explorer_sentinel": # Should not happen here
                current_campaign_folder = None 
        elif campaign_choice_action == "2":
            new_campaign_name = input("Enter name for the new campaign: ")
            new_campaign_abbrev = input(f"Enter abbreviation for '{new_campaign_name}': ")
            current_campaign_folder, _, _ = generate_new_campaign(new_campaign_name, new_campaign_abbrev, get_working_directory())
        
        if not current_campaign_folder:
            print("No campaign selected/created. Aborting full pipeline.")
            return
        
        # Move the selected file to this campaign
        file_path = move_file_to_campaign(file_path, current_campaign_folder)
        if file_path is None or not os.path.exists(file_path): # move might fail or user cancel
            print("File move failed or was cancelled. Aborting.")
            return
    
    # At this point, file_path is (ideally) inside current_campaign_folder's "Audio Files"
    # and current_campaign_folder is set.

    title_from_filename = os.path.splitext(os.path.basename(file_path))[0]
    # Remove date and _norm like patterns for a cleaner default title
    title_from_filename = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", title_from_filename)
    title_from_filename = title_from_filename.replace("_norm", "").replace("_", " ").strip()
    
    title = input(f"Enter the title for the file (default: '{title_from_filename}'): ")
    if not title.strip():
        title = title_from_filename

    process_full_pipeline(file_path, current_campaign_folder, title)


def process_single_operation_wrapper():
    """Handles the "Process Single Operation" menu option."""
    campaign_folder_path = select_campaign()
    if not campaign_folder_path or campaign_folder_path == "f_explorer_sentinel": # Campaign selection cancelled or led to file explorer
        if campaign_folder_path == "f_explorer_sentinel": # User selected file explorer from campaign menu
             # handle_file_explorer returns a file path. We need a campaign context here.
             print("Please select a file via the main menu's File Explorer option for campaign-less operations, or ensure a campaign context.")
             return
        print("No campaign selected. Aborting.")
        return

    current_file_path = select_file(campaign_folder_path) # select_file needs campaign_folder_path
    if not current_file_path:
        print("No file selected. Aborting.")
        return

    # Define operations with lambdas that take current path and return next path
    # Note: transcribe_and_revise_audio returns (output_dir, revised_tsv_file)
    #       apply_corrections_and_formatting needs to return output_txt path
    #       generate_summary_and_chapters doesn't change the primary file path for subsequent steps
    
    # Helper to get title
    def get_title_input(base_path):
        default_title = os.path.splitext(os.path.basename(base_path))[0].replace("_norm","")
        return input(f"Enter the title for '{os.path.basename(base_path)}' (default: {default_title}): ") or default_title

    single_op_menu_options = [
        (lambda p: convert_to_m4a(p, get_title_input(p)), "1. Encode to M4A & Normalize"),
        (lambda p: apply_metadata(p, {"title": get_title_input(p)}) or p, "2. Apply Metadata (to existing M4A/MP3/FLAC)"), # apply_metadata doesn't return path, so return p
        (lambda p: transcribe_and_revise_audio(p)[1], "3. Transcribe (Audio to Revised TSV->TXT)"), # Returns revised_txt_file
        # apply_corrections_and_formatting expects TSV, produces TXT. For this menu, assume input is TSV.
        (lambda p: apply_corrections_and_formatting(p, p.replace(".tsv", "_revised.txt").replace("_norm.m4a_revised.txt", "_norm_revised.txt") ), "4. Apply Corrections & Formatting (TSV to TXT)"),
        (lambda p: generate_summary_and_chapters(p) or p, "5. Generate Summary and Chapters (from TXT)"), # operates on TXT, returns None, so return p
    ]

    selected_option = display_menu("Select Operation", single_op_menu_options)
    if selected_option is None:
        return

    op_func, op_label, *_ = selected_option
    
    print(f"Processing '{op_label}' on '{os.path.basename(current_file_path)}'")
    try:
        next_file_path = op_func(current_file_path)
        if next_file_path:
            print(f"Operation successful. Output: {os.path.basename(next_file_path)}")
            current_file_path = next_file_path
        else: # Operation might return None but still be successful (e.g. metadata, summary)
            print(f"Operation '{op_label}' completed.")
            # current_file_path remains the same if None was returned, which is fine for some ops
    except Exception as e:
        print(f"Error during operation '{op_label}': {e}")
        return

    if get_yes_no_input("Process subsequent operations in the pipeline?", default="n"):
        process_subsequent_operations(current_file_path, campaign_folder_path, single_op_menu_options, selected_option, get_title_input)


def process_subsequent_operations(file_path, campaign_folder_path, menu_options, selected_initial_op, title_getter_func):
    """Processes operations after the selected one in the pipeline."""
    try:
        # Find the index of the selected operation
        # Need to compare based on the function object or a unique part of the label
        selected_op_label = selected_initial_op[1]
        selected_op_index = -1
        for i, (_, label, *_) in enumerate(menu_options):
            if label == selected_op_label:
                selected_op_index = i
                break
        
        if selected_op_index == -1:
            print("Warning: Could not find the starting operation in the list. Cannot process subsequent operations.")
            return
    except Exception as e:
        print(f"Error finding index of selected operation: {e}")
        return

    current_file_path = file_path
    for i in range(selected_op_index + 1, len(menu_options)):
        op_func, op_label, *_ = menu_options[i]
        if get_yes_no_input(f"Proceed with next operation: '{op_label}' on '{os.path.basename(current_file_path)}'?", default="y"):
            print(f"Processing '{op_label}' on '{os.path.basename(current_file_path)}'")
            try:
                # Special handling if title is needed for ops like convert_to_m4a
                if "Encode to M4A" in op_label: # A bit fragile, relies on label string
                    # The lambda for convert_to_m4a already calls title_getter_func
                     pass # The lambda structure op_func(current_file_path) is fine

                next_output_path = op_func(current_file_path)
                if next_output_path:
                    print(f"Operation successful. Output: {os.path.basename(next_output_path)}")
                    current_file_path = next_output_path
                else:
                    print(f"Operation '{op_label}' completed.")
                    # current_file_path might not change, which is fine for some ops
            except Exception as e:
                print(f"Error during operation '{op_label}': {e}")
                if not get_yes_no_input("Error occurred. Continue with next operations?", default="n"):
                    break
        else:
            print(f"Skipping '{op_label}'.")


def bulk_operations_wrapper():
    """Handles the "Bulk Operations" menu option."""
    campaign_folder_path = select_campaign()
    if not campaign_folder_path or campaign_folder_path == "f_explorer_sentinel":
        print("No campaign selected. Aborting bulk operations.")
        return

    # Bulk Operation Menu Options - store parameters in the tuple
    # The third element (boolean) indicates if "all_or_missing" choice is needed
    bulk_op_menu_options = [
        (bulk_encode, "1. Encode Audio (to M4A & Normalize)", True),
        (bulk_apply_metadata_op, "2. Apply Metadata", True), # Renamed to avoid conflict
        (bulk_transcribe, "3. Transcribe Audio", True),
        (bulk_process_text_op, "4. Process Text (TSV to TXT, Apply Corrections)", True), # Renamed
        (bulk_generate_summaries_and_chapters_op, "5. Generate Summaries and Chapters", True), # Renamed
        (lambda camp_path, all_missing_ignored: collate_summaries(find_transcriptions_folder(camp_path) or camp_path), "6. Collate Summaries (from campaign's Transcriptions folder)", False),
    ]

    selected_option = display_menu("Select Bulk Operation", bulk_op_menu_options)
    if selected_option is None: # User chose 'x'
        return

    operation_func, op_label, needs_all_missing_choice = selected_option
    all_missing_mode = "a. All" # Default if not needed

    if needs_all_missing_choice:
        while True:
            choice = input("Apply to all files or only missing/unprocessed files? (a/m, default=a): ").lower()
            if not choice: choice = "a"
            if choice in ("a", "all"):
                all_missing_mode = "a. All"
                break
            elif choice in ("m", "missing"):
                all_missing_mode = "m. Missing"
                break
            else:
                print("Invalid input. Please enter 'a' or 'm'.")

    print(f"Starting bulk operation: {op_label} for campaign '{os.path.basename(campaign_folder_path)}' (Mode: {all_missing_mode if needs_all_missing_choice else 'N/A'})")
    operation_func(campaign_folder_path, all_missing_mode) # Pass mode even if not used by func

    if get_yes_no_input("Process subsequent bulk operations in the pipeline?", default="n"):
        # Find index of current operation
        current_op_index = -1
        for i, (_, label, *_) in enumerate(bulk_op_menu_options):
            if label == op_label:
                current_op_index = i
                break
        
        if current_op_index != -1:
            for i in range(current_op_index + 1, len(bulk_op_menu_options)):
                next_op_func, next_op_label, next_needs_all_missing = bulk_op_menu_options[i]
                
                current_all_missing_mode = all_missing_mode # Use the initially chosen mode
                if next_needs_all_missing: # Ask again if the user wants to change mode for this specific step
                    if not get_yes_no_input(f"For '{next_op_label}', continue with mode '{current_all_missing_mode}'? (Or choose new a/m)", default='y'):
                        while True:
                            choice = input("Apply to all files or only missing/unprocessed files? (a/m, default=a): ").lower()
                            if not choice: choice = "a"
                            if choice in ("a", "all"):
                                current_all_missing_mode = "a. All"; break
                            elif choice in ("m", "missing"):
                                current_all_missing_mode = "m. Missing"; break
                            else: print("Invalid input.")

                if get_yes_no_input(f"Proceed with bulk operation: '{next_op_label}'? (Mode: {current_all_missing_mode if next_needs_all_missing else 'N/A'})", default="y"):
                    print(f"Starting bulk operation: {next_op_label}...")
                    next_op_func(campaign_folder_path, current_all_missing_mode)
                else:
                    print(f"Skipping '{next_op_label}'. Further subsequent operations will be skipped.")
                    break


def open_files_and_tools():
    """Handles the "Open Files and Tools" menu option."""
    while True:
        menu_options = [
            (open_general_files, "a. General Files (Dictionary, Config, etc.)"),
            (open_campaign_files, "b. Campaign-Specific Files (Audio, Transcripts, Summaries)"),
        ]
        selected_option = display_menu("Open Files and Tools", menu_options)

        if selected_option is None: # 'x' to go back to Main Menu
            break
        selected_option[0]() # Execute open_general_files or open_campaign_files

def open_campaign_files():
    """Opens campaign-specific files."""
    campaign_folder_path = select_campaign()
    if not campaign_folder_path or campaign_folder_path == "f_explorer_sentinel":
        print("No campaign selected.")
        return

    # Lambdas for display_files need to be callable without arguments for the menu
    # So, capture campaign_folder_path
    audio_folder = find_audio_files_folder(campaign_folder_path)
    trans_folder = find_transcriptions_folder(campaign_folder_path)

    while True:
        menu_options = [
            (lambda: display_files_and_open(audio_folder, "Audio Files") if audio_folder else print("Audio folder not found."), "1. Audio Files"),
            (lambda: display_files_and_open(trans_folder, "Transcriptions", filter_ext=(".tsv", "_revised.txt", ".txt")) if trans_folder else print("Transcriptions folder not found."), "2. Transcriptions (TSV, TXT)"),
            (lambda: display_files_and_open(trans_folder, "Summaries", filter_ext="_summary.txt") if trans_folder else print("Transcriptions folder (for summaries) not found."), "3. Individual Summaries"), # Summaries are in Transcriptions folder
            (lambda: display_files_and_open(trans_folder, "Chapters", filter_ext="_chapters.txt") if trans_folder else print("Transcriptions folder (for chapters) not found."), "4. Individual Chapters"), # Chapters are in Transcriptions folder
            (lambda: open_file(os.path.join(campaign_folder_path, f"{os.path.basename(campaign_folder_path)} - Collated Summary.txt")), "5. Collated Summary (Campaign Level)"),
            (lambda: open_file(os.path.join(campaign_folder_path, f"{os.path.basename(campaign_folder_path)} - Collated Chapters.txt")), "6. Collated Chapters (Campaign Level)"), # Assuming this file exists or will be created
        ]
        selected_option = display_menu(f"Campaign Files: {os.path.basename(campaign_folder_path)}", menu_options)

        if selected_option is None: # 'x' to go back
            break
        selected_option[0]() # Execute the chosen lambda

def display_files_and_open(folder_path, file_type_display_name, filter_ext=None):
    """Displays files and allows opening one. folder_path must be absolute."""
    if not folder_path or not os.path.exists(folder_path): # Added check for None
        print(f"Error: {file_type_display_name} folder not found or path is invalid: {folder_path}")
        return

    files_in_folder = []
    if filter_ext:
        if isinstance(filter_ext, str): # Single extension
            files_in_folder = [f for f in os.listdir(folder_path) if f.endswith(filter_ext)]
        elif isinstance(filter_ext, tuple): # Multiple extensions
            files_in_folder = [f for f in os.listdir(folder_path) if f.endswith(filter_ext)]
    else: # No filter, list all files
        files_in_folder = [f for f in os.listdir(folder_path)]
    
    files_in_folder = sorted(files_in_folder)


    if not files_in_folder:
        print(f"No {file_type_display_name.lower()} found in {folder_path}")
        return

    print(f"\nAvailable {file_type_display_name} in '{os.path.basename(folder_path)}':")
    for i, file_name in enumerate(files_in_folder):
        print(f"{i+1}. {file_name}")

    while True:
        try:
            choice = input(f"\nEnter the number of the {file_type_display_name.lower()} to open (or 'x' to cancel): ").lower()
            if choice == 'x':
                return
            file_choice_idx = int(choice) - 1
            if 0 <= file_choice_idx < len(files_in_folder):
                open_file(os.path.join(folder_path, files_in_folder[file_choice_idx]))
                return # Return after opening one file
            else:
                print("Invalid file number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a valid number or 'x'.")

def open_file(file_path):
    """Opens a file using the default system application."""
    abs_file_path = os.path.abspath(file_path) # Ensure path is absolute
    print(f"Attempting to open: {abs_file_path}")
    if not os.path.exists(abs_file_path):
        print(f"Error: File not found: {abs_file_path}")
        return

    try:
        if os.name == 'nt':  # For Windows
            os.startfile(abs_file_path)
        elif os.name == 'posix':  # For macOS and Linux
            subprocess.call(('open', abs_file_path))
        else:
            print(f"Unsupported OS ({os.name}) for opening files automatically.")
    except Exception as e:
        print(f"Error opening file '{abs_file_path}': {e}")


# --- Wrapper functions for direct calls ---
def process_full_pipeline(file_path, campaign_folder_path, title):
    """Processes a single file through the full pipeline.
    Assumes file_path is already in the correct campaign audio folder.
    """
    print(f"\n--- Starting Full Pipeline for: {os.path.basename(file_path)} ---")
    print(f"Campaign: {os.path.basename(campaign_folder_path)}, Title: {title}")

    print("\nStep 1: Converting to M4A and Normalizing...")
    normalized_path = convert_to_m4a(file_path, title)
    if not normalized_path or not os.path.exists(normalized_path):
        print("Normalization/conversion failed. Aborting pipeline.")
        return
    print(f"Normalized audio: {os.path.basename(normalized_path)}")

    print("\nStep 2: Transcribing Audio...")
    # transcribe_and_revise_audio returns (output_dir, revised_txt_file_path)
    # campaign_folder_path is the parent of output_dir (Transcriptions folder)
    # We need revised_txt_file_path
    _, revised_txt_file_path = transcribe_and_revise_audio(normalized_path)
    if not revised_txt_file_path or not os.path.exists(revised_txt_file_path):
        print("Transcription failed. Aborting pipeline.")
        return
    print(f"Revised transcription: {os.path.basename(revised_txt_file_path)}")

    # Note: transcribe_combine is usually for multiple files.
    # For a single file pipeline, it might not be strictly necessary here yet,
    # but useful if other files exist. Let's keep it.
    print("\nStep 3: Combining Transcriptions (collating all in campaign)...")
    combined_transcriptions_path = transcribe_combine(campaign_folder_path)
    if combined_transcriptions_path:
        print(f"Combined campaign transcriptions: {os.path.basename(combined_transcriptions_path)}")

    print("\nStep 4: Generating Summary and Chapters for the current file...")
    generate_summary_and_chapters(revised_txt_file_path) # Operates on the single revised TXT

    print("\nStep 5: Collating Summaries (all in campaign)...")
    # collate_summaries needs the transcriptions folder path
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if transcriptions_folder:
        collate_summaries(transcriptions_folder)
    else:
        print(f"Warning: Transcriptions folder not found for campaign {os.path.basename(campaign_folder_path)}, cannot collate summaries.")

    print(f"\n--- Full Pipeline Completed for: {os.path.basename(file_path)} ---")


# --- Bulk Operation Implementations ---
# These functions are called by bulk_operations_wrapper

def bulk_encode(campaign_folder_path, all_or_missing_mode):
    """Handles bulk encoding for a campaign."""
    bulk_normalize_audio(campaign_folder_path, all_or_missing_mode) # Re-use existing detailed logic

def bulk_apply_metadata_op(campaign_folder_path, all_or_missing_mode):
    """Handles bulk apply metadata for a campaign."""
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in {campaign_folder_path}")
        return

    files_to_process = [
        os.path.join(audio_files_folder, f)
        for f in os.listdir(audio_files_folder)
        if f.endswith((".m4a", ".mp3", ".flac")) # Common formats for metadata
    ]

    if not files_to_process:
        print("No suitable audio files found for metadata application.")
        return

    for file_path in files_to_process:
        filename = os.path.basename(file_path)
        # For "missing" mode, it's hard to define what "missing metadata" means without checking tags.
        # So, for simplicity, "missing" might not be very effective here unless we check specific tags.
        # Let's assume "all" means re-apply/prompt for all, "missing" is a bit of a no-op or applies to files without ANY known metadata.
        # For now, both modes will iterate all files and prompt.
        
        print(f"Processing metadata for: {filename}")
        # Extract a default title from filename (stripping date and _norm)
        default_title = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", os.path.splitext(filename)[0])
        default_title = default_title.replace("_norm", "").replace("_", " ").strip()
        
        title = input(f"Enter title for '{filename}' (default: '{default_title}'): ") or default_title
        # Potentially prompt for other metadata fields if needed (artist, album etc.)
        # For now, just title. Other metadata is set during encoding by convert_to_m4a.
        # This bulk op is more for *updating* existing files if needed.
        metadata = {"title": title}
        # Add more fields as configured or prompted
        # metadata["artist"] = config["podcasts"]["artist_name"] # etc.
        
        apply_metadata(file_path, metadata)
        print(f"Metadata applied/updated for {filename}.")


def bulk_transcribe(campaign_folder_path, all_or_missing_mode):
    """Handles bulk transcription for a campaign."""
    # Re-use existing bulk_transcribe_audio from transcription.py but add all_or_missing logic
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)

    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in {campaign_folder_path}. Cannot transcribe.")
        return
    if not transcriptions_folder:
        # Attempt to create it
        campaign_abbrev = os.path.basename(campaign_folder_path)
        transcriptions_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Transcriptions")
        try:
            os.makedirs(transcriptions_folder, exist_ok=True)
            print(f"Created 'Transcriptions' folder: {transcriptions_folder}")
        except OSError as e:
            print(f"Error creating 'Transcriptions' folder: {e}. Cannot transcribe.")
            return

    norm_audio_files = [
        f for f in os.listdir(audio_files_folder)
        if f.endswith("_norm.m4a") # Typically transcribe normalized files
    ]

    for audio_filename in norm_audio_files:
        audio_file_path = os.path.join(audio_files_folder, audio_filename)
        base_name = os.path.splitext(audio_filename)[0]
        # Expected output: _revised.txt in transcriptions_folder
        expected_revised_txt_path = os.path.join(transcriptions_folder, f"{base_name}_revised.txt")

        if all_or_missing_mode == "m. Missing" and os.path.exists(expected_revised_txt_path):
            print(f"Skipping {audio_filename} (revised transcript already exists).")
            continue
        
        print(f"Transcribing: {audio_filename}")
        transcribe_and_revise_audio(audio_file_path) # This function handles saving to the correct subfolder
    print("Bulk transcription process finished.")


def bulk_process_text_op(campaign_folder_path, all_or_missing_mode):
    """Handles bulk text processing (TSV to TXT, corrections) for a campaign."""
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found in {campaign_folder_path}")
        return

    # This operation converts _norm.tsv files to _norm_revised.txt files
    tsv_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith("_norm.tsv") # Source files are raw TSV from transcription
    ]

    for tsv_filename in tsv_files:
        tsv_file_path = os.path.join(transcriptions_folder, tsv_filename)
        # Output is _revised.txt, derived from the _norm.tsv name
        revised_txt_filename = tsv_filename.replace(".tsv", "_revised.txt")
        revised_txt_file_path = os.path.join(transcriptions_folder, revised_txt_filename)

        if all_or_missing_mode == "m. Missing" and os.path.exists(revised_txt_file_path):
            print(f"Skipping {tsv_filename} (revised text file already exists).")
            continue

        print(f"Processing text for: {tsv_filename} -> {revised_txt_filename}")
        apply_corrections_and_formatting(tsv_file_path, revised_txt_file_path)
    print("Bulk text processing finished.")


def bulk_generate_summaries_and_chapters_op(campaign_folder_path, all_or_missing_mode):
    """Handles bulk generation of summaries and chapters for a campaign."""
    # This uses the bulk_summarize_transcripts from summarisation.py
    # which iterates _norm_revised.txt files. We need to adapt all_or_missing.
    
    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found in {campaign_folder_path}")
        return

    revised_txt_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith("_norm_revised.txt")
    ]

    for txt_filename in revised_txt_files:
        txt_file_path = os.path.join(transcriptions_folder, txt_filename)
        
        # Check if summary and chapters already exist for "missing" mode
        base_name_for_summary = txt_filename.replace(".txt", "") # e.g. YYYY_MM_DD_title_norm_revised
        summary_file = os.path.join(transcriptions_folder, f"{base_name_for_summary}_summary.txt")
        chapters_file = os.path.join(transcriptions_folder, f"{base_name_for_summary}_chapters.txt")
        # subtitle_file = os.path.join(transcriptions_folder, f"{base_name_for_summary}_subtitle.txt") # Also check subtitle

        if all_or_missing_mode == "m. Missing" and \
           os.path.exists(summary_file) and \
           os.path.exists(chapters_file): # and os.path.exists(subtitle_file):
            print(f"Skipping {txt_filename} (summary/chapters already exist).")
            continue
        
        print(f"Generating summary and chapters for: {txt_filename}")
        generate_summary_and_chapters(txt_file_path)
    
    print("Bulk summary/chapter generation finished. Now collating summaries...")
    collate_summaries(transcriptions_folder) # Collate after all individual ones are done.


def main():
    """Main function for the sessionscribe application."""
    working_directory = get_working_directory()
    if not os.path.isdir(working_directory):
        print(f"Error: Working directory '{working_directory}' not found. Please check config.json.")
        new_wd = input("Enter a valid path for the working directory (or leave blank to exit): ")
        if new_wd and os.path.isdir(new_wd):
            # TODO: Update config.json here if desired, or just use for this session
            # For now, this is a temporary fix for the session
            # config_data['general']['working_directory'] = new_wd
            # with open('config.json', 'w') as cf: json.dump(config_data, cf, indent=4)
            print(f"Note: config.json not updated. Using '{new_wd}' for this session only.")
            # This requires a way to override get_working_directory for the session or reload config.
            # Simplest for now: ask user to fix config.json and restart.
            print("Please update config.json with a valid working_directory and restart the application.")
            return
        else:
            print("Exiting.")
            return


    dictionary_path = os.path.join(working_directory, "wack_dictionary.txt")

    if not os.path.exists(dictionary_path):
        print(f"wack_dictionary.txt not found in {working_directory}, creating it...")
        try:
            with open(dictionary_path, "w", encoding="utf-8") as f:
                f.write("Flumph\n")
                f.write("Githyanki\n")
                f.write("Modron\n")
                f.write("Slaad\n")
                f.write("Umberhulk\n")
                f.write("Yuan-ti\n")
            if get_yes_no_input("wack_dictionary.txt created. Would you like to open it now to add custom words?"):
                open_file(dictionary_path)
        except Exception as e:
            print(f"Could not create wack_dictionary.txt: {e}")


    while True: # Main menu loop
        menu_options = [
            (process_full_pipeline_wrapper, "1. Process Full Pipeline (Single File)", False),
            (process_single_operation_wrapper, "2. Process Single Operation (Single File)", False),
            (bulk_operations_wrapper, "3. Bulk Operations (Campaign Level)", False),
            (open_files_and_tools, "4. Open Files and Tools", False),
            (lambda: (print("Exiting..."), True), "x. Exit", False) # Lambda returns True to signal exit
        ]

        selected_option = display_menu("sessionscribe   -   ttrpg session/podcast management tool", menu_options)

        if selected_option is None: # User chose 'x' from display_menu's own prompt if it had one, or invalid choice repeatedly
            # This case should ideally not be reached if display_menu always returns a tuple or None for 'x'
            # Assuming 'x' in display_menu now returns None, and None is passed up
            print("Exiting due to 'x' or unhandled menu exit.")
            break # Exit main loop

        callback_func, _, _ = selected_option # Unpack, ignore other elements for main menu

        exit_signal = callback_func() # Execute the chosen function
        if exit_signal is True and callback_func == menu_options[-1][0]: # Check if it was the exit lambda
            break # Exit main loop

if __name__ == "__main__":
    main()