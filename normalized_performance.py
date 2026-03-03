import numpy as np
import matplotlib.pyplot as plt

def plot_normalized_performance():
    # X labels (Option A: first 6) with line breaks for better readability
    systems = [
        "Ideal \n(thermally \nunconstrained)",
        "Baseline",
        "Baseline +\nAlN infill",
        "Baseline +\nAlN underfill",
        "Baseline +\nTflex SF-10 TIM",
        "Baseline +\nall",
        "Baseline +\nall + HTC \n10 kW/(m²·K)",
    ]

    # Raw series (6 values each)
    s_25d_8 = np.array([52.69, 56.1615303628725, 56.1737714209768, 56.076258410236, 55.2728822401582, 55.1838901415619, 52.6885519904313])
    # s_25d_16 = np.array([50.49, 53.0657731714855, 52.3035073687014, 52.6817689953803, 51.2018399262433, 50.4938159548663])
    s_3d_8 = np.array([50.49, 64.9649396534505, 64.381106868673, 64.381106868673, 61.6386131763644, 61.6386131763644, 53.0657731714855])
    # s_3d_16 = np.array([50.49, 68.0311474347068, 68.0311474347068, 67.3888731680683, 64.9649396534505, 61.6386131763644])

    # Normalizing factors
    norm_25d_8 = 52.69
    norm_others = 50.49

    # Normalized performance = value / normalizing_factor
    p_25d_8 = norm_25d_8 / s_25d_8
    # p_25d_16 = norm_others / s_25d_16
    p_3d_8 = norm_others / s_3d_8
    # p_3d_16 = norm_others / s_3d_16

    print("Normalized Performance (2.5D 8-high HBM):", p_25d_8)
    # print("Normalized Performance (2.5D 16-hi):", p_25d_16)
    print("Normalized Performance (3D 8-high HBM):", p_3d_8)
    # print("Normalized Performance (3D 16-hi):", p_3d_16)

    # Set up the plot with a clean style
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.color'] = '#E5E5E5'
    plt.rcParams['grid.linestyle'] = '-'
    plt.rcParams['grid.linewidth'] = 0.5
    plt.rcParams['axes.facecolor'] = 'white'
    fig, ax = plt.subplots(figsize=(12, 7))  # Wider figure to accommodate labels
    
    x = np.arange(len(systems))
    width = 0.4  # Width of each bar
    colors = ['#2E86C1', '#E74C3C', '#27AE60', '#8E44AD']
    
    # Create bars with proper grouping (pairs of bars directly adjacent)
    bars1 = ax.bar(x - width, p_25d_8, width, label='GPU w/ 2.5D HBM', color=colors[0], alpha=0.8, edgecolor='black', linewidth=1)
    # bars2 = ax.bar(x - 0.67*width, p_25d_16, width, label='2.5D 16-high', color=colors[1], alpha=0.8, edgecolor='black', linewidth=1)
    bars3 = ax.bar(x, p_3d_8, width, label='GPU w/ 3D stacked HBM', color=colors[2], alpha=0.8, edgecolor='black', linewidth=1)
    # bars4 = ax.bar(x + 2*width, p_3d_16, width, label='3D 16-high', color=colors[3], alpha=0.8, edgecolor='black', linewidth=1)

    # Add value annotations on bars
    def annotate_bars(bars):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.3f}',
                       xy=(bar.get_x() + bar.get_width()/2, height),
                       xytext=(0, 3),  # 3 points vertical offset
                       textcoords="offset points",
                       ha='center', va='bottom',
                       fontsize=int(10*1.2*1.2))

    annotate_bars(bars1)
    # annotate_bars(bars2)
    annotate_bars(bars3)
    # annotate_bars(bars4)

    ax.set_xlabel('System configurations', fontsize=int(12*1.3*1.2))
    ax.set_ylabel('Normalized Performance', fontsize=int(12*1.3*1.2))
    
    ax.set_xticks(x)
    ax.set_xticklabels(systems, fontsize=int(10*1.2*1.2))
    ax.tick_params(axis='both', labelsize=int(10*1.2*1.2))
    plt.setp(ax.get_xticklabels(), rotation=0, ha='center', rotation_mode='anchor')
    
    # Adjust bottom margin to make room for labels
    plt.subplots_adjust(bottom=0.2)
    
    ax.set_title('Normalized performance for different configurations.', fontsize=int(16*1.3*1.2), pad=20)
    
    # Create legend on the left, matching paper_plot1.py
    legend = ax.legend(
        fontsize=int(11*1.3*1.2),
        loc='lower left',
        bbox_to_anchor=(0.02, 0.02),
        frameon=True,
        facecolor='white',
        framealpha=1.0,
        edgecolor='black'
    )
    
    # Set y-axis limits with some padding
    ax.set_ylim(0.5, max(
        max(p_25d_8),
        # max(p_25d_16),
        max(p_3d_8),
        # max(p_3d_16)
    ) * 1.05)
    
    plt.tight_layout()
    plt.savefig('normalized_performance.png', dpi=400, bbox_inches='tight')

if __name__ == '__main__':
    plot_normalized_performance()
