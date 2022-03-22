from src.agents.components.Component import Component


class Instrument(Component):
    """
    Abstract class that describes a generic instrument
    Is an implementation of the Abstract Components Class
    """
    def __init__(self, mass=0, xdim=0, ydim=0, zdim=0, peak_power=0, data_rate=0, duty_cycle=0, frequency=None):
        """
        :param mass: instrument's mass in [kg]
        :param xdim: instrument's dimension in the x-axis in [m]
        :param ydim: instrument's dimension in the y-axis in [m]
        :param zdim: instrument's dimension in the z-axis in [m]
        :param peak_power: instrument's peak power consumed in [W]
        :param data_rate: instrument's data generation rate in [Mbps]
        :param duty_cycle: instrument's duty cycle in percentage values between 0 to 1
        :param frequency: instrument's measurement frequency or frequencies
        """
        super().__init__(False, mass=mass, xdim=xdim, ydim=ydim, zdim=zdim,
                         power_generation=0, power_usage=peak_power*duty_cycle, power_storage=0, power_capacity=0,
                         data_generation=data_rate, data_usage=0, data_storage=0, data_capacity=0)
        self.frequency = frequency
        self.peak_power = peak_power
        self.duty_cycle = duty_cycle