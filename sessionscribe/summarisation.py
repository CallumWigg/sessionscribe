import os
import re
import time
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig, SafetySettingDict

from . import utils, database_management as db

## C-IMPROVEMENT: A mapping from config strings to the actual API objects.
## This makes the config file user-friendly and the code robust.
SAFETY_SETTING_MAP = {
    "BLOCK_NONE": HarmBlockThreshold.BLOCK_NONE,
    "BLOCK_LOW_AND_ABOVE": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "BLOCK_MEDIUM_AND_ABOVE": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "BLOCK_ONLY_HIGH": HarmBlockThreshold.BLOCK_ONLY_HIGH,
}
ALL_HARM_CATEGORIES = [
    HarmCategory.HARM_CATEGORY_HARASSMENT, 
    HarmCategory.HARM_CATEGORY_HATE_SPEECH, 
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, 
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT
]

# Configure Gemini client
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

def _call_gemini_api(prompt, content, max_output_tokens, temperature, safety_setting_str):
    """
    Internal helper to centralize Gemini API calls, retries, and error handling.
    'content' can be a string or an uploaded file object.
    """
    if not model: return None
    
    ## C-IMPROVEMENT: Get the correct threshold from the map, defaulting to BLOCK_NONE
    ## for maximum permissiveness if the config value is invalid.
    threshold = SAFETY_SETTING_MAP.get(safety_setting_str, HarmBlockThreshold.BLOCK_NONE)
    gemini_safety_settings = [SafetySettingDict(harm_category=c, threshold=threshold) for c in ALL_HARM_CATEGORIES]
    
    for attempt in range(3):
        try:
            response = model.generate_content(
                [prompt, content],
                generation_config=GenerationConfig(max_output_tokens=max_output_tokens, temperature=temperature),
                safety_settings=gemini_safety_settings,
            )
            
            # Process and validate the response in one place
            if not response or (response.prompt_feedback and response.prompt_feedback.block_reason):
                print(f"Warning: Gemini response was blocked. Reason: {response.prompt_feedback.block_reason if response else 'Unknown'}")
                return None
            if not response.candidates or response.candidates[0].finish_reason != 1:
                print(f"Warning: Gemini response did not finish generating. Reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
                return None
            if not response.candidates[0].content or not response.candidates[0].content.parts:
                return None
            
            return response.candidates[0].content.parts[0].text.strip()

        except Exception as e:
            print(f"Gemini API Error (Attempt {attempt + 1}): {e}")
            if attempt < 2: 
                print("Retrying in 5 seconds...")
                time.sleep(5)
    return None

def _generate_summary(campaign_path, episode_id, transcript_txt_path, output_dir, base_output_name):
    """Generates and saves a summary for the episode."""
    # C-IMPROVEMENT: Reads text directly into memory instead of creating a temp file.
    summary_input_text = ""
    try:
        with open(transcript_txt_path, "r", encoding="utf-8") as f:
            # Skip file headers
            next(f, None); next(f, None)
            for line in f:
                # A more robust regex to find the timestamp and text
                match = re.search(r'(\d{2}:\d{2}:\d{2})\s*\|\s*(.*)', line)
                if match:
                    # Logic to skip the intro for summary generation remains
                    h, m, s = map(int, match.group(1).split(':'))
                    if (h * 3600 + m * 60 + s) >= utils.config["general"]["summary_skip_minutes"] * 60:
                        summary_input_text += match.group(2).strip() + "\n"
    except Exception as e:
        print(f"Error reading transcript for summary: {e}")
        return

    if summary_input_text.strip():
        summary_prompt = "Generate a concise summary (around 150-200 words) of the provided D&D fantasy session transcript excerpt. Focus on the key events, character actions, and major plot developments. The tone should be engaging and suitable for a podcast episode description."
        
        summary_text = _call_gemini_api(
            prompt=summary_prompt, 
            content=summary_input_text, # Pass the text directly
            max_output_tokens=400, 
            temperature=utils.config["gemini"]["temperature"],
            safety_setting_str=utils.config["gemini"]["safety_settings"]
        )

        if summary_text:
            summary_file_path = os.path.join(output_dir, f"{base_output_name}_summary.txt")
            with open(summary_file_path, 'w', encoding='utf-8') as f_out:
                f_out.write(sanitize_summary(summary_text))
            
            db.update_episode_path(campaign_path, episode_id, "summary_file", summary_file_path)
            db.update_processing_status(campaign_path, episode_id, summarized=True, summarized_date=datetime.now(), summarized_model=MODEL_NAME)
            print(f"  -> Summary saved.")
        else:
            print("  -> Summary generation failed or returned empty.")

def _generate_chapters(campaign_path, episode_id, uploaded_file, output_dir, base_output_name):
    """Generates and saves chapters for the episode using a pre-uploaded file."""
    chapters_prompt = "Analyze the Dungeons and Dragons session transcript provided. Identify 5-7 main chapters or distinct scenes. For each chapter, provide a start timestamp in [HH:MM:SS] format and a short, descriptive title. The output should be a simple list, with each chapter on a new line."
    
    chapters_text = _call_gemini_api(
        prompt=chapters_prompt,
        content=uploaded_file, # Reuse the uploaded file
        max_output_tokens=500,
        temperature=utils.config["gemini"]["temperature"],
        safety_setting_str=utils.config["gemini"]["safety_settings"]
    )
    
    if chapters_text:
        chapters_file_path = os.path.join(output_dir, f"{base_output_name}_chapters.txt")
        with open(chapters_file_path, 'w', encoding='utf-8') as f_out:
            f_out.write(sanitize_chapters(chapters_text))
            
        db.update_episode_path(campaign_path, episode_id, "chapters_file", chapters_file_path)
        db.update_processing_status(campaign_path, episode_id, chapters_generated=True)
        print(f"  -> Chapters saved.")
    else:
        print("  -> Chapter generation failed or returned empty.")

def _generate_subtitles(campaign_path, episode_id, uploaded_file, output_dir, base_output_name):
    """Generates and saves subtitle ideas for the episode using a pre-uploaded file."""
    subtitle_prompt = "Based on the provided D&D session transcript, generate a list of 8-10 witty, intriguing, and concise podcast episode subtitles. Each subtitle should be a short phrase that captures a key moment, a funny quote, or a dramatic event from the session. List each subtitle on a new line without any prefixes like numbers or dashes."
    
    subtitles_text = _call_gemini_api(
        prompt=subtitle_prompt,
        content=uploaded_file, # Reuse the uploaded file
        max_output_tokens=600,
        temperature=0.5 * utils.config["gemini"]["temperature"], # Lower temp for more focused output
        safety_setting_str=utils.config["gemini"]["safety_settings"]
    )
    
    if subtitles_text:
        subtitle_file_path = os.path.join(output_dir, f"{base_output_name}_subtitle.txt")
        with open(subtitle_file_path, 'w', encoding='utf-8') as f_out:
            # Clean up the output to ensure one subtitle per line
            for line in subtitles_text.splitlines():
                clean_line = line.strip()
                if clean_line:
                    f_out.write(clean_line + "\n")
                    
        db.update_episode_path(campaign_path, episode_id, "subtitle_file", subtitle_file_path)
        db.update_processing_status(campaign_path, episode_id, subtitles_generated=True)
        print(f"  -> Subtitles saved.")
    else:
        print("  -> Subtitle generation failed or returned empty.")


def generate_summary_and_chapters(campaign_path, episode_id):
    """
    Generates summary, chapters, and subtitles for a specific episode.
    Now optimized to upload the transcript only ONCE.
    """
    if not model:
        print("Summarization skipped: Gemini model not configured or failed to initialize.")
        return

    episode = db.get_episode_by_id(campaign_path, episode_id)
    if not episode or not episode['transcription_file']:
        print(f"Error: Transcript file for episode {episode_id} not found in DB.")
        return
    
    transcript_txt_path = os.path.join(campaign_path, episode['transcription_file'])
    if not os.path.exists(transcript_txt_path):
        print(f"Error: Transcript file not found on disk: {transcript_txt_path}")
        return

    print(f"Generating Gemini content for: {os.path.basename(transcript_txt_path)}")
    output_dir = os.path.dirname(transcript_txt_path)
    # The base name for all generated files, e.g., "YYYY_MM_DD_Episode_Title_norm_revised"
    base_output_name = os.path.splitext(os.path.basename(transcript_txt_path))[0]
    
    # --- Step 1: Generate Summary (uses text, no upload needed) ---
    _generate_summary(campaign_path, episode_id, transcript_txt_path, output_dir, base_output_name)
    
    # --- Step 2: Upload file ONCE for chapters and subtitles ---
    uploaded_file = None
    try:
        print("Uploading transcript to Google for chapter and subtitle generation...")
        uploaded_file = genai.upload_file(path=transcript_txt_path, display_name=os.path.basename(transcript_txt_path))
        
        # --- Step 3: Generate Chapters and Subtitles using the uploaded file ---
        _generate_chapters(campaign_path, episode_id, uploaded_file, output_dir, base_output_name)
        _generate_subtitles(campaign_path, episode_id, uploaded_file, output_dir, base_output_name)
        
    except Exception as e:
        print(f"Error during file upload or generation for Gemini: {e}")
    finally:
        # Clean up the uploaded file from Google's servers
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e_del:
                print(f"Warning: Could not delete temporary uploaded file from Google: {e_del}")


def sanitize_summary(summary_text):
    """Removes extra newlines from summary text."""
    if not summary_text: return ""
    return re.sub(r'(\n\s*){2,}', '\n\n', summary_text).strip()

def sanitize_chapters(chapters_text):
    """Cleans chapter output to only include lines that look like chapters."""
    if not chapters_text: return ""
    # More robust regex: allows for optional whitespace and different bracket styles
    chapter_lines = [line.strip() for line in chapters_text.splitlines() if re.search(r'\[\s*\d{1,2}:\d{2}:\d{2}\s*\]', line)]
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
                if episode['summary_file']:
                    summary_path = os.path.join(campaign_path, episode['summary_file'])
                    if os.path.exists(summary_path):
                        with open(summary_path, 'r', encoding='utf-8') as f_summary:
                            output_file.write(f"{f_summary.read().strip()}\n\n")
                    else:
                        output_file.write("Summary file not found on disk.\n\n")
                else:
                    output_file.write("Summary file not found in database record.\n\n")
        print(f"Collated summary file generated: {output_filename}")
    except IOError as e:
        print(f"Error writing collated summary file '{output_filename}': {e}")


def bulk_summarize_transcripts(campaign_path):
    """Summarizes all text-processed episodes in a campaign that haven't been summarized."""
    if not model:
        print("Bulk summarization skipped: Gemini model not available.")
        return

    episodes_to_summarize = db.get_episodes_for_campaign(
        campaign_path, "WHERE ps.text_processed = TRUE AND (ps.summarized = FALSE OR ps.chapters_generated = FALSE OR ps.subtitles_generated = FALSE)"
    )

    if not episodes_to_summarize:
        print("No new transcripts found to summarize.")
        return

    print(f"\nFound {len(episodes_to_summarize)} episode(s) needing summarization/chapter generation.")
    for episode in episodes_to_summarize:
        print(f"\nProcessing for summarization: Episode #{episode['episode_number']} - {episode['episode_title']}")
        generate_summary_and_chapters(campaign_path, episode['episode_id'])
    
    if episodes_to_summarize:
        print(f"\nBulk summarization complete. Now collating all summaries...")
        collate_summaries(campaign_path)