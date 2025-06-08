import os
import re
import time
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig, SafetySettingDict, HarmProbability

from .utils import config # Assuming utils.py is in the same package
# Removed format_time import as it's not used in this file.

# Gemini Configuration
try:
    genai.configure(api_key=config["gemini"]["api_key"])
    MODEL_NAME = config["gemini"]["model_name"]
    model = genai.GenerativeModel(model_name=MODEL_NAME)
except KeyError as e:
    print(f"Error: Missing Gemini configuration key: {e}. Summarization features will not work.")
    model = None
except Exception as e:
    print(f"Error configuring Gemini: {e}. Summarization features will not work.")
    model = None

# Mapping for safety settings string from config to Gemini enums
SAFETY_SETTING_MAP = {
    "BLOCK_NONE": HarmBlockThreshold.BLOCK_NONE,
    "BLOCK_LOW_AND_ABOVE": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "BLOCK_MEDIUM_AND_ABOVE": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "BLOCK_ONLY_HIGH": HarmBlockThreshold.BLOCK_ONLY_HIGH,
    # Add more mappings if your config uses different strings
}

ALL_HARM_CATEGORIES = [
    HarmCategory.HARM_CATEGORY_HARASSMENT,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
]


def generate_text_with_gemini(prompt, input_text_path, max_output_tokens, temperature, safety_setting_str):
    """Uploads text from file to Gemini, generates content, and handles retries."""
    if not model:
        print("Gemini model not initialized. Cannot generate text.")
        return None

    max_retries = 3
    current_temp = temperature

    # Construct safety settings dictionary
    gemini_safety_settings = []
    if safety_setting_str in SAFETY_SETTING_MAP:
        threshold = SAFETY_SETTING_MAP[safety_setting_str]
        for category in ALL_HARM_CATEGORIES:
            gemini_safety_settings.append(SafetySettingDict(harm_category=category, threshold=threshold))
    else:
        print(f"Warning: Unknown safety setting string '{safety_setting_str}'. Using Gemini defaults.")
        # gemini_safety_settings will be empty, letting model use defaults


    for attempt in range(max_retries):
        try:
            # Gemini API expects files to be uploaded if they are used as direct input like this.
            # The path is used for display_name. Content is read from the path.
            print(f"Uploading file to Gemini: {os.path.basename(input_text_path)} for prompt: '{prompt[:50]}...'")
            uploaded_file = genai.upload_file(path=input_text_path, display_name=os.path.basename(input_text_path))
            
            # Wait for processing, though for text/plain it's usually fast
            # It's good practice if upload_file doesn't block until active
            # However, current genai.upload_file seems to return an active file or raise error.
            # If it were asynchronous:
            # while uploaded_file.state.name == "PROCESSING":
            #     print("Waiting for file processing by Gemini...")
            #     time.sleep(5)
            #     uploaded_file = genai.get_file(name=uploaded_file.name) # Refresh status
            # if uploaded_file.state.name != "ACTIVE":
            #     raise Exception(f"File '{uploaded_file.name}' failed to process. State: {uploaded_file.state.name}")


            generation_config_obj = GenerationConfig(
                max_output_tokens=max_output_tokens,
                temperature=current_temp
            )

            print(f"Generating content (Attempt {attempt + 1}, Temp: {current_temp}, Safety: {safety_setting_str})...")
            response = model.generate_content(
                [prompt, uploaded_file], # Pass the uploaded file object
                generation_config=generation_config_obj,
                safety_settings=gemini_safety_settings if gemini_safety_settings else None,
            )
            
            # After generation, can delete the uploaded file if no longer needed by Gemini
            # genai.delete_file(uploaded_file.name) # Optional cleanup

            return response
        
        except Exception as e:
            print(f"Gemini API Error (Attempt {attempt + 1}): {e}")
            current_temp = min(1.0, current_temp + 0.2) # Increase temperature, max 1.0
            if attempt < max_retries - 1:
                print(f"Retrying with temperature: {current_temp}")
                time.sleep(5) # Wait before retrying
            else:
                print(f"Warning: Could not generate text after {max_retries} attempts for {os.path.basename(input_text_path)}.")
    return None

