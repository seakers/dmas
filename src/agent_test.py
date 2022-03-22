from mesa import Agent, Model
from mesa.time import RandomActivation


class MoneyAgent(Agent):
    def __init__(self, unique_id, model):
        super().__init__(unique_id=unique_id, model=model)
        self.wealth = 1

    def step(self):
        if self.wealth == 0:
            return
        other_agent = self.random.choice(self.model.schedule.agents)
        other_agent.wealth += 1
        self.wealth -= 1
        print(str(self.unique_id) + " gives " + str(other_agent.unique_id) +
              " 1 coin. " + str(self.unique_id) + " now has " + str(self.wealth))

class MoneyModel(Model):
    def __init__(self, N):
        self.num_agents = N
        self.schedule = RandomActivation(self)

        for i in range(self.num_agents):
            a = MoneyAgent(i, self)
            self.schedule.add(a)

    def step(self):
        self.schedule.step()

model = MoneyModel(10)
for i in range(10):
    model.step()