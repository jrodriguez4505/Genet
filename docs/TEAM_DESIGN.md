# Team structure: design

Status: proposal, 28 October 2026. Part 2, the independent verifier, is built (v0.7.0); the rest is not. Part 7 was added on 29 October.

## What it must serve

Genet started from agent counts used as a headline number. Products advertise hundreds of sub-agents on one task: [Kimi's Agent Swarm](https://www.kimi.com/help/agent/agent-swarm) runs up to 300. A count says what was spent, not what was gained.

Genet's question is whether a second agent does new work. Its claim is the best baseline's accuracy at close to single-agent cost. This design keeps both. It adds a picture of the team that the kernel should serve:

- The team is small.
- The lead knows what each member can do.
- Members differ where it matters.
- Everyone works from the same goal, purpose and done-when.
- Responsibility is shared, and the outcome is the lead's.

The test of the design is the one Genet already uses. Does each member the team adds do work the others could not?

## What the live runs show so far

- **Every team was a set of identical sub-agents:** one model with the same skills, split only by which files each could open. A team like that can buy room and time, and nothing else. A single agent needed neither. It got every answer right up to 20 companies, about 84,000 tokens a task, and 11 of 12 in the 28 October rerun. "Splitting did not help" is the right result for this team. It says nothing yet about a team whose members differ.
- **The always-split crew lost answers as the work grew:** 8 of 8, then 5 of 8, then 5 of 7, in hand-offs and merges. Each added hand-off is a chance to lose information.
- **The verifier cannot check sources.** The `verify` skill has no tools. Its brief carries the product, up to 12 evidence lines, and the shared context. Every reply's `context_update` is merged into that context, so the verifier also reads the author's own notes. On 28 October it passed a wrong total (1152.1 for 1142.6) and said it "could not open the 20 source files". The wrong figure came from a look-alike company's file.
- **Judging fit before the work is unreliable** on a real model. The lead misjudges it, and the estimate from file sizes runs short.

## The model: positions, not kinds of agent

Every agent is the same model and can hold any skill. So a member is not a kind of agent. It is a **position**, and any agent can fill it. A position has four parts:

| Part | What it is | In the kernel today |
|---|---|---|
| Responsibility | function, skill and channel | `Slot.function`, `Slot.skill`, `Slot.channel_id` |
| View | what goes into its brief | implicit in `Engine._brief` |
| Access | the tools it may call, and on which files | `Slot.tools`, `Toolbox.scoped()` |
| Model | which model fills it | a skill can have its own model |

Two copies of one model differ only in view, access and model. That gives four reasons a second member could do new work:

1. **Focus.** The part needs a fresh context, because it does not fit beside the rest or would crowd it.
2. **Independence.** A check needs a view without the author's reasoning, so that its mistakes are not the author's.
3. **Access.** The part needs access the others must not have.
4. **Cost.** The part can run on a cheaper model.

Today's should-we gate measures two of these: material that does not fit is focus, and declared isolation is access. Independence and cost are new. Time saved by running in parallel is real too, but it is not one of Genet's measures and stays out of the gates.

### What every position shares

Positions differ. What they share is what lets each member do more than it could alone:

- the goal, its purpose and done-when;
- the shared context, with every member's notes, except where a view leaves them out;
- the guidelines and the lessons from past runs, which every brief carries;
- the run's record, which the kernel writes, and from which come the lead's account, the review and the verifier's sources;
- the kernel's rules, the same for every position.

## Seven parts

### 1. Views are written rules

What each position sees becomes a rule the kernel states, records and tests. Today it falls out of `_brief`:

| Position | Sees today |
|---|---|
| Lead | everything |
| Sub-agent | the context as it stood at the split, plus its own channel's working facts |
| Verifier | everything, the lead's notes included |

A `View` per function names what is included. Each call's record states the view it was built from, and tests check that what a view leaves out never reaches the brief.

### 2. An independent verifier (built in v0.7.0)

Built as `--verify-view independent` and `--verify-sources layered|full`. It is in `taskorg/checks.py`, and the README's Verification section describes it. Building it changed the proposal in three places.

- **The kernel opens the sources, not the verifier.** The proposal gave the verifier `read` and `retrieve`. Instead the kernel picks the files and puts them in the verifier's brief, as many as fit the per-call limit. The pick follows a rule in code, so the author cannot steer it, and the verifier cannot skip a file it was meant to check. It costs no tool rounds, and it is deterministic, so tapes replay.
- **A sharper flag than file names that nearly match.** The record now keeps the file each read showed and the files each search returned lines from. The strongest signal is a file the goal names that no call in the run read or searched. The product states something about that subject, so it came from somewhere else. That is exactly how the 28 October miss happened. The search for "Saffron Grid FY2026 Q2 revenue" returned only `saffron-grid-partners.md` lines, and `saffron-grid.md` never reached the run. On that run's tape, the layered pick opens `saffron-grid.md` first.
- **The layered check, as built:**
  1. **In code, at no cost:** an evidence quote that is not in the file it cites is named to the verifier. The verifier still gives the verdict.
  2. **Risky files:** a file the goal names that the run never saw, then the files the product's uncertainty names.
  3. **Two files drawn at random** from what the goal names or the product cites. The draw is seeded by the goal and the product, so the same product opens the same files under every setup.

  `full` opens every file the goal names, the product cites or its uncertainty names, or the run read. Tying the mode to the budget tier is not built: the operator chooses it with the flag.
- **View, as proposed.** The verifier gets the context as the operator gave it, the goal, the purpose, done-when, the criteria, and the product with its evidence. It does not get the lead's `context_update` trail, the working product, or sub-agents' reports.
- **Unchanged.** PASS still needs every criterion and no world misses, and a failed check still allows one rework. With `--verify-sources none`, the brief is byte for byte what it was. `layered` is the default since its live run.

The test is `verify-bench`. It reviews products the harness builds for 20-company aggregate questions, each with the record its author would have left:
- right ones;
- ones with a company's figure taken from its look-alike's file, which the author read instead of its own;
- ones with the FY2025 figure.

Natural misses are too rare to count, 1 in 12 in the rerun, so the errors are planted, and the total always adds up. Five setups:

1. today's verifier;
2. sources with today's view, full or layered;
3. sources with the independent view, full or layered.

That separates what access buys from what independence buys. The full check is the yardstick that shows what the layered check misses.

Measures: wrong products caught by kind, right products failed, whether the company's own file was shown, and tokens a review.

On the simulated reader, a perfect checker of what it is shown, `full` catches every planted error. `layered` catches every look-alike error and 17% of wrong-year ones, since only the random draw can find those. `today` catches none, and nothing right is failed. The sim cannot show what the view changes: that needs a real model.

The live run on Haiku 5.5 (`scripts/verify_runs.sh`), on 29 October, was 24 products, 12 of them wrong, under 5 setups: 120 reviews, $0.21. `full` caught 12 of 12 in both views, `layered` 9 of 12 for the right reason in both, and `today` 2. No setup failed a right product. Whenever a planted error's own file was in the brief, the verifier caught it.

Add one Sonnet 5.5 arm only if Haiku's independent verifier still passes planted errors. It would use the independent view and the layered check, at about $1.00 capped, and it would separate a design that falls short from a model that does. A full check on Sonnet costs about $0.10 a review, too much for development.

### 3. Nesting (build second)

A sub-agent whose part is itself too big becomes the lead of a run of its own, a child run, under the same kernel:

- **Same rules at every level.** The same gates, invariants and JSON artifact apply. A child lead can change only its own roster (INV-1 per run).
- **Budget.** The child's budget is carved out of the parent's remaining budget and reserved before the child starts. Its spend counts in the parent's.
- **Limits.** Depth 2 to start: a top-level run and one level of child runs. Each lead keeps the cap of 4 sub-agents.
- **Coverage.** The child's can-someone-else gate sees the parent's world and its siblings' channels, so it cannot staff work that is already covered.
- **Reporting.** The child's verified product comes back through the parent's merge stream. A failed child hands its part to the parent's lead, as a failed sub-agent does today.

This changes something the README refuses: "Workers that spawn workers". That refusal guards against uncontrolled growth. Nesting keeps every addition behind the gates, inside a reserved budget and a fixed depth. The README line would become "Sub-agents that add sub-agents without passing the gates."

It is worth it only where a part cannot be done in one context, because each level adds a hand-off. The test runs in the sim first, at 40 or more companies with a tight per-call cap, where a flat team of 4 has parts that do not fit. It compares single, flat Genet and nested Genet. A live run follows only if the sim shows a case.

### 4. Succession (build third)

The lead position can be refilled from the record. The kernel writes a handover from:

- the goal, the purpose and done-when;
- the initial context;
- the gate record;
- the working product;
- the parts done and checked.

The handover is built from the record, never from model text. A fresh agent takes the lead with it.

Two triggers:

- **The lead's next call would not fit.** This is the open item from the tight-cap runs: re-plan on a measured overflow instead of halting.
- **The lead's reply fails twice** (SCHEMA or LIVE).

The test is a tight cap where the lead's working calls overflow. It compares today's halt with a handover: is the goal still met, and at what cost?

### 5. Authority stays in the kernel

Any agent can fill any position, so authority cannot belong to an agent. It belongs to the position, and the kernel checks it. Nothing a model writes reaches a roster, a view, an access list or a budget without a check in code and an entry in the record, at any level.

### 6. Members that differ by model (later)

A skill can already have its own model. The test: a cheap model reads, and a stronger one leads or verifies. It needs a Sonnet run, so it waits for the operator's go-ahead on spend.

### 7. The lead knows its members (proposed 29 October)

Today the lead's plan brief names the skills and nothing more. It does not say what each skill can open, what a call costs, or how each has done before. Every agent is the same model, so knowing the members means knowing the positions: what a skill, its access and its model have done.

- **A card for each position the lead can staff,** written by the kernel. It gives the skill, its tools, its model, and the measured cost of one of its calls.
- **A record for each position from past runs,** kept in the store beside the lessons. It counts:
  - parts done;
  - parts verified;
  - parts that failed, and how (`SCHEMA`, `LIVE`);
  - parts the lead had to cover.

  It is built from the record, never from model text. It is kept by position (skill and model), not by agent, because agents are copies.
- **In the plan brief, bounded.** The cards go in a table of fixed size. They show counts, not scores, and a position's record shows only after three runs, so one bad run does not steer the lead.
- **The gates do not read it.** It informs what the lead proposes, and the gates still decide with the same three checks.
- Comparison trials each use a fresh store, as they do for lessons, and a flag turns the cards off.

The test runs the same tasks with and without the cards. The sim shows only what the cards cost in tokens, because its reader ignores them. Haiku then shows whether they change the plan. Does a lead with the cards propose fewer parts that are refused or that fail, at the same accuracy and comparable tokens?

## What does not change

- A single agent is the default.
- The gates run in order and fail closed.
- Models fill only the fixed JSON artifact.
- Shared ownership: failed parts go to the lead, and every failure gets a blameless review.
- Budgets are hard stops.

## What would count as a result

This design makes a second claim testable: a team that beats its best member.

- If the independent verifier catches more seeded errors than today's, without failing more right products, independence is new work.
- If nested Genet holds accuracy where flat Genet and a single agent fall, at comparable cost, nesting is new work.

If neither holds, Genet's claim stays as it stands, and its value stays governance and cost.

A third result would not be new work by a member, but it would make the lead better at staffing: if a lead given its members' records proposes fewer parts that are refused or that fail, at the same accuracy, the records pay for their tokens.

Each could fail in a specific way:

- The independent verifier catches no more than today's, or fails right answers.
- The layered check misses too much to matter.
- Nesting's extra hand-offs lose more than the fresh context gains.
- A handover drops something the old lead knew.
- The cards cost tokens in every plan call and change no plan.

## Order

1. The independent verifier: built in v0.7.0, with the full and layered checks and the verify bench, and run on Haiku 5.5 on 29 October (`docs/LIVE_TESTS.md`). Sources decided the catch: `full` caught 12 of 12, `layered` 9 of 12 for the right reason, `today` 2. The independent view made no measurable difference at this size.
2. The lead knows its members: sim for cost, then Haiku. It comes before nesting because nesting multiplies the leads that plan.
3. Nesting: sim at large sizes. Live only if the sim shows a case.
4. Succession, together with re-planning on a measured overflow.
5. Members that differ by model: on the operator's go-ahead.

## Decisions

- **Decided, 28 October:** lift the "workers that spawn workers" refusal. Nesting keeps the gates, a depth limit and a reserved budget. The README changes when nesting is built.
- **Recommended: checks.**
  - In development, build both the full check and the layered check. The full check is the yardstick.
  - In the system, the layered check is the default. The open tier, or an operator flag, runs the full check.
- **Recommended: models.**
  - In development, every arm runs on Haiku 5.5. One Sonnet arm runs only if Haiku's independent verifier misses planted errors.
  - In the system, a cheap model does the work and a stronger model verifies a sample. A sampled review reads a fraction of what the work read, so it is the cheapest place to put a stronger model. A different model's mistakes also match the author's less often.

## Related work

A survey on 28 October 2026 covered about 40 searches across papers, framework docs and engineering posts. The field moves fast and much of it is preprints, so read the "not found" notes as "not found in that search".

| Part of this design | Prior work | How it differs |
|---|---|---|
| Positions, not kinds of agent | Roles as purpose and accountabilities that anyone can fill, in [holacracy's constitution](https://www.holacracy.org/constitution/5-0/). Prompt-defined subagents with their own tools and model, in [Claude Code](https://code.claude.com/docs/en/sub-agents). Same-model "homogeneous" teams, shown to be simulable by one agent ([Xu et al. 2026](https://arxiv.org/abs/2601.12307)). | Well established. Holacracy governs people, and agent frameworks mostly name agent types. |
| Nesting | Recursive spawning in [Self-Organized Agents](https://arxiv.org/html/2404.02183) (depth 2), [ReDel](https://arxiv.org/html/2408.02248) (a depth limit), and [recursive agent harnesses](https://arxiv.org/html/2606.13643v1). A child's budget kept within its parent's, in [Agent Contracts](https://arxiv.org/abs/2601.08815). | Mostly done. A limit on direct reports as a design parameter was not found, and neither were the same admission gates at every level. |
| Succession | A lead that saves its plan and starts fresh subagents, in [Anthropic's research system](https://www.anthropic.com/engineering/multi-agent-research-system). Progress files that let a fresh session continue, in [long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). A task ledger with replanning, in [Magentic-One](https://arxiv.org/html/2411.04468v1). | Partly done. Handing the lead of a live team to a successor, from a kernel-written record, was not found. |
| Authority in code | Plans moved into code ([Claude Code workflows](https://code.claude.com/docs/en/workflows)). Hooks that can block task creation. Policy layers that approve or block actions ([arXiv 2606.04306](https://arxiv.org/abs/2606.04306)). Budget-constrained team selection done offline ([BAMAS](https://arxiv.org/abs/2511.21572)). | Partly done. Ordered admission gates for each proposed agent (covered already, then a measured reason, then affordable), with the model only proposing, were not found. |
| Independent verifier | Verification prompts that leave out the original answer score better ([Chain-of-Verification, factored](https://arxiv.org/abs/2309.11495)). Reviewers given only a diff, from a clean context ([Cognition, April 2026](https://cognition.com/blog/multi-agents-working)). Models catch errors framed as someone else's that they miss as their own ([arXiv 2507.02778](https://arxiv.org/abs/2507.02778)). | Done as practice, with limits. Models agree about 60% of the time when both are wrong ([arXiv 2506.07962](https://arxiv.org/abs/2506.07962)). Verification gains shrink as solver and verifier grow alike, and cross-family checking works best ([arXiv 2512.02304](https://arxiv.org/abs/2512.02304)). No measurement was found that withholding the author's reasoning lowers error correlation between agents of one model. The verify bench measures that: on Haiku 5.5, over 24 products whose author note does not argue for the error, it made no difference. |
| The lead knows its members (searched 29 October) | Executors described by capability, cost and tools, from which an orchestrator picks ([EASy](https://arxiv.org/abs/2608.04588)). Agents chosen by a reputation built from rated performance ([DRF](https://arxiv.org/abs/2509.05764)). Trust kept for each skill rather than one score for each agent ([arXiv 2606.14200](https://arxiv.org/abs/2606.14200)). Perfect delegation would beat measured delegation by 15 to 31 points ([arXiv 2605.19099](https://arxiv.org/abs/2605.19099)). | Mostly done. Profiles and track records exist. Here the kernel keeps them from the run record, by position rather than by agent, and they inform proposals that still pass the gates. |
| "Does a second agent do new work?" | Add complexity only when it shows better results ([Building effective agents](https://www.anthropic.com/research/building-effective-agents)). At equal token budgets, single agents match or beat multi-agent systems on multi-hop reasoning, unless one agent's context is degraded ([Tran and Kiela](https://arxiv.org/abs/2604.02460)). | Partly done. That question as the rule checked for each agent at runtime, with the claim "the best baseline's accuracy at close to single-agent cost", was not found. Existing work reaches cheaper teams by searching designs offline. |

**What looks new:**
- the ordered admission gates in code, as the runtime test for each agent a lead proposes;
- the same gates at every level once teams nest;
- handing a live team's lead to a successor from a record the kernel writes.

Part 7 is not on that list: profiles and track records already exist.

**Closest analogy overall:** holacracy, which has roles, nested circles and authority held by a written constitution. It governs people, not models.

**What others measured.** The evidence agrees with Genet's live runs so far:
- Multi-agent systems win on wide, decomposable work, at many times the tokens: [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) reports 90% over a single agent at about 15 times the tokens.
- Across 260 configurations, [Google](https://arxiv.org/abs/2512.08296) found results from +81% on decomposable tasks to -70% on sequential ones, with gains fading against a strong single agent.
- The benefit shrinks as models improve ([Gao et al.](https://arxiv.org/abs/2505.18286)).
- A supervisor helps only "when it can verify work" ([Agachan et al.](https://arxiv.org/abs/2609.14767)). That supports building the verifier first.
