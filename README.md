# sessionscribe

>I am not a programmer  
>I am making something for fun and usefulness  
>I will learn lots, but this will be bad code  
>I am severly cheating, chatgpt/gemini has written most of this.

## what do
this script helps manage and process audio recordings, particularly for D&D sessions, by normalizing audio, transcribing, applying corrections based on custom dictionaries, and generating summaries and chapters with gemini.

i've written this to manage the session recordings of for my (private) D&D podcasts, due to all the strange character names, wack city names, and outlandish spells which get transcribed incorrectly. 

## Usage
```pip install -r requirements.txt```

```install``` [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)

```make changes to the config.json```

```python -m sessionscribe```

## current feature set:

- new campaign wizard (get it? wizard? dungeons and dragons?) for setting up folder structure
- audio normalisation to consistent level with [ffmpeg](https://github.com/kkroening/ffmpeg-python)
- local transcription with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- custom dictionary for your wack dnd words
- corrections list for non-dictionary transcribed words, manual and automatic
- phonetic matching with [double metaphone](https://github.com/ZackDibe/phonetics)
- combined transcriptions and summaries. ctrl+f to your hearts content
- summarisation and chapter generation with ultra long context [google gemini](https://github.com/google-gemini/generative-ai-python)
- bulk processing of files for working through your backlog

## how to make work
good luck

fill out any non-standard words you'd like to correct (such as people names, or location names) as one per line in the "wack_dictionary.txt" file in the allocated folder for putting files

corrections.txt will propogate after the first run, and can be manually adjusted if there are any additional overrides.

you'll need to create a file called keys.py, with gemini_key = "insert your key here".

set your working directory of where the podcast files will be, then create a new campaign.

## to do
~~oh god the list keeps growing faster than i can tick them off~~

okay its getting smaller 
- [ ]  about to do a complete overhaul of the ui to make it flow more logically, and more customisable.
- [ ]  different word dictionary for each campaign, so there’s no cross-contamination.
- [ ]  fix the silly summary compile. dunno why its still bad.
- [ ]  implement session_length and other general stats and data. Need somewhere to store it all, ideally rewrite it so that all the data is stored somewhere in a database.
- [ ]  bulk functions dont work currently
- [ ]  each combine/revised exports to different locations?
- [ ]  want to be able to just generate revised for one at a time, or only those that havent been done yet.
- [ ]  function which will look through all the files and check theyve all been transcribed, summaries, chaptered, and everything, for missing files.
- [ ]  Check transcripts for repeating words. (the text will have ~10 lines that all have the same repeating word/phrase) If it’s a lot retranscribe. If it has to be retranscribed 3 times, just leave it after the third one.


### deep future to do pipe dream never going to happen
- [ ] implement a way to automatically
    - [ ] upload to wiki like fandom
    - [ ] upload to podcast/rss service
- [ ] transcript saved in a html that users can access? search better, seperate page for summaries? data, etc.
- [ ]  [semantic-grep](https://github.com/arunsupe/semantic-grep) semantic search, investigate how it works and if its worth (that one isnt great, very slow and only really synonyms)
    - [ ]  [semantra](https://github.com/freedmand/semantra) - html ui, try with above todo?
    - [ ]  [Semantify](https://github.com/MohammedAly22/Semantify) another option maybe
- [ ] implement GUI for it all, which will allow you to correctly set up folder structure, locations (and save them to the info file, drag and drop of files in?)
- [ ] functionarlity with ai of choice (chatgpt, gemini, claude, etc. i've only got free access to gemini, and most dont have long enough context windows, so not in a rush)