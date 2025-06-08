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
from mutagen.wave import WAVE # For WAVE, metadata support is limited with mutagen

from .utils import get_working_directory, config # Assuming utils.py for config
from .file_management import find_audio_files_folder # Assuming file_management.py
from . import user_interaction # Assuming user_interaction.py

def convert_to_m4a(file_path, title):
    """Convert an audio file to m4a format, normalize, and apply metadata.
    Returns the absolute path to the output m4a file, or None on failure.
    """
    input_dir_abs, input_filename = os.path.split(os.path.abspath(file_path))
    
    try:
        probe_data = ffmpeg.probe(file_path)
        input_duration = float(probe_data['format']['duration'])
    except ffmpeg.Error as e:
        print(f"Error probing file {file_path}: {e}. Cannot convert.")
        return None
    except KeyError:
        print(f"Could not determine duration for {file_path}. Cannot convert accurately.")
        return None

    try:
        file_mtime = os.path.getmtime(file_path)
        year = datetime.datetime.fromtimestamp(file_mtime).year
        file_date_from_mtime = datetime.datetime.fromtimestamp(file_mtime).strftime("%Y_%m_%d")
    except OSError:
        year = datetime.datetime.now().year
        file_date_from_mtime = datetime.datetime.now().strftime("%Y_%m_%d")


    target_size_mb = config["general"].get("ffmpeg_target_size_mb", 50) # Default if not in config
    target_size_bytes = target_size_mb * 1024 * 1024
    # Ensure bitrate isn't excessively low or high
    min_bitrate = config["general"].get("minimum_bitrate_kbps", 64)
    max_bitrate = 256 # Sensible max for AAC speech
    
    calculated_bitrate_kbps = math.floor((target_size_bytes * 8) / (input_duration * 1000)) # kbps needs *1000 not *1024 for duration
    target_bitrate_kbps = max(min_bitrate, min(calculated_bitrate_kbps, max_bitrate))


    # Determine campaign name from directory structure if possible
    # Example: file_path is .../CampaignName/Audio Files/audio.wav
    # input_dir_abs is .../CampaignName/Audio Files
    # os.path.dirname(input_dir_abs) is .../CampaignName
    campaign_name_default = os.path.basename(os.path.dirname(input_dir_abs))
    # If "Audio Files" is not part of input_dir_abs, campaign_name might be input_dir_abs itself
    if "Audio Files" not in os.path.basename(input_dir_abs) and "Transcriptions" not in os.path.basename(input_dir_abs) :
         campaign_name_default = os.path.basename(input_dir_abs)


    # Filename components
    base_name_no_ext = os.path.splitext(input_filename)[0]
    
    # Try to extract date from filename, else use mtime-derived date
    date_match = re.match(r"(\d{4}_\d{2}_\d{2})", base_name_no_ext)
    file_date_str = date_match.group(1) if date_match else file_date_from_mtime
    
    # Clean base_name_no_ext for use in output, remove existing date prefix if present
    clean_base_name = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", base_name_no_ext)
    clean_base_name = clean_base_name.replace("_norm", "") # Remove if re-processing

    # Handle part numbers if present (e.g., _p1, _part1)
    part_match = re.search(r'[_-][Pp](?:art)?(\d+)', clean_base_name)
    part_suffix = ""
    if part_match:
        part_number = part_match.group(1)
        part_suffix = f"_p{part_number}"
        # Remove the part string from clean_base_name to avoid duplication
        clean_base_name = re.sub(r'[_-][Pp](?:art)?\d+', '', clean_base_name)
        clean_base_name = clean_base_name.strip(" _-")


    output_filename_base = f"{file_date_str}_{clean_base_name}{part_suffix}_norm"
    output_filename = f"{output_filename_base}.m4a"
    output_path_abs = os.path.join(input_dir_abs, output_filename)


    # Track Number Logic: Sort all _norm.m4a files in the dir and find index
    all_norm_files_in_dir = sorted([
        f for f in os.listdir(input_dir_abs)
        if f.endswith("_norm.m4a") and f != output_filename # Exclude self if overwriting for sorting
    ])
    
    # Hypothetical list including the current file to find its place
    hypothetical_sorted_list = sorted(all_norm_files_in_dir + [output_filename])
    try:
        track_number = hypothetical_sorted_list.index(output_filename) + 1
    except ValueError: # Should not happen if output_filename is in the list
        track_number = len(hypothetical_sorted_list) # Fallback

    metadata = {
        "title": title,
        "artist": config["podcasts"]["artist_name"],
        "albumartist": config["podcasts"]["artist_name"], # Often same as artist
        "album": campaign_name_default, # Use derived campaign name
        "genre": config["podcasts"]["genre"],
        "date": str(year), # Year of original file mtime
        "tracknumber": str(track_number)
        # Add comment/description if desired: "comment": f"Normalized on {datetime.datetime.now().strftime('%Y-%m-%d')}"
    }

    print(f"Encoding '{input_filename}' to '{output_filename}' at {target_bitrate_kbps}k...")
    try:
        (
            ffmpeg
            .input(file_path)
            .filter("loudnorm") # Integrated loudness normalization
            .output(
                output_path_abs,
                acodec='aac', # M4A uses AAC
                ab=f"{target_bitrate_kbps}k",
                ac=config["podcasts"]["audio_channels"],
                ar=config["podcasts"]["sampling_rate"],
                # Add metadata directly during ffmpeg encoding if possible for M4A
                # metadata:title=value doesn't work for all tags with -metadata flag for m4a
                # So we use mutagen after.
            )
            .overwrite_output()
            .run(cmd=config["general"].get("ffmpeg_path", "ffmpeg")) # Use configured ffmpeg path
        )
    except ffmpeg.Error as e:
        print(f"FFmpeg conversion error: {e.stderr.decode() if e.stderr else e}")
        return None
    except FileNotFoundError:
        print(f"Error: ffmpeg command not found. Ensure ffmpeg is installed and in your system's PATH, or configure 'ffmpeg_path' in config.json.")
        return None


    # Apply metadata using mutagen (more reliable for various tags)
    apply_metadata(output_path_abs, metadata)

    print(f"Successfully converted and normalized '{input_filename}' to '{output_filename}'.")
    return output_path_abs


