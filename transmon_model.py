"""
transmon_model.py
Transmon qubit Hamiltonian and dynamics simulation.
Implements the standard transmon Hamiltonian with anharmonicity.

"""

import numpy as np
from scipy.linalg import expm
from scipy.special import factorial
from typing import Tuple, List, Optional
import matplotlib.pyplot as plt

class TransmonQubit:
    """
    Simulates a transmon qubit with tunable anharmonicity.
    
    The transmon Hamiltonian is:
    H = 4*Ec*(n - ng)^2 - Ej*cos(phi)
    
    In the charge basis, this is diagonalized to yield energy levels
    with characteristic anharmonicity alpha.
    
    References:
    - Koch et al., "Charge-insensitive qubit design derived from the Cooper pair box"
    - Physical Review A 76, 042319 (2007)
    - DRAG correction theory: Motzoi et al., PRA 80, 022320 (2009)
    """
    
    def __init__(self, 
                 Ec: float = 0.3,      # Charging energy in GHz
                 Ej: float = 15.0,      # Josephson energy in GHz
                 n_levels: int = 4,     # Number of energy levels to include
                 ng: float = 0.0):      # Gate charge offset
        """
        Initialize transmon with given parameters.
        
        The transmon regime is defined by Ej/Ec >> 1.
        Typical values: Ej/Ec ~ 50-100 for standard transmons.
        """
        self.Ec = Ec
        self.Ej = Ej
        self.n_levels = n_levels
        self.ng = ng
        
        # Build Hamiltonian in charge basis
        self._build_hamiltonian()
        self._compute_transition_frequencies()
        self._compute_anharmonicity()
        
    def _build_hamiltonian(self):
        """
        Constructs the transmon Hamiltonian in the charge basis.
        
        In the charge basis (number states |n>):
        - Charging energy: 4*Ec*(n - ng)^2
        - Josephson energy: -0.5*Ej*(|n><n+1| + |n+1><n|)
        """
        n_max = self.n_levels * 2  # Need basis larger than number of levels
        
        # Charge basis states from -n_max to +n_max
        n_states = 2 * n_max + 1
        n_array = np.arange(-n_max, n_max + 1)

        """* The Theory: Transmon physics is described using the charge basis $\vert{}n\rangle$, 
        where $n$ represents the number of excess Cooper pairs (pairs of electrons) on the superconducting island. In theory, $n$ ranges from $-\infty$ to $+\infty$.
            Why this happens: A computer cannot handle an infinite matrix. 
        The code truncates the infinite space to a finite range from $-n_{max}$ to $+n_{max}$. 
        Setting $n_{max}$ to twice the desired energy levels ensures that the boundary cutoff does not introduce calculation errors for the lower states."""
        
        # Charging energy term (diagonal)
        H_charge = np.diag(4 * self.Ec * (n_array - self.ng)**2)
        
        # Josephson energy term (off-diagonal)
        H_josephson = np.zeros((n_states, n_states))
        for i in range(n_states - 1):
            H_josephson[i, i+1] = -self.Ej / 2.0
            H_josephson[i+1, i] = -self.Ej / 2.0
            
        # Total Hamiltonian
        self.H_full = H_charge + H_josephson
        
        # Diagonalize to get eigenstates and energies
        self.eigenenergies, self.eigenstates = np.linalg.eigh(self.H_full)
        
        # Keep only lowest n_levels
        self.energies = self.eigenenergies[:self.n_levels]
        self.states = self.eigenstates[:, :self.n_levels]
        
        # Remove global energy offset
        self.energies -= self.energies[0]
        
        # Compute dipole operator (for microwave driving)
        self._compute_dipole_operator()
        
    def _compute_dipole_operator(self):
        """
        Computes the dipole operator in the transmon basis.
        
        The dipole operator is proportional to n (charge number operator).
        This determines the coupling strength of microwave drives.
        """
        n_max = self.n_levels * 2
        n_states = 2 * n_max + 1
        n_array = np.arange(-n_max, n_max + 1)
        n_operator = np.diag(n_array)
        
        # Project n_operator into the transmon eigenbasis
        self.dipole = self.states.T @ n_operator @ self.states
        
    def _compute_transition_frequencies(self):
        """Computes transition frequencies between adjacent levels."""
        self.transitions = np.zeros(self.n_levels - 1)
        for i in range(self.n_levels - 1):
            self.transitions[i] = self.energies[i+1] - self.energies[i]
            
    def _compute_anharmonicity(self):
        """Computes the anharmonicity alpha = omega_12 - omega_01."""
        if self.n_levels >= 3:
            self.alpha = self.transitions[1] - self.transitions[0]
        else:
            self.alpha = 0.0
            
    def get_hamiltonian(self, drive_amplitude: float = 0.0, 
                        drive_detuning: float = 0.0) -> np.ndarray:
        """
        Returns the full Hamiltonian with microwave drive.
        
        In the rotating frame of the drive frequency:
        H = -delta/2 * sigma_z + Omega/2 * sigma_x
        
        Args:
            drive_amplitude: Rabi frequency Omega in GHz
            drive_detuning: detuning delta = omega_q - omega_d in GHz
        """
        # Static Hamiltonian in the rotating frame
        H0 = np.diag(self.energies)
        
        # Apply rotating frame transformation (subtract drive frequency)
        omega_d = self.transitions[0] - drive_detuning
        H0 -= omega_d * np.diag(np.arange(self.n_levels))
        
        # Drive term: proportional to dipole operator
        H_drive = drive_amplitude * self.dipole
        
        return H0 + H_drive
    
    def evolve(self, 
               H: np.ndarray, 
               time: float, 
               initial_state: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Evolves the quantum state under a time-independent Hamiltonian.
        
        Args:
            H: Hamiltonian matrix
            time: evolution time in ns
            initial_state: initial state vector (default: |0>)
        """
        if initial_state is None:
            initial_state = np.zeros(self.n_levels)
            initial_state[0] = 1.0
            
        # Time evolution operator
        U = expm(-1j * H * time)
        return U @ initial_state
    
    def get_fidelity(self, 
                     evolved_state: np.ndarray, 
                     target_state: np.ndarray) -> float:
        """Computes the fidelity between two quantum states."""
        return np.abs(np.vdot(target_state, evolved_state))**2


class TransmonQudit(TransmonQubit):
    """
    Extends the transmon model to support qudit operations (d-level systems).
    Useful for exploring leakage to higher energy levels.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def get_multitonal_Givens_rotation(self, target_levels: List[int]) -> np.ndarray:
        """
        Constructs a target unitary for selective transitions.
        
        This implements the Givens rotation approach for multi-tone control
        as described in the transmon-qudit-control framework [citation:10].
        """
        n = self.n_levels
        U_target = np.eye(n, dtype=complex)
        
        for i in range(0, len(target_levels), 2):
            if i+1 < len(target_levels):
                l1, l2 = target_levels[i], target_levels[i+1]
                # Construct 2x2 rotation between levels l1 and l2
                theta = np.pi / 2.0
                rot = np.array([[np.cos(theta), -np.sin(theta)],
                               [np.sin(theta), np.cos(theta)]])
                U_target[l1, l1] = rot[0, 0]
                U_target[l1, l2] = rot[0, 1]
                U_target[l2, l1] = rot[1, 0]
                U_target[l2, l2] = rot[1, 1]
                
        return U_target


class STOResonator:
    """
    Models the Strontium Titanate (STO) quantum paraelectric resonator.
    
    The STO resonator exhibits voltage-dependent phase shifts due to
    the electric field modulation of the dielectric constant.
    
    Key properties from the literature [citation from earlier response]:
    - Dielectric tunability: up to 16,500
    - Frequency shift: ~180 MHz for +15V DC bias
    - Phase shift: ~1.57 rad/V near resonance
    
    The modified Landau-Ginzburg-Devonshire (LGD) model describes
    the dielectric response as a function of electric field.
    """
    
    def __init__(self, 
                 f0: float = 0.393,      # Fundamental resonance in GHz
                 Q_loaded: float = 93.7,  # Loaded Q-factor
                 phase_shift_per_volt: float = 1.57):  # rad/V near resonance
        """
        Initialize the STO resonator model.
        """
        self.f0 = f0
        self.Q = Q_loaded
        self.phase_shift_per_volt = phase_shift_per_volt
        
    def get_phase_shift(self, voltage: float) -> float:
        """
        Computes the phase shift induced by a DC bias voltage.
        
        The phase shift is approximately linear near resonance,
        following the LGD model predictions [citation: earlier].
        """
        # Simple linear model near resonance
        # In reality, the response is nonlinear and temperature-dependent
        return self.phase_shift_per_volt * voltage
    
    def get_frequency_shift(self, voltage: float) -> float:
        """
        Computes the frequency shift as a function of voltage.
        
        The frequency shift follows:
        Δf = -f0 * (Δε / (2*ε)) where Δε is the voltage-induced
        change in dielectric constant.
        """
        # Simplified model based on the reported 180 MHz shift at 15V
        max_shift = 0.180  # GHz
        return max_shift * (voltage / 15.0) if abs(voltage) <= 15 else np.sign(voltage) * max_shift
    
    def apply_phase_modulation(self, 
                               pulse: np.ndarray, 
                               voltage_envelope: np.ndarray) -> np.ndarray:
        """
        Applies voltage-controlled phase modulation to a pulse.
        
        Args:
            pulse: Complex baseband pulse
            voltage_envelope: Time-dependent voltage control signal
        
        Returns:
            Phase-modulated complex pulse
        """
        phase_shifts = self.get_phase_shift(voltage_envelope)
        return pulse * np.exp(1j * phase_shifts)