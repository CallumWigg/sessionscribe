import datetime
import ffmpeg
import json
import math
import os

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
    output_file = f"{file_date}_{file_name[11:]}_norm.m4a"
    output_path = os.path.join(input_dir, output_file)

    norm_files_count = sum(1 for f in os.listdir(input_dir) if '_norm' in f and f.endswith('.m4a'))
    new_track_number = norm_files_count + 1

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

    apply_metadata(file_path, metadata)
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
    """Trawl through working directory and grab the all the audio files in the last 7 days."""
    audio_files = []
    current_time = datetime.datetime.now()
    cutoff_time = current_time - datetime.timedelta(days=7)

    for root, _, files in os.walk(get_working_directory()):
        for file in files:
            if file.endswith((".wav", ".m4a", ".flac")) and "_norm" not in file:
                file_path = os.path.join(root, file)
                file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_modified_time >= cutoff_time:
                    audio_files.append(file_path)
    return audio_files

def bulk_normalize_audio(campaign_folder):
    """Normalizes audio files in a specified campaign folder."""
    audio_files_folder = find_audio_files_folder(campaign_folder)
    if audio_files_folder:
        for filename in os.listdir(audio_files_folder):
            if filename.endswith((".wav", ".m4a", ".flac")):
                file_path = os.path.join(audio_files_folder, filename)
                # Add logic here to determine the title for each file (e.g., extract from filename)
                title = filename  # Placeholder - you'll need to implement title extraction
                convert_to_m4a(file_path, title)
    else:
        print(f"No 'Audio Files' folder found in {campaign_folder}")

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