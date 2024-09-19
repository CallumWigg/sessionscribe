import os
import re
import time
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory, GenerationConfig, SafetySettingDict
from .utils import config, format_time


# Gemini Configuration
genai.configure(api_key=config["gemini"]["api_key"])

model = genai.GenerativeModel(
  model_name=config["gemini"]["model_name"]
)

def generate_text_with_gemini(prompt, input_text, max_output_tokens, temperature, safety_settings="HIGH"):
    """Uploads text to Gemini, generates content, and handles retries."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            file_input = genai.upload_file(input_text, mime_type="text/plain", display_name=os.path.basename(input_text))
            while file_input.state.name == "PROCESSING":
                time.sleep(10)
                file_input = genai.get_file(file_input.name)
            if file_input.state.name != "ACTIVE":
                raise Exception(f"File {file_input.name} failed to process")

            content_config = GenerationConfig(
                max_output_tokens=max_output_tokens,
                temperature=temperature
            )

            response = model.generate_content(
                [prompt, file_input],
                generation_config=content_config,
                safety_settings=safety_settings,
            )

            return response
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            temperature += 0.2
            if attempt < max_retries - 1:
                print(f"Retrying with temperature: {temperature}")
            else:
                print(f"Warning: Could not generate text after {max_retries} attempts.")
    return None

def process_gemini_response(response):
    """Checks for safety violations and extracts generated text."""
    if response is None:
        return None

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.finish_reason == FinishReason.SAFETY:
            safety_issues = [rating.category.name for rating in candidate.safety_ratings if rating.severity >= HarmSeverity.SEVERITY_MEDIUM]
            raise Exception(f"Response candidate blocked due to safety violations: {', '.join(safety_issues)}")

    return response.text


def generate_summary_and_chapters(transcript_path):
    """Generates summary, chapters, and subtitle using Gemini."""
    summary = None
    chapters = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    # Generate Summary (without timestamps)
    skip_seconds = config["general"]["summary_skip_minutes"] * 60  # Convert minutes to seconds
    text_without_timestamps = ""
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            match = re.match(r'(\d{2}:\d{2}:\d{2})   \|   (.*)', line)
            if match:
                timestamp = match.group(1)
                text = match.group(2)
                hours, minutes, seconds = map(int, timestamp.split(':'))
                total_seconds = hours * 3600 + minutes * 60 + seconds
                if total_seconds >= skip_seconds:  # Only include text after the skipped duration
                    text_without_timestamps += text + "\n"

    temp_summary_file = transcript_path.replace("_revised.txt", "_temp_summary.txt")
    with open(temp_summary_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(text_without_timestamps)

    # Generate Summary
    summary_prompt = "Generate a short 200-word summary of this D&D fantasy session transcript. Write as a synopsis of the events, assuming the reader understands the context of the campaign." 
    summary_response = generate_text_with_gemini(summary_prompt, temp_summary_file, 300, config["gemini"]["temperature"], config["gemini"]["safety_settings"])
    summary = process_gemini_response(summary_response)
    #print(summary_response)

    if summary is not None:
        summary_file_path = transcript_path.replace(".txt", "_summary.txt")

        # Save the summary to the file
        with open(summary_file_path, 'w', encoding='utf-8') as f:
            f.write(summary)
            desired_part = '_'.join(os.path.splitext(os.path.basename(summary_file_path))[0].split('_')[:4])
            print(f"Summary saved to: {desired_part}")
    else:
        print(f"Warning: Could not generate summary for {transcript_path}. Skipping...")

    # Generate Chapters (with timestamps)
    chapters_prompt = """
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
    
    temp_chapters_file = transcript_path.replace("_revised.txt", "_temp_chapters.txt")
    with open(temp_chapters_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(transcript_text)
    
    chapters_response = generate_text_with_gemini(chapters_prompt, temp_chapters_file, 300, config["gemini"]["temperature"], config["gemini"]["safety_settings"])
    chapters = process_gemini_response(chapters_response)

    # Generate Podcast Subtitle
    subtitle_prompt = "Generate 10 different very short and concise, ~50 character podcast subtitles that capture the main plot points or advancements that occurred in this Dungeons and Dragons session. Avoid using character names. Output each subtitle on a new line."
    subtitle_response = generate_text_with_gemini(subtitle_prompt, temp_summary_file, 500, 0.5*config["gemini"]["temperature"], config["gemini"]["safety_settings"])
    subtitles = process_gemini_response(subtitle_response)
    if subtitles is not None:
        subtitle_file_path = transcript_path.replace(".txt", "_subtitle.txt")
        with open(subtitle_file_path, 'w', encoding='utf-8') as f:
            # Write each subtitle on a new line
            for subtitle in subtitles.splitlines():
                f.write(subtitle.strip() + "\n")
            desired_part = '_'.join(os.path.splitext(os.path.basename(subtitle_file_path))[0].split('_')[:4])
            print(f"Subtitles saved to: {desired_part}")
    else:
        print(f"Warning: Could not generate subtitles for {transcript_path}. Skipping...")

    # Generate Chapters (with timestamps)
    if chapters is not None:
        chapters = sanitize_chapters(chapters)

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

def sanitize_chapters(chapters_text):
    """Removes extraneous text before and after the chapter list."""
    chapter_lines = chapters_text.splitlines()
    start_index = None
    end_index = None

    # Find the start and end indices of the actual chapter list
    for i, line in enumerate(chapter_lines):
        if line.startswith("["):  # Assuming chapters start with a timestamp in brackets
            if start_index is None:
                start_index = i
            end_index = i

    # Extract the relevant chapter lines
    if start_index is not None and end_index is not None:
        sanitized_chapters = "\n".join(chapter_lines[start_index:end_index+1])
        return sanitized_chapters
    else:
        # Handle cases where no chapters were found (maybe return original text or an error message)
        print("Warning: No chapters found in the generated text.")
        return chapters_text  # Return the original text if no chapters are found

def collate_summaries(transcriptions_folder):
    """Collate individual summary files from the transcriptions folder into 
    a single summary file in the parent (campaign) folder.
    """
    collated_data = []

    for filename in os.listdir(transcriptions_folder):
        date_match = re.match(r'^(\d{4}_\d{2}_\d{2})_.*', filename) 
        if not date_match:
            continue

        date_str = date_match.group(1)
        date = datetime.strptime(date_str, '%Y_%m_%d')

        if '_norm_revised.txt' in filename and not filename.endswith('_summary.txt'):
            with open(os.path.join(transcriptions_folder, filename), 'r', encoding='utf-8') as f:
                title = f.readline().strip()
            print(f"Title: {title}")
            collated_data.append((date, title, None))

        elif filename.endswith('_norm_revised_summary.txt'):
            with open(os.path.join(transcriptions_folder, filename), 'r', encoding='utf-8') as f:
                summary = f.read().strip()
            sanitized_summary = sanitize_summary(summary)

            for i, (stored_date, stored_title, _) in enumerate(collated_data):
                if stored_date == date:
                    collated_data[i] = (stored_date, stored_title, sanitized_summary)
                    break
            else:
                collated_data.append((date, None, sanitized_summary)) 

    collated_data.sort(key=lambda x: x[0])  # Sort data by date

    campaign_folder = os.path.dirname(transcriptions_folder)  # Get the parent campaign folder
    folder_name = os.path.basename(campaign_folder)
    output_filename = f"{folder_name} - Collated Summary.txt"  # Updated filename format

    with open(os.path.join(campaign_folder, output_filename), 'w', encoding='utf-8') as output_file:
        for date, title, summary in collated_data:
            if title:
                output_file.write(title + "\n")
            if summary:
                output_file.write(summary + "\n\n")

    print(f"Collated summary file generated: {output_filename}")

def bulk_summarize_transcripts(campaign_folder):
    """Summarizes all revised transcription files in a campaign folder."""
    from .file_management import find_transcriptions_folder
    transcriptions_folder = find_transcriptions_folder(campaign_folder)
    if transcriptions_folder:
        for filename in os.listdir(transcriptions_folder):
            if filename.endswith("_revised.txt") and "_norm" in filename:
                file_path = os.path.join(transcriptions_folder, filename)
                print(f"Summarizing: {file_path}")
                generate_summary_and_chapters(file_path)  # Use existing summarization function
        collate_summaries(transcriptions_folder)  # Collate after summarizing all files
    else:
        print(f"No 'Transcriptions' folder found in {campaign_folder}")