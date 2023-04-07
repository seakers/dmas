import math
from dmas.managers import *
from examples.planning.messages import *

class PlanningSimulationManager(AbstractManager):

    def _check_element_list(self):
        for sim_element_name in self._simulation_element_name_list:
            if SimulationElementRoles.ENVIRONMENT.value in sim_element_name:
                return

        raise AttributeError(f'`simulation_element_name_list` must contain {SimulationElementRoles.ENVIRONMENT.value}.')
        
    async def setup(self) -> None:
        return

    async def teardown(self) -> None:
        return

    async def sim_wait(self, delay: float) -> None:
        try:
            if isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                desc = f'{self.name}: Simulating for {delay}[s]'
                for _ in tqdm (range (10), desc=desc):
                    await asyncio.sleep(delay/10)

            elif isinstance(self._clock_config, FixedTimesStepClockConfig):
                dt = self._clock_config.dt
                n_steps = math.ceil(delay/dt)
                desc = f'{self.name}: Simulating for {delay}[s]'
                
                for t in tqdm (range (n_steps), desc=desc):
                    # announce new time
                    toc = TocMessage(self.name, self.get_network_name(), t)
                    await self.send_manager_broadcast(toc)

                    # wait for everyone to ask to fast forward
                    await self.wait_for_tic_requests()

            else:
                raise NotImplemented(f'clock configuration of type {type(self._clock_config)} not yet supported.')

        except asyncio.CancelledError:
            return
        
    async def wait_for_tic_requests(self):
        """
        Awaits for all agents to send tic requests
        
        #### Returns:
            - `dict` mapping simulation elements' names to the messages they sent.
        """
        try:
            received_messages = dict()
            read_task = None
            send_task = None

            while(
                    len(received_messages) < len(self._simulation_element_name_list) - 1
                    and len(self._simulation_element_name_list) > 1
                ):
                # reset tasks
                read_task = None
                send_task = None

                # wait for incoming messages
                read_task = asyncio.create_task( self.listen_for_requests(zmq.REP) )
                await read_task
                _, src, msg_dict = read_task.result()
                msg_type = msg_dict['msg_type']

                if (SimulationMessageTypes[msg_type] != SimulationMessageTypes.TIC_REQ
                    or SimulationElementRoles.ENVIRONMENT.value in src):
                    # ignore all incoming messages that are not of the desired type 
                    self.log(f'Received {msg_type} message from node {src}! Ignoring message...')

                    # inform node that its message request was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                    send_task = asyncio.create_task( self._send_manager_msg(msg_resp, zmq.REP) )
                    await send_task

                    continue

                # unpack and message
                self.log(f'Received {msg_type} message from node {src}!')
                tic_req = TicRequest(**msg_dict)
                msg_resp = None

                # log subscriber confirmation
                if src not in self._simulation_element_name_list and self.get_network_name() + '/' + src not in self._simulation_element_name_list:
                    # node is not a part of the simulation
                    self.log(f'{src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # inform agent that its message was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                    print(self._simulation_element_name_list)

                elif src in received_messages:
                    # node is a part of the simulation but has already communicated with me
                    self.log(f'{src} has already reported to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                else:
                    # node is a part of the simulation and has not yet been synchronized
                    received_messages[src] = tic_req

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionAckMessage(src, -1)
                    self.log(f'{src} has now reported to be online to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list)})')

                # send response
                send_task = asyncio.create_task( self._send_manager_msg(msg_resp, zmq.REP) )
                await send_task

            return received_messages

        except asyncio.CancelledError:            
            return

        except Exception as e:
            self.log(f'wait failed. {e}', level=logging.ERROR)
            raise e

        finally: 
            # cancel read message task in case it is still being performed
            if read_task is not None and not read_task.done(): 
                read_task.cancel()
                await read_task

            # cancel send message task in case it is still being performed
            if send_task is not None and not send_task.done(): 
                send_task.cancel()
                await send_task
                