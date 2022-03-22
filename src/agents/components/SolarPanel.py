from src.agents.components.Component import Component


class SolarPanel(Component):
    """
    Describes a solar panel component within a spacecraft
    Is an implementation of the Abstract Components Class
    """
    def __init__(self, mass=0, xdim=0, ydim=0, zdim=0, power_density=0):
        """
        :param mass: panel's mass in [kg]
        :param xdim: panel's dimension in the x-axis in [m]
        :param ydim: panel's dimension in the y-axis in [m]
        :param zdim: panel's thickness in [m]
        :param power_density: power generated per area [W/m^2]
        """
        super().__init__(status=False, mass=mass, xdim=xdim, ydim=ydim, zdim=zdim,
                 power_generation=power_density*xdim*ydim, power_usage=0, power_storage=0, power_capacity=0,
                 data_generation=0, data_usage=0, data_storage=0, data_capacity=0)
        self.area = xdim * ydim
        self.power_density = power_density
