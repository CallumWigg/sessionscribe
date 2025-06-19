import os
import re
from datetime import datetime

from .summarisation import collate_summaries, generate_summary_and_chapters
from .transcription import transcribe_and_revise_audio
from . import user_interaction, database_management as db
# C-IMPROVEMENT: Import CampaignContext for the new dictionary tool.
from .utils import get_working_directory, config, CampaignContext
# C-IMPROVEMENT: Import the new dictionary update function.
from .text_processing import dictionary_update

def find_original_audio(audio_folder, normalized_basename):
    """
    Finds the original audio file that corresponds to a normalized file.
    """
    if not audio_folder: return None
    
    base_name_to_match = normalized_basename.replace("_norm", "")
    supported_extensions = tuple(config["general"].get("supported_audio_extensions", [".wav", ".m4a", ".flac", ".mp3"]))

    for filename in os.listdir(audio_folder):
        if "_norm" not in filename.lower() and filename.lower().endswith(supported_extensions):
            if os.path.splitext(filename)[0] == base_name_to_match:
                return os.path.join(audio_folder, filename)
    return None

def find_audio_files_folder(campaign_folder_path):
    """
    Finds or creates a standard 'Audio Files' folder within the campaign directory.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None

    # More robust check for "Audio Files" in the folder name
    audio_folders = [
        os.path.join(campaign_folder_path, f) for f in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, f)) and "audio files" in f.lower()
    ]
    
    if not audio_folders:
        campaign_abbrev = os.path.basename(campaign_folder_path)
        default_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Audio Files")
        print(f"No 'Audio Files' folder found, creating: {default_folder}")
        os.makedirs(default_folder, exist_ok=True)
        return default_folder
    elif len(audio_folders) == 1:
        return audio_folders[0]
    else:
        # Let user choose if multiple matching folders are found
        return user_interaction.choose_from_list(
            [os.path.basename(f) for f in audio_folders],
            "Multiple folders with 'Audio Files' found. Please select one:",
            "Enter the number of the folder:"
        )

def find_transcriptions_folder(campaign_folder_path):
    """
    Finds or creates a standard 'Transcriptions' folder within the campaign directory.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None
        
    trans_folders = [
        os.path.join(campaign_folder_path, f) for f in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, f)) and "transcriptions" in f.lower()
    ]

    if not trans_folders:
        campaign_abbrev = os.path.basename(campaign_folder_path)
        default_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Transcriptions")
        print(f"No 'Transcriptions' folder found, creating: {default_folder}")
        os.makedirs(default_folder, exist_ok=True)
        return default_folder
    elif len(trans_folders) == 1:
        return trans_folders[0]
    else:
        return user_interaction.choose_from_list(
            [os.path.basename(f) for f in trans_folders],
            "Multiple folders with 'Transcriptions' found. Please select one:",
            "Enter the number of the folder:"
        )

def generate_new_campaign(campaign_name, abbreviation, base_directory):
    """Generates a new campaign directory structure and initializes its database and dictionary files."""
    campaign_folder_abs = os.path.join(base_directory, campaign_name)
    if os.path.exists(campaign_folder_abs):
        print(f"Error: A directory named '{campaign_name}' already exists.")
        return None

    print(f"Creating new campaign '{campaign_name}'...")
    try:
        # Create standard folders
        os.makedirs(os.path.join(campaign_folder_abs, f"{abbreviation} Audio Files"), exist_ok=True)
        os.makedirs(os.path.join(campaign_folder_abs, f"{abbreviation} Transcriptions"), exist_ok=True)
        
        # Initialize the database
        db.init_campaign_db(campaign_folder_abs)
        
        # C-IMPROVEMENT: Initialize dictionary files using the CampaignContext to ensure they are created correctly.
        context = CampaignContext(campaign_folder_abs)
        _ = context.custom_words  # Accessing property triggers file creation
        _ = context.corrections_dict # Accessing property triggers file creation

        print(f"Campaign '{campaign_name}' structure and database created successfully.")
        return campaign_folder_abs
    except OSError as e:
        print(f"Error creating campaign structure for '{campaign_name}': {e}")
        return None


