PROJECT := dmas

.DEFAULT_GOAL := all

INSTRUPY = instrupy
ORBITPY = orbitpy
TEST = tests
DOC = docs

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  all        	to perform clean-up and installation"
	@echo "  install    	to set up the python package (pip install -e .)"
	@echo "  runtest    	to perform unit testing"
	@echo "  runtest_eosim  to confirm install for instrupy and orbitpy dependencies"
	@echo "  testlog    	to perform unit testing with no log capture"
	@echo "  fulltest   	to perform unit testing with no log capture and with verbose"
	@echo "  clean      	to remove *.pyc files and __pycache__ directories"
	@echo "  bare       	to uninstall the package and remove *egg*"


all: bare install 

install: 
	-X=`pwd`; \
	cd $$X; pip install -e .; \
	pip install matplotlib; \
	pip install neo4j; \
	pip install pyzmq; \
	pip install tqdm
	
runtest_eosim:
	-X=`pwd`; \
	cd $$X; cd $(INSTRUPY); python -m unittest discover; \
	cd $$X; cd $(ORBITPY); python -m unittest discover

docs: docs_clean #Build the documentation
	-X=`pwd`; \
	echo '<<<' $$DOC '>>>'; cd $$X; cd $(DOC); make html;

docs_clean: 
	-X=`pwd`; \
	echo '<<<' $$DOC '>>>'; cd $$X; cd $(DOC); make clean;

clean: 
	@echo "Cleaning up..."
	@find . -name "*.pyc" -delete
	@find . -type d -name __pycache__ -print0 | xargs -0 rm -rf

bare: clean
	pip uninstall -y $(PROJECT) 
	rm -rf $(PROJECT).egg-info .eggs

runtest:
	-X=`pwd`; \
	cd $$X; cd $(TEST); python -m unittest discover