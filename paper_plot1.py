import numpy as np
import matplotlib.pyplot as plt
import math
from thermal_analysis_gui import run_thermal_performance_stco

def plot_system_runtimes(systems, runtime_per_batch_seconds, runtime_per_batch_seconds_16, batch_size, seq_len_8, seq_len_16, ntokens):
    """
    Create a single bar chart comparing total runtime (in days) for each system.
    """
    # System labels and corresponding runtime per batch (seconds) for batch size 16

    # systems = np.array([
    #     "Epoxy infill \n TIM 5 W/mK",
    #     "AlN infill \n TIM 5 W/mK",
    #     "Epoxy infill \n TIM 10 W/mK",
    #     "AlN infill \n TIM 10 W/mK",
    # ])

    # runtime_per_batch_seconds = np.array([24.7135084060381, 24.0358617900307, 23.654757145396, 23.1735034148336]) #OPT-2.7B-8tall
    # runtime_per_batch_seconds_16 = np.array([121.637388735602, 116.467023973371, 115.455655329434, 110.856998312938]) #OPT-2.7B-16tall
    # runtime_per_batch_seconds = np.array([5.37657805545297, 5.19138943463329, 5.08782400919772, 4.95700471795265]) #Llama-2-7B-8tall #TODO: Comment out when OPT-2.7B
    # runtime_per_batch_seconds_16 = np.array([26.5963450260578, 25.8761856804724, 25.2018743888083, 24.3564511026491]) #Llama-2-7B-16tall #TODO: Comment out when OPT-2.7B
    
    # runtime_per_batch_seconds = np.array([2.8881529142008406, 2.7964234692956977, 2.7964234692956977, 2.712868102166074]) # Llama 2-7B 8-tall 1K seq_len #TODO: Comment out when OPT-2.7B

    # runtime_per_batch_seconds_16 = np.array([243.26315186132885, 232.92242181913332, 230.89968443331043, 221.70236993590257]) #OPT-2.7B-16tall-2xbatchsize
    # runtime_per_batch_seconds_16 = np.array([53.18107550225796, 51.74075618164408, 50.392133003205934, 48.70128568612993]) # Llama-2-7B-16tall-2xbatchsize #TODO: Comment out when OPT-2.7B
    # runtime_per_batch_seconds_16 = np.array([69.32623869715488, 66.75915373699432, 64.96493965345056, 63.245742062408844]) # 16K seq_len # Llama 2-7B 16-tall #TODO: Comment out when OPT-2.7B
    # runtime_per_batch_seconds_16 = np.array([203.91146694533845, 203.91146694533845, 189.08279001118655, 189.08279001118655]) # 32K seq_len
    # runtime_per_batch_seconds_16 = np.array([666.0975261760673, 666.0975261760673, 617.4662775785575, 617.4662775785575]) # 64K seq_len
    # runtime_per_batch_seconds_16 = np.array([2367.982471142758, 2367.982471142758, 2194.8244001208905, 2194.8244001208905]) # 128K seq_len

    # ntokens = 1e10
    # batch_size = 128 # 16 for Llama 2-7B, 128 for OPT 2.7B #TODO: Change when OPT-2.7B
    # seq_len_8 = 2048  # Sequence length for 8-tall model
    # seq_len_8 = 1024
    # seq_len_16 = 8192 # Sequence length for 16-tall model 
    # seq_len_16 = 16384 # 16384, 32768, 65536, 131072
    total_batches_8 = math.ceil(ntokens / (batch_size * seq_len_8))
    # batch_size *= 2
    total_batches_16 = math.ceil(ntokens / (batch_size * seq_len_16))

    print(f"Batch size: {batch_size}")
    print(f"Sequence length (8-tall): {seq_len_8}")
    print(f"Sequence length (16-tall): {seq_len_16}")
    print(f"Total batches (8-tall): {total_batches_8:.2f}")
    print(f"Total batches (16-tall): {total_batches_16:.2f}")
    print(f"Runtime per batch (seconds, 8-tall): {runtime_per_batch_seconds}")
    print(f"Runtime per batch (seconds, 16-tall): {runtime_per_batch_seconds_16}")

    seconds_per_day = 24 * 3600
    total_runtime_days_8 = (runtime_per_batch_seconds * total_batches_8) / seconds_per_day
    total_runtime_days_16 = (runtime_per_batch_seconds_16 * total_batches_16) / seconds_per_day

    total_runtime_days_8 /= total_runtime_days_8[0]  # Normalize to the first system
    total_runtime_days_16 /= total_runtime_days_16[0]  # Normalize to the first system
    # total_runtime_days_16 /= total_runtime_days_8[0]  # Normalize to the first system

    # Use professional style
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Set up bar positions
    x = np.arange(len(systems))
    width = 0.35

    # Plot total runtimes
    bars_8 = ax.bar(x - width / 2, total_runtime_days_8, width,
                    label=f"8-tall HBM (80GB total, batch size {batch_size} @ {seq_len_8} seq len)", color='#2E86C1', alpha=0.8,
                    edgecolor='black', linewidth=1)

    bars_16 = ax.bar(x + width / 2, total_runtime_days_16, width,
                     label=f"16-tall HBM (160GB total, batch size {batch_size} @ {seq_len_16} seq len)", color='#E74C3C', alpha=0.8,
                     edgecolor='black', linewidth=1)

    ax.set_xlabel('System', fontsize=int(12*1.3*1.2))
    ax.set_ylabel('Normalized Runtime (days)', fontsize=int(12*1.3*1.2))
    ax.tick_params(axis='x', labelsize=int(10*1.2*1.2))
    ax.tick_params(axis='y', labelsize=int(10*1.2*1.2))
    ax.set_xticks(x)
    ax.set_xticklabels(systems)
    ax.set_ylim(0.8, max(np.max(total_runtime_days_8), np.max(total_runtime_days_16)) * 1.05)

    # Set title
    #TODO: Comment out when OPT-2.7B
    ax.set_title('Normalized runtime (Llama 2-7B-style model)',
                 fontsize=int(16*1.3*1.2), pad=20)
    
    #TODO: Uncomment when OPT-2.7B
    # ax.set_title('Normalized runtime (OPT 2.7B-style model)',
                #  fontsize=int(16*1.3*1.2), pad=20)

    # Add value annotations on bars
    for bar, value in zip(bars_8, total_runtime_days_8):
        ax.annotate(f'{value:.2f}', (bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 3), textcoords='offset points', ha='center', va='bottom',
                    fontsize=int(10*1.2*1.2), color='#2E86C1', fontweight='bold')

    for bar, value in zip(bars_16, total_runtime_days_16):
        ax.annotate(f'{value:.2f}', (bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 3), textcoords='offset points', ha='center', va='bottom',
                    fontsize=int(10*1.2*1.2), color='#E74C3C', fontweight='bold')

    # Create legend on the left
    legend = ax.legend(
        fontsize=int(11*1.3*1.2),
        loc='lower left',
        bbox_to_anchor=(0.02, 0.02),
        frameon=True,
        facecolor='white',
        framealpha=1.0,
        edgecolor='black'
    )

    plt.tight_layout()
    plt.savefig('system_runtime_days.png', dpi=400, bbox_inches='tight')
    plt.show()

if __name__ == '__main__':
    print("=== Thermal System Analysis ===")
    print("Generating runtime comparison chart...")

    system_name = "2p5D_1GPU"
    systems, runtime_per_batch_seconds, runtime_per_batch_seconds_16 = run_thermal_performance_stco(system_name = system_name)
    systems = np.array(systems)
    runtime_per_batch_seconds = np.array(runtime_per_batch_seconds)
    runtime_per_batch_seconds_16 = np.array(runtime_per_batch_seconds_16)
    batch_size = 16
    seq_len_8 = 16384
    seq_len_16 = 16384
    ntokens = 1e10
    plot_system_runtimes(systems, runtime_per_batch_seconds, runtime_per_batch_seconds_16, batch_size, seq_len_8, seq_len_16, ntokens)

    print("✅ Plot saved as: system_runtime_days.png")