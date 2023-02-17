from dmas.element import SimulationElement
from dmas.node import Node
from dmas.utils import NodeNetworkConfig


class EnvironentNode(Node):
    """
    ## Environment Node 

    Represents an environment node in a simulation.

    ### Communications diagram:
    +--------------+       +---------+----------+---------+       +--------------+
    |              |<------| PUSH    |          | REQ     |------>|              | 
    |              |       +---------+          +---------+       |              |
    |   INTERNAL   |------>| PULL    | ABSTRACT | PUB     |------>| SIM ELEMENTS |
    |     NODE     |       +---------+   SIM    +---------+       |              |
    |    MODULES   |       |         ENVIRONMENT| SUB     |<------|              |
    |              |       |             NODE   +---------+       +==============+ 
    |              |       |                    | PUSH    |------>|  SIM MONITOR |
    +--------------+       +---------+----------+---------+       +--------------+
    """
    __doc__ += SimulationElement.__doc__
    def __init__(self, name: str, network_config: NodeNetworkConfig, modules: list = ..., level: int = logging.INFO) -> None:
        super().__init__(name, network_config, modules, level)