def process_gemini_response(response):
    """Checks for safety violations and extracts generated text."""
    if response is None:
        return None

    # Check for outright blocking first via prompt_feedback
    if response.prompt_feedback and response.prompt_feedback.block_reason:
        print(f"Warning: Prompt blocked by Gemini. Reason: {response.prompt_feedback.block_reason.name}")
        # You might want to see detailed safety ratings that caused the block if available
        for rating in response.prompt_feedback.safety_ratings:
            print(f"  - Category: {rating.category.name}, Probability: {rating.probability.name}")
        return None # Or raise an exception

    if not response.candidates:
        print("Warning: No candidates in Gemini response.")
        if hasattr(response, 'text'): # Sometimes simple errors might just have text
             print(f"Response text (if any): {response.text}")
        return None

    candidate = response.candidates[0]
    
    # Check finish reason
    if candidate.finish_reason != 1: # 1 is 'STOP' (successful)
        # Other reasons: 2=MAX_TOKENS, 3=SAFETY, 4=RECITATION, 5=OTHER
        print(f"Warning: Gemini generation finished with reason: {candidate.finish_reason.name}")
        if candidate.finish_reason == 3: # SAFETY
                    print("  Detailed safety ratings for the generated content:")
                    for rating in candidate.safety_ratings:
                        # HarmProbability enum: NEGLIGIBLE, LOW, MEDIUM, HIGH
                        # We might consider MEDIUM or HIGH as problematic
                        if rating.probability in [HarmProbability.MEDIUM, HarmProbability.HIGH]: # Changed SafetyRating.HarmProbability to HarmProbability
                            print(f"    - Harm Category: {rating.category.name}, Probability: {rating.probability.name} (Problematic)")
                        else:
                            print(f"    - Harm Category: {rating.category.name}, Probability: {rating.probability.name}")
                    return None # Blocked due to safety
    

    if not candidate.content or not candidate.content.parts:
        print("Warning: No text parts found in the response candidate.")
        return None
    
    # Assuming the first part is the text we want
    generated_text = candidate.content.parts[0].text
    return generated_text.strip()


