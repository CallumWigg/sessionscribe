import os
import subprocess
import math

def convert_to_mp3(input_path):
    # get the file name and directory separately
    input_dir, input_file = os.path.split(input_path)
    cmd = ['ffprobe', '-i', input_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']
    output = subprocess.check_output(cmd, universal_newlines=True)
    input_duration = float(output.strip())

    # Calculate required bitrate for 145MB output file size
    target_size = 145 * 1024 * 1024
    target_bitrate = math.floor((target_size * 8) / (input_duration * 1024))

    # Convert to MP3 with calculated bitrate
    file_name = os.path.splitext(input_file)[0]
    fil_date = file_name[:10]
    output_file = f"{fil_date}_norm_{file_name[11:]}.mp3"
    output_path = os.path.join(input_dir, output_file)
    cmd = ['ffmpeg', '-i', input_path, '-af', 'loudnorm', '-c:a', 'libmp3lame', '-b:a', str(target_bitrate)+'k', output_path]
    subprocess.run(cmd, check=True)

    print(f'Successfully converted {input_path} to {output_path} with {target_bitrate} kbps bitrate.')


input_path = '2023_04_15_KR.wav'
convert_to_mp3(input_path)
