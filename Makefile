PROJECT := DMAS

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


all: bare install docs

install: install_intrupy install_orbitpy
	-X=`pwd`; \
	cd $$X; pip install -e .

install_intrupy: #Installs instrupy submodule
	-X=`pwd`; \
	cd $$X; cd $(INSTRUPY); make install
	
install_orbitpy: install_intrupy #Installs orbit submodule
	-X=`pwd`; \
	cd $$X; cd $(ORBITPY); make install

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

bare: clean
	pip uninstall -y $(PROJECT) 
	rm -rf $(PROJECT).egg-info .eggs