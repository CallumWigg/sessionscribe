import os
import re
import numpy as np
import matplotlib.pyplot as plt
from mutagen.mp4 import MP4
from scipy.optimize import curve_fit
from datetime import datetime, timedelta

# Function to read the duration of m4a files
def get_audio_length(file_path):
    audio = MP4(file_path)
    return audio.info.length / 3600  # convert seconds to hours

# Linear function for curve fitting
def linear_func(x, a, b):
    return a * x + b

# Function to calculate R²
def calculate_r_squared(y_values, y_fit):
    residuals = y_values - y_fit
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y_values - np.mean(y_values))**2)
    return 1 - (ss_res / ss_tot)

# Function to calculate standard deviation of residuals
def calculate_std_dev(residuals):
    return np.std(residuals)

# Function to format time
def format_time(hours):
    hours_int = int(hours)
    minutes = (hours - hours_int) * 60
    minutes_int = int(round(minutes))
    return f"{hours_int} hrs {minutes_int:02d} mins"

# Function to convert ordinal date to months since start
def ordinal_to_months_since_start(ordinal_date, start_date):
    start_month = start_date.year * 12 + start_date.month
    end_month = datetime.fromordinal(ordinal_date).year * 12 + datetime.fromordinal(ordinal_date).month
    return end_month - start_month

# Main function
def main():
    current_folder = os.getcwd()
    campaign_name = input("Enter the Campaign name: ")

    # Regex to extract date from file name
    date_pattern = re.compile(r'(\d{4})_(\d{2})_(\d{2})')

    files = []
    dates = []

    # Find all files with '_norm.m4a' suffix and extract dates
    for f in os.listdir(current_folder):
        if f.endswith('_norm.m4a') and not ('p1' in f or 'p2' in f):
            match = date_pattern.match(f)
            if match:
                date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                date = datetime.strptime(date_str, "%Y-%m-%d")
                files.append(f)
                dates.append(date)

    if not dates:
        print("No matching files found.")
        return

    # Sort files and dates by date
    dates, files = zip(*sorted(zip(dates, files)))

    # Get the lengths of these files
    lengths = []
    for file in files:
        file_path = os.path.join(current_folder, file)
        length = get_audio_length(file_path)
        lengths.append(length)

    # Convert dates to numerical format (months since start)
    start_date = min(dates)
    x_values = np.array([ordinal_to_months_since_start(date.toordinal(), start_date) for date in dates])
    y_values = np.array(lengths)

    # Perform linear curve fitting
    popt, _ = curve_fit(linear_func, x_values, y_values)

    # Calculate y values for the linear fit
    y_fit = linear_func(x_values, *popt)

    # Calculate R² value
    r_squared = calculate_r_squared(y_values, y_fit)

    # Calculate standard deviation of residuals
    residuals = y_values - y_fit
    std_dev = calculate_std_dev(residuals)

    # Calculate statistics
    avg_length = np.mean(y_values)
    max_length = np.max(y_values)
    min_length = np.min(y_values)

    # Format statistics
    avg_length_formatted = format_time(avg_length)
    max_length_formatted = format_time(max_length)
    min_length_formatted = format_time(min_length)

    # Plot the data points
    plt.plot(dates, y_values, 'x', color='red', label='Data points')  # Changed to crosses

    # Plot the linear fit
    fitted_x_values = np.linspace(min(x_values), max(x_values), 1000)
    fitted_dates = [start_date + timedelta(days=(x * 30)) for x in fitted_x_values]  # Convert months back to days
    plt.plot(fitted_dates, linear_func(fitted_x_values, *popt), color='blue', label=f'Linear fit (r² = {r_squared:.1f})')

    # Add title and labels
    plt.title(f'Session Length - {campaign_name}')
    plt.xlabel('Date')
    plt.ylabel('Length (hours)')

    # Format the x-axis to show dates correctly
    plt.gcf().autofmt_xdate()

    # Add grid for better readability
    plt.grid(True)

    # Show legend with additional information in the top left
    legend_text = (
        f"Linear fit: t(hrs) = {popt[0]:.2f} * (months) + {popt[1]:.2f}\n"
        f"Average length: {avg_length_formatted}\n"
        f"Max length: {max_length_formatted}\n"
        f"Min length: {min_length_formatted}\n"
        f"Standard deviation: {std_dev:.2f} hours"
    )
    plt.legend([legend_text], loc='upper left', fontsize=10, frameon=True)

    # Display the plot
    plt.show()

if __name__ == "__main__":
    main()
