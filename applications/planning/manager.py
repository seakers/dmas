import math
from dmas.managers import *
from messages import *

class PlanningSimulationManager(AbstractManager):
    def _check_element_list(self):
        env_count = 0
        for sim_element_name in self._simulation_element_name_list:
            if SimulationElementRoles.ENVIRONMENT.value in sim_element_name:
                env_count += 1
        
        if env_count > 1:
            raise AttributeError(f'`simulation_element_name_list` must only contain one {SimulationElementRoles.ENVIRONMENT.value}. contains {env_count}')
        elif env_count < 1:
            raise AttributeError(f'`simulation_element_name_list` must contain {SimulationElementRoles.ENVIRONMENT.value}.')
        
    async def setup(self) -> None:
        # nothing to set-up
        return

    async def sim_wait(self, delay: float) -> None:
        """
        Waits for the total number of seconds in the simulation.
        Time waited depends on length of simulation and clock type in use.
        """
        try:
            desc = f'{self.name}: Simulating for {delay}[s]'
            if isinstance(self._clock_config, AcceleratedRealTimeClockConfig):
                for _ in tqdm (range (10), desc=desc):
                    await asyncio.sleep(delay/10)

            elif isinstance(self._clock_config, FixedTimesStepClockConfig):
                dt = self._clock_config.dt
                n_steps = math.ceil(delay/dt)
                t = 0
                tf = t + delay
                
                # for t in tqdm (range (1, n_steps+1), desc=desc):
                with tqdm(total=n_steps + 1, desc=desc) as pbar:
                    while t < tf:
                        # wait for everyone to ask to fast forward            
                        self.log(f'waiting for tic requests...')
                        await self.wait_for_tic_requests()
                        self.log(f'tic requests received!')

                        # announce new time to simulation elements
                        self.log(f'sending toc for time {t}[s]...', level=logging.INFO)
                        toc = TocMessage(self.get_network_name(), t)

                        await self.send_manager_broadcast(toc)

                        # announce new time to simulation monitor
                        self.log(f'sending toc for time {t}[s] to monitor...')
                        toc.dst = SimulationElementRoles.MONITOR.value
                        await self.send_monitor_message(toc) 

                        self.log(f'toc for time {t}[s] sent!')

                        # updete time and display
                        pbar.update(dt)
                        t += dt

                    self.log('TIMER DONE!', level=logging.INFO)
            
            elif isinstance(self._clock_config, EventDrivenClockConfig):  
                t = 0
                tf = self._clock_config.get_total_seconds()
                with tqdm(total=tf , desc=desc) as pbar:
                    while t < tf:
                        # wait for everyone to ask to fast forward            
                        self.log(f'waiting for tic requests...')
                        reqs = await self.wait_for_tic_requests()
                        self.log(f'tic requests received!')

                        t_next = tf
                        for src in reqs:
                            tic_req : TicRequest
                            tic_req = reqs[src]
                            if tic_req.tf < t_next:
                                t_next = tic_req.tf
                        
                        # announce new time to simulation elements
                        self.log(f'sending toc for time {t_next}[s]...', level=logging.INFO)
                        toc = TocMessage(self.get_network_name(), t_next)

                        await self.send_manager_broadcast(toc)

                        # announce new time to simulation monitor
                        self.log(f'sending toc for time {t_next}[s] to monitor...')
                        toc.dst = SimulationElementRoles.MONITOR.value
                        await self.send_monitor_message(toc) 

                        self.log(f'toc for time {t_next}[s] sent!')

                        # updete time and display
                        pbar.update(t_next - t)
                        t = t_next

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
                read_task = asyncio.create_task( self.listen_for_requests() )
                await read_task
                _, src, msg_dict = read_task.result()
                msg_type = msg_dict['msg_type']

                if (NodeMessageTypes[msg_type] != NodeMessageTypes.TIC_REQ
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
                    self.log(f'{src} is not part of this simulation. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list) - 1})')

                    # inform agent that its message was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(src, -1)

                elif src in received_messages:
                    # node is a part of the simulation but has already communicated with me
                    self.log(f'{src} has already reported its tic request to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list) - 1})')

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionIgnoredMessage(src, -1)
                else:
                    # node is a part of the simulation and has not yet been synchronized
                    received_messages[src] = tic_req

                    # inform agent that its message request was not accepted
                    msg_resp = ManagerReceptionAckMessage(src, -1)
                    self.log(f'{src} has now reported reported its tic request  to the simulation manager. Wait status: ({len(received_messages)}/{len(self._simulation_element_name_list) - 1})')

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
    
    async def teardown(self) -> None:
        # nothing to tear-down
        return