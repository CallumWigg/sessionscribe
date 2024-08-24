import os
import subprocess

def convert_wav_to_flac():
    # Get the current working directory
    current_dir = os.getcwd()

    # Loop through all files in the current directory
    for filename in os.listdir(current_dir):
        # Check if the file is a .wav file
        if filename.endswith('.wav'):
            # Define the output file name
            output_filename = os.path.splitext(filename)[0] + '.flac'
            
            # Build the ffmpeg command
            command = [
                'ffmpeg', '-i', filename,  # Input file
                '-c:a', 'flac',            # Codec: FLAC (lossless)
                output_filename            # Output file
            ]
            
            # Run the command
            subprocess.run(command)

if __name__ == "__main__":
    convert_wav_to_flac()