def search_audio_files():
    """
    Searches working directory for audio files modified in the last 100 days,
    excluding those that seem to have a corresponding _norm.m4a file in the same directory.
    Returns a list of absolute file paths, newest first, max 20.
    """
    audio_files_found = []
    # Use a more specific time window from config if available, else default
    days_to_scan = config["general"].get("recent_files_scan_days", 100)
    cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_to_scan)
    
    # Supported extensions (can be from config)
    supported_extensions = tuple(config["general"].get("supported_audio_extensions", [".wav", ".m4a", ".flac", ".mp3"]))
    
    working_dir = get_working_directory()
    if not os.path.isdir(working_dir):
        print(f"Warning: Working directory '{working_dir}' not found. Cannot search for audio files.")
        return []

    for root, _, files in os.walk(working_dir):
        # Avoid walking into "x " or hidden folders at the root of working_dir
        if root == working_dir:
            dir_basename = os.path.basename(root) # This is confusing.
            # We want to filter subdirectories of working_dir, not root itself.
            # This logic needs to be applied to `dirs` in os.walk if we want to prune.
            # For now, let it walk, then filter based on norm file existence.
            pass

        for file_name in files:
            if file_name.lower().endswith(supported_extensions) and "_norm" not in file_name.lower():
                file_path_abs = os.path.join(root, file_name)
                
                # Check if a _norm.m4a version exists in the same directory
                base_name_no_ext = os.path.splitext(file_name)[0]
                # A more robust check for norm file: YYYY_MM_DD_originalbase_norm.m4a or originalbase_norm.m4a
                # This simplified check might miss some if naming isn't strict
                # A more precise way: after potential conversion, the norm file would have a predictable name.
                # Here, we just check if *any* file starting with base_name_no_ext and ending with _norm.m4a exists.
                
                # Simplified: look for a file that looks like 'originalbasename_pX_norm.m4a' or 'originalbasename_norm.m4a'
                # This is still heuristic.
                norm_candidate_pattern = re.compile(rf"^{re.escape(base_name_no_ext)}(_p\d+)?_norm\.m4a$", re.IGNORECASE)
                
                has_norm_version = any(norm_candidate_pattern.match(f) for f in os.listdir(root))

                if not has_norm_version:
                    try:
                        file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path_abs))
                        if file_modified_time >= cutoff_time:
                            audio_files_found.append((file_path_abs, file_modified_time))
                    except OSError:
                        continue # Skip if mtime can't be read

    # Sort by modification time (newest first)
    audio_files_found.sort(key=lambda x: x[1], reverse=True)

    return [file_path for file_path, _ in audio_files_found[:20]] # Return top 20 absolute paths


