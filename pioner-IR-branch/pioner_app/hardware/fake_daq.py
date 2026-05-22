import numpy as np
import time


class FakeDAQDevice:

    def __init__(self, sample_rate=10000):

        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.sample_rate = sample_rate

        self.t0 = time.time()

        # modulation
        self.freq = 10
        self.amp = 1
        self.offset = 0

        # heater
        self.heater_voltage = 0

    # =========================================
    # AO (управление)
    # =========================================
    def set_modulation(self, freq, amp, offset):
        """????????????? ?????? `set_modulation`."""
        self.freq = freq
        self.amp = amp
        self.offset = offset

    def set_heater(self, voltage):
        """????????????? ?????? `set_heater`."""
        self.heater_voltage = voltage

    # =========================================
    # AI (сигналы)
    # =========================================
    def read(self, samples=1000):

        """?????? ?????? `read`."""
        t = np.arange(samples) / self.sample_rate
        t_global = time.time() - self.t0

        # ===== modulation =====
        ref = self.offset + self.amp * np.sin(2*np.pi*self.freq*(t + t_global))

        # ===== signal (с фазой) =====
        phase_shift = 0.5  # рад
        signal = 0.2 * np.sin(2*np.pi*self.freq*(t + t_global) + phase_shift)

        # ===== heater =====
        heater = self.heater_voltage + 0.01*np.random.randn(samples)

        # ===== aux =====
        aux = 0.2 + 0.01*np.random.randn(samples)

        # ===== tpl =====
        tpl = 0.5 + 0.05*np.sin(0.1*t_global)  # медленная температура

        tpl = np.ones(samples) * tpl

        # ===== abs =====
        abs_sig = heater - ref * 0.1

        data = np.column_stack([
            ref,        # ch0
            signal,     # ch1 (Umod)
            heater,     # ch2
            aux,        # ch3
            tpl,        # ch4
            abs_sig     # ch5
        ])

        return data