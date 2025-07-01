import csv
import os
import tempfile
from datetime import datetime
from faster_whisper import WhisperModel
from tqdm import tqdm

from .text_processing import apply_corrections_and_formatting
from .utils import config, CampaignContext 
from . import database_management as db

os.environ['KMP_DUPLICATE_LIB_OK']='True'

def transcribe_and_revise_audio(campaign_path, episode_id, transcriptions_output_dir):
    """
    Transcribes audio, saves TSV, then creates a revised TXT in the provided directory.
    ## FIX: Now accepts transcriptions_output_dir to break circular import.
    """
    episode = db.get_episode_by_id(campaign_path, episode_id)
    if not episode:
        print(f"Error: Cannot transcribe, episode {episode_id} not found.")
        return None

    if not episode['normalized_audio_file']:
        print(f"Error: Episode #{episode['episode_number']} has no normalized audio file. Cannot transcribe.")
        return None
    input_audio_file_path = os.path.join(campaign_path, episode['normalized_audio_file'])
    if not os.path.exists(input_audio_file_path):
        print(f"Error: Input audio file not found: {input_audio_file_path}")
        return None
        
    if not transcriptions_output_dir:
        print(f"Error: No transcription output directory provided.")
        return None
    os.makedirs(transcriptions_output_dir, exist_ok=True)
    
    try:
        model_size = config["transcription"]["model"]
        device_type = config["transcription"]["device"]
        compute_type = config["transcription"]["compute"]
        
        print(f"Loading Whisper model: {model_size} (Device: {device_type}, Compute: {compute_type})")
        model = WhisperModel(model_size, device=device_type, compute_type=compute_type)
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        return None
        
    context = CampaignContext(campaign_path)
    hotwords_list = context.custom_words
    hotwords_str = ", ".join(hotwords_list) if hotwords_list else None
    
    print(f"Starting transcription for: {os.path.basename(input_audio_file_path)}")
    try:
        segments_generator, info = model.transcribe(
            input_audio_file_path,
            language=config["transcription"].get("language", "en"),
            condition_on_previous_text=config["transcription"].get("condition_on_previous_text", True),
            repetition_penalty=config["transcription"].get("repetition_penalty", 1.05),
            hotwords=hotwords_str,
            beam_size=config["transcription"].get("beam_size", 5),
            vad_filter=config["transcription"].get("vad_filter", True),
            vad_parameters=config["transcription"].get("vad_parameters", {"threshold": 0.5})
        )
        
        base_filename_no_ext = os.path.splitext(os.path.basename(input_audio_file_path))[0]
        raw_tsv_file_path = os.path.join(transcriptions_output_dir, f"{base_filename_no_ext}.tsv")

        total_duration = round(info.duration, 2)
        segments = []
        
        with tqdm(total=total_duration, unit="s", desc="Transcription Progress", bar_format='{l_bar}{bar}| {n:.2f}/{total:.2f}s') as pbar:
            last_pos = 0
            for segment in segments_generator:
                segments.append(segment)
                pbar.update(segment.end - last_pos)
                last_pos = segment.end
            if pbar.n < total_duration:
                pbar.update(total_duration - pbar.n)

        with open(raw_tsv_file_path, 'w', newline='', encoding='utf-8') as tsv_file:
            tsv_writer = csv.writer(tsv_file, delimiter='\t')
            tsv_writer.writerow(['start', 'end', 'text'])
            for segment in segments:
                tsv_writer.writerow([f"{segment.start:.3f}", f"{segment.end:.3f}", segment.text.strip()])

        print(f"Transcription info: Language '{info.language}', Confidence {info.language_probability:.2f}")

    except Exception as e:
        print(f"An error occurred during Whisper transcription: {e}")
        return None

    db.update_processing_status(campaign_path, episode_id, transcribed=True, transcribed_model=model_size, transcribed_date=datetime.now())

    revised_txt_filename = f"{base_filename_no_ext}_revised.txt"
    revised_txt_file_path_abs = os.path.join(transcriptions_output_dir, revised_txt_filename)
    
    print(f"Applying corrections and formatting...")
    processed_txt_path = apply_corrections_and_formatting(context, episode_id, raw_tsv_file_path, revised_txt_file_path_abs)

    if processed_txt_path:
        print(f"Revised transcript saved to: {os.path.basename(processed_txt_path)}")
        return processed_txt_path
    else:
        print(f"Failed to apply corrections and formatting.")
        return None

def bulk_transcribe_audio(campaign_path):
    episodes_to_transcribe = db.get_episodes_for_campaign(campaign_path, where_clause="WHERE ps.normalized = TRUE AND ps.transcribed = FALSE")

    if not episodes_to_transcribe:
        print(f"No new normalized audio files found in campaign '{os.path.basename(campaign_path)}' for bulk transcription.")
        return
    
    trans_dir = find_transcriptions_folder(campaign_path)
    if not trans_dir:
        print(f"Could not find transcription folder for {os.path.basename(campaign_path)}. Aborting bulk transcribe.")
        return

    print(f"\nStarting bulk transcription for {len(episodes_to_transcribe)} episodes.")
    for episode in tqdm(episodes_to_transcribe, desc="Bulk Transcribing Episodes"):
        print(f"\nProcessing: Episode #{episode['episode_number']} - {episode['episode_title']}")
        transcribe_and_revise_audio(campaign_path, episode['episode_id'], trans_dir) 

    print(f"\nBulk transcription process completed.")