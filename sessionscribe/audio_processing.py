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

from .utils import get_working_directory
from .file_management import find_audio_files_folder

# Load configuration
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

def convert_to_m4a(file_path, title):
    """Convert an audio file to m4a format and apply metadata."""
    input_dir, input_file = os.path.split(file_path)
    input_duration = float(ffmpeg.probe(file_path)['format']['duration'])
    year = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).year
    target_size = config["general"]["ffmpeg_target_size_mb"] * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))

    campaign_name = os.path.basename(os.path.dirname(input_dir))
    file_name = os.path.splitext(input_file)[0]
    file_date = file_name[:10]

    # Extract part number (if present)
    part_match = re.search(r'_p(\d+)', input_file)
    part_number = part_match.group(1) if part_match else None

    # Modify output filename to include part number
    if part_number:
        output_file = f"{file_date}_{file_name[11:].replace(f'_p{part_number}', '')}_p{part_number}_norm.m4a"
    else:
        output_file = f"{file_date}_{file_name[11:]}_norm.m4a"
    
    output_path = os.path.join(input_dir, output_file)

    # Improved Track Number Logic (Corrected)
    norm_files = [f for f in os.listdir(input_dir) if '_norm' in f and f.endswith('.m4a')]

    # Group files by base filename (without part numbers)
    files_by_base_name = {}
    for file in norm_files:
        base_name = re.sub(r'_p\d+', '', file)  # Remove _p1, _p2, etc.
        if base_name not in files_by_base_name:
            files_by_base_name[base_name] = []
        files_by_base_name[base_name].append(file)

    # Calculate track number based on base name groups
    new_track_number = 1
    for base_name, files in files_by_base_name.items():
        for i, file in enumerate(sorted(files)):  # Sort files within each base name group
            if file == output_file:  # Found the current file
                new_track_number += i
                break
        else:  # Loop finished without finding the current file
            new_track_number += len(files)  # Add all files in the base name group

    # Build the metadata dictionary
    metadata = {
        "title": title,
        "artist": config["podcasts"]["artist_name"],
        "albumartist": config["podcasts"]["artist_name"],
        "album": campaign_name,
        "genre": config["podcasts"]["genre"],
        "date": str(year),
        "tracknumber": str(new_track_number)
    }

    (
        ffmpeg
        .input(file_path)
        .filter("loudnorm")
        .output(
            output_path,
            acodec='aac',
            ab=f"{target_bitrate}k",
            ac=config["podcasts"]["audio_channels"],
            ar=config["podcasts"]["samping_rate"],
        )
        .overwrite_output()
        .run()
    )

    # Apply metadata to the output m4a file
    apply_metadata(output_path, metadata)

    print(f'\n\nSuccessfully converted {file_path} to {output_path} with {target_bitrate} kbps bitrate and applied metadata.\n\n')
    return output_path

def search_audio_files():
    """Trawl through working directory and grab the all the audio files in the last 100 days, 
    excluding those that have a corresponding _norm file.
    """
    audio_files = []
    current_time = datetime.datetime.now()
    cutoff_time = current_time - datetime.timedelta(days=100)

    for root, _, files in os.walk(get_working_directory()):
        for file in files:
            if file.endswith((".wav", ".m4a", ".flac")) and "_norm" not in file:
                file_path = os.path.join(root, file)
                norm_file_path = file_path.replace(".", "_norm.")  # Construct the _norm file path
                
                # Check if _norm version exists 
                if not os.path.exists(norm_file_path):
                    file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_modified_time >= cutoff_time:
                        audio_files.append(file_path)
    return audio_files[:20]

def calculate_target_bitrate(file_path):
    """Calculates the target bitrate based on file duration and desired file size."""
    input_duration = float(ffmpeg.probe(file_path)['format']['duration'])
    target_size = config["general"]["ffmpeg_target_size_mb"] * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))
    return target_bitrate

def split_audio_file(file_path):
    """Splits a long audio file into multiple parts based on user input."""
    input_duration = float(ffmpeg.probe(file_path)['format']['duration'])
    target_bitrate = config["general"]["minimum_bitrate_kbps"]
    target_size_bytes = config["general"]["ffmpeg_target_size_mb"] * 1024 * 1024

    # Calculate the maximum duration per part to achieve the target bitrate
    max_duration_per_part = (target_size_bytes * 8) / (target_bitrate * 1024)

    # Calculate the number of parts needed
    num_parts = math.ceil(input_duration / max_duration_per_part)

    print(f"This file is very long ({input_duration / 3600:.2f} hours).")
    print(f"To achieve a minimum bitrate of {target_bitrate} kbps with a target size of {config['general']['ffmpeg_target_size_mb']} MB,")
    print(f"it is suggested to split the file into {num_parts} parts, each with an approximate duration of {max_duration_per_part / 3600:.2f} hours.")

    # Open audio player for user to identify split points
    try:
        if os.name == 'nt':  # For Windows
            os.startfile(file_path)
        elif os.name == 'posix':  # For macOS and Linux
            subprocess.call(('open', file_path))
        else:
            print("Warning: Could not determine operating system to open audio player.")
    except Exception as e:
        print(f"Warning: Could not open audio player: {e}")

    parts = []
    start_time = 0
    for i in range(num_parts - 1):
        split_time_str = input(f"Enter the split timecode for part {i+1} (hh:mm:ss): ")
        split_time = sum(int(x) * 60**i for i, x in enumerate(reversed(split_time_str.split(':'))))

        output_file = file_path.replace(".m4a", f"_p{i+1}.m4a")
        (
            ffmpeg
            .input(file_path)
            .output(output_file, ss=start_time, to=split_time, c='copy')
            .run()
        )
        parts.append(output_file)
        start_time = split_time

    # Add the last part
    output_file = file_path.replace(".m4a", f"_p{num_parts}.m4a")
    (
        ffmpeg
        .input(file_path)
        .output(output_file, ss=start_time, c='copy')
        .run()
    )
    parts.append(output_file)

    return parts