def calculate_target_bitrate(file_path_abs):
    """Calculates the target bitrate based on file duration and desired file size from config."""
    try:
        probe_data = ffmpeg.probe(file_path_abs)
        input_duration_seconds = float(probe_data['format']['duration'])
    except (ffmpeg.Error, KeyError):
        print(f"Warning: Could not get duration for {os.path.basename(file_path_abs)}. Using default bitrate.")
        return config["general"].get("minimum_bitrate_kbps", 64) # Default if probe fails

    target_size_mb = config["general"].get("ffmpeg_target_size_mb", 50)
    target_size_bytes = target_size_mb * 1024 * 1024
    
    if input_duration_seconds == 0: # Avoid division by zero
        return config["general"].get("minimum_bitrate_kbps", 64)

    # Bitrate (kbps) = (Size in Bytes * 8) / (Duration in Seconds * 1000)
    calculated_bitrate_kbps = math.floor((target_size_bytes * 8) / (input_duration_seconds * 1000))
    
    min_bitrate = config["general"].get("minimum_bitrate_kbps", 64)
    # max_bitrate could also be in config, e.g., 256 for AAC speech
    
    return max(min_bitrate, calculated_bitrate_kbps)


def split_audio_file(file_path_abs):
    """Splits a long audio file into multiple parts based on calculated max duration per part.
    User is prompted for split timecodes. Returns list of output part file paths.
    """
    try:
        probe_data = ffmpeg.probe(file_path_abs)
        input_duration_seconds = float(probe_data['format']['duration'])
    except (ffmpeg.Error, KeyError) as e:
        print(f"Error probing audio file {os.path.basename(file_path_abs)}: {e}. Cannot split.")
        return [file_path_abs] # Return original if cannot determine duration

    min_bitrate_kbps = config["general"]["minimum_bitrate_kbps"]
    target_size_mb = config["general"]["ffmpeg_target_size_mb"]
    target_size_bytes = target_size_mb * 1024 * 1024

    if min_bitrate_kbps == 0: # Avoid division by zero
        print("Error: Minimum bitrate is 0. Cannot calculate split parts.")
        return [file_path_abs]

    # Max duration (seconds) per part = (Target Size in Bytes * 8) / (Min Bitrate kbps * 1000)
    max_duration_per_part_seconds = (target_size_bytes * 8) / (min_bitrate_kbps * 1000)

    if max_duration_per_part_seconds == 0:
        print("Error: Calculated max duration per part is 0. Cannot split.")
        return [file_path_abs]
        
    num_parts_needed = math.ceil(input_duration_seconds / max_duration_per_part_seconds)

    if num_parts_needed <= 1:
        print("File duration is within acceptable limits for a single part. No split needed.")
        return [file_path_abs] # No split needed

    print(f"\nFile '{os.path.basename(file_path_abs)}' is long ({input_duration_seconds / 3600:.2f} hours).")
    print(f"To maintain quality (min {min_bitrate_kbps} kbps at ~{target_size_mb}MB/part),")
    print(f"it's suggested to split into {num_parts_needed} parts, each approx. {max_duration_per_part_seconds / 3600:.2f} hours.")

    if not user_interaction.get_yes_no_input("Do you want to split this file now?", default="y"):
        return [file_path_abs] # User chose not to split

    # Open audio player for user to identify split points
    print(f"Please open '{os.path.basename(file_path_abs)}' in an audio player to find split points.")
    try:
        if os.name == 'nt': os.startfile(file_path_abs)
        elif os.name == 'posix': subprocess.call(('open', file_path_abs))
    except Exception as e:
        print(f"Warning: Could not automatically open audio player: {e}")

    output_parts_paths = []
    current_start_time_seconds = 0
    input_dir, input_filename = os.path.split(file_path_abs)
    base_name, ext = os.path.splitext(input_filename)

    for i in range(num_parts_needed -1 ): # Need num_parts - 1 split points
        while True:
            split_time_str = input(f"Enter split timecode for end of part {i+1} (e.g., HH:MM:SS or MM:SS or SSS): ")
            try:
                time_parts = list(map(int, split_time_str.split(':')))
                if len(time_parts) == 3: # HH:MM:SS
                    split_point_seconds = time_parts[0]*3600 + time_parts[1]*60 + time_parts[2]
                elif len(time_parts) == 2: # MM:SS
                    split_point_seconds = time_parts[0]*60 + time_parts[1]
                elif len(time_parts) == 1: # SSS
                    split_point_seconds = time_parts[0]
                else:
                    raise ValueError("Invalid timecode format.")
                
                if split_point_seconds <= current_start_time_seconds or split_point_seconds >= input_duration_seconds:
                    print("Split time must be after previous split and before end of file. Try again.")
                else:
                    break # Valid split point
            except ValueError as e:
                print(f"Invalid input: {e}. Please use HH:MM:SS, MM:SS, or SSS format.")
        
        output_part_filename = f"{base_name}_p{i+1}{ext}"
        output_part_path = os.path.join(input_dir, output_part_filename)
        
        print(f"Creating part {i+1}: {output_part_filename} (from {current_start_time_seconds}s to {split_point_seconds}s)")
        try:
            (ffmpeg.input(file_path_abs, ss=current_start_time_seconds, to=split_point_seconds)
             .output(output_part_path, c='copy') # Fast copy if format doesn't change
             .overwrite_output()
             .run(cmd=config["general"].get("ffmpeg_path", "ffmpeg")))
            output_parts_paths.append(output_part_path)
            current_start_time_seconds = split_point_seconds
        except ffmpeg.Error as e:
            print(f"Error splitting part {i+1}: {e.stderr.decode() if e.stderr else e}")
            if not user_interaction.get_yes_no_input("Continue splitting remaining parts?", default="n"):
                return [file_path_abs] # Return original if user aborts
        except FileNotFoundError:
             print(f"Error: ffmpeg command not found. Cannot split.")
             return [file_path_abs]


    # Create the last part (from last split point to end of file)
    last_part_filename = f"{base_name}_p{num_parts_needed}{ext}"
    last_part_path = os.path.join(input_dir, last_part_filename)
    print(f"Creating last part {num_parts_needed}: {last_part_filename} (from {current_start_time_seconds}s to end)")
    try:
        (ffmpeg.input(file_path_abs, ss=current_start_time_seconds)
         .output(last_part_path, c='copy')
         .overwrite_output()
         .run(cmd=config["general"].get("ffmpeg_path", "ffmpeg")))
        output_parts_paths.append(last_part_path)
    except ffmpeg.Error as e:
        print(f"Error creating last part: {e.stderr.decode() if e.stderr else e}")
    except FileNotFoundError:
        print(f"Error: ffmpeg command not found. Cannot create last part.")


    if output_parts_paths:
        print("File splitting complete.")
        if user_interaction.get_yes_no_input("Delete original large file after splitting?", default="n"):
            try:
                os.remove(file_path_abs)
                print(f"Original file '{os.path.basename(file_path_abs)}' deleted.")
            except OSError as e:
                print(f"Error deleting original file: {e}")
        return output_parts_paths
    else:
        print("File splitting failed or was aborted.")
        return [file_path_abs] # Return original if no parts were successfully created

