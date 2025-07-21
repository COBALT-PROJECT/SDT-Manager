import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import gaussian_kde

def plot_deployment_cdf():
    # Read the CSV file
    df = pd.read_csv('sdt_create_time.csv')
    
    # Extract and sort the time values
    times = np.sort(df['Time Taken (seconds)'].values)
    
    # Compute the empirical CDF
    y_vals = np.arange(1, len(times) + 1) / len(times)
    
    # Create the plot with a step function for CDF
    plt.figure(figsize=(10, 6))
    plt.step(times, y_vals, 'b-', linewidth=2, where='post')  # Stepwise function (true CDF)
    plt.grid(True)
    
    # **Optional KDE for visualization** (does NOT change the data)
    kde = gaussian_kde(times, bw_method=0.2)  # Bandwidth controls smoothness
    x_kde = np.linspace(times.min(), times.max(), 200)
    kde_vals = kde(x_kde) / kde(x_kde).max()  # Normalize for comparison
    
    plt.twinx()  # Add a second Y-axis for KDE visualization
    plt.plot(x_kde, kde_vals, 'r--', alpha=0.5, label="Density (for reference)")
    
    # Add labels and title
    plt.xlabel('Time Taken (seconds)')
    plt.ylabel('Cumulative Probability')
    plt.title('CDF of SDT Pod Creation Time')

    # Add statistics to the plot
    stats_text = (f'Statistics:\nMean: {times.mean():.2f}s\nMedian: {np.median(times):.2f}s\n'
                  f'95th percentile: {np.percentile(times, 95):.2f}s\n'
                  f'99th percentile: {np.percentile(times, 99):.2f}s')

    plt.text(0.95, 0.05, stats_text,
             transform=plt.gca().transAxes,
             verticalalignment='bottom',
             horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Save the plot
    plt.savefig('sdt_deployment_cdf_improved.png')
    plt.close()

    # Print summary statistics
    print("\nDeployment Time Statistics:")
    print(f"Number of deployments: {len(times)}")
    print(f"Mean time: {times.mean():.2f} seconds")
    print(f"Median time: {np.median(times):.2f} seconds")
    print(f"95th percentile: {np.percentile(times, 95):.2f} seconds")
    print(f"99th percentile: {np.percentile(times, 99):.2f} seconds")
    print(f"Minimum time: {times.min():.2f} seconds")
    print(f"Maximum time: {times.max():.2f} seconds")

if __name__ == "__main__":
    plot_deployment_cdf()
