db:
	bash scripts/startdb.sh

demo: # db
	python3 src/main.py

test: # db
	python3 test/test.py

clean:
	rm -f solver.in solver.out
	find . -depth -name *pyc -delete
	find . -depth -name __pycache__ -exec rm -rf '{}' \;

all: demo

.PHONY: demo test db clean
