import datetime
import ffmpeg
import json
import math
import os
import re
import subprocess

from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC
from mutagen.wave import WAVE

from .utils import get_working_directory, config
from .file_management import find_audio_files_folder
from . import user_interaction, database_management as db
from .database_management import DATABASE_NAME

def convert_to_m4a(campaign_path, file_path, title):
    """
    Convert an audio file to m4a, normalize, apply metadata, and create a new episode record in the DB.
    This function is now safer, only creating a DB record after a successful conversion.
    Returns the episode_id of the newly created record, or None on failure.
    """
    ## C-IMPROVEMENT: The logic has been restructured to be safer.
    ## Conversion happens BEFORE database interaction to prevent orphaned records.

    # --- 1. Prepare all conversion parameters ---
    input_dir_abs, input_filename = os.path.split(os.path.abspath(file_path))

    try:
        probe_data = ffmpeg.probe(file_path)
        input_duration = float(probe_data['format']['duration'])
    except (ffmpeg.Error, KeyError) as e:
        print(f"Error probing file {file_path}: {e}. Cannot convert.")
        return None

    try:
        file_mtime = os.path.getmtime(file_path)
        file_date_from_mtime = datetime.datetime.fromtimestamp(file_mtime)
    except OSError:
        file_date_from_mtime = datetime.datetime.now()

    target_size_mb = config["general"].get("ffmpeg_target_size_mb", 50)
    target_size_bytes = target_size_mb * 1024 * 1024
    min_bitrate = config["general"].get("minimum_bitrate_kbps", 64)
    max_bitrate = 256
    
    calculated_bitrate_kbps = math.floor((target_size_bytes * 8) / (input_duration * 1000))
    target_bitrate_kbps = max(min_bitrate, min(calculated_bitrate_kbps, max_bitrate))

    campaign_name = os.path.basename(campaign_path)
    base_name_no_ext = os.path.splitext(input_filename)[0]
    date_match = re.match(r"(\d{4}_\d{2}_\d{2})", base_name_no_ext)
    file_date_str = date_match.group(1) if date_match else file_date_from_mtime.strftime("%Y_%m_%d")
    clean_base_name = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", base_name_no_ext).replace("_norm", "")

    part_match = re.search(r'[_-][Pp](?:art)?(\d+)', clean_base_name)
    part_suffix = f"_p{part_match.group(1)}" if part_match else ""
    if part_match:
        clean_base_name = re.sub(r'[_-][Pp](?:art)?\d+', '', clean_base_name).strip(" _-")

    output_filename_base = f"{file_date_str}_{clean_base_name}{part_suffix}_norm"
    output_filename = f"{output_filename_base}.m4a"
    output_path_abs = os.path.join(input_dir_abs, output_filename)

    # --- 2. Execute FFmpeg Conversion ---
    print(f"Encoding '{input_filename}' to '{output_filename}' at {target_bitrate_kbps}k...")
    try:
        (
            ffmpeg
            .input(file_path)
            .filter("loudnorm", i=-14, tp=-1.0, print_format='json') 
            .output(
                output_path_abs, acodec='aac', ab=f"{target_bitrate_kbps}k",
                ac=config["podcasts"]["audio_channels"], ar=config["podcasts"]["sampling_rate"]
            )
            .overwrite_output().run(cmd=config["general"].get("ffmpeg_path", "ffmpeg"), capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        # Provide more useful feedback on failure
        print(f"\n--- FFmpeg Conversion ERROR ---")
        print(f"Failed to convert '{input_filename}'.")
        print(f"FFmpeg STDERR:\n{e.stderr.decode('utf8', errors='ignore') if e.stderr else 'No stderr output.'}")
        print(f"-----------------------------\n")
        return None
    except FileNotFoundError:
        print("Error: ffmpeg command not found. Ensure it's in your system's PATH or configured correctly in config.json.")
        return None

    # --- 3. Create Database Record (only after successful conversion) ---
    episode_data = {
        'episode_title': title,
        'base_episode_title': re.sub(r'\s*\(Part \d+\)$', '', title, flags=re.IGNORECASE).strip(),
        'recorded_date': file_date_from_mtime.date().isoformat(),
        'episode_length_seconds': input_duration,
        'original_audio_file': file_path,
        'season_number': 1
    }
    episode_id = db.add_episode(campaign_path, episode_data)
    if not episode_id:
        print("FFmpeg conversion succeeded, but failed to create a database record. Aborting.")
        # We could potentially delete the output file here, but it's safer to leave it for manual recovery.
        return None
    
    # --- 4. Apply Metadata and Finalize DB ---
    new_episode = db.get_episode_by_id(campaign_path, episode_id)
    track_number = new_episode['episode_number']

    metadata = {
        "title": title,
        "artist": config["podcasts"]["artist_name"],
        "album": campaign_name,
        "genre": config["podcasts"]["genre"],
        "date": str(file_date_from_mtime.year),
        "tracknumber": str(track_number)
    }

    apply_metadata(output_path_abs, metadata)
    
    db.update_episode_path(campaign_path, episode_id, "normalized_audio_file", output_path_abs)
    db.update_processing_status(
        campaign_path, episode_id,
        normalized=True,
        normalized_bitrate=target_bitrate_kbps
    )

    print(f"Successfully converted '{input_filename}' and created Episode #{track_number}.")
    return episode_id


def search_audio_files():
    """Searches working directory for audio files not yet in any campaign DB."""
    ## It loads all tracked paths from all databases ONCE, then checks against that set.
    working_dir = get_working_directory()
    
    # 1. First, build a master set of all audio files already tracked by any database.
    all_tracked_paths = set()
    all_campaign_paths = [os.path.join(working_dir, d) for d in os.listdir(working_dir) if os.path.isdir(os.path.join(working_dir, d))]
    
    for camp_path in all_campaign_paths:
        db_file = os.path.join(camp_path, DATABASE_NAME)
        if os.path.exists(db_file):
            try:
                conn = db.get_db_connection(camp_path)
                # Fetch both original and normalized file paths
                cursor = conn.execute("SELECT original_audio_file, normalized_audio_file FROM Episodes")
                for row in cursor:
                    if row['original_audio_file']:
                        all_tracked_paths.add(os.path.abspath(os.path.join(camp_path, row['original_audio_file'])))
                    if row['normalized_audio_file']:
                        all_tracked_paths.add(os.path.abspath(os.path.join(camp_path, row['normalized_audio_file'])))
                conn.close()
            except Exception as e:
                print(f"Warning: Could not read database for campaign '{os.path.basename(camp_path)}': {e}")

    # 2. Now, walk the file system and find untracked files.
    audio_files_found = []
    days_to_scan = config["general"].get("recent_files_scan_days", 100)
    cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_to_scan)
    supported_extensions = tuple(config["general"].get("supported_audio_extensions", [".wav", ".m4a", ".flac", ".mp3"]))
    
    for root, _, files in os.walk(working_dir):
        # A simple way to avoid searching in already processed folders
        if "_norm" in root or "Transcription" in root or "Summaries" in root:
            continue
        
        for file_name in files:
            # Check extension and avoid already-normalized files by name
            if file_name.lower().endswith(supported_extensions) and "_norm" not in file_name.lower():
                file_path_abs = os.path.abspath(os.path.join(root, file_name))
                
                # The efficient check: is the file's path in our master set?
                if file_path_abs not in all_tracked_paths:
                    try:
                        file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path_abs))
                        if file_modified_time >= cutoff_time:
                            audio_files_found.append((file_path_abs, file_modified_time))
                    except OSError:
                        continue

    # Sort by modification time (most recent first) and return the top 20
    audio_files_found.sort(key=lambda x: x[1], reverse=True)
    return [file_path for file_path, _ in audio_files_found[:20]]

