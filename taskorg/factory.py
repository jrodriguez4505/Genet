from .run import Run
from .models import RunState, Slot
from .situation import DECISION_POINTS


# What a run checks when the operator names nothing. Any reply that echoes its brief meets these,
# so a run verified against them alone is flagged: see diagnostics.default_criteria.
DEFAULT_CRITERIA = ("default task", "purpose")


def new_run(run_id: str, goal: str, purpose: str, done_when: str) -> Run:
    """A new run: one lead, a verifier, memory and a reviewer. Skills latent; no workers."""
    lead = Slot(id="lead-1", function="lead", skill="execute")
    verifier = Slot(id="verifier-1", function="verifier", skill="verify")
    memory = Slot(id="memory-1", function="memory", skill="execute")
    reviewer = Slot(id="reviewer-1", function="reviewer", skill="execute")
    state = RunState(
        lead_id="lead-1",
        slots=[lead, verifier, memory, reviewer],
        primary="",
        goal=goal,
        success_criteria=list(DEFAULT_CRITERIA),
        checkpoints=list(DECISION_POINTS),
        context="initial context",
        done_when=done_when,
        purpose=purpose,
        method="inspect then act",
        context_sufficient=False,
    )
    return Run(id=run_id, state=state)
