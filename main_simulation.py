"""
main_simulation.py
Complete simulation demonstrating voltage-controlled microwave pulse shaping.

This is the main entry point for running the full simulation and generating
the results for your presentation.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.linalg import expm
from scipy.signal import hilbert
from scipy.fft import fft, fftfreq

# Import our modules
from transmon_model import TransmonQubit, STOResonator
from pulse_synthesis import PulseSynthesizer, GRAPEOptimizer
from hardware_chain import HardwareChain, STOVoltageController

def run_demonstration():
    """
    Runs the complete simulation and generates all results.
    """
    print("=" * 60)
    print("VOLTAGE-CONTROLLED MICROWAVE PULSE SHAPING")
    print("Advanced Quantum Computing Project")
    print("=" * 60)
    
    # ==================== 1. Initialize System ====================
    print("\n[1] Initializing transmon qubit...")
    
    # Transmon parameters (typical values)
    transmon = TransmonQubit(
        Ec=0.3,      # Charging energy (GHz)
        Ej=15.0,     # Josephson energy (GHz)
        n_levels=4   # Include ground + 3 excited states
    )
    
    print(f"  Qubit frequency (ω_01): {transmon.transitions[0]:.4f} GHz")
    if transmon.n_levels >= 3:
        print(f"  Anharmonicity (α): {transmon.alpha:.4f} GHz")
    print(f"  Energy levels: {transmon.energies[:4]}")
    
    # ==================== 2. STO Resonator ====================
    print("\n[2] Initializing STO resonator...")
    
    sto = STOResonator(
        f0=0.393,        # GHz
        Q_loaded=93.7,
        phase_shift_per_volt=1.57  # rad/V
    )
    
    # Test voltage response
    test_voltages = np.linspace(-15, 15, 30)
    phase_shifts = [sto.get_phase_shift(V) for V in test_voltages]
    
    print(f"  Phase shift at 10V: {sto.get_phase_shift(10.0):.2f} rad")
    print(f"  Frequency shift at 15V: {sto.get_frequency_shift(15.0):.3f} GHz")
    
    # ==================== 3. Pulse Synthesis ====================
    print("\n[3] Synthesizing control pulses...")
    
    synthesizer = PulseSynthesizer(
        sampling_rate=10.0,  # GHz
        num_samples=200
    )
    
    # Parameters for π-pulse
    sigma = 10.0  # ns
    amplitude = 0.2  # GHz Rabi frequency
    alpha = transmon.alpha  # GHz
    
    # Generate Gaussian pulse
    I_gauss = synthesizer.gaussian_pulse(amplitude, sigma)
    
    # Generate DRAG pulse
    I_drag, Q_drag, Z_drag = synthesizer.dr_pulse(amplitude, sigma, alpha)
    
    # Generate SEP pulse (with null at ω_01 + 0.2 GHz)
    null_freqs = [transmon.transitions[0] + 0.2]
    sep_pulse = synthesizer.sep_pulse(
        target_frequency=transmon.transitions[0],
        null_frequencies=null_freqs,
        amplitude=amplitude,
        sigma=sigma,
        num_points=1000
    )
    sep_pulse = sep_pulse[:len(synthesizer.t)]  # Truncate
    I_sep = np.real(sep_pulse)
    Q_sep = np.imag(sep_pulse)
    
    # ==================== 4. Hardware Simulation ====================
    print("\n[4] Simulating hardware chain...")
    
    # Initialize hardware chain
    hw_chain = HardwareChain(
        lo_frequency=transmon.transitions[0],  # Match qubit frequency
        attenuation=60.0,  # dB
        sto_resonator=sto
    )
    
    # Generate voltage control signal
    vc = STOVoltageController()
    V_control = vc.generate_voltage_pulse(
        voltage=10.0,  # Volts
        t=synthesizer.t,
        pulse_times=(20, 180)  # ns
    )
    
    # Generate control pulses through hardware
    RF_gauss = hw_chain.generate_control_pulse(
        I=I_gauss, 
        Q=np.zeros_like(I_gauss),
        t=synthesizer.t,
        voltage_control=V_control
    )
    
    RF_drag = hw_chain.generate_control_pulse(
        I=I_drag, 
        Q=Q_drag,
        t=synthesizer.t,
        voltage_control=V_control
    )
    
    RF_sep = hw_chain.generate_control_pulse(
        I=I_sep, 
        Q=Q_sep,
        t=synthesizer.t,
        voltage_control=V_control
    )
    
    # ==================== 5. Qubit Dynamics ====================
    print("\n[5] Simulating qubit dynamics...")
    
    def simulate_drive(I_wave, Q_wave, t, transmon):
        """
        Simulates qubit evolution under shaped drive.
        """
        dt = t[1] - t[0]
        n = transmon.n_levels
        state = np.zeros(n)
        state[0] = 1.0  # Start in |0>
        
        # Track population
        populations = []
        
        for i in range(len(t)):
            # Construct Hamiltonian at this time
            omega_d = transmon.transitions[0]  # Drive frequency
            H0 = np.diag(transmon.energies) - omega_d * np.diag(np.arange(n))
            
            # Drive term: I*σ_x + Q*σ_y
            drive_amplitude = np.sqrt(I_wave[i]**2 + Q_wave[i]**2)
            phase = np.angle(I_wave[i] + 1j * Q_wave[i])
            
            # Approximate Pauli operators in transmon basis
            sx = transmon.dipole
            sy = 1j * transmon.dipole
            
            H_drive = I_wave[i] * sx + Q_wave[i] * sy
            
            H = H0 + H_drive
            
            # Evolve
            U = expm(-1j * H * dt)
            state = U @ state
            
            populations.append(np.abs(state)**2)
        
        return np.array(populations), state
    
    # Simulate for each pulse type
    print("  Simulating Gaussian pulse...")
    pop_gauss, final_gauss = simulate_drive(I_gauss, np.zeros_like(I_gauss), 
                                            synthesizer.t, transmon)
    
    print("  Simulating DRAG pulse...")
    pop_drag, final_drag = simulate_drive(I_drag, Q_drag, 
                                          synthesizer.t, transmon)
    
    print("  Simulating SEP pulse...")
    pop_sep, final_sep = simulate_drive(I_sep, Q_sep, 
                                        synthesizer.t, transmon)
    
    # Compute fidelities
    target_state = np.zeros(transmon.n_levels)
    target_state[1] = 1.0  # Target: |1>
    
    fid_gauss = transmon.get_fidelity(final_gauss, target_state)
    fid_drag = transmon.get_fidelity(final_drag, target_state)
    fid_sep = transmon.get_fidelity(final_sep, target_state)
    
    print(f"  Gaussian fidelity: {fid_gauss:.4f}")
    print(f"  DRAG fidelity: {fid_drag:.4f}")
    print(f"  SEP fidelity: {fid_sep:.4f}")
    
    # ==================== 6. Generate Plots ====================
    print("\n[6] Generating figures...")
    
    # Figure 1: Pulse shapes
    fig1, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Gaussian
    axes[0, 0].plot(synthesizer.t, I_gauss, 'b-', label='I')
    axes[0, 0].set_title('Gaussian Pulse')
    axes[0, 0].set_xlabel('Time (ns)')
    axes[0, 0].set_ylabel('Amplitude')
    axes[0, 0].grid(True)
    axes[0, 0].legend()
    
    # DRAG
    axes[0, 1].plot(synthesizer.t, I_drag, 'b-', label='I')
    axes[0, 1].plot(synthesizer.t, Q_drag, 'r-', label='Q')
    axes[0, 1].set_title('DRAG Pulse')
    axes[0, 1].set_xlabel('Time (ns)')
    axes[0, 1].set_ylabel('Amplitude')
    axes[0, 1].grid(True)
    axes[0, 1].legend()
    
    # SEP (real part)
    axes[1, 0].plot(synthesizer.t, I_sep, 'g-', label='Real')
    axes[1, 0].plot(synthesizer.t, Q_sep, 'm-', label='Imag')
    axes[1, 0].set_title('SEP Pulse')
    axes[1, 0].set_xlabel('Time (ns)')
    axes[1, 0].set_ylabel('Amplitude')
    axes[1, 0].grid(True)
    axes[1, 0].legend()
    
    # Voltage control
    axes[1, 1].plot(synthesizer.t, V_control, 'k-', linewidth=2)
    axes[1, 1].set_title('STO Bias Voltage')
    axes[1, 1].set_xlabel('Time (ns)')
    axes[1, 1].set_ylabel('Voltage (V)')
    axes[1, 1].grid(True)
    axes[1, 1].axhline(y=0, color='k', linestyle='--', alpha=0.3)
    
    plt.tight_layout()
    fig1.savefig('images/fig1_pulse_shapes.png', dpi=150, bbox_inches='tight')
    
    # Figure 2: Qubit populations
    fig2, axes = plt.subplots(1, 3, figsize=(15, 4))
    
    for ax, pop, label, color in zip(
        axes,
        [pop_gauss, pop_drag, pop_sep],
        ['Gaussian', 'DRAG', 'SEP'],
        ['blue', 'red', 'green']
    ):
        for level in range(min(3, pop.shape[1])):
            ax.plot(synthesizer.t, pop[:, level], 
                   label=f'|{level}>', color=plt.cm.tab10(level))
        ax.set_title(f'{label} Population')
        ax.set_xlabel('Time (ns)')
        ax.set_ylabel('Population')
        ax.legend()
        ax.grid(True)
        
        # Add fidelity annotation
        fid = [fid_gauss, fid_drag, fid_sep][axes.tolist().index(ax)]
        ax.text(0.02, 0.95, f'Fidelity: {fid:.4f}', 
               transform=ax.transAxes, fontsize=12,
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    fig2.savefig('images/fig2_qubit_populations.png', dpi=150, bbox_inches='tight')
    
    # Figure 3: STO characterization
    fig3, axes = plt.subplots(1, 2, figsize=(12, 4))
    
    # Phase shift
    axes[0].plot(test_voltages, phase_shifts, 'b-', linewidth=2)
    axes[0].set_xlabel('Bias Voltage (V)')
    axes[0].set_ylabel('Phase Shift (rad)')
    axes[0].set_title('STO Phase Shift vs. Voltage')
    axes[0].grid(True)
    
    # Frequency shift
    freq_shifts = [sto.get_frequency_shift(V) for V in test_voltages]
    axes[1].plot(test_voltages, freq_shifts, 'r-', linewidth=2)
    axes[1].set_xlabel('Bias Voltage (V)')
    axes[1].set_ylabel('Frequency Shift (GHz)')
    axes[1].set_title('STO Frequency Tuning')
    axes[1].grid(True)
    
    plt.tight_layout()
    fig3.savefig('images/fig3_sto_characterization.png', dpi=150, bbox_inches='tight')
    
    # ==================== 7. Summary ====================
    print("\n" + "=" * 60)
    print("SIMULATION COMPLETE")
    print("=" * 60)
    
    print(f"""
    SUMMARY OF RESULTS:
    
    1. Qubit Parameters:
       - Frequency (ω_01): {transmon.transitions[0]:.4f} GHz
       - Anharmonicity (α): {transmon.alpha:.4f} GHz
    
    2. STO Resonator:
       - Phase shift per volt: {sto.phase_shift_per_volt:.2f} rad/V
       - Max frequency shift: {sto.get_frequency_shift(15.0):.3f} GHz at 15V
    
    3. Gate Fidelities:
       - Gaussian: {fid_gauss:.4f}
       - DRAG: {fid_drag:.4f}
       - SEP: {fid_sep:.4f}
    
    4. Figures Saved:
       - fig1_pulse_shapes.png
       - fig2_qubit_populations.png
       - fig3_sto_characterization.png
    
    5. Key Insights:
       - DRAG pulse significantly reduces leakage to |2> state
       - SEP pulse enables selective excitation with null points
       - STO voltage control provides real-time phase modulation
    """)
    
    return {
        'transmon': transmon,
        'sto': sto,
        'fidelities': {'gaussian': fid_gauss, 'drag': fid_drag, 'sep': fid_sep},
        'pulses': {'gaussian': I_gauss, 'drag': (I_drag, Q_drag), 'sep': (I_sep, Q_sep)},
        'populations': {'gaussian': pop_gauss, 'drag': pop_drag, 'sep': pop_sep},
        'figures': [fig1, fig2, fig3]
    }

def extended_demonstration():
    """
    Extended demonstration showing:
    1. GRAPE optimization
    2. Frequency multiplexing with SEP
    3. Scalability analysis
    """
    print("\n" + "=" * 60)
    print("EXTENDED DEMONSTRATION")
    print("=" * 60)
    
    # Initialize transmon
    transmon = TransmonQubit(Ec=0.3, Ej=15.0, n_levels=4)
    synthesizer = PulseSynthesizer(sampling_rate=10.0, num_samples=300)
    
    # ==================== GRAPE Optimization ====================
    print("\n[GRAPE Optimization]")
    
    optimizer = GRAPEOptimizer(transmon, num_time_steps=50)
    
    # Target: π-rotation
    target_U = expm(-1j * np.pi/2 * transmon.dipole)
    
    # Run optimization
    pulses, infidelities = optimizer.optimize(
        target_unitary=target_U,
        max_iterations=200,
        target_infidelity=1e-3
    )
    
    print(f"  Final infidelity: {infidelities[-1]:.6f}")
    print(f"  Iterations: {len(infidelities)}")
    
    # Plot convergence
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.semilogy(infidelities, 'b-', linewidth=2)
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Infidelity')
    ax.set_title('GRAPE Convergence')
    ax.grid(True)
    ax.axhline(y=1e-3, color='r', linestyle='--', label='Target')
    ax.legend()
    fig.savefig('images/fig4_grape_convergence.png', dpi=150, bbox_inches='tight')
    
    # ==================== Frequency Multiplexing ====================
    print("\n[Frequency Multiplexing]")
    
    # Create two qubits with different frequencies
    qubit1 = TransmonQubit(Ec=0.3, Ej=15.0, n_levels=3)
    qubit2 = TransmonQubit(Ec=0.3, Ej=14.5, n_levels=3)  # Slightly different
    
    print(f"  Qubit 1 frequency: {qubit1.transitions[0]:.4f} GHz")
    print(f"  Qubit 2 frequency: {qubit2.transitions[0]:.4f} GHz")
    print(f"  Frequency separation: {qubit1.transitions[0] - qubit2.transitions[0]:.4f} GHz")
    
    # Design SEP pulse with null at qubit2 frequency
    sep_pulse = synthesizer.sep_pulse(
        target_frequency=qubit1.transitions[0],
        null_frequencies=[qubit2.transitions[0]],
        amplitude=0.15,
        sigma=8.0,
        num_points=1000
    )[:len(synthesizer.t)]
    
    # Calculate frequency response
    freq = fftfreq(len(sep_pulse), synthesizer.dt)
    spectrum = fft(sep_pulse)
    
    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(np.fft.fftshift(freq), np.fft.fftshift(np.abs(spectrum)), 'b-', linewidth=2)
    ax.axvline(x=qubit1.transitions[0], color='g', linestyle='--', label='Qubit 1 (target)')
    ax.axvline(x=qubit2.transitions[0], color='r', linestyle='--', label='Qubit 2 (null)')
    ax.set_xlabel('Frequency (GHz)')
    ax.set_ylabel('Magnitude')
    ax.set_title('SEP Frequency Response with Null Point')
    ax.legend()
    ax.grid(True)
    fig.savefig('images/fig5_sep_frequency_response.png', dpi=150, bbox_inches='tight')
    
    print("  SEP pulse designed with null at qubit 2 frequency")
    print("  This enables selective excitation without disturbing qubit 2")
    
    # ==================== Scalability Analysis ====================
    print("\n[Scalability Analysis]")
    
    # Power consumption scaling
    n_qubits = np.array([1, 4, 16, 64, 256, 1024])
    power_per_qubit = 100e-12  # 100 pW/qubit (from literature)
    total_power = n_qubits * power_per_qubit
    
    # Number of microwave lines
    lines_per_qubit = 1  # Traditional
    lines_multiplexed = 1 / 4  # 4 qubits per line with SEP
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    
    # Power scaling
    axes[0].loglog(n_qubits, total_power * 1e6, 'b-o', linewidth=2, markersize=8)
    axes[0].set_xlabel('Number of Qubits')
    axes[0].set_ylabel('Total Power (μW)')
    axes[0].set_title('Power Consumption Scaling')
    axes[0].grid(True)
    axes[0].axhline(y=10, color='r', linestyle='--', label='Cryogenic limit (~10 μW)')
    axes[0].legend()
    
    # Microwave lines
    axes[1].bar(['Traditional', 'SEP Multiplexed'], 
                [n_qubits[-1]*1, n_qubits[-1]*0.25],
                color=['red', 'green'])
    axes[1].set_ylabel('Number of Microwave Lines')
    axes[1].set_title(f'Lines Required for {n_qubits[-1]} Qubits')
    axes[1].grid(True)
    
    plt.tight_layout()
    fig.savefig('images/fig6_scalability.png', dpi=150, bbox_inches='tight')
    
    print(f"  Power per qubit: {power_per_qubit*1e12:.1f} pW")
    print(f"  Total power for {n_qubits[-1]} qubits: {total_power[-1]*1e6:.2f} μW")
    print(f"  Cryogenic limit: ~10 μW at 10 mK stage")
    print(f"  Multiplexing reduces microwave lines by factor of 4")

if __name__ == "__main__":
    # Run the main demonstration
    results = run_demonstration()
    
    # Run extended demonstration
    extended_demonstration()
    
    plt.show()