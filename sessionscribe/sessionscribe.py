import os
import subprocess

# Import functions from modules
from .audio_processing import convert_to_m4a, search_audio_files, bulk_normalize_audio
from .transcription import transcribe_and_revise_audio, bulk_transcribe_audio
from .text_processing import generate_revised_transcripts, dictionary_update, fuzzy_fix, corrections_replace, transcribe_combine
from .summarisation import generate_summary_and_chapters, collate_summaries
from .file_management import retranscribe_single_file, resummarise_single_file, generate_new_campaign

from . import file_management
from . import user_interaction
from . import utils

def transcribe_and_process():
    """Menu item; transcribe and process new audio file."""

    audio_files = search_audio_files() # Search for audio files created in the last 3 days
    selected_file = user_interaction.choose_from_list(
        audio_files, None, "Enter the number of the file you want to process"
    )
  
    title = input("Enter the title: ") # Prompt the user for metadata: Title    
    normalised_path = convert_to_m4a(selected_file, title) # Run the selected file through the convert_to_m4a function and apply metadata
    campaign_folder, revised_tsv_file = transcribe_and_revise_audio(normalised_path) # Transcribe and create revised version
    summary_location = transcribe_combine(campaign_folder) # Combine revised transcriptions
    generate_summary_and_chapters(revised_tsv_file)
    collate_summaries(campaign_folder)
    print(f"Combined transcription saved to: {summary_location}")

def update_existing_transcriptions():
    """Menu item; update existing revised transcriptions."""

    campaign_folder = user_interaction.select_campaign_folder()
    revised_txt_files = [
        os.path.join(dirpath, f)
        for dirpath, dirnames, filenames in os.walk(campaign_folder)
        for f in filenames
        if f.endswith("_revised.txt")
    ]
    if not revised_txt_files:
        generate_revised_transcripts(campaign_folder)
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
    campaign_folder = user_interaction.select_campaign_folder()
    generate_revised_transcripts(campaign_folder)
    collate_summaries(campaign_folder)
    print(f"Generated revised transcripts in: {campaign_folder}")

def retranscribe_single_file_wrapper():
    """Menu item; retranscribe single file."""
    campaign_folder = user_interaction.select_campaign_folder()
    retranscribe_single_file(campaign_folder)

def resummarise_single_file_wrapper():
    """Menu item; resummarise single file."""
    campaign_folder = user_interaction.select_campaign_folder()
    resummarise_single_file(campaign_folder)

def generate_new_campaign_wizard():
    """Menu item; generate a new campaign."""
    campaign_name = input("Enter the name of the new campaign: ")
    abbreviation = input(f"Enter the abbreviation for '{campaign_name}': ")
    campaign_folder, audio_files_folder, transcriptions_folder = generate_new_campaign(campaign_name, abbreviation, utils.get_working_directory())
    print(f"New campaign '{campaign_name}' created at:")
    print(f"Campaign Folder: {campaign_folder}")
    print(f"Audio Files Folder: {audio_files_folder}")
    print(f"Transcriptions Folder: {transcriptions_folder}")

def bulk_normalise_audio_wrapper():
    """Menu item; bulk normalise audio files in a campaign."""
    campaign_folder = user_interaction.select_campaign_folder()
    bulk_normalize_audio(campaign_folder)

def bulk_transcribe_audio_wrapper():
    """Menu item; bulk transcribe audio files in a campaign."""
    campaign_folder = user_interaction.select_campaign_folder()
    bulk_transcribe_audio(campaign_folder)

def bulk_summarize_tsv_wrapper():
    """Menu item; bulk summarize existing _revised.txt files in a campaign."""

    campaign_folder = user_interaction.select_campaign_folder()

    transcriptions_folder = file_management.find_transcriptions_folder(campaign_folder)
    if transcriptions_folder:
        for filename in os.listdir(transcriptions_folder):
            if filename.endswith("_revised.txt"):
                file_path = os.path.join(transcriptions_folder, filename)
                print(f"Summarizing: {file_path}")
                generate_summary_and_chapters(file_path)
        collate_summaries(transcriptions_folder)  # Collate after summarizing all files
    else:
        print(f"No 'Transcriptions' folder found in {campaign_folder}")

def main():
    working_directory = utils.get_working_directory()
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
        callback = user_interaction.choose_from_list(
            labels,
            "DnD Session Transcription Menu",
            f"Enter your choice (1-{len(options)})",
            values=callbacks
        )
        callback()

# Call the main function to start the interactive menu
if __name__ == "__main__":
    main()