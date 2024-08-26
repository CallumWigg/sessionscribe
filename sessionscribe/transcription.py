import os
import csv
from faster_whisper import WhisperModel

from .utils import config, format_time
from .text_processing import apply_corrections_and_formatting


class BatchedInferencePipeline:
    def __init__(self, model):
        self.model = model

    def transcribe(
        self,
        audio_file,
        batch_size=16,
        language=None,
        condition_on_previous_text=False,
        initial_prompt=None,
        verbose=False,
        vad_filter=False,
        repetition_penalty=1.2,
        no_repeat_ngram_size=3,
        suppress_tokens = -1,
    ):
        segments = []
        segment_generator = self.model.transcribe(
            audio_file,
            language=language,
            condition_on_previous_text=condition_on_previous_text,
            initial_prompt=initial_prompt,
            verbose=verbose,
            vad_filter=vad_filter,
            repetition_penalty=repetition_penalty,
            no_repeat_ngram_size=no_repeat_ngram_size,
            suppress_tokens=suppress_tokens
        )
        all_segments = list(segment_generator)
        for segment in all_segments:
            segments.append(segment)

        return segments, all_segments


def transcribe_and_revise_audio(input_audio_file):
    """Transcribe and revise audio using the batched_model."""
    parent_dir = os.path.dirname(os.path.dirname(input_audio_file))
    transcriptions_folder = next((folder for folder in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, folder)) and "Transcriptions" in folder), None)
    output_dir = os.path.join(parent_dir, transcriptions_folder) if transcriptions_folder else None

    model = WhisperModel(config["transcription"]["model_type"], device=config["transcription"]["device"], compute_type=config["transcription"]["compute_type"])
    batched_model = BatchedInferencePipeline(model=model)
    segments, _ = batched_model.transcribe(
        input_audio_file,
        batch_size=16,
        language=config["general"]["language"],
        condition_on_previous_text = False,
        verbose = True,
        vad_filter = True,
        repetition_penalty = 1.2,
        no_repeat_ngram_size = 3,
        suppress_tokens = -1,
    )

    # Define file paths
    base_filename = os.path.splitext(os.path.basename(input_audio_file))[0]
    text_file_path = os.path.join(output_dir, f"{base_filename}.txt")
    tsv_file_path = os.path.join(output_dir, f"{base_filename}.tsv")

    # Save text and TSV
    with open(text_file_path, 'w') as text_file, open(tsv_file_path, 'w', newline='') as tsv_file:
        tsv_writer = csv.writer(tsv_file, delimiter='\t')
        tsv_writer.writerow(['start', 'end', 'text'])
        for segment in segments:
            text_file.write(f"{segment.text}\n")
            tsv_writer.writerow([f"{segment.start:.2f}", f"{segment.end:.2f}", segment.text])

    # Apply corrections and formatting to the TSV file
    revised_tsv_file = tsv_file_path.replace(".tsv", "_revised.txt")
    apply_corrections_and_formatting(tsv_file_path, revised_tsv_file)

    return output_dir, revised_tsv_file

def bulk_transcribe_audio(campaign_folder):
    """Transcribes audio files in a specified campaign folder."""
    from .file_management import find_audio_files_folder
    audio_files_folder = find_audio_files_folder(campaign_folder)
    if audio_files_folder:
        for filename in os.listdir(audio_files_folder):
            if filename.endswith((".wav", ".m4a", ".flac")):
                file_path = os.path.join(audio_files_folder, filename)
                print(f"Transcribing: {file_path}")
                transcribe_and_revise_audio(file_path)
    else:
        print(f"No 'Audio Files' folder found in {campaign_folder}")