# A bare `python3` is whatever PATH resolves first, which in a container whose venv
# is not activated is the SYSTEM interpreter -- and ad6 needs lxml/pycosat/python-sat,
# so `make test` then dies on `ModuleNotFoundError: No module named 'pycosat'`, which
# reads as a broken checkout rather than a missing venv. Overridable, and FaVe's
# ./test.sh exports the interpreter it resolved.
PYTHON ?= python3

demo:
	PYTHONPATH=. $(PYTHON) main.py

test:
	PYTHONPATH=. $(PYTHON) test/test.py

clean:
	rm -f solver.in solver.out
	find . -depth -name *pyc -delete
	find . -depth -name __pycache__ -exec rm -rf '{}' \;

all: demo

.PHONY: demo test clean
