import os
import re
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from .utils import config, format_time

# Gemini Configuration
genai.configure(api_key=config["gemini"]["api_key"])

GENAI_GENERATION_CONFIG = {
  "temperature": config["gemini"]["temperature"],
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 1000,
  "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
  model_name=config["gemini"]["model_name"],
  generation_config=GENAI_GENERATION_CONFIG,
  safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE, 
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,        
    }
)

def generate_summary_and_chapters(transcript_path):
    """Generates a summary and timestamped chapters using the Gemini API."""
    summary = None
    chapters = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    # Generate Summary (without timestamps)
    text_without_timestamps = re.sub(r'^\d{2}:\d{2}:\d{2}   \|   ', '', transcript_text, flags=re.MULTILINE)
    temp_summary_file = transcript_path.replace("_revised.txt", "_temp_summary.txt")
    with open(temp_summary_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(text_without_timestamps)

    file_summary = genai.upload_file(temp_summary_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.txt", "_summary.txt"))
    while file_summary.state.name == "PROCESSING":
      time.sleep(10)
      file_summary = genai.get_file(file_summary.name)
    if file_summary.state.name != "ACTIVE":
      raise Exception(f"File {file_summary.name} failed to process")

    summary_response = model.generate_content([file_summary, "Generate a short 200-word summary of this dungeons and dragons session transcript. Write as a synopsis of the events, assuming the reader understands the context of the campaign."])
    if summary_response.prompt_feedback:
        print(f"Prompt Feedback: {summary_response.prompt_feedback}", end='')
    else: 
        summary = summary_response.text

    if summary is not None:
        summary_file_path = transcript_path.replace(".txt", "_summary.txt")  # Create summary filename

        with open(summary_file_path, 'w', encoding='utf-8') as f:
            f.write(summary)
            desired_part = '_'.join(os.path.splitext(os.path.basename(summary_file_path))[0].split('_')[:4])
            print(f"Summary saved to: {desired_part}")
    else:
        print(f"Warning: Could not generate summary for {transcript_path}. Skipping...")

    # Generate Chapters (with timestamps)
    temp_chapters_file = transcript_path.replace("_revised.txt", "_temp_chapters.txt")
    with open(temp_chapters_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(transcript_text)

    file_chapters = genai.upload_file(temp_chapters_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.txt", "_chapters.txt"))
    while file_chapters.state.name == "PROCESSING":
      time.sleep(10)
      file_chapters = genai.get_file(file_chapters.name)
    if file_chapters.state.name != "ACTIVE":
      raise Exception(f"File {file_chapters.name} failed to process")

    prompt_text = """
    Generate timestamps for main chapter/topics in a Dungeons and Dragons podcast session transcript.
    Given text segments with their time, generate timestamps for main topics discussed in the session. Format timestamps as hh:mm:ss and provide clear and concise topic titles, with a short one sentence description.  

    IMPORTANT:
    1. Ensure that the chapters are an accurate representation of the entire session, and that the chapters are distributed evenly. The session is often 6 hours long, so they should be well distributed.
    2. There should aim to be 5 chapters TOTAL for the whole transcript.

    List only topic titles and timestamps, and a short description.
    Example for output:
    [hh:mm:ss] Topic Title One - Topic 1 brief description
    [hh:mm:ss] Topic Title Two - Topic 2 brief description
    - and so on 

    Transcript is provided below, in the format of hh:mm:ss   |   "text":
    """

    chapters_response = model.generate_content([file_chapters, prompt_text])
    if chapters_response.prompt_feedback:
        print(f"Prompt Feedback: {chapters_response.prompt_feedback}", end='')
    else:
        chapters = chapters_response.text

    if chapters is not None:
        chapters_file_path = transcript_path.replace(".txt", "_chapters.txt")  # Create chapter filename

        with open(chapters_file_path, 'w', encoding='utf-8') as f:
            f.write(chapters)
            desired_part = '_'.join(os.path.splitext(os.path.basename(chapters_file_path))[0].split('_')[:4])
            print(f"Chapters saved to: {desired_part}")
    else:
        print(f"    Warning: Could not generate chapters for {transcript_path}. Skipping...")

    # Delete the temporary files
    os.remove(temp_chapters_file)
    os.remove(temp_summary_file)

def sanitize_summary(summary):
    """Replace multiple line breaks with a single line break."""
    sanitized_summary = re.sub(r'\n\s*\n', '\n', summary)
    return sanitized_summary.strip()

def collate_summaries(directory):
    """Collate individual summary files into a single summary file for the campaign."""
    collated_data = []

    for filename in os.listdir(directory):
        date_match = re.match(r'^(\d{4}_\d{2}_\d{2})_.*', filename)  # Match YYYY_MM_DD pattern
        if not date_match:
            continue

        date_str = date_match.group(1)
        date = datetime.strptime(date_str, '%Y_%m_%d')

        if '_norm_revised.txt' in filename and not filename.endswith('_summary.txt'):
            with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
                title = f.readline().strip()
            print(f"Title: {title}")
            collated_data.append((date, title, None))

        elif filename.endswith('_norm_revised_summary.txt'):
            with open(os.path.join(directory, filename), 'r', encoding='utf-8') as f:
                summary = f.read().strip()
            sanitized_summary = sanitize_summary(summary)

            for i, (stored_date, stored_title, _) in enumerate(collated_data):
                if stored_date == date:
                    collated_data[i] = (stored_date, stored_title, sanitized_summary)
                    break
            else:
                collated_data.append((date, None, sanitized_summary))  # If title is not found, append summary alone

    collated_data.sort(key=lambda x: x[0])  # Sort data by date

    folder_name = os.path.basename(directory)
    output_filename = f"{folder_name}_Collated_Summary.txt"

    with open(os.path.join(directory, output_filename), 'w', encoding='utf-8') as output_file:
        for date, title, summary in collated_data:
            if title:
                output_file.write(title + "\n")
            if summary:
                output_file.write(summary + "\n\n")

    print(f"Collated summary file generated: {output_filename}")