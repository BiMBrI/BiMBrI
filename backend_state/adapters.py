"""
Per-source DST adapters: discrete threshold codes from the biomarker
monitor scripts -> mass functions over Θ = {rest, arousal, null} plus
the ignorance slot m(Θ).

Bandpower codes match `backend_state/eeg/monitor.py`:

    0  no band over threshold      ->  null
    1  theta band over threshold   ->  weak arousal/null hint, mostly ignorance
    2  alpha band over threshold   ->  strong rest signal
    3  beta  band over threshold   ->  no diagnostic value here, pure ignorance

Heart-rate codes match `backend_state/polar/connect_polar.py`:

    0  below threshold             ->  rest or null (equally)
    1  at or above threshold       ->  strong arousal signal

These are point-in-time encodings of one sensor reading. Trust
discounting and temporal decay are applied separately by `dst.discount`
and `dst.trust_from_age` before combination.
"""

from __future__ import annotations

from .dst import Mass

BANDPOWER_MASS: dict[int, Mass] = {
    0: Mass(rest=0.0, arousal=0.0,  null=1.0,  theta=0.0),
    1: Mass(rest=0.0, arousal=0.25, null=0.25, theta=0.5),
    2: Mass(rest=1.0, arousal=0.0,  null=0.0,  theta=0.0),
    3: Mass(rest=0.0, arousal=0.0,  null=0.0,  theta=1.0),
}

HEART_RATE_MASS: dict[int, Mass] = {
    0: Mass(rest=0.5, arousal=0.0, null=0.5, theta=0.0),
    1: Mass(rest=0.0, arousal=1.0, null=0.0, theta=0.0),
}


def bandpower_mass(code: int) -> Mass:
    """Map a `backend_state.eeg.monitor` band-trigger code (0/1/2/3) to a DST mass."""
    try:
        return BANDPOWER_MASS[code]
    except KeyError:
        raise ValueError(f"unknown bandpower code {code!r}; expected 0..3")


def heart_rate_mass(code: int) -> Mass:
    """Map a `backend_state.polar.connect_polar` threshold code (0/1) to a DST mass."""
    try:
        return HEART_RATE_MASS[code]
    except KeyError:
        raise ValueError(f"unknown heart-rate code {code!r}; expected 0 or 1")
