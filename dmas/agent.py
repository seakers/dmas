from yaml import Node


class AgentNode(Node):
    """    
    ## Abstract Agent Node 
    
    ### Attributes:
        - _modules (`list`): list of modules contained within 

    ### Communications diagram:
    +--------------+       +---------+----------+---------+       +--------------+
    |              |<------| PUB     |          | REQ     |------>|              | 
    |              |       +---------+          +---------+       |              |
    |   INTERNAL   |------>| SUB     | ABSTRACT | PUB     |------>| SIM ELEMENTS |
    |     NODE     |       +---------+   SIM    +---------+       |              |
    |    MODULES   |       |         PARTICIPANT| SUB     |<------|              |
    |              |       |                    +---------+       +==============+ 
    |              |       |                    | PUSH    |------>|  SIM MONITOR |
    +--------------+       +---------+----------+---------+       +--------------+
    """