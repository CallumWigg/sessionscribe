def print_options(audio_files):
    """Print all audio files to the screen awaiting user input."""
    for i, file_path in enumerate(audio_files):
        print(f"{i+1}. {file_path}")

def get_user_input():
    """Grab user input for file selection."""
    while True:
        try:
            option = int(input("Enter the number of the file you want to process: "))
            return option
        except ValueError:
            print("Invalid input. Please enter a number.")

def select_campaign_folder():
    """Allows the user to select a campaign folder from the working directory."""
    from .utils import get_working_directory
    # Get the list of campaigns
    campaigns = [
        f for f in os.listdir(get_working_directory()) 
        if os.path.isdir(os.path.join(get_working_directory(), f)) and not f.startswith(("x ", ".", "_", " ", "-"))
    ]

    # Check if any campaigns were found
    if not campaigns:
        print("No campaign folders found in the working directory.")
        return None
    
    # Display available campaigns
    print("\nAvailable Campaigns:")
    for i, campaign in enumerate(campaigns):
        print(f"{i+1}. {campaign}")

    # Prompt user to choose a campaign
    while True:
        try:
            campaign_choice = int(input("\nEnter the number of the campaign: ")) - 1
            if 0 <= campaign_choice < len(campaigns):
                campaign_folder = os.path.join(get_working_directory(), campaigns[campaign_choice])
                return campaign_folder
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")