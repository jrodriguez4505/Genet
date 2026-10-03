.PHONY: test bench run single brief board

test:
	PYTHONPATH=. pytest -q

bench:
	PYTHONPATH=. python -m taskorg.cli bench

run:
	PYTHONPATH=. python -m taskorg.cli run --tier tight --out data/runs/ms-001.json

single:
	PYTHONPATH=. python -m taskorg.cli single --tier tight --out data/runs/single.json

brief:
	PYTHONPATH=. python -m taskorg.cli brief --goal "Write the report" --purpose "Keep the context" --context "enough" --out data/runs/brief-001.json

board:
	PYTHONPATH=. python -m taskorg.cli board data/runs/brief-001.json
