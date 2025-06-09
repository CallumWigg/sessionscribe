import os
import re
import time
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig, SafetySettingDict, HarmProbability

from . import utils, database_management as db

# Gemini Configuration
try:
    genai.configure(api_key=utils.config["gemini"]["api_key"])
    MODEL_NAME = utils.config["gemini"]["model_name"]
    model = genai.GenerativeModel(model_name=MODEL_NAME)
except KeyError as e:
    print(f"Error: Missing Gemini configuration key: {e}. Summarization features will not work.")
    model = None
except Exception as e:
    print(f"Error configuring Gemini: {e}. Summarization features will not work.")
    model = None

SAFETY_SETTING_MAP = {
    "BLOCK_NONE": HarmBlockThreshold.BLOCK_NONE,
    "BLOCK_LOW_AND_ABOVE": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "BLOCK_MEDIUM_AND_ABOVE": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "BLOCK_ONLY_HIGH": HarmBlockThreshold.BLOCK_ONLY_HIGH,
}
ALL_HARM_CATEGORIES = [HarmCategory.HARM_CATEGORY_HARASSMENT, HarmCategory.HARM_CATEGORY_HATE_SPEECH, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT]

# generate_text_with_gemini and process_gemini_response can remain the same.
def generate_text_with_gemini(prompt, input_text_path, max_output_tokens, temperature, safety_setting_str):
    if not model: return None
    gemini_safety_settings = [SafetySettingDict(harm_category=c, threshold=SAFETY_SETTING_MAP.get(safety_setting_str)) for c in ALL_HARM_CATEGORIES] if safety_setting_str in SAFETY_SETTING_MAP else None
    for attempt in range(3):
        try:
            uploaded_file = genai.upload_file(path=input_text_path, display_name=os.path.basename(input_text_path))
            response = model.generate_content(
                [prompt, uploaded_file],
                generation_config=GenerationConfig(max_output_tokens=max_output_tokens, temperature=temperature),
                safety_settings=gemini_safety_settings,
            )
            return response
        except Exception as e:
            print(f"Gemini API Error (Attempt {attempt + 1}): {e}")
            if attempt < 2: time.sleep(5)
    return None

def process_gemini_response(response):
    if not response or (response.prompt_feedback and response.prompt_feedback.block_reason): return None
    if not response.candidates or response.candidates[0].finish_reason != 1: return None
    if not response.candidates[0].content or not response.candidates[0].content.parts: return None
    return response.candidates[0].content.parts[0].text.strip()
    

def generate_summary_and_chapters(campaign_path, episode_id):
    """Generates summary, chapters, and subtitle for a specific episode."""
    if not model:
        print("Summarization skipped: Gemini model not available.")
        return

    episode = db.get_episode_by_id(campaign_path, episode_id)
    if not episode or not episode['transcription_file']:
        print(f"Error: Transcript file for episode {episode_id} not found in DB.")
        return
    
    transcript_txt_path = os.path.join(campaign_path, episode['transcription_file'])
    if not os.path.exists(transcript_txt_path):
        print(f"Error: Transcript file not found on disk: {transcript_txt_path}")
        return

    output_dir = os.path.dirname(transcript_txt_path)
    base_output_name = os.path.splitext(os.path.basename(transcript_txt_path))[0]

    # --- Generate Summary ---
    summary_input_text = ""
    try:
        with open(transcript_txt_path, "r", encoding="utf-8") as f:
            next(f, None); next(f, None) # Skip headers
            for line in f:
                match = re.match(r'(\d{2}:\d{2}:\d{2})\s*\|\s*(.*)', line)
                if match:
                    h, m, s = map(int, match.group(1).split(':'))
                    if (h * 3600 + m * 60 + s) >= utils.config["general"]["summary_skip_minutes"] * 60:
                        summary_input_text += match.group(2) + "\n"
    except Exception as e:
        print(f"Error reading transcript for summary: {e}"); return

    if summary_input_text.strip():
        temp_summary_input_file = os.path.join(output_dir, f"{base_output_name}_temp_for_summary.txt")
        try:
            with open(temp_summary_input_file, "w", encoding="utf-8") as temp_f: temp_f.write(summary_input_text)
            
            summary_prompt = "Generate a concise summary (around 150-200 words) of the provided D&D fantasy session transcript excerpt..."
            summary_response = generate_text_with_gemini(summary_prompt, temp_summary_input_file, 300, utils.config["gemini"]["temperature"], utils.config["gemini"]["safety_settings"])
            summary_text = process_gemini_response(summary_response)

            if summary_text:
                summary_file_path = os.path.join(output_dir, f"{base_output_name}_summary.txt")
                with open(summary_file_path, 'w', encoding='utf-8') as f_out: f_out.write(sanitize_summary(summary_text))
                db.update_episode_path(campaign_path, episode_id, "summary_file", summary_file_path)
                db.update_processing_status(campaign_path, episode_id, summarized=True, summarized_date=datetime.now(), summarized_model=MODEL_NAME)
                print(f"Summary saved to: {os.path.basename(summary_file_path)}")
        finally:
            if os.path.exists(temp_summary_input_file): os.remove(temp_summary_input_file)

    # --- Generate Chapters ---
    chapters_prompt = "Analyze the Dungeons and Dragons session transcript provided. Identify 5-7 main chapters..."
    chapters_response = generate_text_with_gemini(chapters_prompt, transcript_txt_path, 500, utils.config["gemini"]["temperature"], utils.config["gemini"]["safety_settings"])
    chapters_text = process_gemini_response(chapters_response)
    if chapters_text:
        chapters_file_path = os.path.join(output_dir, f"{base_output_name}_chapters.txt")
        with open(chapters_file_path, 'w', encoding='utf-8') as f_out: f_out.write(sanitize_chapters(chapters_text))
        db.update_episode_path(campaign_path, episode_id, "chapters_file", chapters_file_path)
        db.update_processing_status(campaign_path, episode_id, chapters_generated=True)
        print(f"Chapters saved to: {os.path.basename(chapters_file_path)}")

    # --- Generate Subtitles ---
    # This logic can be simplified as it's similar to summary generation
    subtitle_prompt = "Based on the provided D&D session transcript excerpt, generate 8-10 witty and concise podcast episode subtitles..."
    subtitles_response = generate_text_with_gemini(subtitle_prompt, transcript_txt_path, 600, 0.5 * utils.config["gemini"]["temperature"], utils.config["gemini"]["safety_settings"])
    subtitles_text = process_gemini_response(subtitles_response)
    if subtitles_text:
        subtitle_file_path = os.path.join(output_dir, f"{base_output_name}_subtitle.txt")
        with open(subtitle_file_path, 'w', encoding='utf-8') as f_out:
            for line in subtitles_text.splitlines():
                if line.strip(): f_out.write(line.strip() + "\n")
        db.update_episode_path(campaign_path, episode_id, "subtitle_file", subtitle_file_path)
        db.update_processing_status(campaign_path, episode_id, subtitles_generated=True)
        print(f"Subtitles saved to: {os.path.basename(subtitle_file_path)}")

