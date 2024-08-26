import csv
import os

from faster_whisper import WhisperModel  # , BatchedInferencePipeline

from text_processing import apply_corrections_and_formatting
from utils import config, load_custom_words

os.environ['KMP_DUPLICATE_LIB_OK']='True' #its not working without this for some reason

def transcribe_and_revise_audio(input_audio_file):
    """Transcribe and revise audio using faster-whisper."""
    parent_dir = os.path.dirname(os.path.dirname(input_audio_file))
    transcriptions_folder = next((folder for folder in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder), None)
    output_dir = os.path.join(parent_dir, transcriptions_folder) if transcriptions_folder else None

    model = WhisperModel(config["transcription"]["model"], device=config["transcription"]["device"], compute_type=config["transcription"]["compute"])
    #batched_model = BatchedInferencePipeline(model=model)  #going to try get this going soon, but not working as of yet.
    #segments, _ = batched_model.transcribe(
    hotwords_str = " ".join(load_custom_words())
    segments, _ = model.transcribe(
        input_audio_file,
        language=config["transcription"]["language"],
        condition_on_previous_text = False,
        vad_filter = True,
        repetition_penalty = 1.2,
        hotwords = hotwords_str,
    )

    base_filename = os.path.splitext(os.path.basename(input_audio_file))[0]
    text_file_path = os.path.join(output_dir, f"{base_filename}.txt")
    tsv_file_path = os.path.join(output_dir, f"{base_filename}.tsv")

    # Save text and TSV
    with open(text_file_path, 'w', encoding='utf-8') as text_file, open(tsv_file_path, 'w', newline='', encoding='utf-8') as tsv_file:
        tsv_writer = csv.writer(tsv_file, delimiter='\t')
        tsv_writer.writerow(['start', 'end', 'text'])
        for segment in segments:
            print([f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text])
            text_file.write(f"{segment.text}\n")
            tsv_writer.writerow([f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text])
    # Apply corrections and formatting to the TSV file
    revised_tsv_file = tsv_file_path.replace(".tsv", "_revised.txt")
    apply_corrections_and_formatting(tsv_file_path, revised_tsv_file)

    return output_dir, revised_tsv_file

def bulk_transcribe_audio(campaign_folder):
    """Transcribes audio files in a specified campaign folder."""
    from file_management import find_audio_files_folder
    audio_files_folder = find_audio_files_folder(campaign_folder)
    if audio_files_folder:
        for filename in os.listdir(audio_files_folder):
            if filename.endswith((".wav", ".m4a", ".flac")):
                file_path = os.path.join(audio_files_folder, filename)
                print(f"Transcribing: {file_path}")
                transcribe_and_revise_audio(file_path)
    else:
        print(f"No 'Audio Files' folder found in {campaign_folder}")