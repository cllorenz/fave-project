demo:
	PYTHONPATH=. python3 main.py

test:
	PYTHONPATH=. python3 test/test.py

clean:
	rm -f solver.in solver.out
	find . -depth -name *pyc -delete
	find . -depth -name __pycache__ -exec rm -rf '{}' \;

all: demo

.PHONY: demo test clean
