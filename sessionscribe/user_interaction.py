import os

def choose_from_list(options_list, header_text, prompt_text, *, default_value_if_invalid=None, allow_cancel=True):
    """
    Prompts the user to choose an entry from a list.
    Args:
        options_list: A list of strings to display as choices.
        header_text: Text to display before the list of options (can be None).
        prompt_text: Text for the input prompt.
        default_value_if_invalid: If provided, returns this if user input is invalid after retries or immediately.
                                   If None, keeps prompting until valid.
        allow_cancel: If True, adds an 'x' option to cancel/go back, returning None.

    Returns:
        The selected option string from options_list, or default_value_if_invalid, or None if cancelled.
    """
    if not options_list:
        print("No options available to choose from.")
        return None if allow_cancel else default_value_if_invalid

    while True:
        print() # Blank line for readability
        if header_text:
            print(header_text)

        for i, entry in enumerate(options_list, start=1):
            print(f"{i}. {entry}")
        
        if allow_cancel:
            print("x. Cancel / Go Back")

        full_prompt = f"{prompt_text} (1-{len(options_list)}{', x' if allow_cancel else ''}): "
        choice = input(full_prompt).lower()

        if allow_cancel and choice == 'x':
            return None

        if choice.isdigit():
            try:
                number = int(choice)
                if 1 <= number <= len(options_list):
                    return options_list[number - 1] # Return the actual option string
            except ValueError:
                pass # Fall through to invalid choice message

        # Invalid choice
        if default_value_if_invalid is not None:
            print(f"Invalid choice. Using default: {default_value_if_invalid}")
            return default_value_if_invalid
        else:
            print("Invalid choice. Please try again.")


def get_user_input(prompt_text, input_type=str, validation_func=None, error_message="Invalid input."):
    """
    Generic function to get validated user input.
    Args:
        prompt_text: The prompt to display to the user.
        input_type: The type to convert the input to (e.g., str, int, float).
        validation_func: A function that takes the converted input and returns True if valid, False otherwise.
        error_message: Message to display if validation fails.
    Returns:
        The validated user input of the specified type, or None if user cancels (e.g. empty input for non-critical fields).
    """
    while True:
        raw_input = input(prompt_text + " ") # Add space for cursor
        if not raw_input.strip() and input_type is not float and input_type is not int: # Allow empty for string, implies cancel/default
            # For critical int/float, empty is usually not acceptable unless handled by caller
            # This behavior might need adjustment based on how "cancel" is signaled for various inputs
            return None 

        try:
            converted_input = input_type(raw_input)
            if validation_func:
                if validation_func(converted_input):
                    return converted_input
                else:
                    print(error_message)
            else: # No validation function, type conversion is enough
                return converted_input
        except ValueError:
            print(f"Invalid format. Please enter a valid {input_type.__name__}.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


def select_campaign_folder():
    """Allows the user to select a campaign folder from the working directory.
    Returns the absolute path to the selected campaign folder, or None if cancelled.
    This function is largely superseded by sessionscribe.select_campaign() which has more features.
    Kept for compatibility if directly called by older code, but should be deprecated.
    """
    from .utils import get_working_directory # Local import
    base_dir = get_working_directory()

    campaign_basenames = [
        f_name for f_name in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, f_name)) 
        and not f_name.startswith(("x ", ".", "_", " ", "-")) # Filter out non-campaign folders
    ]

    if not campaign_basenames:
        print("No campaign folders found in the working directory.")
        return None
    
    selected_campaign_basename = choose_from_list(
        campaign_basenames,
        "Available Campaigns:",
        "Enter the number of the campaign"
    )

    if selected_campaign_basename:
        return os.path.join(base_dir, selected_campaign_basename)
    return None


def get_yes_no_input(prompt_text, default_choice="n"):
    """
    Prompts the user for a yes/no input.
    Args:
        prompt_text (str): The prompt to display.
        default_choice (str): The default answer if user presses Enter ('y' or 'n').
    Returns:
        bool: True for yes, False for no.
    """
    default_map = {"y": "(Y/n)", "n": "(y/N)"}
    prompt_suffix = default_map.get(default_choice.lower(), "(y/n)")

    while True:
        choice = input(f"{prompt_text} {prompt_suffix}: ").lower().strip()
        
        if not choice: # User pressed Enter
            return default_choice.lower() == 'y'
        
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            print("Invalid input. Please answer 'y' (yes) or 'n' (no).")