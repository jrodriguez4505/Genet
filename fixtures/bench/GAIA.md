# GAIA vs CrewAI — not claimed

GAIA scores whether the final answer string matches. CrewAI (and most graphs) will spend agents to chase that string.

Genet would wrap GAIA as:

1. Crawl: one body reads the question. If one source is enough, stop.
2. Walk: first method wrong (bad site, bad file) → CHANGE_METHOD, still one body.
3. Run: two independent files/sites → two gated Workers, isolation checked.
4. Someone else: if the answer file already exists in World, decide() returns None.

To *prove a beat* you still need:

- Official GAIA validation split (not leaked answers as prompts)
- The same tools CrewAI gets (web, files)
- Same model behind both
- Report two numbers: GAIA exact-match **and** illegal-spawn rate

Until that harness exists, do not put “beats CrewAI on GAIA” on a README.

In-repo now: `taskorg compare` runs the same experiment on a synthetic suite. It holds the model, tools and budget equal, and compares one agent, an always-split crew, and Genet. That measures the task-organization effect; it is not a GAIA score.

What is proven in-repo instead:

- `decide()` reads World (files, channels, covered seams) and refuses spawn
- Verifier fails if Where/How/product/Why/element-deltas are empty even when the claim says PASS
