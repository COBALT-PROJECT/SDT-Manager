# File: plot_cdf.py (plot cdf from time taken to instantiate the sdt pod (ditto pods are already running))
# File: plot_cdf.py
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def plot_deployment_cdf():
    # Set larger font sizes
    plt.rcParams.update({
        'font.size': 14,
        'axes.titlesize': 18,
        'axes.labelsize': 16,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 14
    })
    
    # Read the CSV file
    df = pd.read_csv('sdt_create_time.csv')
    
    # Extract the time taken column and sort it
    times = df['Time Taken (seconds)'].sort_values()
    
    # Calculate CDF
    y_vals = np.arange(len(times)) / float(len(times))
    
    # Create the plot
    plt.figure(figsize=(12, 8))
    plt.plot(times, y_vals, 'b-', linewidth=3)
    plt.grid(True)
    
    # Add labels and title
    plt.xlabel('Time Taken (seconds)', fontweight='bold')
    plt.ylabel('Cumulative Probability', fontweight='bold')
    plt.title('CDF of SDT Pod Scaling', fontweight='bold', pad=20)
    
    # Add statistics to the plot
    stats_text = f'Statistics:\nMean: {times.mean():.2f}s\nMedian: {times.median():.2f}s\n'
    stats_text += f'95th percentile: {times.quantile(0.95):.2f}s\n'
    stats_text += f'99th percentile: {times.quantile(0.99):.2f}s'
    
    plt.text(0.95, 0.05, stats_text,
             transform=plt.gca().transAxes,
             verticalalignment='bottom',
             horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.9),
             fontsize=14)
    
    # Increase tick size
    plt.tick_params(axis='both', which='major', labelsize=14, width=2)
    
    # Increase axis line width
    plt.gca().spines['top'].set_linewidth(2)
    plt.gca().spines['right'].set_linewidth(2)
    plt.gca().spines['bottom'].set_linewidth(2)
    plt.gca().spines['left'].set_linewidth(2)
    
    # Save the plot with high DPI for better quality
    plt.tight_layout()
    plt.savefig('sdt_deployment_cdf.png', dpi=300)
    plt.close()

    # Print summary statistics
    print("\nDeployment Time Statistics:")
    print(f"Number of deployments: {len(times)}")
    print(f"Mean time: {times.mean():.2f} seconds")
    print(f"Median time: {times.median():.2f} seconds")
    print(f"95th percentile: {times.quantile(0.95):.2f} seconds")
    print(f"99th percentile: {times.quantile(0.99):.2f} seconds")
    print(f"Minimum time: {times.min():.2f} seconds")
    print(f"Maximum time: {times.max():.2f} seconds")

if __name__ == "__main__":
    plot_deployment_cdf()