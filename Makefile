# Front door for the book. Every target here is what CI runs, so a green
# `make check` locally means a green pull request.
#
# Run `make` for the list.

OUT ?= dist
DAYS ?= 7
PYTHON ?= python3

.DEFAULT_GOAL := help
.PHONY: help setup build build-strict html pdf serve watch check check-links \
        check-external-links check-spelling check-code check-workflows check-fleet \
        check-epub check-worker check-prose check-skill notes fleet-report \
        reindex-notes clean

help: ## Show this list
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[1m%-22s\033[0m %s\n", $$1, $$2}'

setup: ## Install the pinned toolchain into .tools/ (Typst, gh)
	tools/install-typst.sh
	tools/install-gh.sh

build: ## Build the website and the PDF into $(OUT)
	$(PYTHON) tools/build.py --out $(OUT)

html: ## Build the website only (skips the PDF)
	$(PYTHON) tools/build.py --out $(OUT) --no-pdf

pdf: ## Build the PDF only
	$(PYTHON) tools/build.py --out $(OUT) --pdf-only

serve: ## Build, serve on :8000, rebuild and reload on every save
	$(PYTHON) tools/build.py --out $(OUT) --serve

watch: ## Rebuild on every save, without serving
	$(PYTHON) tools/build.py --out $(OUT) --watch

check: build-strict check-links check-epub check-code check-workflows check-fleet check-worker check-spelling check-skill check-prose ## Run every gate CI runs
	@echo "all checks passed"

build-strict: ## Build with warnings treated as failures
	$(PYTHON) tools/build.py --out $(OUT) --strict

check-links: ## Check internal links and anchors in $(OUT)
	$(PYTHON) tools/check_links.py $(OUT)

fleet-report: ## Judge the fleet: runs, cost, branches, what is stuck
	$(PYTHON) tools/fleet_report.py --days $(DAYS) --html build/fleet-report.html

check-external-links: ## Check outbound links with lychee, if installed
	@if command -v lychee > /dev/null; then \
		lychee --config lychee.toml $(OUT); \
	else \
		echo "lychee not installed; CI checks outbound links on every pull request"; \
	fi

check-spelling: ## Check spelling with typos, if installed
	@if command -v typos > /dev/null; then \
		typos; \
	else \
		echo "typos not installed; CI checks spelling on every pull request"; \
	fi

check-code: ## Type-check the example code under code/
	tools/check_code.sh

check-worker: ## Test the notes inbox worker, if node is installed
	@if command -v node > /dev/null; then \
		node worker/notes-intake/test.mjs; \
	else \
		echo "node not installed; CI tests the worker on every pull request"; \
	fi
check-skill: ## Check the skill generator makes a real zip
	$(PYTHON) tools/check_skill_page.py
check-epub: ## Check the EPUB is a well-formed EPUB 3 container
	$(PYTHON) tools/check_epub.py $(OUT)/book.epub

check-prose: ## Find the mechanical faults in the chapters
	$(PYTHON) tools/prose_scan.py --self-test
	$(PYTHON) tools/prose_scan.py
	$(PYTHON) tools/prose_scan.py

check-workflows: ## Check the GitHub Actions definitions
	$(PYTHON) tools/check_workflows.py

check-fleet: ## Check every fleet brief routes to a defined agent
	$(PYTHON) tools/fleet_brief.py --self-test
	$(PYTHON) tools/post_review.py --self-test

notes: ## Download a source into notes/ (make notes URL=https://..)
	$(PYTHON) tools/ingest_notes.py $(URL)

reindex-notes: ## Rebuild notes/index.md
	$(PYTHON) tools/ingest_notes.py --reindex

clean: ## Remove build output
	rm -rf $(OUT) build
