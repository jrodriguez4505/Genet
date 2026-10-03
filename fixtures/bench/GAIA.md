# GAIA vs CrewAI — not claimed

GAIA scores whether the final answer string matches. CrewAI (and most graphs) will spend agents to chase that string.

Genet would wrap GAIA like this:

1. **Tight tier:** a single agent reads the question. If one source is enough, stop.
2. **Normal tier:** if the first method is wrong (bad site, bad file), replan with `CHANGE_METHOD`, still as a single agent.
3. **Open tier:** two independent files or sites become two gated sub-agents, with isolation checked.
4. **Already covered:** if the answer file already exists in the world, `decide()` returns None.

To *prove a beat* you still need:

- Official GAIA validation split (not leaked answers as prompts)
- The same tools CrewAI gets (web, files)
- Same model behind both
- Report two numbers: GAIA exact-match **and** illegal-spawn rate

Until that harness exists, do not put “beats CrewAI on GAIA” on a README.

In-repo now: `taskorg compare` runs the same experiment on a synthetic suite. It holds the model, tools and budget equal, and compares one agent, an always-split crew and Genet. That measures how much staffing matters; it is not a GAIA score.

What is proven in-repo instead:

- `decide()` reads the world (files, channels, covered sub-tasks) and refuses to start a sub-agent.
- The verifier fails, even when its claim says PASS, if any of these is empty: the context, the method, the product, an open review, or the sub-agents' merged results.
