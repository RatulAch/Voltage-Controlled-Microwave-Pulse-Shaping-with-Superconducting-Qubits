"""
pulse_synthesis.py
Implementation of DRAG and SEP pulse synthesis for superconducting qubits.

DRAG (Derivative Removal by Adiabatic Gate) suppresses leakage to higher
energy levels by adding a quadrature component proportional to the derivative
of the in-phase pulse [citation:2], [citation:6].

SEP (Selective Excitation Pulse) creates null points in the frequency
domain at non-target qubit frequencies [citation:3], [citation:7].
"""
from __future__ import annotations
import numpy as np
from scipy.signal import hilbert
from scipy.linalg import expm
from scipy.fft import fft, ifft, fftfreq
from typing import Tuple, List, Optional
import matplotlib.pyplot as plt

from transmon_model import TransmonQubit

class PulseSynthesizer:
    """
    Synthesizes shaped microwave pulses for qubit control.
    
    Implements:
    1. Gaussian pulses (baseline)
    2. DRAG-corrected pulses for leakage suppression
    3. SEP pulses for selective excitation
    """
    
    def __init__(self, 
                 sampling_rate: float = 10.0,  # GHz
                 num_samples: int = 200):
        """
        Initialize the pulse synthesizer.
        
        Args:
            sampling_rate: AWG sampling rate in GHz
            num_samples: Number of samples in the pulse
        """
        self.fs = sampling_rate
        self.num_samples = num_samples
        self.dt = 1.0 / sampling_rate  # Time step in ns
        
        # Time array
        self.t = np.linspace(0, num_samples * self.dt, num_samples)
        
    def gaussian_pulse(self, 
                       amplitude: float, 
                       sigma: float, 
                       center: Optional[float] = None) -> np.ndarray:
        """
        Generates a Gaussian pulse envelope.
        
        Args:
            amplitude: Peak amplitude of the pulse
            sigma: Standard deviation (controls pulse width)
            center: Center of the pulse (default: midpoint)
        """
        if center is None:
            center = self.t[-1] / 2.0
            
        envelope = amplitude * np.exp(-(self.t - center)**2 / (2 * sigma**2))
        return envelope
    
    def dr_pulse(self, 
                 amplitude: float, 
                 sigma: float,
                 alpha: float,
                 shape: str = 'gaussian') -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates a DRAG-corrected pulse.
        
        DRAG correction adds:
        - Y-component: -dot(Omega_0) / alpha
        - Z-component: -Omega_0^2 / alpha + 2*Omega_0^2/alpha^2
        
        Reference: Motzoi et al., PRA 80, 022320 (2009)
        Implementation based on QuTiP SCQubitsCompiler [citation:2][citation:6].
        """
        # In-phase component (I)
        if shape == 'gaussian':
            I = self.gaussian_pulse(amplitude, sigma)
        else:
            I = amplitude * np.ones_like(self.t)  # Square pulse for testing
        
        # Derivative of I
        dI = np.gradient(I, self.dt)
        
        # DRAG Y-component: -dI / alpha
        Q = -dI / alpha
        
        # DRAG Z-component (for phase correction)
        Z = -(I**2) / alpha + (2 * I**2) / (alpha**2)
        
        return I, Q, Z
    
    def sep_pulse(self,
                  target_frequency: float,
                  null_frequencies: List[float],
                  amplitude: float,
                  sigma: float,
                  num_points: int = 1000) -> np.ndarray:
        """
        Synthesizes a Selective Excitation Pulse (SEP).
        
        The SEP is designed in the frequency domain as:
        S_SEP(omega) = A * [∏_{j∈Q_NT}(ω - ω_j)] * exp[-(ω - ω_d)^2 / (2σ^2)]
        
        Reference: Matsuda et al., Phys. Rev. Research 8, L012003 (2026) [citation:3]
        
        Args:
            target_frequency: Center frequency of the pulse (GHz)
            null_frequencies: Frequencies where response should be zero
            amplitude: Peak amplitude
            sigma: Spectral width parameter
            num_points: Number of frequency points
        
        Returns:
            Time-domain SEP pulse
        """
        # Frequency domain design
        omega = np.linspace(target_frequency - 2.0, target_frequency + 2.0, num_points)
        domega = omega[1] - omega[0]
        
        # Gaussian envelope
        gaussian = np.exp(-(omega - target_frequency)**2 / (2 * sigma**2))
        
        # Null polynomial: ∏(ω - ω_j)
        null_poly = np.ones_like(omega)
        for omega_null in null_frequencies:
            null_poly *= (omega - omega_null)
        
        # Frequency domain SEP
        S_freq = amplitude * null_poly * gaussian
        
        # Transform to time domain using inverse FFT
        S_time = np.fft.ifftshift(np.fft.ifft(np.fft.fftshift(S_freq)))
        
        # Normalize and apply envelope window
        S_time = S_time / np.max(np.abs(S_time)) * amplitude
        
        # Truncate to pulse duration
        return S_time[:self.num_samples]
    
    def square_pulse(self, amplitude: float, duration: float) -> np.ndarray:
        """Generates a square pulse (for benchmarking)."""
        pulse = np.zeros(self.num_samples)
        samples = int(duration / self.dt)
        pulse[:samples] = amplitude
        return pulse
    
    def hann_window(self, pulse: np.ndarray) -> np.ndarray:
        """Applies a Hann window to smooth pulse edges."""
        window = np.hanning(len(pulse))
        return pulse * window
    
    def calibrate_amplitude(self, 
                           pulse: np.ndarray, 
                           target_rotation: float) -> np.ndarray:
        """
        Calibrates pulse amplitude to achieve target rotation angle.
        
        The rotation angle is proportional to the integral of the pulse.
        """
        current_integral = np.sum(np.abs(pulse)) * self.dt
        scaling = target_rotation / current_integral
        return pulse * scaling
    
    def plot_pulse(self, 
                   I: np.ndarray, 
                   Q: Optional[np.ndarray] = None,
                   title: str = "Pulse Shape"):
        """
        Visualizes the pulse in time and frequency domains.
        """
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        
        # Time domain
        axes[0].plot(self.t, I, label='I (in-phase)')
        if Q is not None:
            axes[0].plot(self.t, Q, label='Q (quadrature)')
            axes[0].plot(self.t, np.sqrt(I**2 + Q**2), 'k--', label='Envelope')
        axes[0].set_xlabel('Time (ns)')
        axes[0].set_ylabel('Amplitude')
        axes[0].set_title(title)
        axes[0].legend()
        axes[0].grid(True)
        
        # Frequency domain
        freq = fftfreq(len(I), self.dt)
        if Q is not None:
            complex_pulse = I + 1j * Q
        else:
            complex_pulse = I
            
        spectrum = fft(complex_pulse)
        axes[1].plot(np.fft.fftshift(freq), np.fft.fftshift(np.abs(spectrum)))
        axes[1].set_xlabel('Frequency (GHz)')
        axes[1].set_ylabel('Magnitude')
        axes[1].set_title('Frequency Spectrum')
        axes[1].grid(True)
        
        plt.tight_layout()
        return fig


class GRAPEOptimizer:
    """
    Implements GRAPE (Gradient Ascent Pulse Engineering) optimization.
    
    GRAPE optimizes pulse amplitudes to achieve a target unitary transformation
    by minimizing an infidelity loss function [citation:12].
    
    This implementation uses the QuTiP-inspired approach with support for
    analytical gradients.
    """
    
    def __init__(self, 
                 transmon: 'TransmonQubit',
                 num_time_steps: int = 100,
                 learning_rate: float = 0.01):
        """
        Initialize the GRAPE optimizer.
        
        Args:
            transmon: TransmonQubit instance
            num_time_steps: Number of piecewise-constant pulse segments
            learning_rate: Step size for gradient updates
        """
        self.transmon = transmon
        self.num_time_steps = num_time_steps
        self.lr = learning_rate
        self.dt = 1.0 / num_time_steps  # Each segment duration
        
    def optimize(self, 
                 target_unitary: np.ndarray,
                 initial_pulses: Optional[List[np.ndarray]] = None,
                 max_iterations: int = 500,
                 target_infidelity: float = 1e-4) -> Tuple[np.ndarray, float]:
        """
        Runs GRAPE optimization to find optimal pulse shapes.
        
        The algorithm:
        1. Initialize pulse amplitudes (random or provided)
        2. Compute forward and backward propagators
        3. Calculate gradient of infidelity with respect to pulse amplitudes
        4. Update pulses using gradient descent
        5. Repeat until convergence
        
        Reference: Khaneja et al., JMR 172, 296-305 (2005)
        QuTiP implementation described in [citation:12].
        """
        n = self.transmon.n_levels
        
        # Initialize pulses
        if initial_pulses is None:
            pulses = [np.random.randn(self.num_time_steps) for _ in range(2)]
            pulses = [p / np.max(np.abs(p)) * 0.1 for p in pulses]
        else:
            pulses = initial_pulses
            
        # Identity Hamiltonian (drift)
        H0 = np.diag(self.transmon.energies)
        
        infidelity_history = []
        
        for iteration in range(max_iterations):
            # Forward propagators for each time step
            U_forward = [np.eye(n, dtype=complex)]
            for t in range(self.num_time_steps):
                H = H0.astype(complex) + pulses[0][t] * self.transmon.dipole
                # Add quadrature if available
                if len(pulses) > 1:
                    H += pulses[1][t] * 1j * self.transmon.dipole
                U = expm(-1j * H * self.dt)
                U_forward.append(U @ U_forward[-1])
            
            # Compute fidelity
            U_total = U_forward[-1]
            fidelity = np.abs(np.trace(target_unitary.conj().T @ U_total))**2 / n**2
            infidelity = 1 - fidelity
            infidelity_history.append(infidelity)
            
            if infidelity < target_infidelity:
                break
                
            # Backward propagators
            U_backward = [np.eye(n, dtype=complex)]
            for t in reversed(range(self.num_time_steps)):
                H = H0.astype(complex) + pulses[0][t] * self.transmon.dipole
                if len(pulses) > 1:
                    H += pulses[1][t] * 1j * self.transmon.dipole
                U = expm(-1j * H * self.dt)
                U_backward.append(U.conj().T @ U_backward[-1])
            
            # Compute gradients using GRAPE formula
            # dF/dp_k = -2 * Re{Tr[U_target† * U_backward_k * H_k * U_forward_k]}
            gradients = []
            for pulse_idx in range(len(pulses)):
                grad = np.zeros(self.num_time_steps)
                for t in range(self.num_time_steps):
                    # Forward evolution up to t
                    U_f = U_forward[t]
                    # Backward evolution from t+1 to end
                    U_b = U_backward[self.num_time_steps - t - 1]
                    
                    H_k = self.transmon.dipole
                    if pulse_idx == 1:
                        H_k = 1j * self.transmon.dipole
                    
                    term = U_b @ H_k @ U_f
                    grad[t] = -2 * np.real(np.trace(target_unitary.conj().T @ term))
                gradients.append(grad)
            
            # Update pulses using gradient descent with momentum
            for pulse_idx in range(len(pulses)):
                pulses[pulse_idx] += self.lr * gradients[pulse_idx]
            
            # Enforce amplitude constraints
            max_amp = 0.5  # GHz
            for pulse_idx in range(len(pulses)):
                pulses[pulse_idx] = np.clip(pulses[pulse_idx], -max_amp, max_amp)
            
        return pulses, infidelity_history