import sys

# Get the name of the input file from the command line
input_file = sys.argv[1]

# Open the input file and read the lines
with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

# Sort the lines in alphabetical order, regardless of case
lines.sort(key=str.lower)

# Write the sorted lines to the output file
with open("sorted_lines.txt", "w", encoding="utf-8", errors="ignore") as f:
    for line in lines:
        f.write(line)