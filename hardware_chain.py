"""
hardware_chain.py
Simulates the complete microwave control hardware chain.

This models:
1. AWG pulse generation (I/Q signals)
2. IQ mixing with local oscillator
3. STO voltage-controlled phase modulation
4. Cryogenic attenuation and filtering
5. Arrival at qubit

Based on the hardware architecture described in the literature [citation:11]
and the pulse generation schematics [citation:14].
"""
from __future__ import annotations  
from typing import Optional 
import numpy as np
from scipy.signal import butter, lfilter, hilbert
from typing import Tuple, Optional
import matplotlib.pyplot as plt

from transmon_model import STOResonator 

class IQMixer:
    """
    Simulates an IQ mixer for upconversion of baseband pulses.
    
    The mixer combines I and Q baseband signals with a local oscillator
    to produce the final microwave signal:
    RF(t) = I(t)*cos(ω_LO*t) - Q(t)*sin(ω_LO*t)
    """
    
    def __init__(self, lo_frequency: float, phase_imbalance: float = 0.0):
        """
        Args:
            lo_frequency: Local oscillator frequency in GHz
            phase_imbalance: IQ phase imbalance in radians (for error modeling)
        """
        self.lo_freq = lo_frequency
        self.phase_imbalance = phase_imbalance
        
    def upconvert(self, 
                  I: np.ndarray, 
                  Q: np.ndarray, 
                  t: np.ndarray) -> np.ndarray:
        """
        Upconverts baseband I/Q signals to RF.
        
        RF(t) = I(t)*cos(ω*t) - Q(t)*sin(ω*t + φ_imb)
        """
        omega = 2 * np.pi * self.lo_freq
        RF = I * np.cos(omega * t) - Q * np.sin(omega * t + self.phase_imbalance)
        return RF
    
    def downconvert(self, 
                    RF: np.ndarray, 
                    t: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Downconverts RF signal to baseband (for analysis).
        """
        omega = 2 * np.pi * self.lo_freq
        I = RF * np.cos(omega * t)
        Q = RF * np.sin(omega * t)
        return I, Q


class CryogenicAttenuator:
    """
    Simulates cryogenic attenuation and filtering.
    
    Attenuators at different temperature stages reduce thermal noise
    and set the appropriate signal level at the qubit.
    """
    
    def __init__(self, attenuation: float, temperature: float = 10e-3):
        """
        Args:
            attenuation: Attenuation in dB
            temperature: Stage temperature in Kelvin
        """
        self.att_db = attenuation
        self.temp = temperature
        
    def apply(self, signal: np.ndarray) -> np.ndarray:
        """Applies attenuation to the signal."""
        attenuation_linear = 10 ** (-self.att_db / 20)
        return signal * attenuation_linear
    
    def add_thermal_noise(self, signal: np.ndarray, bandwidth: float) -> np.ndarray:
        """
        Adds thermal noise appropriate for the temperature.
        
        Noise power: P_noise = k_B * T * B
        For 10 mK and 1 GHz bandwidth: ~1.38e-25 W
        """
        k_B = 1.38e-23  # J/K
        noise_power = k_B * self.temp * bandwidth * 1e9  # GHz to Hz
        noise = np.sqrt(noise_power) * np.random.randn(len(signal))
        return signal + noise


class CryogenicSwitch:
    """
    Simulates a cryogenic microwave switch for signal routing.
    
    Based on the cryogenic switch controller described in the literature [citation: earlier].
    """
    
    def __init__(self, insertion_loss: float = 0.1, isolation: float = 40.0):
        """
        Args:
            insertion_loss: Loss when switch is ON (dB)
            isolation: Isolation when switch is OFF (dB)
        """
        self.insertion_loss = insertion_loss
        self.isolation = isolation
        
    def route(self, signal: np.ndarray, state: bool) -> np.ndarray:
        """
        Routes the signal through the switch.
        
        Args:
            signal: Input RF signal
            state: True = ON, False = OFF
        """
        if state:
            # ON state: minimal loss
            loss_linear = 10 ** (-self.insertion_loss / 20)
            return signal * loss_linear
        else:
            # OFF state: high isolation
            isolation_linear = 10 ** (-self.isolation / 20)
            return signal * isolation_linear


class HardwareChain:
    """
    Complete simulation of the microwave control chain.
    
    Signal flow:
    AWG -> IQ Mixer -> Attenuator -> STO Phase Shifter -> Switch -> Qubit
    
    This matches the experimental setup described in [citation:11] and [citation:14].
    """
    
    def __init__(self, 
                 lo_frequency: float = 6.0,  # GHz
                 attenuation: float = 60.0,   # dB
                 sto_resonator: Optional['STOResonator'] = None):
        """
        Initialize the hardware chain.
        """
        self.mixer = IQMixer(lo_frequency)
        self.attenuator = CryogenicAttenuator(attenuation, temperature=10e-3)
        
        if sto_resonator is None:
            from transmon_model import STOResonator
            self.sto = STOResonator()
        else:
            self.sto = sto_resonator
            
        self.switch = CryogenicSwitch()
        
    def generate_control_pulse(self, 
                               I: np.ndarray, 
                               Q: np.ndarray,
                               t: np.ndarray,
                               voltage_control: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Generates the complete control pulse through the hardware chain.
        
        Args:
            I: In-phase baseband signal
            Q: Quadrature baseband signal
            t: Time array (ns)
            voltage_control: STO bias voltage waveform
        
        Returns:
            RF signal arriving at the qubit
        """
        # Step 1: Upconvert to RF
        RF = self.mixer.upconvert(I, Q, t)
        
        # Step 2: Apply cryogenic attenuation
        RF = self.attenuator.apply(RF)
        
        # Step 3: STO phase modulation (if control voltage provided)
        if voltage_control is not None:
            RF = self.sto.apply_phase_modulation(RF, voltage_control)
        
        # Step 4: Route through cryogenic switch
        RF = self.switch.route(RF, state=True)
        
        return RF
    
    def analyze_signal(self, 
                       signal: np.ndarray, 
                       t: np.ndarray) -> dict:
        """
        Analyzes the signal characteristics.
        
        Returns:
            Dict with frequency spectrum, power, and phase information
        """
        # Frequency spectrum
        spectrum = np.fft.fft(signal)
        freq = np.fft.fftfreq(len(signal), t[1] - t[0])
        
        # Instantaneous phase
        analytic = hilbert(signal)
        phase = np.unwrap(np.angle(analytic))
        
        # Power
        power = np.mean(np.abs(signal)**2)
        
        return {
            'spectrum': spectrum,
            'freq': freq,
            'phase': phase,
            'power': power
        }


class STOVoltageController:
    """
    Simulates the voltage controller for the STO resonator.
    
    This generates the time-dependent voltage signals required for
    pulse shaping via phase modulation.
    """
    
    def __init__(self, 
                 max_voltage: float = 15.0,
                 min_voltage: float = -15.0):
        """
        Args:
            max_voltage: Maximum DC bias voltage
            min_voltage: Minimum DC bias voltage
        """
        self.max_V = max_voltage
        self.min_V = min_voltage
        
    def generate_voltage_ramp(self, 
                              start_V: float,
                              end_V: float,
                              t: np.ndarray) -> np.ndarray:
        """
        Generates a linear voltage ramp.
        """
        return np.linspace(start_V, end_V, len(t))
    
    def generate_voltage_pulse(self,
                               voltage: float,
                               t: np.ndarray,
                               pulse_times: Tuple[float, float]) -> np.ndarray:
        """
        Generates a rectangular voltage pulse.
        
        Args:
            voltage: Pulse amplitude
            t: Time array
            pulse_times: (start_time, end_time) in ns
        """
        V = np.zeros_like(t)
        mask = (t >= pulse_times[0]) & (t <= pulse_times[1])
        V[mask] = voltage
        return V
    
    def generate_modulation_signal(self,
                                   base_voltage: float,
                                   modulation_amplitude: float,
                                   frequency: float,
                                   t: np.ndarray) -> np.ndarray:
        """
        Generates a sinusoidal modulation signal.
        """
        return base_voltage + modulation_amplitude * np.sin(2 * np.pi * frequency * t)