def generate_summary_and_chapters(transcript_txt_path):
    """Generates summary, chapters, and subtitle using Gemini from a revised TXT file.
    transcript_txt_path is the absolute path to the _norm_revised.txt file.
    """
    if not model:
        print("Summarization skipped: Gemini model not available.")
        return

    if not os.path.exists(transcript_txt_path):
        print(f"Error: Transcript file not found: {transcript_txt_path}")
        return

    # Base name for output files, e.g., YYYY_MM_DD_title_norm_revised
    base_output_name = os.path.splitext(os.path.basename(transcript_txt_path))[0]
    output_dir = os.path.dirname(transcript_txt_path) # Summaries/chapters go in same dir as transcript

    # --- Generate Summary ---
    # For summary, we often skip initial chit-chat. Use text without timestamps for this.
    # And potentially skip first N minutes of content.
    
    summary_input_text = ""
    try:
        with open(transcript_txt_path, "r", encoding="utf-8") as f:
            # Skip header line (Title - #Track - Date)
            next(f, None) 
            next(f, None) # Skip blank line after header

            for line in f:
                # Line format: HH:MM:SS   |   Caption text
                match = re.match(r'(\d{2}:\d{2}:\d{2})\s*\|\s*(.*)', line)
                if match:
                    timestamp_str = match.group(1)
                    caption = match.group(2)
                    
                    # Convert HH:MM:SS to total seconds
                    h, m, s = map(int, timestamp_str.split(':'))
                    total_seconds = h * 3600 + m * 60 + s
                    
                    if total_seconds >= config["general"]["summary_skip_minutes"] * 60:
                        summary_input_text += caption + "\n"
    except Exception as e:
        print(f"Error reading transcript for summary: {e}")
        return # Cannot proceed if transcript can't be read

    if not summary_input_text.strip():
        print(f"No content found in {transcript_txt_path} after skipping initial minutes. Cannot generate summary.")
    else:
        # Write this filtered text to a temporary file for Gemini upload
        temp_summary_input_file = os.path.join(output_dir, f"{base_output_name}_temp_for_summary.txt")
        try:
            with open(temp_summary_input_file, "w", encoding="utf-8") as temp_f:
                temp_f.write(summary_input_text)

            summary_prompt = "Generate a concise summary (around 150-200 words) of the provided D&D fantasy session transcript excerpt. Focus on the key events and plot progression, assuming the reader has context of the ongoing campaign."
            summary_response = generate_text_with_gemini(
                summary_prompt, 
                temp_summary_input_file, 
                max_output_tokens=300, # Generous for a 200-word summary
                temperature=config["gemini"]["temperature"], 
                safety_setting_str=config["gemini"]["safety_settings"]
            )
            summary_text = process_gemini_response(summary_response)

            if summary_text:
                summary_file_path = os.path.join(output_dir, f"{base_output_name}_summary.txt")
                with open(summary_file_path, 'w', encoding='utf-8') as f_out:
                    f_out.write(sanitize_summary(summary_text))
                print(f"Summary saved to: {os.path.basename(summary_file_path)}")
            else:
                print(f"Failed to generate summary for {os.path.basename(transcript_txt_path)}.")
        
        finally:
            if os.path.exists(temp_summary_input_file):
                os.remove(temp_summary_input_file)


    # --- Generate Chapters (uses the full transcript_txt_path) ---
    chapters_prompt = """
    Analyze the Dungeons and Dragons session transcript provided. Identify 5-7 main chapters or distinct topic segments. 
    For each chapter, provide:
    1. The starting timestamp in HH:MM:SS format.
    2. A concise, engaging title for the chapter.
    3. A brief one-sentence description of what happens in that chapter.

    Format each chapter as:
    [HH:MM:SS] Chapter Title - Brief description.

    Ensure chapters are distributed reasonably across the session's duration and represent significant shifts in activity, location, or plot.
    The transcript is formatted with lines like: HH:MM:SS   |   Dialogue or action.
    """
    chapters_response = generate_text_with_gemini(
        chapters_prompt,
        transcript_txt_path, # Use the original full transcript with timestamps
        max_output_tokens=500, # Enough for 5-7 chapters with titles/descriptions
        temperature=config["gemini"]["temperature"],
        safety_setting_str=config["gemini"]["safety_settings"]
    )
    chapters_text = process_gemini_response(chapters_response)

    if chapters_text:
        chapters_file_path = os.path.join(output_dir, f"{base_output_name}_chapters.txt")
        with open(chapters_file_path, 'w', encoding='utf-8') as f_out:
            f_out.write(sanitize_chapters(chapters_text))
        print(f"Chapters saved to: {os.path.basename(chapters_file_path)}")
    else:
        print(f"Failed to generate chapters for {os.path.basename(transcript_txt_path)}.")

    # --- Generate Podcast Subtitles (uses the summary_input_text or full transcript if summary failed) ---
    # Use temp_summary_input_file if it was created and populated, otherwise full transcript
    subtitle_source_file_for_gemini = None
    temp_summary_file_path_for_subtitles = os.path.join(output_dir, f"{base_output_name}_temp_for_summary.txt") # Path from summary section

    if summary_input_text.strip(): # If summary_input_text was successfully prepared
        # We need to ensure the temp file for summary exists if we re-use it here
        try:
            with open(temp_summary_file_path_for_subtitles, "w", encoding="utf-8") as temp_f: # Recreate or ensure it exists
                 temp_f.write(summary_input_text)
            subtitle_source_file_for_gemini = temp_summary_file_path_for_subtitles
        except Exception as e:
            print(f"Could not prepare temp summary file for subtitles, using full transcript: {e}")
            subtitle_source_file_for_gemini = transcript_txt_path
    else: # Fallback to full transcript if summary text was empty
        subtitle_source_file_for_gemini = transcript_txt_path


    subtitle_prompt = """
    Based on the provided D&D session transcript excerpt, generate 8-10 witty and concise podcast episode subtitles.
    Each subtitle should be around 40-60 characters.
    These should be catchy taglines hinting at major events, themes, or memorable moments, not direct summaries.
    Avoid character names. Focus on intriguing phrases that pique listener interest.
    Output each subtitle on a new line, without numbering or bullet points.
    """
    subtitles_response = generate_text_with_gemini(
        subtitle_prompt,
        subtitle_source_file_for_gemini,
        max_output_tokens=600, # Enough for 10 lines of ~60 chars
        temperature=0.5 * config["gemini"]["temperature"], # Slightly lower temp for more focused taglines
        safety_setting_str=config["gemini"]["safety_settings"]
    )
    subtitles_text = process_gemini_response(subtitles_response)

    if subtitles_text:
        subtitle_file_path = os.path.join(output_dir, f"{base_output_name}_subtitle.txt")
        with open(subtitle_file_path, 'w', encoding='utf-8') as f_out:
            # Sanitize: ensure each subtitle is on its own line, strip extra whitespace
            for line in subtitles_text.splitlines():
                clean_line = line.strip()
                if clean_line: # Only write non-empty lines
                    f_out.write(clean_line + "\n")
        print(f"Subtitles saved to: {os.path.basename(subtitle_file_path)}")
    else:
        print(f"Failed to generate subtitles for {os.path.basename(transcript_txt_path)}.")
    
    # Clean up temp summary file if it was created for subtitles
    if os.path.exists(temp_summary_file_path_for_subtitles):
        try:
            os.remove(temp_summary_file_path_for_subtitles)
        except OSError:
            pass # Ignore if removal fails


def sanitize_summary(summary_text):
    """Replace multiple line breaks with a single line break and strip."""
    if not summary_text: return ""
    sanitized = re.sub(r'(\n\s*){2,}', '\n\n', summary_text) # Max 2 newlines for paragraph breaks
    return sanitized.strip()

