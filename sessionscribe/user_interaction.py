import os

def choose_from_list(options_list, header_text, prompt_text="Enter number:", allow_cancel=True):
    """
    Prompts the user to choose an entry from a list by number.

    Args:
        options_list (list): A list of strings to display as choices.
        header_text (str): Text to display before the list of options.
        prompt_text (str): Text for the input prompt.
        allow_cancel (bool): If True, adds an 'x' option to cancel, returning None.

    Returns:
        The selected option string from options_list, or None if cancelled or empty list.
    """
    if not options_list:
        print("No options available to choose from.")
        return None

    while True:
        print() # Blank line for readability
        if header_text:
            print(f"--- {header_text} ---")

        for i, entry in enumerate(options_list, start=1):
            print(f"{i}. {entry}")
        
        if allow_cancel:
            print("x. Cancel / Go Back")

        full_prompt = f"{prompt_text} (1-{len(options_list)}{', x' if allow_cancel else ''}): "
        choice = input(full_prompt).lower().strip()

        if allow_cancel and choice == 'x':
            return None

        if choice.isdigit():
            try:
                number = int(choice)
                if 1 <= number <= len(options_list):
                    return options_list[number - 1] # Return the actual option string
            except ValueError:
                pass # Fall through to invalid choice message

        print("Invalid choice. Please try again.")


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

# C-IMPROVEMENT: This function is now superseded by the more generic `choose_from_list`
# and the campaign selection logic within sessionscribe.py itself. It can be removed to
# reduce code duplication. I am keeping it here commented out for reference, but it is no longer used.
# def select_campaign_folder(): ...