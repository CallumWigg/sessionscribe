import os
import datetime
from mutagen.mp3 import MP3

# Create a list of all VTT files in the current directory
vtt_files = []
for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".vtt"):
             vtt_files.append(os.path.join(root, file))

# Sort the list in descending order by filename
vtt_files.sort(reverse=True)



# Get campaign, party, DM, and player information
campaign = 'NAME'
party = 'NAME'
dm = 'DM'
players = 'Player (PC)'



# Create a new Markdown file to write to
output_file = open(campaign+' - Transcriptions.md', 'w', encoding='utf-8')

# Write the campaign information to the output file
output_file.write('# ' + campaign + '\n\n')
output_file.write('**DM:** ' + dm + '\n\n')
output_file.write('**Players:** ' + players + '\n\n')
output_file.write('**Sessions:** ' + str(len(vtt_files)) + '\n\n')

# Loop through each VTT file and write the contents to the output file
for i, vtt_file in enumerate(vtt_files):
    # Extract the date and title from the VTT filename
    file_name = os.path.basename(vtt_file)  # Get file name without directory path
    day_str = file_name.split('_')[2].replace('-', '_')
    mon_str = file_name.split('_')[1].replace('-', '_')
    year_str = file_name.split('_')[0].replace('-', '_')
    date_str = (year_str)+'_'+(mon_str)+'_'+(day_str)
    date = datetime.datetime.strptime(date_str, '%Y_%m_%d').strftime('%d/%m/%Y')

    # Get the title and track number metadata from the MP3 file using mutagen
    mp3_file = os.path.basename(vtt_file.replace('.vtt', '.mp3'))
    audio = MP3(mp3_file)
    title = str(audio.get('TIT2', ''))
    track_num = str(audio.get('TRCK', ''))
    print(date + ' - #' + track_num + ' - ' + title)
    # Write the header for this section, including track number
    output_file.write('## '+ title + ' - Session ' + str(track_num) + ' - ' + date + '\n\n')

    # Read the contents of the VTT file and write to the output file
    with open(vtt_file, 'r', encoding='utf-8') as f:
        # Skip the first two lines of the VTT file
        lines = f.readlines()[2:]
        
        # Write the remaining lines to the output file, indented with 4 spaces
        for j, line in enumerate(lines):
            if '-->' in line:
                times = line.strip().split(' --> ')
                if len(times) >= 2:
                    start_time = times[0]
                    end_time = times[1]
                    caption = lines[j+1].strip()
                    if caption:
                        output_file.write(start_time + ' --> ' + end_time + '    |    ' + caption + '\n')
            else:
                continue
                
        output_file.write('\n')

# Close the output file
output_file.close()        