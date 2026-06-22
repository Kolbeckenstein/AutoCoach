.PHONY: help backend-install backend-test backend-test-unit backend-test-integration \
        backend-lint backend-format backend-type-check backend-check-all \
        docker-up docker-down docker-logs \
        wlan-expose wlan-status

help:  ## Show this help message
	@echo "AutoCoach Monorepo Commands"
	@echo "==========================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "For full backend command list: make -C backend help"

# ------------------------------------------------------------------
# Backend
# ------------------------------------------------------------------

backend-install:  ## Install backend dependencies
	$(MAKE) -C backend install

backend-test:  ## Run backend tests
	$(MAKE) -C backend test

backend-test-unit:  ## Run backend unit tests
	$(MAKE) -C backend test-unit

backend-test-integration:  ## Run backend integration tests
	$(MAKE) -C backend test-integration

backend-lint:  ## Lint backend code
	$(MAKE) -C backend lint

backend-format:  ## Format backend code
	$(MAKE) -C backend format

backend-type-check:  ## Type-check backend
	$(MAKE) -C backend type-check

backend-check-all:  ## Run all backend checks
	$(MAKE) -C backend check-all

pipeline-scrape:  ## Run the Reddit scraper (usage: make pipeline-scrape ARGS="--limit 10")
	$(MAKE) -C backend pipeline-scrape ARGS="$(ARGS)"

pipeline-pose:  ## Run pose processing on a video (usage: make pipeline-pose ARGS="path/to/video.mp4 [--options]") (example: make pipeline-pose ARGS="backend/data/scraped/Deadlift/1rppphk.mp4 --lift-type Deadlift")
	$(MAKE) -C backend pipeline-pose \
	  ARGS="$(abspath $(word 1,$(ARGS))) $(wordlist 2,$(words $(ARGS)),$(ARGS))"

download-models:  ## Download MediaPipe model files
	$(MAKE) -C backend download-models

# ------------------------------------------------------------------
# Infrastructure (shared across all services)
# ------------------------------------------------------------------

docker-up:  ## Start all development services
	docker-compose -f .devcontainer/docker-compose.yml up -d postgres redis qdrant

docker-down:  ## Stop all development services
	docker-compose -f .devcontainer/docker-compose.yml down

docker-logs:  ## Stream logs from all services
	docker-compose -f .devcontainer/docker-compose.yml logs -f

# ------------------------------------------------------------------
# WSL2 WLAN exposure (run from inside the devcontainer)
# ------------------------------------------------------------------

wlan-expose:  ## Print the command to expose the API to WLAN (run the printed command in an admin PowerShell on Windows)
	@echo ""
	@echo "Run this in an admin PowerShell on Windows:"
	@echo ""
	@echo "  powershell -ExecutionPolicy Bypass -File scripts\wlan-expose.ps1"
	@echo ""
	@echo "Or right-click scripts\wlan-expose.ps1 in Explorer and choose 'Run with PowerShell'."
	@echo "(script auto-detects WSL2 IP — re-run after WSL2 restarts)"
	@echo ""

wlan-status:  ## Show container IP (run portproxy check separately in Windows PowerShell)
	@echo "--- Container/WSL2 IP (as seen from inside devcontainer) ---"
	@hostname -I | awk '{print $$1}'
	@echo ""
	@echo "--- To check portproxy rules, run in Windows PowerShell ---"
	@echo "  netsh interface portproxy show v4tov4"
