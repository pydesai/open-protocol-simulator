PYTHON ?= python3

.PHONY: test catalog coverage

catalog:
	$(PYTHON) scripts/extract_mid_catalog.py --spec-pdf OpenProtocol_Specification_R_2.16.0.pdf --output backend/data/mid_catalog.json

coverage:
	$(PYTHON) scripts/generate_mid_coverage_report.py

test:
	cd backend && PYTHONPATH=. $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

