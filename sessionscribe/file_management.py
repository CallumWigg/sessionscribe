import os
import re
from datetime import datetime

from .summarisation import collate_summaries, generate_summary_and_chapters
from .transcription import transcribe_and_revise_audio
from . import user_interaction, database_management as db
from .utils import get_working_directory

def find_audio_files_folder(campaign_folder_path):
    """
    Find a folder within the campaign folder that contains 'Audio Files' in its name.
    Prompts user if multiple are found. Returns absolute path or None.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None

    audio_folders = [
        os.path.join(campaign_folder_path, folder_name)
        for folder_name in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, folder_name)) and "Audio Files" in folder_name
    ]
    if not audio_folders:
        # If not found, create a standard one
        campaign_abbrev = os.path.basename(campaign_folder_path)
        default_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Audio Files")
        os.makedirs(default_folder, exist_ok=True)
        return default_folder
    elif len(audio_folders) == 1:
        return audio_folders[0]
    else:
        # Let user choose if multiple are found
        folder_basenames = [os.path.basename(f) for f in audio_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Audio Files' found. Please select one:",
            "Enter the number of the folder:"
        )
        return os.path.join(campaign_folder_path, chosen_basename) if chosen_basename else None

def find_transcriptions_folder(campaign_folder_path):
    """
    Find a folder within the campaign folder that contains 'Transcriptions' in its name.
    Prompts user if multiple are found. Returns absolute path or None.
    """
    if not campaign_folder_path or not os.path.isdir(campaign_folder_path):
        return None
        
    transcriptions_folders = [
        os.path.join(campaign_folder_path, folder_name)
        for folder_name in os.listdir(campaign_folder_path)
        if os.path.isdir(os.path.join(campaign_folder_path, folder_name)) and "Transcriptions" in folder_name
    ]
    if not transcriptions_folders:
        # If not found, create a standard one
        campaign_abbrev = os.path.basename(campaign_folder_path)
        default_folder = os.path.join(campaign_folder_path, f"{campaign_abbrev} Transcriptions")
        os.makedirs(default_folder, exist_ok=True)
        return default_folder
    elif len(transcriptions_folders) == 1:
        return transcriptions_folders[0]
    else:
        folder_basenames = [os.path.basename(f) for f in transcriptions_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Transcriptions' found. Please select one:",
            "Enter the number of the folder:"
        )
        return os.path.join(campaign_folder_path, chosen_basename) if chosen_basename else None

def generate_new_campaign(campaign_name, abbreviation, base_directory):
    """Generates a new campaign directory structure and initializes its database."""
    campaign_folder_abs = os.path.join(base_directory, campaign_name)
    if os.path.exists(campaign_folder_abs):
        print(f"Error: A directory named '{campaign_name}' already exists.")
        return None, None, None

    audio_files_folder_abs = os.path.join(campaign_folder_abs, f"{abbreviation} Audio Files")
    transcriptions_folder_abs = os.path.join(campaign_folder_abs, f"{abbreviation} Transcriptions")

    try:
        os.makedirs(audio_files_folder_abs, exist_ok=True)
        os.makedirs(transcriptions_folder_abs, exist_ok=True)
        # Initialize the database for the new campaign
        db.init_campaign_db(campaign_folder_abs)
        # Create campaign-specific dictionary files
        with open(os.path.join(campaign_folder_abs, "wack_dictionary.txt"), 'w', encoding='utf-8') as f:
            f.write("# Add campaign-specific proper nouns, one per line\n")
        with open(os.path.join(campaign_folder_abs, "corrections.txt"), 'w', encoding='utf-8') as f:
            f.write("# Add campaign-specific corrections: wrong -> right\n")

        print(f"Campaign '{campaign_name}' structure and database created successfully.")
    except OSError as e:
        print(f"Error creating campaign structure for '{campaign_name}': {e}")
        return None, None, None

    return campaign_folder_abs, audio_files_folder_abs, transcriptions_folder_abs


def get_sort_key_from_episode(episode):
    """Generates a sort key for episodes from the database."""
    # Primary sort: recorded_date. Secondary: episode_number
    try:
        date_obj = datetime.strptime(episode['recorded_date'], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        date_obj = datetime.min.date() # Oldest possible date if invalid
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
                txt_file_path = os.path.join(campaign_folder_path, episode['transcription_file'])
                if os.path.exists(txt_file_path):
                    with open(txt_file_path, 'r', encoding='utf-8') as f_in:
                        # Reconstruct header for clarity in combined file
                        output_file.write(f"--- Episode {episode['episode_number']}: {episode['episode_title']} ---\n\n")
                        # Skip original header line in file
                        next(f_in, None); next(f_in, None)
                        output_file.write(f_in.read())
                        if i < len(sorted_episodes) - 1:
                            output_file.write('\n\n---\n\n')
        
        print(f"Combined transcription saved to: {output_file_name}")
        return output_file_name
    except IOError as e:
        print(f"Error writing combined transcription file '{output_file_name}': {e}")
        return None


def retranscribe_single_file(campaign_folder_path):
    """Retranscribe a single episode from the campaign."""
    episodes = db.get_episodes_for_campaign(campaign_folder_path, "WHERE ps.normalized = TRUE")
    if not episodes:
        print("No normalized episodes available for retranscription.")
        return

    episode_choices = [f"#{e['episode_number']}: {e['episode_title']}" for e in episodes]
    chosen_str = user_interaction.choose_from_list(episode_choices, "Select episode to retranscribe:", "Enter number:")
    if not chosen_str: return
    
    choice_index = episode_choices.index(chosen_str)
    selected_episode = episodes[choice_index]
    
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

    choice_index = episode_choices.index(chosen_str)
    selected_episode = episodes[choice_index]

    print(f"\nGenerating summary and chapters for: {selected_episode['episode_title']}...")
    generate_summary_and_chapters(campaign_folder_path, selected_episode['episode_id'])
    
    print("\nCollating all campaign summaries...")
    collate_summaries(campaign_folder_path)
    print("\nRe-summarisation process complete.")