def bulk_normalize_audio(campaign_folder_path, all_or_missing_mode="a. All"):
    """Normalizes audio files in a specified campaign folder.
    all_or_missing_mode: "a. All" or "m. Missing" (skip if _norm.m4a exists)
    """
    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in campaign '{os.path.basename(campaign_folder_path)}'.")
        return

    # Option for FLAC conversion is more of a one-time utility, maybe separate
    # For now, let's focus on normalization to M4A.
    # If FLAC update is desired, it's a different flow.

    audio_files_to_process = [
        f for f in os.listdir(audio_files_folder)
        if f.lower().endswith(tuple(config["general"].get("supported_audio_extensions", [".wav", ".m4a", ".flac", ".mp3"])))
        and "_norm" not in f.lower() # Process non-normalized files
    ]

    if not audio_files_to_process:
        print(f"No suitable non-normalized audio files found in {audio_files_folder}.")
        return
    
    print(f"\nStarting bulk normalization for campaign '{os.path.basename(campaign_folder_path)}' (Mode: {all_or_missing_mode}).")

    for filename in audio_files_to_process:
        file_path_abs = os.path.join(audio_files_folder, filename)
        
        # For "missing" mode, check if a _norm.m4a version already exists.
        # The convert_to_m4a function will generate a predictable _norm.m4a name.
        # We need to predict that name here to check for "missing".
        # This is a bit duplicative of logic in convert_to_m4a for filename generation.
        # Simplified check: if any file like basename_norm.m4a exists.
        base_name_no_ext = os.path.splitext(filename)[0]
        # A more robust check would try to form the exact expected norm filename
        # For now, a simpler heuristic for "missing":
        potential_norm_pattern = re.compile(rf"^{re.escape(base_name_no_ext)}(_p\d+)?_norm\.m4a$", re.IGNORECASE)
        norm_exists = any(potential_norm_pattern.match(f_existing) for f_existing in os.listdir(audio_files_folder))

        if all_or_missing_mode == "m. Missing" and norm_exists:
            print(f"Skipping '{filename}' (normalized version likely already exists).")
            continue

        # Extract a default title from filename (strip date, _norm, parts)
        default_title_base = re.sub(r"^\d{4}_\d{2}_\d{2}_?", "", base_name_no_ext)
        default_title_base = re.sub(r'[_-][Pp](?:art)?\d+', '', default_title_base) # Remove part indicators
        default_title = default_title_base.replace("_", " ").strip()
        
        # For bulk, usually don't prompt for title for each. Use derived title.
        # If interactive title is needed, this function needs a flag.
        print(f"Normalizing '{filename}' with derived title: '{default_title}'")
        
        # Check if file needs splitting before conversion
        bitrate_for_original = calculate_target_bitrate(file_path_abs)
        if bitrate_for_original < config["general"]["minimum_bitrate_kbps"]:
            print(f"File '{filename}' may result in low bitrate ({bitrate_for_original} kbps).")
            split_files_paths = split_audio_file(file_path_abs) # This prompts user
            
            for i, part_path in enumerate(split_files_paths):
                part_basename = os.path.basename(part_path)
                part_title = f"{default_title} (Part {i+1})" if len(split_files_paths) > 1 else default_title
                print(f"Converting split part: {part_basename} with title '{part_title}'")
                convert_to_m4a(part_path, part_title)
                if part_path != file_path_abs and os.path.exists(part_path) and len(split_files_paths) > 1:
                    # If split_audio_file didn't delete the part source (if it was an intermediate split)
                    # And if convert_to_m4a doesn't delete its source.
                    # Usually, source of convert_to_m4a (the part) should be kept or handled by user.
                    pass
        else: # No splitting needed
            convert_to_m4a(file_path_abs, default_title)
            
    print("\nBulk normalization process finished.")