def bulk_normalize_audio(campaign_folder_path):
    """Normalizes all non-normalized audio files in a campaign's audio folder."""
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in campaign '{os.path.basename(campaign_folder_path)}'.")
        return
        
    all_audio_in_folder = [
        f for f in os.listdir(audio_files_folder)
        if f.lower().endswith(tuple(config["general"].get("supported_audio_extensions", []))) and "_norm" not in f.lower()
    ]

    # This check is efficient for a single campaign context.
    conn = db.get_db_connection(campaign_folder_path)
    tracked_originals = {row['original_audio_file'] for row in conn.execute("SELECT original_audio_file FROM Episodes WHERE original_audio_file IS NOT NULL").fetchall()}
    conn.close()

    files_to_process = []
    for f in all_audio_in_folder:
        file_path_abs = os.path.join(audio_files_folder, f)
        # Use absolute path for comparison to avoid ambiguity
        if file_path_abs not in tracked_originals:
            files_to_process.append(f)
    
    if not files_to_process:
        print(f"No new, un-normalized audio files found in {audio_files_folder}.")
        return
    
    print(f"\nStarting bulk normalization for {len(files_to_process)} files in '{os.path.basename(campaign_folder_path)}'.")

    for filename in files_to_process:
        file_path_abs = os.path.join(audio_files_folder, filename)
        
        # Derive a sensible default title from the filename
        default_title_base = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", os.path.splitext(filename)[0])
        default_title_base = re.sub(r'[_-][Pp](?:art)?\d+', '', default_title_base)
        default_title = default_title_base.replace("_", " ").strip()
        
        print(f"\nNormalizing '{filename}' with derived title: '{default_title}'")
        # This now calls the safer, refactored version of convert_to_m4a
        convert_to_m4a(campaign_folder_path, file_path_abs, default_title)
            
    print("\nBulk normalization process finished.")

def apply_metadata(file_path_abs, metadata_dict):
    """Applies metadata to various audio file formats using mutagen."""
    if not os.path.exists(file_path_abs):
        print(f"Error applying metadata: File not found - {file_path_abs}")
        return False
        
    ext = os.path.splitext(file_path_abs)[1].lower()
    audio = None
    save_needed = False
    
    try:
        # Load the audio file based on its extension
        if ext == ".mp3":
            audio = EasyID3(file_path_abs)
        elif ext == ".m4a":
            audio = MP4(file_path_abs)
        elif ext == ".flac":
            audio = FLAC(file_path_abs)
        else:
            print(f"Warning: Metadata application not supported for '{ext}' files.")
            return False

        # Map our standard metadata keys to the format-specific tags
        m4a_map = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "genre": "\xa9gen", "date": "\xa9day", "tracknumber": "trkn"}
        
        for key, value in metadata_dict.items():
            if ext == ".m4a":
                m4a_key = m4a_map.get(key.lower())
                if m4a_key:
                    # Special handling for M4A track numbers
                    new_val = [(int(value.split('/')[0]), 0)] if m4a_key == "trkn" and value else [value]
                    if audio.get(m4a_key) != new_val:
                        audio[m4a_key] = new_val
                        save_needed = True
            else: # For MP3 and FLAC
                tag_key = key.lower() if ext == ".mp3" else key.upper()
                if audio.get(tag_key) != [value]:
                    audio[tag_key] = [value]
                    save_needed = True
        
        if audio and save_needed:
            audio.save()
            print(f"Metadata successfully applied to {os.path.basename(file_path_abs)}.")
        elif audio and not save_needed:
             print(f"Metadata for {os.path.basename(file_path_abs)} is already up to date.")
        return True

    except Exception as e:
        print(f"Error applying metadata to {os.path.basename(file_path_abs)}: {e}")
        return False