def sanitize_summary(summary_text):
    if not summary_text: return ""
    return re.sub(r'(\n\s*){2,}', '\n\n', summary_text).strip()

def sanitize_chapters(chapters_text):
    if not chapters_text: return ""
    chapter_lines = [line.strip() for line in chapters_text.splitlines() if re.match(r'^\[\s*\d{2}:\d{2}:\d{2}\s*\]', line)]
    return "\n".join(chapter_lines) if chapter_lines else chapters_text.strip()


def collate_summaries(campaign_path):
    """Collates all summaries for a campaign from its database."""
    episodes_with_summaries = db.get_episodes_for_campaign(campaign_path, "WHERE ps.summarized = TRUE")
    if not episodes_with_summaries:
        print(f"No summarized episodes found to collate in campaign '{os.path.basename(campaign_path)}'.")
        return

    campaign_basename = os.path.basename(campaign_path)
    output_filename = f"{campaign_basename} - Collated Summaries.txt"
    output_filepath = os.path.join(campaign_path, output_filename)

    try:
        with open(output_filepath, 'w', encoding='utf-8') as output_file:
            output_file.write(f"# {campaign_basename} - Collated Summaries\n\n")
            for episode in episodes_with_summaries:
                output_file.write(f"## Episode {episode['episode_number']}: {episode['episode_title']}\n")
                summary_path = os.path.join(campaign_path, episode['summary_file'])
                if os.path.exists(summary_path):
                    with open(summary_path, 'r', encoding='utf-8') as f_summary:
                        output_file.write(f"{f_summary.read().strip()}\n\n")
                else:
                    output_file.write("Summary file not found.\n\n")
        print(f"Collated summary file generated: {output_filename}")
    except IOError as e:
        print(f"Error writing collated summary file '{output_filename}': {e}")


def bulk_summarize_transcripts(campaign_path):
    """Summarizes all text-processed episodes in a campaign that haven't been summarized."""
    if not model:
        print("Bulk summarization skipped: Gemini model not available.")
        return

    episodes_to_summarize = db.get_episodes_for_campaign(
        campaign_path, "WHERE ps.text_processed = TRUE AND ps.summarized = FALSE"
    )

    if not episodes_to_summarize:
        print("No new transcripts found to summarize.")
        return

    files_processed_count = 0
    for episode in episodes_to_summarize:
        print(f"\nProcessing for summarization: Episode #{episode['episode_number']} - {episode['episode_title']}")
        generate_summary_and_chapters(campaign_path, episode['episode_id'])
        files_processed_count += 1
    
    if files_processed_count > 0:
        print(f"\nBulk summarization complete for {files_processed_count} file(s). Now collating all summaries...")
        collate_summaries(campaign_path)
    else:
        print("No suitable transcript files found for bulk summarization.")