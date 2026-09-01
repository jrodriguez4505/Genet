.PHONY: test brief crawl board

test:
	PYTHONPATH=. pytest -q

crawl:
	PYTHONPATH=. python -m taskorg.cli run --pace crawl --out data/missions/crawl.json

brief:
	PYTHONPATH=. python -m taskorg.cli brief --effect "Complete the default task" --purpose "Keep one shared context" --look "enough" --out data/missions/brief-001.json

board:
	PYTHONPATH=. python -m taskorg.cli board data/missions/brief-001.json
