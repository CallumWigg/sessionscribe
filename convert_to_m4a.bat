@echo off
setlocal enabledelayedexpansion

rem Get the file path of the dragged file
set "file_path=%~1"

rem Check if a file was dragged onto the batch file
if "%file_path%"=="" (
    echo No file was dragged onto the batch file.
    exit /b
)

rem Call the Python script with the file path as an argument
python -c "import os, subprocess, datetime, math; file_path = r'%file_path%'; input_dir, input_file = os.path.split(file_path); cmd = ['ffprobe', '-i', file_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0']; output = subprocess.check_output(cmd, universal_newlines=True); input_duration = float(output.strip()); year = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).year; target_size = 140 * 1024 * 1024; target_bitrate = math.floor((target_size * 8) / (input_duration * 1024)); file_name = os.path.splitext(input_file)[0]; fil_date = file_name[:10]; output_file = f'{fil_date}_{file_name[11:]}_norm.m4a'; output_path = os.path.join(input_dir, output_file); cmd = ['ffmpeg', '-i', file_path, '-af', 'loudnorm', '-ac', '1', '-ar', '44100','-c:a', 'aac', '-b:a', str(target_bitrate)+'k', output_path]; subprocess.run(cmd, check=True)"

rem Pause to see any error messages before closing the window
pause
