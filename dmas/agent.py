import argparse

class AbstractAgent:
    def __init__(self, scenario_dir) -> None:
        pass

    async def live() -> None:
        pass

class readable_dir(argparse.Action):
    """Defines a custom argparse Action to identify a readable directory."""
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError(
                '{0} is not a valid path'.format(prospective_dir)
            )
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError(
                '{0} is not a readable dir'.format(prospective_dir)
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Run Simulation'
    )
    parser.add_argument(
        'scenario_dir',
        action=readable_dir,
        help="Directory with user config JSON file, and also to write the results."
    )
    args = parser.parse_args()
    
    agent = AbstractAgent(args.scenario_dir)
    await agent.live()
