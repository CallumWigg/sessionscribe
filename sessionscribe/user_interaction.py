import os

def choose_from_list(options, header, prompt, *, values=None, default=None):
    """Get the user to choose an entry from a list."""

    while True:
        print()
        if header:
            print(header + ":")

        for (i, entry) in enumerate(options, start=1):
            print(f"{i}. {entry}")

        # Get user to select a command by number.
        index = -1
        while True:
            choice = input(prompt + ":")
            if choice.isnumeric():
                number = int(choice)
                if number > 0 and number <= len(options):
                    index = number - 1
                    break

            if default is not None:
                print(f"Invalid choice. Using {default}.")
                return default
            print("Invalid choice. Please try again.")
        
        if values:
            return values[index]
        else:
            return options[index]

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
    base_dir = get_working_directory()  # Get the base directory

    # Get the list of campaigns using absolute paths
    campaigns = [
        os.path.join(base_dir, f)  # Create absolute path
        for f in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, f)) and not f.startswith(("x ", ".", "_", " ", "-"))
    ]

    # Check if any campaigns were found
    if not campaigns:
        print("No campaign folders found in the working directory.")
        return None
    
    # Extract and display only the base folder names
    campaign_names = [os.path.basename(campaign) for campaign in campaigns] 
    
    selected_campaign_name = choose_from_list(
        campaign_names,  # Use campaign_names here
        "Available Campaigns",
        "Enter the number of the campaign"
    )

    # Construct the full path of the selected campaign
    selected_campaign_path = os.path.join(base_dir, selected_campaign_name)

    return selected_campaign_path 