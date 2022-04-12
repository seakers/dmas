from src.agents.components.Component import Component


class Comms(Component):
    """
    Class that describes the communications module of a satellite
    Is an implementation of the Abstract Components Class
    """
    def __init__(self, name, rf_power, data_rate, data_capacity, mass=0, xdim=0, ydim=0, zdim=0,frequency=None):
        """
        :param name: module's name
        :param rf_power: module's peak power consumed in [W]
        :param data_rate: module's data output rate in [Mbps]
        :param data_capacity: module's data capacity in [Mb]
        :param mass: module's mass in [kg]
        :param xdim: module's dimension in the x-axis in [m]
        :param ydim: module's dimension in the y-axis in [m]
        :param zdim: module's dimension in the z-axis in [m]
        :param frequency: module's communication frequency or frequencies
        """
        super().__init__(name, status=False, mass=mass, xdim=xdim, ydim=ydim, zdim=zdim,
                         power_generation=0, power_usage=rf_power, power_storage=0, power_capacity=0,
                         data_generation=0, data_usage=data_rate, data_storage=0, data_capacity=data_capacity)
        self.rf_power = rf_power
        self.frequency = frequency

    def update_data_storage(self, data_rate=0, data=0, step_size=1) -> None:
        """
        Updates data storage
        :param data_rate: total of data rate being introduced to the storage of positive or how much is exiting if negative
        :param step_size:
        :return: None
        """
        self.data_storage += data_rate*step_size + data

    def get_data_rate(self):
        return self.data_usage

    def set_storage_to_max_cap(self) -> None:
        self.data_storage = self.data_capacity

    def is_full(self) -> bool:
        return self.data_storage >= self.data_capacity

    def get_overflow(self) -> float:
        if self.is_full():
            return self.data_storage - self.data_capacity
        return 0.0

    def add_data(self, data=0) -> None:
        self.data_storage += data

    def empty_data_storage(self) -> None:
        self.data_storage = 0.0
