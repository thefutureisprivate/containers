PYTHON ?= python3
IMAGE ?= prometheus

.PHONY: check configure refresh status log verify

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/obs.py check

configure:
	$(PYTHON) scripts/obs.py configure

refresh:
	$(PYTHON) scripts/obs.py refresh

status:
	$(PYTHON) scripts/obs.py status

log:
	$(PYTHON) scripts/obs.py log $(IMAGE)

verify:
	$(PYTHON) scripts/obs.py verify $(IMAGE)
