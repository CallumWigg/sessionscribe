# sessionscribe

>I am not a programmer  
>I am making something for fun and usefulness  
>I will learn lots, but this will be bad code  
>I am severly cheating, chatgpt has written most of this.

## what do
currently in a somewhat functional state, but will likely require some tweaking on your end to get working. sorry!

this script will find podcast episodes to normalise and transcribe for publishing.

i've written this to manage the DnD session recordings of for my (private) DnD podcasts, due to all the strange character names, wack city names, and outlandish spells which get transcribed incorrectly. 

## Usage
```pip install -r requirements.txt```

[Install WhisperX](https://github.com/m-bain/whisperX?tab=readme-ov-file#setup-%EF%B8%8F)

```py sessionscribe.py```
This will run through the full feature set as below.

## current feature set:

- looks for a wav file modified in the last 3 days, user to select
- user inputs Title and Track Number/Episode Number
- wav file is encoded as <150MB .mp3 with loudness normalisation to EBU R128.
- mp3 file is transcribed with faster-whisper (edit script to change model size/settings) to transcription folder
- all completed transcriptions are combined together into a markdown file for easy searching all
- a set of non-standard US dictionary words is created/updated from combined file
- note that this txt file can be edited to overwrite any poor choices by fuzzy wuzzy, which won't overwrite your hard work
- drawing from a list of non-dictionary words written by the user as corrections, all the non-standard words are compared for phoenetic similarity and fixed if confidence is very high.
- with the now updated corrections list, the combined transcriptions markdown has all incorrect words corrected.
- summarisation and chapter generationof transcripts with Gemini LLM.
- batch transcription and summarisation 


## how to make work
good luck

fill out any non-standard words you'd like to correct (such as people names, or location names) as one per line in the "wack_dictionary.txt" file as linked to in the start of the script.

corrections.txt will propogate after the first run, and can be manually adjusted if there are any additional overrides.

you'll need to create a file called keys.py, with gemini_key = "insert your key here".

set your working directory of where the podcast files will be, then create a new campaign.

## to do
- [ ] Check the transcripts to see if theres lots of repeated words. If it's a lot, prompt user to retranscribe.
- [ ] Basic competency in error management should be employed. Currently, it is _very_ easy to break things.
- [ ]  Check transcripts for repeating words. If it’s a lot prompt user to retranscribe.
- [ ]  different word dictionary for each campaign, so there’s no cross-contamination.
- [ ]  implement GUI for it all, which will allow you to correctly set up folder structure, locations (and save them to the info file)
- [ ]  transcript saved in a html that users can access? search better, seperate page for summaries? etc.
- [ ] housekeeping and spring clean. code is pretty terrible.