.PHONY: test bench mission crawl brief board

test:
	PYTHONPATH=. pytest -q

bench:
	PYTHONPATH=. python -m taskorg.cli bench

mission:
	PYTHONPATH=. python -m taskorg.cli mission --pace crawl --out data/missions/ms-001.json

crawl:
	PYTHONPATH=. python -m taskorg.cli run --pace crawl --out data/missions/crawl.json

brief:
	PYTHONPATH=. python -m taskorg.cli brief --effect "Issue the order" --purpose "Hold the picture" --look "enough" --out data/missions/brief-001.json

board:
	PYTHONPATH=. python -m taskorg.cli board data/missions/brief-001.json
