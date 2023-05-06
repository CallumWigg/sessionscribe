import enchant
import re
import sys

input_file = sys.argv[1]
dictionary_file = "path/to/dnd_dictionary.txt"

# Create a dictionary object using the 'en_US' dictionary
dictionary = enchant.Dict("en_US")

# Open the input file
with open(input_file , "r", encoding="utf-8", errors="ignore") as file:
    text = file.read()

# Define regex pattern for words
words_pattern = r"\b\w+\b"

# Find all matches for words
words = sorted(set(re.findall(words_pattern, text)))

# Filter out words that are in the standard dictionary
non_dict_words = [word for word in words if not dictionary.check(word)]

# Check if output file already exists
try:
    with open(dictionary_file, "r", encoding="utf-8", errors="ignore") as file:
        # Read the contents of the file
        lines = file.readlines()

    # Create a set of words that already have corrections
    corrected_words = set(line.split(" -> ")[0] for line in lines if "->" in line)

    # Append new words to the end of the file
    with open(dictionary_file, "a", encoding="utf-8", errors="ignore") as file:
        for word in sorted(non_dict_words, key=lambda x: x.lower()):
            # Only write the word to the file if it does not already have a correction
            if word not in corrected_words:
                file.write(f"{word} -> \n")
except FileNotFoundError:
    # Write the results to a new output file with empty columns for corrections
    with open(dictionary_file, "w", encoding="utf-8", errors="ignore") as file:
        for word in sorted(non_dict_words, key=lambda x: x.lower()):
            file.write(f"{word} -> \n")