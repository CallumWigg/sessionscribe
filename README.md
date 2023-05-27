# sessionscribe

>I am not a programmer  
>I am making something for fun and usefulness  
>I will learn lots, but this will be bad code  
>I am severly cheating, chatgpt has written most of this.

## what do
currently in a somewhat functional state, but will likely require some tweaking on your end to get working. sorry!

this script, when placed in an appropriately organised file directory, will find podcast episodes to normalise and transcribe for publishing.

i've written this to manage the DnD session recordings of for my (private) DnD podcasts, due to all the strange character names, wack city names, and outlandish spells which get transcribed incorrectly. 

### current feature set:
- looks for a wav file modified in the last 3 days, user to select
- user inputs Title and Track Number/Episode Number
- wav file is encoded as <150MB .mp3 with loudness normalisation to EBU R128.
- mp3 file is transcribed with faster-whisper (edit script to change model size/settings) to transcription folder
- all completed transcriptions are combined together into a markdown file for easy searching all
- a set of non-standard US dictionary words is created/updated from combined file
    - note that this txt file can be edited to overwrite any poor choices by fuzzy wuzzy, which won't overwrite your hard work
- drawing from a list of non-dict words written by the user as corrections, all the non-standard words are compared for phoenetic similarity and fixed if confidence is very high.
- with the now updated corrections list, the combined transcriptions markdown has all incorrect words corrected.

### how to make work
good luck

fill out any non-standard words you'd like to correct (such as people names, or location names) as one per line in the "wack_dictionary.txt" file as linked to in the start of the script.

corrections.txt will propogate after the first run, and can be manually adjusted if there are any additional overrides.

### expected folder structure as below:  
names you can change without fear: [Recordings, Podcast 1, Pd1, Podcast 2, Pd2]  
you can change the other names, but only if you're more competant than me (low bar)

- Recordings
    - Podcast 1
        - Podcast 1 Audio Files
            - YYYY_MM_DD_Pd1.wav
            - YYYY_MM_DD_norm_Pd1.mp3 (will be created by the script)
        - Podcast 1 Transcriptions
            - YYYY_MM_DD_norm_Pd1.vtt/txt/tsv/srt/json (will be generated by the script)
        - "Podcast 1 - Transcriptions.md" (will be generated by the script)
    - Podcast 2
        - Podcast 2 Audio Files
            - YYYY_MM_DD_Pd2.wav
            - YYYY_MM_DD_norm_Pd2.mp3 (will be created by the script)
        - Podcast 1 Transcriptions
            - YYYY_MM_DD_norm_Pd2.vtt/txt/tsv/srt/json (will be generated by the script)
        - "Podcast 2 - Transcriptions.md" (will be generated by the script)
    - sessionscribe
        - sessionscribe.py

### to do
- [ ] Would be good if user could run one specific function instead of having complete all in linear fashion
- [ ] All non-standard words should be run through fuzzywuzzy comparing to the enchant standard dict to fix normal word errors
- [ ] Mass encoding, transcribing, and combination would be neat for users who haven't already done this manually for > 50 sessions. _Sigh_
- [ ] Basic competency in error management should be employed. Currently, it is _very_ easy to break things.
- [ ] Podcast api uploading! Very easy with most services if you pay, would be nice to work around, could do with selenium etc?