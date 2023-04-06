# Modified Asynchronous Consensus Constraint-Based Bundle Algorithm 
Simplified scenario meant to showcase the capabilities of the MACCBBA being develpoed in the SEAK Lab.

### Generalized Scenario Description:
- The simulation environment creates an initial population of tasks and broadcasts them to all agents
- Agents receive the task broadcasts and perform a task-assignment procedure using MACCBBA
- Once the planning converges, agents are free to perform the tasks that they were assigned to perform
- The environment may stochastically generate new tasks throughout the simulation

### Manager Description:
In charge of keeping time in the simulation. 
- Listens for all agents to request a time to fast-forward to. 
- Once all agents have done so, the manager will perform a time-step and announce the new time to every member of the simulation. 
- This will be repeated until the final time has been reached.

### Monitor Description:
Tracks agents' status, location, and planning ledgers.

### Agent Description:
Agents exist in a 2D environment with defined borders. They may move in any direction within said 2D space at a fixed velocity. Agents may also perform measurement tasks if they possess the proper insturments. 
Tasks do NOT require collaboration between agents.

#### **Agent State:**
Tracks the position and velocity vector and the status of the agent at a given time. The status of an agent may be idling, traveling, or performing a measurement.

Agents are responsible of tracking their own state and publishing it to the environment and monitor at each time-step. 

#### **Agent Architecture:**
Agents consist of a main `live()` process and a planning submodule.

The agents' `live()` method listens for any incoming messages. 

At the beginning of each time-step, the agent will listen for any environment message. If this message instructs the agent to alter its connectivity to other agents, it will do so by unsubscribing or subscribing to the PUB port of the desired agent.