def apply_metadata(file_path_abs, metadata_dict):
    """Applies metadata to various audio file formats using mutagen.
    file_path_abs: Absolute path to the audio file.
    metadata_dict: Dictionary of metadata tags (e.g., {"title": "My Title", "artist": "Me"}).
    Returns True if successful, False otherwise.
    """
    if not os.path.exists(file_path_abs):
        print(f"Error applying metadata: File not found - {file_path_abs}")
        return False

    ext = os.path.splitext(file_path_abs)[1].lower()
    audio = None
    save_needed = False

    try:
        if ext == ".mp3":
            audio = EasyID3(file_path_abs)
            # EasyID3 uses specific keys like 'title', 'artist', 'album', 'tracknumber'
            for key, value in metadata_dict.items():
                if key.lower() in audio: # Check if tag exists before assigning
                     if audio[key.lower()] != [value]: audio[key.lower()] = [value]; save_needed = True
                else: # Add new tag
                     audio[key.lower()] = [value]; save_needed = True

        elif ext == ".m4a":
            audio = MP4(file_path_abs)
            # M4A (MP4) uses specific internal keys (often starting with ©)
            # See mutagen MP4 documentation for exact keys: e.g. ©nam, ©ART, ©alb, trkn
            m4a_map = {
                "title": "\xa9nam", "artist": "\xa9ART", "albumartist": "aART",
                "album": "\xa9alb", "genre": "\xa9gen", "date": "\xa9day",
                "tracknumber": "trkn" # Tuple: (number, total_tracks) e.g. [(1, 0)] for track 1 of unknown total
            }
            for key, value in metadata_dict.items():
                m4a_key = m4a_map.get(key.lower())
                if m4a_key:
                    current_val = audio.get(m4a_key)
                    new_val = [(int(value.split('/')[0]), 0) if '/' in value else (int(value),0)] if m4a_key == "trkn" and value else [value]

                    if current_val != new_val : audio[m4a_key] = new_val; save_needed = True


        elif ext == ".flac":
            audio = FLAC(file_path_abs)
            # FLAC uses Vorbis comments (key=value strings)
            for key, value in metadata_dict.items():
                # FLAC keys are case-insensitive usually, but convention is uppercase
                # mutagen stores them as list of strings for each key
                tag_key = key.upper() 
                if audio.get(tag_key) != [value]: audio[tag_key] = [value]; save_needed = True


        elif ext == ".wav":
            # WAV metadata is tricky. RIFF INFO tags or ID3 tags in an ID3 chunk.
            # Mutagen's WAVE support for INFO is basic. For ID3 in WAV, might need EasyID3 on WAVE.
            # For simplicity, we might skip extensive WAV tagging or use ffmpeg for it.
            print(f"Metadata application for .wav files ({os.path.basename(file_path_abs)}) is limited with mutagen. Consider converting to FLAC or M4A first.")
            # Try basic INFO tags if supported by mutagen version
            # audio = WAVE(file_path_abs)
            # e.g. audio["TIT2"] = TIT2(encoding=3, text=metadata_dict.get("title","")) # if trying ID3 in WAV
            return True # Assume no error, but limited action

        else:
            print(f"Unsupported audio format for metadata: {ext} for file {os.path.basename(file_path_abs)}")
            return False

        if audio and save_needed:
            audio.save()
            print(f"Metadata successfully applied to {os.path.basename(file_path_abs)}.")
        elif audio and not save_needed:
            print(f"Metadata for {os.path.basename(file_path_abs)} is already up to date.")
            
        return True

    except Exception as e:
        print(f"Error applying metadata to {os.path.basename(file_path_abs)}: {e}")
        return False