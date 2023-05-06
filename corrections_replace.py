campaign = 'NAME'
input_file = campaign+' - Transcriptions.md'
output_file = campaign+' - Fixed.md'
dictionary_file = 'dnd_dictionary.txt'

# Load dictionary
replacements = {}
with open(dictionary_file, 'r') as f:
    for line in f:
        line = line.strip()
        if ' -> ' in line:
            original, replacement = line.split(' -> ')
            if replacement:
                replacements[original] = replacement

# Perform replacements
with open(input_file, 'r') as f:
    text = f.read()
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)

# Save output
with open(output_file, 'w') as f:
    f.write(text)