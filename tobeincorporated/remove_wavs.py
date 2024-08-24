import os

def find_matching_audio_files(directory):
    # Create a set of all files in the directory
    files = set(os.listdir(directory))
    
    # Create a list to store matching pairs of wav and flac
    matching_pairs = []
    
    for file in files:
        if file.endswith('.flac'):
            # Remove the extension to get the base name
            base_name = file[:-5]
            # Check if the corresponding wav file exists
            if f"{base_name}.wav" in files:
                matching_pairs.append(base_name)
    
    return matching_pairs

def prompt_and_delete_wav_files(matching_pairs, directory):
    if not matching_pairs:
        print("No matching .wav and .flac files found.")
        return
    
    print("The following files have both .wav and .flac versions:")
    for base_name in matching_pairs:
        print(f"{base_name}.wav and {base_name}.flac")
    
    delete = input("Do you want to delete all the .wav files listed above? (yes/no): ").strip().lower()
    
    if delete == 'yes':
        for base_name in matching_pairs:
            wav_file_path = os.path.join(directory, f"{base_name}.wav")
            os.remove(wav_file_path)
            print(f"Deleted: {wav_file_path}")
    else:
        print("No files were deleted.")

def main():
    current_directory = os.getcwd()  # Get the current directory
    matching_pairs = find_matching_audio_files(current_directory)
    prompt_and_delete_wav_files(matching_pairs, current_directory)

if __name__ == "__main__":
    main()