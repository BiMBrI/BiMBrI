"""
Dempster-Shafer combination over the frame of discernment

    Θ = {rest, arousal, null}

Each source provides a mass function with four focal elements:

    m({rest}), m({arousal}), m({null}), m(Θ)

where m(Θ) is the mass assigned to the whole frame -- the "ignorance"
slot that grows when a source is uncertain or untrusted.

Sources are combined via Dempster's rule of combination, optionally
after Shafer discounting based on per-source trust α ∈ [0, 1]:

    m'(A) = α · m(A)            for A ⊊ Θ
    m'(Θ) = α · m(Θ) + (1 - α)

A common way to derive α is exponential decay on sample age,
α = exp(-Δt/τ), so a stale sensor's contribution gracefully fades to
total ignorance instead of pinning the fused belief on a dead reading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Mass:
    """Mass function over Θ = {rest, arousal, null} plus ignorance m(Θ)."""

    rest: float
    arousal: float
    null: float
    theta: float

    def __post_init__(self) -> None:
        for name, v in (("rest", self.rest), ("arousal", self.arousal),
                        ("null", self.null), ("theta", self.theta)):
            if v < -1e-9 or v > 1.0 + 1e-9:
                raise ValueError(f"mass {name}={v} outside [0, 1]")
        s = self.rest + self.arousal + self.null + self.theta
        if not math.isclose(s, 1.0, abs_tol=1e-6):
            raise ValueError(f"masses must sum to 1 (got {s})")

    def pignistic(self) -> tuple[float, float, float]:
        """Pignistic probability over (rest, arousal, null).

        Splits m(Θ) equally across the three singletons:
        BetP({s}) = m({s}) + m(Θ) / |Θ|.
        """
        share = self.theta / 3.0
        return (self.rest + share, self.arousal + share, self.null + share)


IGNORANCE = Mass(0.0, 0.0, 0.0, 1.0)


def discount(m: Mass, alpha: float) -> Mass:
    """Shafer discounting: scale singleton masses by α, route remainder to Θ.

    α=1 returns m unchanged; α=0 collapses to total ignorance.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be in [0, 1] (got {alpha})")
    return Mass(
        rest=alpha * m.rest,
        arousal=alpha * m.arousal,
        null=alpha * m.null,
        theta=alpha * m.theta + (1.0 - alpha),
    )


def trust_from_age(age_seconds: float, tau_seconds: float) -> float:
    """Exponential trust decay α = exp(-Δt/τ).

    age <= 0 returns 1.0; tau <= 0 returns 0.0.
    """
    if tau_seconds <= 0.0:
        return 0.0
    if age_seconds <= 0.0:
        return 1.0
    return math.exp(-age_seconds / tau_seconds)


def combine_two(m1: Mass, m2: Mass) -> Mass:
    """Dempster's rule of combination for two mass functions.

    Falls back to total ignorance on K → 1 (sources fully disagree)
    rather than raising, so a real-time loop can keep ticking.
    """
    K = (m1.rest * m2.arousal + m1.rest * m2.null
         + m1.arousal * m2.rest + m1.arousal * m2.null
         + m1.null * m2.rest + m1.null * m2.arousal)
    if K >= 1.0 - 1e-12:
        return IGNORANCE

    norm = 1.0 / (1.0 - K)
    rest = norm * (m1.rest * m2.rest
                   + m1.rest * m2.theta
                   + m1.theta * m2.rest)
    arousal = norm * (m1.arousal * m2.arousal
                      + m1.arousal * m2.theta
                      + m1.theta * m2.arousal)
    null = norm * (m1.null * m2.null
                   + m1.null * m2.theta
                   + m1.theta * m2.null)
    theta = norm * (m1.theta * m2.theta)
    return Mass(rest=rest, arousal=arousal, null=null, theta=theta)


def combine(masses: Sequence[Mass]) -> Mass:
    """Combine N mass functions via repeated application of Dempster's rule.

    Empty sequence -> IGNORANCE. Single mass returned unchanged.
    """
    if not masses:
        return IGNORANCE
    out = masses[0]
    for m in masses[1:]:
        out = combine_two(out, m)
    return out