def get_sort_key_from_episode(episode):
    """Generates a sort key for episodes from the database."""
    try:
        date_obj = datetime.strptime(episode['recorded_date'], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        date_obj = datetime.min.date()
    return (date_obj, episode['episode_number'])


def transcribe_combine(campaign_folder_path):
    """Combine individual revised transcriptions for a campaign using the database."""
    episodes = db.get_episodes_for_campaign(campaign_folder_path, "WHERE ps.text_processed = TRUE")
    if not episodes:
        print(f"No revised transcription files found in DB for campaign '{os.path.basename(campaign_folder_path)}'.")
        return None

    sorted_episodes = sorted(episodes, key=get_sort_key_from_episode)

    campaign_basename = os.path.basename(campaign_folder_path)
    output_file_name = os.path.join(campaign_folder_path, f"{campaign_basename} - Transcriptions Combined.txt")

    try:
        with open(output_file_name, 'w', encoding='utf-8') as output_file:
            output_file.write(f"# {campaign_basename} - Combined Transcriptions\n\n")
            output_file.write(f"Total Sessions: {len(sorted_episodes)}\n\n--- Session Index ---\n")
            
            for episode in sorted_episodes:
                 output_file.write(f"- Episode {episode['episode_number']}: {episode['episode_title']}\n")
            output_file.write("\n---\n\n")

            for i, episode in enumerate(sorted_episodes):
                if not episode['transcription_file']:
                    continue
                txt_file_path = os.path.join(campaign_folder_path, episode['transcription_file'])
                if os.path.exists(txt_file_path):
                    with open(txt_file_path, 'r', encoding='utf-8') as f_in:
                        output_file.write(f"--- Episode {episode['episode_number']}: {episode['episode_title']} ---\n")
                        # Skip header lines from individual files
                        for _ in range(3): next(f_in, None)
                        output_file.write(f_in.read().strip() + '\n')
                        if i < len(sorted_episodes) - 1:
                            output_file.write('\n\n---\n\n')
                else:
                    print(f"Warning: File missing for Ep #{episode['episode_number']}: {txt_file_path}")
        
        print(f"Combined transcription saved to: {os.path.basename(output_file_name)}")
        return output_file_name
    except IOError as e:
        print(f"Error writing combined transcription file '{output_file_name}': {e}")
        return None

# C-IMPROVEMENT: New wrapper for the automated dictionary update tool.
def dictionary_update_wrapper(campaign_folder_path):
    """Wrapper to run the automated dictionary update on a selected transcript."""
    # Find all processed transcripts that can be used as a source.
    episodes = db.get_episodes_for_campaign(campaign_folder_path, "WHERE ps.text_processed = TRUE")
    if not episodes:
        print("No processed transcripts available to build dictionary from.")
        return

    episode_choices = [f"#{e['episode_number']}: {e['episode_title']}" for e in episodes]
    chosen_str = user_interaction.choose_from_list(episode_choices, "Select an episode transcript to analyze for new words:", "Enter number:")
    if not chosen_str: return
    
    choice_index = episode_choices.index(chosen_str)
    selected_episode = episodes[choice_index]
    
    if not selected_episode['transcription_file']:
        print("Error: Selected episode has no transcript file path in the database.")
        return
        
    transcript_path = os.path.join(campaign_folder_path, selected_episode['transcription_file'])
    if not os.path.exists(transcript_path):
        print(f"Error: Transcript file not found on disk: {transcript_path}")
        return

    context = CampaignContext(campaign_folder_path)
    dictionary_update(context, transcript_path)


def retranscribe_single_file(campaign_folder_path):
    """Retranscribe a single episode from the campaign."""
    episodes = db.get_episodes_for_campaign(campaign_folder_path, "WHERE ps.normalized = TRUE")
    if not episodes:
        print("No normalized episodes available for retranscription.")
        return

    episode_choices = [f"#{e['episode_number']}: {e['episode_title']}" for e in episodes]
    chosen_str = user_interaction.choose_from_list(episode_choices, "Select episode to retranscribe:", "Enter number:")
    if not chosen_str: return
    
    selected_episode = episodes[episode_choices.index(chosen_str)]
    
    print(f"\nRetranscribing: {selected_episode['episode_title']}...")
    revised_txt_file_path = transcribe_and_revise_audio(campaign_folder_path, selected_episode['episode_id'])

    if not revised_txt_file_path:
        print("Retranscription failed.")
        return

    print("Retranscription successful. Updating related files...")
    transcribe_combine(campaign_folder_path)
    generate_summary_and_chapters(campaign_folder_path, selected_episode['episode_id'])
    collate_summaries(campaign_folder_path)
    print("\nRetranscription and update process complete.")


def resummarise_single_file(campaign_folder_path):
    """Resummarise a single episode from the campaign."""
    episodes = db.get_episodes_for_campaign(campaign_folder_path, "WHERE ps.text_processed = TRUE")
    if not episodes:
        print("No processed transcripts available for re-summarisation.")
        return

    episode_choices = [f"#{e['episode_number']}: {e['episode_title']}" for e in episodes]
    chosen_str = user_interaction.choose_from_list(episode_choices, "Select episode to re-summarise:", "Enter number:")
    if not chosen_str: return

    selected_episode = episodes[episode_choices.index(chosen_str)]

    print(f"\nGenerating summary and chapters for: {selected_episode['episode_title']}...")
    generate_summary_and_chapters(campaign_folder_path, selected_episode['episode_id'])
    
    print("\nCollating all campaign summaries...")
    collate_summaries(campaign_path)
    print("\nRe-summarisation process complete.")