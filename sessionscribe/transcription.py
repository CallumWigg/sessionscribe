import csv
import os
from faster_whisper import WhisperModel

from .text_processing import apply_corrections_and_formatting # Assuming text_processing.py is in the same package
from .utils import config, load_custom_words # Assuming utils.py for config and custom words


os.environ['KMP_DUPLICATE_LIB_OK']='True' # Keep if needed for specific environments

def transcribe_and_revise_audio(input_audio_file_path, transcriptions_output_dir): # Added parameter
    """Transcribe audio using faster-whisper, save TSV, then apply corrections to create a revised TXT.
    input_audio_file_path: Absolute path to the audio file (e.g., _norm.m4a).
    transcriptions_output_dir: Absolute path to the directory where transcription files should be saved.
    Returns a tuple: (absolute_path_to_transcriptions_output_dir, absolute_path_to_revised_txt_file) or (None, None) on failure.
    """
    if not os.path.exists(input_audio_file_path):
        print(f"Error: Input audio file not found: {input_audio_file_path}")
        return None, None

    if not transcriptions_output_dir or not os.path.isdir(transcriptions_output_dir):
        print(f"Error: Invalid or missing transcriptions output directory: {transcriptions_output_dir}")
        # Consider if creation should happen here or strictly by the caller.
        # For now, require it to exist.
        # Example creation logic if moved here (would need campaign_path also):
        # try:
        #     os.makedirs(transcriptions_output_dir, exist_ok=True)
        #     print(f"Created transcriptions directory: {transcriptions_output_dir}")
        # except OSError as e:
        #     print(f"Error creating transcriptions directory {transcriptions_output_dir}: {e}")
        #     return None, None
        return None, None


    try:
        model_size = config["transcription"]["model"]
        device_type = config["transcription"]["device"]
        compute_type = config["transcription"]["compute"]
        
        print(f"Loading Whisper model: {model_size} (Device: {device_type}, Compute: {compute_type})")
        model = WhisperModel(model_size, device=device_type, compute_type=compute_type)
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        print("Ensure the model name is correct and dependencies are installed (PyTorch for GPU, CTranslate2).")
        return None, None
        
    hotwords_list = load_custom_words()
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
        return None, None

    base_filename_no_ext = os.path.splitext(os.path.basename(input_audio_file_path))[0]
    raw_tsv_file_path = os.path.join(transcriptions_output_dir, f"{base_filename_no_ext}.tsv") 

    try:
        with open(raw_tsv_file_path, 'w', newline='', encoding='utf-8') as tsv_file:
            tsv_writer = csv.writer(tsv_file, delimiter='\t')
            tsv_writer.writerow(['start', 'end', 'text']) 
            
            segment_count = 0
            for segment in segments:
                tsv_writer.writerow([f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text.strip()])
                segment_count +=1
            print(f"Saved {segment_count} segments to TSV: {os.path.basename(raw_tsv_file_path)}")
    except IOError as e:
        print(f"Error writing TSV file {raw_tsv_file_path}: {e}")
        return None, None
    except Exception as e: 
        print(f"Error processing segments for TSV: {e}")
        return None, None

    revised_txt_filename = f"{base_filename_no_ext}_revised.txt"
    revised_txt_file_path_abs = os.path.join(transcriptions_output_dir, revised_txt_filename)
    
    print(f"Applying corrections and formatting: {os.path.basename(raw_tsv_file_path)} -> {revised_txt_filename}")
    processed_txt_path = apply_corrections_and_formatting(raw_tsv_file_path, revised_txt_file_path_abs)

    if processed_txt_path:
        print(f"Revised transcript saved to: {os.path.basename(processed_txt_path)}")
        return transcriptions_output_dir, processed_txt_path
    else:
        print(f"Failed to apply corrections and formatting to {os.path.basename(raw_tsv_file_path)}.")
        return transcriptions_output_dir, None


def bulk_transcribe_audio(campaign_folder_path): # This function also needs to be adapted
    """Transcribes all relevant audio files in a specified campaign folder."""
    from .file_management import find_audio_files_folder, find_transcriptions_folder # Keep local import here

    audio_files_folder = find_audio_files_folder(campaign_folder_path)
    if not audio_files_folder:
        print(f"No 'Audio Files' folder found in campaign '{os.path.basename(campaign_folder_path)}'. Cannot bulk transcribe.")
        return

    transcriptions_output_dir = find_transcriptions_folder(campaign_folder_path) # Determine output dir
    if not transcriptions_output_dir:
         # Attempt to create it if campaign_folder_path is valid
        if os.path.isdir(campaign_folder_path):
            campaign_abbrev = os.path.basename(campaign_folder_path)
            transcriptions_output_dir = os.path.join(campaign_folder_path, f"{campaign_abbrev} Transcriptions")
            try:
                os.makedirs(transcriptions_output_dir, exist_ok=True)
                print(f"Created transcriptions directory: {transcriptions_output_dir}")
            except OSError as e:
                print(f"Error creating transcriptions directory {transcriptions_output_dir}: {e}")
                return
        else:
            print(f"Error: Could not determine or create transcriptions directory for campaign '{campaign_folder_path}'.")
            return


    audio_files_to_transcribe = [
        f for f in os.listdir(audio_files_folder)
        if f.endswith("_norm.m4a") 
    ]

    if not audio_files_to_transcribe:
        print(f"No '_norm.m4a' files found in {audio_files_folder} for bulk transcription.")
        return
    
    print(f"\nStarting bulk transcription for campaign '{os.path.basename(campaign_folder_path)}'.")
    files_processed_count = 0
    for audio_filename in audio_files_to_transcribe:
        audio_file_path_abs = os.path.join(audio_files_folder, audio_filename)
            
        print(f"\nProcessing for transcription: {audio_filename}")
        # Pass the determined transcriptions_output_dir
        _, revised_txt_path = transcribe_and_revise_audio(audio_file_path_abs, transcriptions_output_dir) 
        if revised_txt_path:
            files_processed_count += 1
        else:
            print(f"Failed to transcribe or process {audio_filename}.")

    print(f"\nBulk transcription process completed for {files_processed_count} file(s).")