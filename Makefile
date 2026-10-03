PYTHON ?= python3

.PHONY: check bootstrap publish status log verify

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/obs.py check

bootstrap:
	$(PYTHON) scripts/obs.py bootstrap

publish:
	$(PYTHON) scripts/obs.py publish

status:
	$(PYTHON) scripts/obs.py status

log:
	$(PYTHON) scripts/obs.py log hello

verify:
	$(PYTHON) scripts/obs.py verify hello
