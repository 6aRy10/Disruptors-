# Dependency starter repo — final pre-GitHub

Normal editable source code. Change anything the team needs.

## Run
```bash
python -m venv .venv
pip install -r requirements.txt
```

Windows PowerShell:
```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
uvicorn dependency.api.main:app --reload --port 8000
```

macOS/Linux:
```bash
export PYTHONPATH=src
python -m unittest discover -s tests -v
uvicorn dependency.api.main:app --reload --port 8000
```

## Useful endpoints
- `GET /demo/events` — three guaranteed risk cards with mode/date
- `GET /demo/plan` — Indonesia allocation state
- `GET /demo/risk` — main product risk
- `POST /demo/supplier/parse-reply` — parse supplier text without changing state
- `POST /demo/supplier/confirm` — confirmed capacity changes state and replans
- `POST /demo/reset`

## Principles
- Historical events keep their true dates.
- Public facts and private demo data are marked separately.
- LLMs do not invent risk scores, arithmetic or feasibility.
- Supplier text requires structured confirmation before state changes.
- High-impact action requires planner approval.
