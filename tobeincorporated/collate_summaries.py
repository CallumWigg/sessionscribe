import os
import re
from datetime import datetime

def sanitize_summary(summary):
    # Replace multiple line breaks with a single line break
    sanitized_summary = re.sub(r'\n\s*\n', '\n', summary)
    return sanitized_summary.strip()

def collate_md_files():
    # Get the current folder path
    folder_path = os.getcwd()

    # List to store tuples of (date, title, summary)
    collated_data = []

    # Iterate through files in the current folder
    for filename in os.listdir(folder_path):
        # Match YYYY_MM_DD pattern
        date_match = re.match(r'^(\d{4}_\d{2}_\d{2})_.*', filename)
        if not date_match:
            continue

        date_str = date_match.group(1)
        date = datetime.strptime(date_str, '%Y_%m_%d')

        # Extract title from norm_revised files
        if '_norm_revised.md' in filename and not filename.endswith('_summary.md'):
            with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                title = f.readline().strip()
            # Print the title
            print(f"Title: {title}")
            collated_data.append((date, title, None))

        # Extract summary from norm_revised_summary files
        elif filename.endswith('_norm_revised_summary.md'):
            with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                summary = f.read().strip()
            # Sanitize the summary to ensure single line breaks
            sanitized_summary = sanitize_summary(summary)
            # Match with corresponding title in collated_data
            for i, (stored_date, stored_title, _) in enumerate(collated_data):
                if stored_date == date:
                    collated_data[i] = (stored_date, stored_title, sanitized_summary)
                    break
            else:
                # If title is not found, append summary alone
                collated_data.append((date, None, sanitized_summary))

    # Sort data by date
    collated_data.sort(key=lambda x: x[0])

    # Get folder name for output file name
    folder_name = os.path.basename(folder_path)
    output_filename = f"{folder_name}_Collated_Summary.txt"

    # Write to the output file
    with open(os.path.join(folder_path, output_filename), 'w', encoding='utf-8') as output_file:
        for date, title, summary in collated_data:
            if title:
                output_file.write(title + "\n")
            if summary:
                output_file.write(summary + "\n\n")

    print(f"Collated summary file generated: {output_filename}")

# Run the function
collate_md_files()
