import sqlite3
import os
import re
import json
from datetime import datetime

import ffmpeg

# Local import to avoid circular dependency issues at module load time
from . import file_management
from .utils import config

DATABASE_NAME = "sessionscribe.db"

def get_db_connection(campaign_path):
    """Establishes a connection to the SQLite database for a specific campaign."""
    db_path = os.path.join(campaign_path, DATABASE_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def create_schema(conn):
    """Creates the database schema if the tables don't exist."""
    cursor = conn.cursor()
    # Episodes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Episodes (
        episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_number INTEGER,
        episode_number INTEGER NOT NULL,
        episode_title TEXT NOT NULL,
        base_episode_title TEXT NOT NULL,
        original_audio_file TEXT,
        normalized_audio_file TEXT,
        transcription_file TEXT,
        summary_file TEXT,
        chapters_file TEXT,
        subtitle_file TEXT,
        recorded_date DATE,
        episode_length_seconds REAL DEFAULT -1,
        metadata TEXT -- JSON object
    )
    """)

    # ProcessingStatus Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ProcessingStatus (
        episode_id INTEGER NOT NULL,
        normalized BOOLEAN DEFAULT FALSE,
        normalized_bitrate INTEGER,
        transcribed BOOLEAN DEFAULT FALSE,
        transcribed_model TEXT,
        transcribed_date TIMESTAMP,
        text_processed BOOLEAN DEFAULT FALSE,
        summarized BOOLEAN DEFAULT FALSE,
        summarized_model TEXT,
        summarized_date TIMESTAMP,
        chapters_generated BOOLEAN DEFAULT FALSE,
        subtitles_generated BOOLEAN DEFAULT FALSE,
        last_processed TIMESTAMP,
        PRIMARY KEY (episode_id),
        FOREIGN KEY (episode_id) REFERENCES Episodes(episode_id)
    )
    """)
    conn.commit()

def init_campaign_db(campaign_path):
    """Initializes the database for a campaign, creating it if it doesn't exist."""
    if not os.path.isdir(campaign_path):
        return None
    try:
        conn = get_db_connection(campaign_path)
        create_schema(conn)
        conn.close()
        return os.path.join(campaign_path, DATABASE_NAME)
    except Exception as e:
        print(f"Error initializing database for {campaign_path}: {e}")
        return None

def add_episode(campaign_path, episode_data):
    """Adds a new episode and its initial processing status to the database.
    episode_data is a dict with keys matching Episodes table columns.
    Returns the new episode_id.
    """
    conn = get_db_connection(campaign_path)
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(episode_number) FROM Episodes")
    max_episode_num = cursor.fetchone()[0]
    next_episode_num = (max_episode_num or 0) + 1
    
    episode_data['episode_number'] = next_episode_num

    cols = ', '.join(episode_data.keys())
    placeholders = ', '.join('?' * len(episode_data))
    sql = f"INSERT INTO Episodes ({cols}) VALUES ({placeholders})"
    cursor.execute(sql, list(episode_data.values()))
    episode_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO ProcessingStatus (episode_id, last_processed) VALUES (?, ?)",
        (episode_id, datetime.now())
    )
    
    conn.commit()
    conn.close()
    return episode_id

def update_episode_data(campaign_path, episode_id, data_dict):
    """Updates multiple columns for a given episode_id in the Episodes table."""
    if not data_dict:
        return
    
    update_cols = ', '.join([f"{key} = ?" for key in data_dict.keys()])
    values = list(data_dict.values())
    values.append(episode_id)

    sql = f"UPDATE Episodes SET {update_cols} WHERE episode_id = ?"
    
    conn = get_db_connection(campaign_path)
    conn.execute(sql, values)
    conn.commit()
    conn.close()

def update_episode_path(campaign_path, episode_id, file_type, file_path):
    """Updates the path for a specific file type of an episode."""
    valid_file_types = [
        "original_audio_file", "normalized_audio_file", "transcription_file",
        "summary_file", "chapters_file", "subtitle_file"
    ]
    if file_type not in valid_file_types:
        print(f"Error: Invalid file type '{file_type}' for episode update.")
        return

    try:
        relative_path = os.path.relpath(file_path, campaign_path)
    except ValueError:
        relative_path = file_path

    conn = get_db_connection(campaign_path)
    conn.execute(
        f"UPDATE Episodes SET {file_type} = ? WHERE episode_id = ?",
        (relative_path, episode_id)
    )
    conn.commit()
    conn.close()

def update_processing_status(campaign_path, episode_id, **kwargs):
    """Updates flags in the ProcessingStatus table."""
    if not kwargs:
        return
    
    kwargs['last_processed'] = datetime.now()
    update_cols = ', '.join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values())
    values.append(episode_id)
    sql = f"UPDATE ProcessingStatus SET {update_cols} WHERE episode_id = ?"
    
    conn = get_db_connection(campaign_path)
    conn.execute(sql, values)
    conn.commit()
    conn.close()

def get_episode_by_id(campaign_path, episode_id):
    """Retrieves a single episode's data by its ID."""
    conn = get_db_connection(campaign_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Episodes e JOIN ProcessingStatus ps ON e.episode_id = ps.episode_id WHERE e.episode_id = ?", (episode_id,))
    episode = cursor.fetchone()
    conn.close()
    return episode

def get_episode_by_transcript_path(campaign_path, transcript_path):
    """Finds an episode by its revised transcript file path."""
    try:
        relative_path = os.path.relpath(transcript_path, campaign_path)
    except ValueError:
        relative_path = transcript_path
    conn = get_db_connection(campaign_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Episodes WHERE transcription_file = ?", (relative_path,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_episodes_for_campaign(campaign_path, where_clause=""):
    """Retrieves all episodes for a campaign, with an optional WHERE clause."""
    conn = get_db_connection(campaign_path)
    sql = f"SELECT * FROM Episodes e JOIN ProcessingStatus ps ON e.episode_id = ps.episode_id {where_clause} ORDER BY e.episode_number"
    episodes = conn.execute(sql).fetchall()
    conn.close()
    return episodes

def find_original_audio(audio_folder, normalized_basename):
    """Finds the original audio file that corresponds to a normalized file."""
    if not audio_folder: return None
    
    base_name_to_match = normalized_basename.replace("_norm", "")
    supported_extensions = tuple(config["general"].get("supported_audio_extensions", [".wav", ".m4a", ".flac", ".mp3"]))

    for filename in os.listdir(audio_folder):
        if "_norm" not in filename and filename.lower().endswith(supported_extensions):
            if os.path.splitext(filename)[0] == base_name_to_match:
                return os.path.join(audio_folder, filename)
    return None