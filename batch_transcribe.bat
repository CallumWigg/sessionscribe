@echo off

for %%i in (*_norm*.mp3) do (
    if not exist "%%~ni.txt" (
        whisper-ctranslate2 "%%i" --model medium.en --language en --condition_on_previous_text False
    )
)