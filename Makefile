.PHONY: test style default

default: test style
	@echo "All checks passed!"

test:
	pytest

style:
	pylint src tests
