import os
import re
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory, GenerationConfig, SafetySettingDict

from .utils import config, format_time

# Gemini Configuration
genai.configure(api_key=config["gemini"]["api_key"])

model = genai.GenerativeModel(
  model_name=config["gemini"]["model_name"]
)

safety_config = [
    SafetySettingDict(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySettingDict(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySettingDict(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySettingDict(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
]

def generate_summary_and_chapters(transcript_path):
    """Generates a summary and timestamped chapters using the Gemini API."""
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

    max_retries = 3
    temperature = config["gemini"]["temperature"]  # Initial temperature
    for attempt in range(max_retries):
        try:
            file_summary = genai.upload_file(temp_summary_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.txt", "_summary.txt"))
            while file_summary.state.name == "PROCESSING":
                time.sleep(10)
                file_summary = genai.get_file(file_summary.name)
            if file_summary.state.name != "ACTIVE":
                raise Exception(f"File {file_summary.name} failed to process")

            content_config = GenerationConfig(
                max_output_tokens=300,
                temperature=temperature
            )

            summary_response = model.generate_content(
                [file_summary, "Generate a short 200-word summary of this dungeons and dragons session transcript. Write as a synopsis of the events, assuming the reader understands the context of the campaign."],
                generation_config=content_config,
                safety_settings=safety_config,
            )

            if summary_response.is_blocked:
                raise Exception("Summary generation blocked by safety filter.")

            summary = summary_response.text
            break  # Exit the retry loop if successful
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            temperature += 0.2  # Reduce temperature for the next attempt
            if attempt < max_retries - 1:
                print(f"Retrying with temperature: {temperature}")
            else:
                print(f"Warning: Could not generate summary for {transcript_path} after {max_retries} attempts.")

    if summary is not None:
        summary_file_path = transcript_path.replace(".txt", "_summary.txt")  # Create summary filename

        with open(summary_file_path, 'w', encoding='utf-8') as f:
            f.write(summary)
            desired_part = '_'.join(os.path.splitext(os.path.basename(summary_file_path))[0].split('_')[:4])
            print(f"Summary saved to: {desired_part}")
    else:
        print(f"Warning: Could not generate summary for {transcript_path}. Skipping...")

    # Generate Chapters (with timestamps)
    chapters_prompt_text = """
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

    temperature = config["gemini"]["temperature"]  # Reset temperature for chapters
    temp_chapters_file = transcript_path.replace("_revised.txt", "_temp_chapters.txt")
    with open(temp_chapters_file, "w", encoding="utf-8") as temp_f:
        temp_f.write(transcript_text)

    for attempt in range(max_retries):
        try:
            file_chapters = genai.upload_file(temp_chapters_file, mime_type="text/plain", display_name=os.path.basename(transcript_path).replace("_revised.txt", "_chapters.txt"))
            while file_chapters.state.name == "PROCESSING":
                time.sleep(10)
                file_chapters = genai.get_file(file_chapters.name)
            if file_chapters.state.name != "ACTIVE":
                raise Exception(f"File {file_chapters.name} failed to process")

            # Set the temperature for the model
            model.generation_config["temperature"] = temperature

            content_config = GenerationConfig(
                max_output_tokens=300,
                temperature=temperature
            )

            chapters_response = model.generate_content(
                [file_chapters, chapters_prompt_text],
                generation_config=content_config,
                safety_settings=safety_config,
            )

            if chapters_response.is_blocked:
                raise Exception("Chapters generation blocked by safety filter.")

            chapters = chapters_response.text
            break  # Exit the retry loop if successful
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            temperature += 0.2  # Reduce temperature for the next attempt
            if attempt < max_retries - 1:
                print(f"Retrying with temperature: {temperature}")
            else:
                print(f"Warning: Could not generate chapters for {transcript_path} after {max_retries} attempts.")

    if chapters is not None:
        chapters = sanitize_chapters(chapters)

        chapters_file_path = transcript_path.replace(".txt", "_chapters.txt")  # Create chapter filename

        with open(chapters_file_path, 'w', encoding='utf-8') as f:
            f.write(chapters)
            desired_part = '_'.join(os.path.splitext(os.path.basename(chapters_file_path))[0].split('_')[:4])
            print(f"Chapters saved to: {desired_part}")
    else:
        print(f"    Warning: Could not generate chapters for {transcript_path}. Skipping...")

    # Generate Podcast Subtitle
    subtitle = None
    try:
        # Set the temperature for the model (consider using a lower temperature for conciseness)
        subtitle_temp = 0.5*config["gemini"]["temperature"]
        model.generation_config["temperature"] = subtitle_temp

        content_config = GenerationConfig(
            max_output_tokens=50,
            temperature=subtitle_temp
        )

        subtitle_response = model.generate_content(
            [file_summary, "Generate a very short and concise, ~50 character podcast subtitle that captures the main plot points or advancements that occurred in this Dungeons and Dragons session. Avoid using character names."],
            generation_config=content_config,
            safety_settings=safety_config,
        )

        if subtitle_response.is_blocked:
            raise Exception("Subtitle generation blocked by safety filter.")

        subtitle = subtitle_response.text.strip()

        if len(subtitle) > 50:
            subtitle = subtitle[:50] + "..."  # Truncate if necessary

    except Exception as e:
        print(f"Warning: Could not generate subtitle: {e}")

    if subtitle is not None:
        subtitle_file_path = transcript_path.replace(".txt", "_subtitle.txt")  # Create subtitle filename

        with open(subtitle_file_path, 'w', encoding='utf-8') as f:
            f.write(subtitle)
            desired_part = '_'.join(os.path.splitext(os.path.basename(subtitle_file_path))[0].split('_')[:4])
            print(f"Subtitle saved to: {desired_part}")
    else:
        print(f"    Warning: Could not generate subtitle for {transcript_path}. Skipping...")

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