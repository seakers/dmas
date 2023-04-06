"""
### Generalized Scenario Description:
- The sim environment creates an initial population of tasks and broadcasts them to all agents
- Agents receive the task broadcasts and perform a task-assignment procedure using MACCBBA
- Once the planning converges, agents are free to perform the tasks that they were assigned to perform
- The environment may stochastikly generate new tasks throughout the simulation

### Agent Description:
    Agents exist in a 2D environment with defined borders. They may move in any direction within said 2D space 
    at a fixed velocity. Agents may also perform measurement tasks if they possess the proper insturments. 
    Tasks do NOT require collaboration between agents.

#### Agent State:
    Tracks the position and velocity vector and the status of the agent at a given time. 
    The status of an agent may be idling, traveling, or performing a measurement.

    Agents are responsible of tracking their own state and publish it to the environment at each time-step. 

#### Agent Architecture:
    Agents' live method listens for any incoming messages. If messages are from any outsi

### Manager Description:
    In charge of keeping time in the simulation. Listens for all agents to be in an idle state.
"""