def sanitize_chapters(chapters_text):
    """Removes extraneous text, keeping only lines that look like chapters."""
    if not chapters_text: return ""
    
    chapter_lines = []
    for line in chapters_text.splitlines():
        line = line.strip()
        # Regex for [HH:MM:SS] Chapter Title - Description
        if re.match(r'^\[\s*\d{2}:\d{2}:\d{2}\s*\]\s*.*?\s*-\s*.*', line):
            chapter_lines.append(line)
    
    if not chapter_lines:
        print("Warning: No valid chapter lines found in sanitize_chapters. Returning original text.")
        return chapters_text.strip() # Return original if no standard lines found
        
    return "\n".join(chapter_lines)


def collate_summaries(transcriptions_folder_path):
    """Collate individual summary files from the transcriptions folder into
    a single summary file in the parent (campaign) folder.
    transcriptions_folder_path is the absolute path to the campaign's Transcriptions subfolder.
    """
    if not transcriptions_folder_path or not os.path.isdir(transcriptions_folder_path):
        print(f"Error: Transcriptions folder not found or invalid: {transcriptions_folder_path}")
        return

    collated_entries = [] # List of tuples: (date_obj, title_str, summary_text_str)

    for filename in os.listdir(transcriptions_folder_path):
        file_path = os.path.join(transcriptions_folder_path, filename)
        
        # Match YYYY_MM_DD from filename start
        date_match = re.match(r'^(\d{4}_\d{2}_\d{2})', filename)
        if not date_match:
            continue
        
        date_str = date_match.group(1)
        try:
            date_obj = datetime.strptime(date_str, '%Y_%m_%d')
        except ValueError:
            print(f"Warning: Could not parse date from filename {filename}. Skipping.")
            continue

        # Try to get title from _norm_revised.txt and summary from _norm_revised_summary.txt
        if filename.endswith("_norm_revised.txt"):
            # This is a main transcript file, try to find its corresponding summary
            summary_filename = filename.replace(".txt", "_summary.txt")
            summary_filepath = os.path.join(transcriptions_folder_path, summary_filename)
            
            title_from_transcript = "Unknown Title"
            try:
                with open(file_path, 'r', encoding='utf-8') as f_transcript:
                    title_from_transcript = f_transcript.readline().strip() # First line is header
            except IOError:
                print(f"Warning: Could not read transcript {filename} for title.")

            summary_text = None
            if os.path.exists(summary_filepath):
                try:
                    with open(summary_filepath, 'r', encoding='utf-8') as f_summary:
                        summary_text = sanitize_summary(f_summary.read())
                except IOError:
                    print(f"Warning: Could not read summary file {summary_filename}.")
            
            collated_entries.append((date_obj, title_from_transcript, summary_text))

    if not collated_entries:
        print(f"No summaries or transcripts found to collate in {transcriptions_folder_path}.")
        return

    collated_entries.sort(key=lambda x: x[0])  # Sort by date_obj (chronological)

    campaign_folder_path = os.path.dirname(transcriptions_folder_path)  # Parent campaign folder
    campaign_basename = os.path.basename(campaign_folder_path)
    output_filename = f"{campaign_basename} - Collated Summaries.txt" # Corrected filename
    output_filepath = os.path.join(campaign_folder_path, output_filename)

    try:
        with open(output_filepath, 'w', encoding='utf-8') as output_file:
            output_file.write(f"# {campaign_basename} - Collated Summaries\n\n")
            for date_obj, title, summary in collated_entries:
                output_file.write(f"## {title}\n") # Title from transcript header
                if summary:
                    output_file.write(f"{summary}\n\n")
                else:
                    output_file.write("Summary not available.\n\n")
        print(f"Collated summary file generated: {output_filename} in {campaign_folder_path}")
    except IOError as e:
        print(f"Error writing collated summary file '{output_filename}': {e}")


def bulk_summarize_transcripts(campaign_folder_path):
    """Summarizes all revised transcription files in a campaign folder."""
    from .file_management import find_transcriptions_folder # Local import

    if not model:
        print("Bulk summarization skipped: Gemini model not available.")
        return

    transcriptions_folder = find_transcriptions_folder(campaign_folder_path)
    if not transcriptions_folder:
        print(f"No 'Transcriptions' folder found in campaign '{os.path.basename(campaign_folder_path)}'. Cannot bulk summarize.")
        return

    files_processed_count = 0
    for filename in os.listdir(transcriptions_folder):
        if filename.endswith("_norm_revised.txt"):
            file_path = os.path.join(transcriptions_folder, filename)
            print(f"\nProcessing for summarization: {filename}")
            generate_summary_and_chapters(file_path)
            files_processed_count +=1
    
    if files_processed_count > 0:
        print(f"\nBulk summarization complete for {files_processed_count} file(s). Now collating all summaries...")
        collate_summaries(transcriptions_folder)
    else:
        print("No suitable transcript files found for bulk summarization.")