PYTHON ?= python3
IMAGE ?= hello

.PHONY: check prepare smoke bootstrap publish status log verify

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/obs.py check
	$(PYTHON) scripts/prepare.py --check all

prepare:
	$(PYTHON) scripts/prepare.py all

smoke:
	$(PYTHON) scripts/smoke.py all

bootstrap:
	$(PYTHON) scripts/obs.py bootstrap

publish:
	$(PYTHON) scripts/obs.py publish all

status:
	$(PYTHON) scripts/obs.py status

log:
	$(PYTHON) scripts/obs.py log $(IMAGE)

verify:
	$(PYTHON) scripts/obs.py verify $(IMAGE)
