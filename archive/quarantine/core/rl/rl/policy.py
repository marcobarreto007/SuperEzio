"""Stub: PolicyLearner was archived. Kept for import compatibility."""


class PolicyLearner:
    """Stub — archived. Will be re-implemented in a future phase."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def learn(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {"status": "stub", "reason": "policy_learner_archived"}


policy_learner = PolicyLearner()
