import os
import subprocess

# Import functions from modules
from .audio_processing import convert_to_m4a, search_audio_files, bulk_normalize_audio, calculate_target_bitrate, split_audio_file
from .transcription import transcribe_and_revise_audio, bulk_transcribe_audio
from .text_processing import apply_corrections_and_formatting
from .summarisation import generate_summary_and_chapters, collate_summaries, bulk_summarize_transcripts
from .file_management import retranscribe_single_file, resummarise_single_file, generate_new_campaign, transcribe_combine, find_transcriptions_folder
from .user_interaction import choose_from_list, select_campaign_folder
from .utils import get_working_directory

def transcribe_and_process():
    """Menu item; transcribe and process new audio file."""

    audio_files = search_audio_files()
    selected_file = choose_from_list(
        audio_files, None, "Enter the number of the file you want to process"
    )

    target_bitrate = calculate_target_bitrate(selected_file) # Calculate bitrate before prompting for title

    if target_bitrate < config["general"]["minimum_bitrate"]:
        print(f"Warning: The calculated bitrate ({target_bitrate} kbps) is very low and might result in poor audio quality.")
        choice = choose_from_list(
            ["Proceed with encoding", "Split the file into parts"],
            "Choose an option:",
            "Enter the number of your choice:"
        )

        if choice == "Split the file into parts":
            parts = split_audio_file(selected_file) # Split the file
            for i, part in enumerate(parts):
                title = input(f"Enter the title for part {i+1}: ")
                normalized_path = convert_to_m4a(part, title)
                campaign_folder, revised_tsv_file = transcribe_and_revise_audio(normalized_path)
                summary_location = transcribe_combine(campaign_folder)
                generate_summary_and_chapters(revised_tsv_file)
                collate_summaries(campaign_folder)
                print(f"Combined transcription saved to: {summary_location}")
            return  # Exit after processing all parts

    # If not splitting or bitrate is acceptable, continue with normal process
    title = input("Enter the title: ")
    normalized_path = convert_to_m4a(selected_file, title)
    campaign_folder, revised_tsv_file = transcribe_and_revise_audio(normalized_path)
    summary_location = transcribe_combine(campaign_folder)
    generate_summary_and_chapters(revised_tsv_file)
    collate_summaries(campaign_folder)
    print(f"Combined transcription saved to: {summary_location}")

def update_existing_transcriptions():
    """Menu item; update existing revised transcriptions."""

    campaign_folder = select_campaign_folder()
    revised_txt_files = [
        os.path.join(dirpath, f)
        for dirpath, dirnames, filenames in os.walk(campaign_folder)
        for f in filenames
        if f.endswith("_revised.txt")
    ]
    if not revised_txt_files:
        generate_revised_transcriptions(campaign_folder)
        collate_summaries(campaign_folder)
    else:
        # Update ALL revised transcription files
        for txt_file in revised_txt_files:
            print(f'Starting dictionary_update on {txt_file}')
            dictionary_update(txt_file)
            print('Starting fuzzy_fix')
            fuzzy_fix()
            print(f'Starting corrections_replace on {txt_file}')
            corrections_replace(txt_file)
            print(f'Done updating {txt_file}') 

        # Combine revised transcriptions
        txt_location = transcribe_combine(campaign_folder) 
        print(f"Combined transcriptions (text) saved to: {txt_location}")


def generate_revised_transcriptions():
    """Menu item; generate revised transcriptions."""
    campaign_folder = select_campaign_folder()
    transcriptions_folder = find_transcriptions_folder(campaign_folder)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found in {campaign_folder}")
        return

    # Find all TSV files that don't have a corresponding _revised.txt file
    tsv_files = [
        f for f in os.listdir(transcriptions_folder)
        if f.endswith(".tsv") and not os.path.exists(os.path.join(transcriptions_folder, f.replace(".tsv", "_revised.txt")))
    ]

    if not tsv_files:
        print("All TSV files already have corresponding revised transcriptions.")
        return

    print("\nTSV files without revised transcriptions:")
    for i, file in enumerate(tsv_files):
        print(f"{i+1}. {file}")

    # Process each TSV file
    for tsv_file in tsv_files:
        tsv_file_path = os.path.join(transcriptions_folder, tsv_file)
        revised_txt_file = tsv_file_path.replace(".tsv", "_revised.txt")

        print(f"Generating revised transcription for: {tsv_file}")
        apply_corrections_and_formatting(tsv_file_path, revised_txt_file)

        print(f"Revised transcription saved to: {revised_txt_file}")
    print(f"Generated revised transcripts in: {campaign_folder}")

