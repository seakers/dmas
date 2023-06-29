
import logging

import zmq
from dmas.messages import *
from dmas.nodes import Node
from dmas.utils import *
from dmas.network import NetworkConfig

class InternalModule(Node):
    
    def __init__(   self, 
                    module_name: str, 
                    module_network_config: NetworkConfig, 
                    parent_node_network_config: NetworkConfig, 
                    level: int = logging.INFO, 
                    logger: logging.Logger = None
                ) -> None:

        super().__init__(module_name,
                         module_network_config, 
                         parent_node_network_config,
                         [],
                         module_network_config.network_name,
                         level, 
                         logger)
        

        if len(module_network_config.get_external_addresses()) > 0:
            raise AttributeError(f'`module_network_config` cannot contain external addresses')
    
    async def send_manager_message(self, msg : SimulationMessage) -> list:
        """
        Sends a message through this node's manager request socket

        ### Arguments:
            - msg (:obj:`SimulationMessage`): message being sent

        ### Returns:
            - `list` containing the received response from the request:  
                name of the intended destination as `dst` (`str`) 
                name of sender as `src` (`str`) 
                and the message contents `content` (`dict`)
        """
        self._manager_address_ledger : dict
        dst_network_config : NetworkConfig = self._manager_address_ledger.get(msg.dst, None)
        if dst_network_config is None:
            raise RuntimeError(f'Could not find network config for simulation element of name {msg.dst}.')

        dst_address = dst_network_config.get_internal_addresses().get(zmq.REP, None)[-1]
        if '*' in dst_address:
            dst_address : str
            dst_address = dst_address.replace('*', 'localhost')
                
        if dst_address is None:
            raise RuntimeError(f'Could not find address for simulation element of name {msg.dst}.')
            
        return await self._send_request_message(msg, dst_address, self._manager_socket_map)

    def get_name(self) -> str:
        """
        Returns full name of this module
        """
        return self.name

    def get_module_name(self) -> str:
        """
        Returns the name of this module
        """
        return self._element_name

    def get_parent_name(self) -> str:
        """
        Returns the name of this module's parent network node
        """
        return self._network_name    
