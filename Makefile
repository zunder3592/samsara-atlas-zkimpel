.PHONY: setup seed api ui demo test load

venv:
	python3 -m venv .venv

setup: venv
	.venv/bin/pip install -r requirements.txt

seed:
	.venv/bin/python data/seed.py

api:
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

api-ollama:
	PROVIDER_TYPE=ollama .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

ui:
	.venv/bin/streamlit run ui/streamlit_app.py --server.port 8501

demo:
	@echo "Run in two terminals: make api (terminal 1) and make ui (terminal 2)"
	@echo "Or: make api & sleep 3 && make ui"
	@.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
	@sleep 3 && .venv/bin/streamlit run ui/streamlit_app.py --server.port 8501

test:
	.venv/bin/pytest tests/ -v

load:
	.venv/bin/python scripts/load_test.py
