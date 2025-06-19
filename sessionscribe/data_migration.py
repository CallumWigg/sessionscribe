import os
import re
import json
from datetime import datetime

import ffmpeg

from . import file_management
from . import database_management as db
from .utils import config

def run_migration_for_campaign(campaign_path):
    """
    Scans a campaign folder and creates or updates database records from existing files.
    This function now lives in its own module to prevent circular dependencies.
    """
    print(f"\nRunning data migration check for campaign: '{os.path.basename(campaign_path)}'...")
    db_path = db.init_campaign_db(campaign_path)
    if not db_path: return

    trans_folder = file_management.find_transcriptions_folder(campaign_path)
    audio_folder = file_management.find_audio_files_folder(campaign_path)

    if not trans_folder:
        print("No 'Transcriptions' folder found. Migration skipped.")
        return

    # Use the revised transcript as the "source of truth" for what episodes exist
    for filename in os.listdir(trans_folder):
        if filename.endswith("_norm_revised.txt"):
            revised_txt_path = os.path.join(trans_folder, filename)
            episode = db.get_episode_by_transcript_path(campaign_path, revised_txt_path)
            
            updates_to_perform = {}
            status_updates = {}

            normalized_basename = filename.replace("_revised.txt", "")
            base_for_derivatives = filename.replace(".txt", "")

            norm_m4a_path = os.path.join(audio_folder, f"{normalized_basename}.m4a") if audio_folder else None
            if norm_m4a_path and os.path.exists(norm_m4a_path):
                status_updates['normalized'] = True
                updates_to_perform['normalized_audio_file'] = os.path.relpath(norm_m4a_path, campaign_path)
                try:
                    probe = ffmpeg.probe(norm_m4a_path)
                    updates_to_perform['episode_length_seconds'] = float(probe['format']['duration'])
                    updates_to_perform['metadata'] = json.dumps(probe.get('format', {}).get('tags', {}))
                except Exception as e:
                    print(f"  Warning: Could not probe {os.path.basename(norm_m4a_path)}: {e}")

                if not episode or not episode['original_audio_file']:
                    # C-IMPROVEMENT: Calling the function from its new, correct location.
                    original_audio_path = file_management.find_original_audio(audio_folder, normalized_basename)
                    if original_audio_path:
                        updates_to_perform['original_audio_file'] = os.path.relpath(original_audio_path, campaign_path)

            status_updates['text_processed'] = True
            tsv_path = os.path.join(trans_folder, f"{normalized_basename}.tsv")
            if os.path.exists(tsv_path):
                 status_updates['transcribed'] = True
                 status_updates['transcribed_date'] = datetime.fromtimestamp(os.path.getmtime(tsv_path))

            summary_path = os.path.join(trans_folder, f"{base_for_derivatives}_summary.txt")
            if os.path.exists(summary_path):
                updates_to_perform['summary_file'] = os.path.relpath(summary_path, campaign_path)
                status_updates['summarized'] = True
            
            chapters_path = os.path.join(trans_folder, f"{base_for_derivatives}_chapters.txt")
            if os.path.exists(chapters_path):
                updates_to_perform['chapters_file'] = os.path.relpath(chapters_path, campaign_path)
                status_updates['chapters_generated'] = True

            subtitle_path = os.path.join(trans_folder, f"{base_for_derivatives}_subtitle.txt")
            if os.path.exists(subtitle_path):
                updates_to_perform['subtitle_file'] = os.path.relpath(subtitle_path, campaign_path)
                status_updates['subtitles_generated'] = True

            if episode:
                print(f"  Checking/updating existing record for: {filename}")
                episode_id = episode['episode_id']
                if updates_to_perform:
                    db.update_episode_data(campaign_path, episode_id, updates_to_perform)
                update_processing_status(campaign_path, episode_id, **status_updates)
            else:
                print(f"  Migrating new record for: {filename}")
                new_episode_data = updates_to_perform
                new_episode_data['transcription_file'] = os.path.relpath(revised_txt_path, campaign_path)

                with open(revised_txt_path, 'r', encoding='utf-8') as f:
                    header = f.readline().strip()
                    # A more robust regex to handle titles that might contain numbers
                    title_match = re.match(r"(.*) - #(\d+)$", header)
                    if title_match:
                        title = title_match.group(1).strip()
                    else:
                        # Fallback to deriving title from filename
                        title = normalized_basename.replace("_norm","").replace("_"," ")
                
                new_episode_data['episode_title'] = title
                new_episode_data['base_episode_title'] = re.sub(r'\s*\(Part \d+\)$', '', title, flags=re.IGNORECASE).strip()
                
                date_match = re.match(r"(\d{4}_\d{2}_\d{2})", normalized_basename)
                if date_match:
                    new_episode_data['recorded_date'] = datetime.strptime(date_match.group(1), "%Y_%m_%d").date()

                episode_id = db.add_episode(campaign_path, new_episode_data)
                if episode_id:
                    db.update_processing_status(campaign_path, episode_id, **status_updates)

    print("Migration check complete.")