def retranscribe_single_file_wrapper():
    """Menu item; retranscribe single file."""
    campaign_folder = select_campaign_folder()
    retranscribe_single_file(campaign_folder)

def resummarise_single_file_wrapper():
    """Menu item; resummarise single file."""
    campaign_folder = select_campaign_folder()
    resummarise_single_file(campaign_folder)

def generate_new_campaign_wizard():
    """Menu item; generate a new campaign."""
    campaign_name = input("Enter the name of the new campaign: ")
    abbreviation = input(f"Enter the abbreviation for '{campaign_name}': ")
    campaign_folder, audio_files_folder, transcriptions_folder = generate_new_campaign(campaign_name, abbreviation, get_working_directory())
    print(f"New campaign '{campaign_name}' created at:")
    print(f"Campaign Folder: {campaign_folder}")
    print(f"Audio Files Folder: {audio_files_folder}")
    print(f"Transcriptions Folder: {transcriptions_folder}")

def bulk_normalise_audio_wrapper():
    """Menu item; bulk normalise audio files in a campaign."""
    campaign_folder = select_campaign_folder()
    bulk_normalize_audio(campaign_folder)

def bulk_transcribe_audio_wrapper():
    """Menu item; bulk transcribe audio files in a campaign."""
    campaign_folder = select_campaign_folder()
    bulk_transcribe_audio(campaign_folder)

def bulk_summarize_tsv_wrapper():
    """Menu item; bulk summarize existing _revised.txt files in a campaign."""
    campaign_folder = select_campaign_folder()
    bulk_summarize_transcripts(campaign_folder)

def main():
    working_directory = get_working_directory()
    dictionary_path = os.path.join(working_directory, "wack_dictionary.txt")

    if not os.path.exists(dictionary_path):
        print("wack_dictionary.txt not found, creating it...")
        with open(dictionary_path, "w", encoding="utf-8") as f:
            f.write("Flumph\n")
            f.write("Githyanki\n")
            f.write("Modron\n")
            f.write("Slaad\n")
            f.write("Umberhulk\n")
            f.write("Yuan-ti\n")

        # Prompt user to open the dictionary file
        if input("Would you like to open wack_dictionary.txt in a text editor? (y/n): ").lower() == 'y':
            try:
                # Attempt to open the file using the default text editor
                os.startfile(dictionary_path)  # For Windows
            except AttributeError:
                # For macOS and Linux, use the 'open' command
                subprocess.call(['open', dictionary_path])

    options = [
        (transcribe_and_process, "Transcribe and process new audio file"),
        (update_existing_transcriptions, "Update existing transcriptions (corrections, combining)"),
        (generate_revised_transcriptions, "Generate revised transcripts from TSVs"),
        (retranscribe_single_file_wrapper, "Retranscribe a single file"),
        (resummarise_single_file_wrapper, "Resummarise a single file"),
        (generate_new_campaign_wizard, "Generate a new campaign"),
        (bulk_normalise_audio_wrapper, "Bulk normalise audio files"),
        (bulk_transcribe_audio_wrapper, "Bulk transcribe audio"),
        (bulk_summarize_tsv_wrapper, "Bulk summarise files"),
        (lambda: (print("Exiting..."), exit()), "Exit")
    ]

    labels = [option[1] for option in options]
    callbacks = [option[0] for option in options]

    while True:
        callback = choose_from_list(
            labels,
            "DnD Session Transcription Menu",
            f"Enter your choice (1-{len(options)})",
            values=callbacks
        )
        callback()

# Call the main function to start the interactive menu
if __name__ == "__main__":
    main()