from .mission import Mission
from .models import FiveWH, Slot


def element_at_rest(mission_id: str, effect: str, purpose: str, end_state: str) -> Mission:
    """Single lead slot. Skills latent. Graph still exists."""
    head = Slot(id="head-1", function="head", skill="execute")
    verifier = Slot(id="verifier-1", function="verifier", skill="verify")
    memory = Slot(id="memory-1", function="memory", skill="execute")
    why = Slot(id="why-1", function="why", skill="execute")
    picture = FiveWH(
        who_head_id="head-1",
        slots=[head, verifier, memory, why],
        primary="head-1",
        effect=effect,
        success_criteria=["default task", "purpose"],
        tempo="mission",
        decision_points=["look", "slide", "gates", "complete"],
        current_picture="initial context",
        end_state=end_state,
        purpose=purpose,
        method="inspect then act",
        context_sufficient=False,
    )
    return Mission(id=mission_id, picture=picture)
