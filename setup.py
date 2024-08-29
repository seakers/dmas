from setuptools import setup

def readme():
    with open('README.md') as f:
        return f.read()

# with open('requirements.txt') as f:
#     requirements = f.read().splitlines()

setup(
    name='DMAS',
    version='1.1.0',
    description='Decentralized Multi-Agent Satellite Simulation Tool',
    author='SEAK Lab',
    author_email='aguilaraj15@tamu.edu',
    packages=['dmas'],
    scripts=[],
    install_requires=['matplotlib', 'neo4j', 'pyzmq', 'tqdm', 'instrupy', 'orbitpy'] 
)
