import os
import re
from datetime import datetime

# ## FIX: All high-level imports are REMOVED to break the circular dependency.
# from .summarisation import collate_summaries, generate_summary_and_chapters
# from .transcription import transcribe_and_revise_audio
from . import user_interaction, database_management as db
from .utils import get_working_directory, config, CampaignContext

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
        folder_basenames = [os.path.basename(f) for f in audio_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Audio Files' found. Please select one:",
        )
        return os.path.join(campaign_folder_path, chosen_basename) if chosen_basename else None

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
        folder_basenames = [os.path.basename(f) for f in trans_folders]
        chosen_basename = user_interaction.choose_from_list(
            folder_basenames,
            "Multiple folders with 'Transcriptions' found. Please select one:",
        )
        return os.path.join(campaign_folder_path, chosen_basename) if chosen_basename else None

def generate_new_campaign(campaign_name, abbreviation, base_directory):
    """Generates a new campaign directory structure and initializes its database and dictionary files."""
    campaign_folder_abs = os.path.join(base_directory, campaign_name)
    if os.path.exists(campaign_folder_abs):
        print(f"Error: A directory named '{campaign_name}' already exists.")
        return None

    print(f"Creating new campaign '{campaign_name}'...")
    try:
        os.makedirs(os.path.join(campaign_folder_abs, f"{abbreviation} Audio Files"), exist_ok=True)
        os.makedirs(os.path.join(campaign_folder_abs, f"{abbreviation} Transcriptions"), exist_ok=True)
        
        db.init_campaign_db(campaign_folder_abs)
        
        context = CampaignContext(campaign_folder_abs)
        _ = context.custom_words
        _ = context.corrections_dict

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