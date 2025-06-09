import csv
import os
from datetime import datetime
from faster_whisper import WhisperModel

from .text_processing import apply_corrections_and_formatting
from .utils import config, load_custom_words
from . import database_management as db

os.environ['KMP_DUPLICATE_LIB_OK']='True'

def transcribe_and_revise_audio(campaign_path, episode_id):
    """
    Transcribes audio for a given episode_id, saves TSV, then creates a revised TXT.
    Returns the absolute path to the revised TXT file or None on failure.
    """
    episode = db.get_episode_by_id(campaign_path, episode_id)
    if not episode:
        print(f"Error: Cannot transcribe, episode {episode_id} not found.")
        return None

    input_audio_file_path = os.path.join(campaign_path, episode['normalized_audio_file'])
    if not os.path.exists(input_audio_file_path):
        print(f"Error: Input audio file not found: {input_audio_file_path}")
        return None
        
    transcriptions_output_dir = os.path.dirname(os.path.join(campaign_path, episode['normalized_audio_file']).replace("Audio Files", "Transcriptions"))
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
        
    hotwords_list = load_custom_words(campaign_path) # Campaign-specific hotwords
    hotwords_str = " ".join(hotwords_list) if hotwords_list else None 
    
    print(f"Starting transcription for: {os.path.basename(input_audio_file_path)}")
    try:
        segments, info = model.transcribe(
            input_audio_file_path,
            language=config["transcription"]["language"],
            condition_on_previous_text=config["transcription"].get("condition_on_previous_text", False),
            repetition_penalty=config["transcription"].get("repetition_penalty", 1.1),
            hotwords=hotwords_str,
            beam_size=config["transcription"].get("beam_size", 5),
            vad_filter=config["transcription"].get("vad_filter", True), 
            vad_parameters=config["transcription"].get("vad_parameters", {"threshold": 0.5}) 
        )
        print(f"Transcription info: Language '{info.language}', Confidence {info.language_probability:.2f}, Duration {info.duration:.2f}s")
    except Exception as e:
        print(f"Error during Whisper transcription: {e}")
        return None

    base_filename_no_ext = os.path.splitext(os.path.basename(input_audio_file_path))[0]
    raw_tsv_file_path = os.path.join(transcriptions_output_dir, f"{base_filename_no_ext}.tsv") 

    try:
        with open(raw_tsv_file_path, 'w', newline='', encoding='utf-8') as tsv_file:
            tsv_writer = csv.writer(tsv_file, delimiter='\t')
            tsv_writer.writerow(['start', 'end', 'text']) 
            
            for segment in segments:
                tsv_writer.writerow([f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text.strip()])
    except Exception as e: 
        print(f"Error processing segments for TSV: {e}")
        return None

    # Update database after successful transcription
    db.update_processing_status(
        campaign_path, episode_id,
        transcribed=True,
        transcribed_model=model_size,
        transcribed_date=datetime.now()
    )
    # We don't store the TSV path in DB, it's intermediate.

    revised_txt_filename = f"{base_filename_no_ext}_revised.txt"
    revised_txt_file_path_abs = os.path.join(transcriptions_output_dir, revised_txt_filename)
    
    print(f"Applying corrections and formatting: {os.path.basename(raw_tsv_file_path)} -> {revised_txt_filename}")
    processed_txt_path = apply_corrections_and_formatting(
        campaign_path, episode_id, raw_tsv_file_path, revised_txt_file_path_abs
    )

    if processed_txt_path:
        print(f"Revised transcript saved to: {os.path.basename(processed_txt_path)}")
        return processed_txt_path
    else:
        print(f"Failed to apply corrections and formatting to {os.path.basename(raw_tsv_file_path)}.")
        return None


def bulk_transcribe_audio(campaign_path):
    """Transcribes all untranscribed audio files in a campaign."""
    episodes_to_transcribe = db.get_episodes_for_campaign(campaign_path, where_clause="WHERE ps.normalized = TRUE AND ps.transcribed = FALSE")

    if not episodes_to_transcribe:
        print(f"No new normalized audio files found in campaign '{os.path.basename(campaign_path)}' for bulk transcription.")
        return
    
    print(f"\nStarting bulk transcription for {len(episodes_to_transcribe)} episodes in '{os.path.basename(campaign_path)}'.")
    files_processed_count = 0
    for episode in episodes_to_transcribe:
        print(f"\nProcessing for transcription: Episode #{episode['episode_number']} - {episode['episode_title']}")
        revised_txt_path = transcribe_and_revise_audio(campaign_path, episode['episode_id']) 
        if revised_txt_path:
            files_processed_count += 1
        else:
            print(f"Failed to transcribe or process Episode #{episode['episode_number']}.")

    print(f"\nBulk transcription process completed for {files_processed_count} file(s).")