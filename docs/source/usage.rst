Usage
=====

.. _installation:

Installation
------------

To use Lumache, first install it using pip:

.. code-block:: console

   (.venv) $ pip install lumache

Creating recipes
----------------

To retrieve a list of random ingredients,
you can use the ``lumache.get_random_ingredients()`` function:

.. autofunction:: lumache.get_random_ingredients

The ``kind`` parameter should be either ``"meat"``, ``"fish"``,
or ``"veggies"``. Otherwise, :py:func:`lumache.get_random_ingredients`
will raise an exception.

.. autoexception:: lumache.InvalidKindError

For example:

>>> import lumache
>>> lumache.get_random_ingredients()
['shells', 'gorgonzola', 'parsley']


### Running 3D-CHESS Scenarios

Run dmas/environment.py as follows: `python dmas/environment.py nadir 5561 5562` where `nadir` is your desired scenario and `5561 5562` are the ports for message broadcasts.

Run dmas/test.py as follows: `python dmas/test.py nadir 5561 5562`  in a separate Ubuntu terminal, after activating the conda environment.

### Neo4J Instructions (not strictly necessary, but without this the knowledge graph queries will fail)

Download [Neo4j Desktop](https://neo4j.com/download/).

Start a local DBMS, with password "ceosdb".

Set up github.com/seakers/historical_db. Switch to "ben" branch. Run scraper following directions.

Set up github.com/CREATE-knowledge-planning. Run measurement_type_rule.py. (Email Ben for updated measurement_type_rule.py script).