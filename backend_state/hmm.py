"""
Hidden Markov Model over hidden states (rest, arousal, null), driven by
soft observations from `dst.combine`.

At each tick the observation is the pignistic probability vector
BetP = (P(rest), P(arousal), P(null)) derived from the combined
mass function. It is treated as a soft emission likelihood, giving
the standard forward-filter update

    belief_t ∝ (Tᵀ · belief_{t-1}) ⊙ BetP_t

where T is a hand-tuned 3×3 row-stochastic transition matrix.

The default encodes one prior fact: a direct rest <-> arousal jump is
unlikely (0.1) -- the chain typically passes through `null` between
the two. All other transitions, including self-loops and the rest/
arousal <-> null transitions, are treated as a priori equally likely
within their row:

                 rest  arousal  null
        rest   [ 0.45, 0.10,   0.45 ]
        arousal[ 0.10, 0.30,   0.60 ]
        null   [ 1/3,  1/3,    1/3  ]

The default initial belief asserts certainty in `null`, matching the
"system has just started, nothing observed yet" convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .dst import Mass

STATES: tuple[str, str, str] = ("rest", "arousal", "null")

DEFAULT_TRANSITION = np.array([
    [0.45,     0.10,     0.45    ],
    [0.10,     0.30,     0.60    ],
    [1.0 / 3,  1.0 / 3,  1.0 / 3 ],
])

UNIFORM_BELIEF = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
INITIAL_BELIEF = np.array([0.0, 0.0, 1.0])


@dataclass
class HMM:
    transition: np.ndarray = field(default_factory=lambda: DEFAULT_TRANSITION.copy())
    belief: np.ndarray = field(default_factory=lambda: INITIAL_BELIEF.copy())

    def __post_init__(self) -> None:
        T = np.asarray(self.transition, dtype=float)
        if T.shape != (3, 3):
            raise ValueError(f"transition must be 3x3 (got {T.shape})")
        if np.any(T < -1e-9) or np.any(T > 1.0 + 1e-9):
            raise ValueError("transition entries must be in [0, 1]")
        if not np.allclose(T.sum(axis=1), 1.0, atol=1e-6):
            raise ValueError("transition rows must sum to 1")
        self.transition = T

        b = np.asarray(self.belief, dtype=float)
        if b.shape != (3,):
            raise ValueError(f"belief must have shape (3,) (got {b.shape})")
        if not np.isclose(b.sum(), 1.0, atol=1e-6):
            raise ValueError(f"belief must sum to 1 (got {b.sum()})")
        self.belief = b

    def step(self, combined: Mass) -> tuple[np.ndarray, str]:
        """Advance one filter step from a combined mass function.

        Returns (posterior_belief, argmax_state_name).
        """
        prior = self.transition.T @ self.belief
        likelihood = np.array(combined.pignistic())
        posterior = prior * likelihood
        s = posterior.sum()
        if s <= 0.0:
            posterior = UNIFORM_BELIEF.copy()
        else:
            posterior = posterior / s
        self.belief = posterior
        return posterior, STATES[int(np.argmax(posterior))]

    def reset(self, belief: Sequence[float] | None = None) -> None:
        if belief is None:
            self.belief = INITIAL_BELIEF.copy()
            return
        b = np.asarray(belief, dtype=float)
        if b.shape != (3,) or not np.isclose(b.sum(), 1.0, atol=1e-6):
            raise ValueError("belief must be a length-3 vector summing to 1")
        self.belief = b
