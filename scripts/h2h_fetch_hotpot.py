"""Fetch the head-to-head's 20 HotpotQA questions (distractor dev set) from the Hugging Face dataset service.

Sample, fixed before any run: random.Random(1108) shuffles the 7,405 dev offsets; rows are fetched in that order
and the first 10 bridge and the first 10 comparison questions are kept. Rows of a type already full are dropped.
Writes one JSON row a line, with its offset.
"""
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = sys.argv[1]
TOTAL = 7405
WANT = {"bridge": 10, "comparison": 10}
BASE = "https://datasets-server.huggingface.co/rows"

order = random.Random(1108).sample(range(TOTAL), TOTAL)


def fetch(offset):
    query = urllib.parse.urlencode({"dataset": "hotpotqa/hotpot_qa", "config": "distractor", "split": "validation",
                                    "offset": offset, "length": 1})
    data = {}
    for attempt in range(8):
        try:
            with urllib.request.urlopen(f"{BASE}?{query}", timeout=60) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
            data = {"error": f"HTTP {e.code}"}
        except (TimeoutError, urllib.error.URLError) as e:
            data = {"error": type(e).__name__}
        if data.get("rows"):
            if data.get("num_rows_total") != TOTAL:
                raise SystemExit(f"the set now has {data.get('num_rows_total')} rows, not {TOTAL}")
            return data["rows"][0]["row"]
        time.sleep(2 + attempt * 2)
    raise SystemExit(f"{offset}: no row after 8 tries: {data.get('error')}")


kept = {k: [] for k in WANT}
fetched = 0
for offset in order:
    if all(len(kept[k]) == n for k, n in WANT.items()):
        break
    row = fetch(offset)
    fetched += 1
    if len(kept[row["type"]]) < WANT[row["type"]]:
        kept[row["type"]].append({"offset": offset, **row})
with open(OUT, "w", encoding="utf-8") as fh:
    for kind in WANT:
        for row in kept[kind]:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(kind, row["offset"], row["id"], row["level"], row["question"][:70])
print(f"fetched {fetched} rows, kept {sum(map(len, kept.values()))}")