def bulk_normalize_audio(campaign_folder):
    """Normalizes audio files in a specified campaign folder."""
    audio_files_folder = find_audio_files_folder(campaign_folder)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in {campaign_folder}")
        return

    # Get user choice for normalization
    normalization_choice = user_interaction.choose_from_list(
        ["Normalize all (overwriting existing _norm files)", 
         "Normalize only new files (skip existing _norm files)",
         "Update master/source audio files to FLAC"],  # Updated text
        "Choose a normalization option:",
        "Enter the number of your choice:"
    )

    audio_files = [
        f for f in os.listdir(audio_files_folder)
        if f.endswith((".wav", ".m4a", ".flac", ".mp3"))
    ]

    for i, filename in enumerate(audio_files):
        file_path = os.path.join(audio_files_folder, filename)
        file_date = filename[:10]
        title = filename[11:].replace("_norm", "").replace(".m4a", "").replace(".wav", "").replace(".flac", "").replace(".mp3", "").strip()

        # Check if a _norm file already exists (for the first two options)
        if normalization_choice in ["Normalize all (overwriting existing _norm files)", 
                                     "Normalize only new files (skip existing _norm files)"]:
            norm_file_exists = any(
                f.startswith(file_date) and "_norm" in f 
                for f in os.listdir(audio_files_folder)
            )

            if normalization_choice == "Normalize only new files (skip existing _norm files)" and norm_file_exists:
                print(f"Skipping {filename} (normalized version already exists)")
                continue  # Skip to the next file

            # Calculate track number
            track_number = i + 1

            # Perform normalization (convert_to_m4a will handle overwriting)
            convert_to_m4a(file_path, title, track_number)

        # Handle FLAC conversion separately
        elif normalization_choice == "Update master/source audio files to FLAC":
            if "_norm" in filename:  # Skip files containing "_norm"
                continue

            if filename.endswith(".flac"):
                print(f"Updating metadata for existing FLAC file: {filename}")
                apply_metadata(file_path, {"title": title})  # Update metadata for FLAC
                continue

            flac_file_path = os.path.splitext(file_path)[0] + ".flac"
            
            # Convert to FLAC using ffmpeg
            try:
                (
                    ffmpeg
                    .input(file_path)
                    .output(flac_file_path)
                    .run(overwrite_output=True)
                )
            except ffmpeg.Error as e:
                print(f"Error converting {file_path} to FLAC: {e}")
                continue  # Skip to the next file

            # Apply metadata to the FLAC file
            apply_metadata(flac_file_path, {"title": title})

            # Prompt user for deleting original files
            delete_original = user_interaction.choose_from_list(
                ["Yes", "No"],
                f"Delete original file: {filename}?",
                "Enter your choice (1-2):"
            )

            if delete_original == "Yes":
                try:
                    os.remove(file_path)
                    print(f"Deleted original file: {file_path}")
                except OSError as e:
                    print(f"Error deleting {file_path}: {e}")

        # Calculate track number
        track_number = i + 1

        # Perform normalization (convert_to_m4a will handle overwriting)
        convert_to_m4a(file_path, title, track_number)

def apply_metadata(file_path, metadata):
    """Applies metadata to various audio file formats."""

    extension = os.path.splitext(file_path)[1].lower()
    
    if extension == ".m4a":
        audio = MP4(file_path)
        metadata_mapping = {
            "title": "\xa9nam",
            "artist": "\xa9ART",
            "albumartist": "aART", 
            "album": "\xa9alb",
            "genre": "\xa9gen",
            "date": "\xa9day",
            "tracknumber": "trkn" 
        }
    elif extension in (".mp3", ".flac", ".wav"):
        audio = EasyID3(file_path) if extension == ".mp3" else FLAC(file_path) if extension == ".flac" else WAVE(file_path)
        metadata_mapping = {
            "title": "title",
            "artist": "artist",
            "albumartist": "albumartist",
            "album": "album",
            "genre": "genre",
            "date": "date",
            "tracknumber": "tracknumber"
        }
    else:
        print(f"Unsupported audio format: {extension}")
        return

    for key, value in metadata.items():
        if key in metadata_mapping:
            audio_key = metadata_mapping[key]
            if audio_key == "trkn":  # Special handling for track number
                audio[audio_key] = [(int(value), 0)]
            else:
                audio[audio_key] = value
    audio.save()