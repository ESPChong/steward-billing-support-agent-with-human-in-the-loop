COMPOSE := docker compose

.PHONY: up up-infra bootstrap down down-vol reindex test test-e2e test-live eval-smith demo-restart logs

up:            ## full stack (waits for model pull)
	$(COMPOSE) up -d --build

up-infra:      ## only db + ollama (for local dev on host)
	$(COMPOSE) up -d db ollama
	$(COMPOSE) run --rm bootstrap

bootstrap:     ## (re)pull models
	$(COMPOSE) run --rm bootstrap

reindex:       ## rebuild policy KB embeddings
	$(COMPOSE) exec backend sh -c "cd backend && python -m app.ingest --force"

test:          ## backend tests (re-seeds demo data!)
	$(COMPOSE) run --rm --no-deps backend sh -c "cd backend && pytest -q"

test-e2e:      ## Playwright (requires db up + backend deps on host)
	cd frontend && npx playwright test

test-live:     ## real-Ollama smoke tests
	$(COMPOSE) run --rm -e AGENT_FAKE_MODEL=false backend sh -c "cd backend && pytest -m live -q"

eval-smith:    ## eval suite vs real Ollama (+ LangSmith traces if env set)
	$(COMPOSE) run --rm -e AGENT_FAKE_MODEL=false backend sh -c "cd backend && python -m app.evals.run_evals"

demo-restart:  ## prove approval survives a backend restart
	$(COMPOSE) restart backend

logs:
	$(COMPOSE) logs -f backend

down:
	$(COMPOSE) down

down-vol:      ## also wipes Postgres + Ollama data
	$(COMPOSE) down -v