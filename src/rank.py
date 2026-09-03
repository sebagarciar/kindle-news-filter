"""Final selection via the model. PRD 5.2, 5.3.

For World and AI, input is pre-ranked clusters (cluster.py). For Chile, the
full candidate list goes straight to the model — no clustering step.

Every category's ranking call takes three inputs: the candidates, the
preferences file (5.7), and the 7-day backlog (5.3), so repeat stories get
skipped or reframed as updates rather than silently resurfacing.

Open question (PRD 8): one model call for ranking + summarising, or two.
Not decided yet — see conversation before implementing.
"""


def select_top_three(candidates: list[dict], preferences: str, backlog: list[dict]) -> list[dict]:
    """Return 3 items for one category, each with a 1-2 sentence summary."""
    raise NotImplementedError
