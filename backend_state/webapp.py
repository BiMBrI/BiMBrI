"""
Dispatcher layer that turns HMM state into web-app calls.

The robot server (`robot/server/server.py`) exposes:

    POST /trigger_rest     -> run the rest subroutine
    POST /trigger_aroused  -> run the aroused subroutine
    GET  /state            -> {status, cooling_down, cooldown_remaining, ...}

The trigger endpoints always return HTTP 200; the body says whether the
trigger was accepted:

    {"ok": true,  "status": "rest"}   -> accepted, replay started
    {"ok": false}                     -> refused (mid-replay, or in the
                                          25 s post-replay cooldown)

There is no endpoint for the `null` HMM state.

Notifications are edge-triggered: a POST fires only when the HMM-
reported state differs from the previously-*delivered* state. When a
trigger is refused, we hold onto it as the `pending` state and don't
retry until the server's cooldown expires (we ask `/state` for the
exact remaining seconds). The pending retry is superseded by:

  - the HMM reverting to the last-delivered state (the world changed
    its mind, no point retrying the stale pending);
  - the HMM transitioning to `null` (always silent, supersedes pending);
  - the HMM moving to a different non-null state (the new state is
    what matters now).

Connection errors don't advance state and use a short fixed backoff so
the next HMM tick can retry quickly; HTTP responses (accepted or
refused) do advance the dispatcher's understanding so a busy arm is
not hammered.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ENDPOINTS = {
    "rest": "/trigger_rest",
    "arousal": "/trigger_aroused",
}

# Backoff used when /state is unreachable or unhelpful (e.g. server
# is replaying and there is no cooldown timer to read yet).
DEFAULT_REFUSAL_BACKOFF_SEC = 5.0

# Backoff used when the trigger POST itself fails to reach the server.
CONNECTION_ERROR_BACKOFF_SEC = 1.0

# Small fudge added to the server-reported cooldown so we don't race
# the moment it transitions out of cooling_down.
COOLDOWN_BUFFER_SEC = 0.5


class WebAppNotifier:
    """Edge-triggered HMM-state -> web-app dispatcher with cooldown-aware retry."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        initial_state: Optional[str] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._clock = clock
        self._last_state: Optional[str] = initial_state
        self._pending_state: Optional[str] = None
        self._earliest_retry: float = 0.0

    @property
    def last_state(self) -> Optional[str]:
        return self._last_state

    @property
    def pending_state(self) -> Optional[str]:
        return self._pending_state

    def reset(self, state: Optional[str] = None) -> None:
        """Clear (or set) the tracked last-state and any pending retry."""
        self._last_state = state
        self._pending_state = None
        self._earliest_retry = 0.0

    def notify(
        self,
        state: str,
        *,
        payload: Optional[dict] = None,
    ) -> bool:
        """Notify the web app if `state` is news vs. what's already delivered.

        Returns True iff the server accepted a POST on this call (`ok=true`).
        Refused triggers (`ok=false`), connection errors, and ticks during
        an active retry backoff all return False; the dispatcher will retry
        on a future call once the cooldown expires.
        """
        if state not in ("rest", "arousal", "null"):
            raise ValueError(f"unknown state {state!r}")

        # The HMM is reporting the state we already delivered. If a stale
        # pending retry is still around for some other state, drop it --
        # the world reverted before we got around to retrying.
        if state == self._last_state:
            if self._pending_state is not None:
                logger.info(
                    "pending %r superseded by current %r; clearing",
                    self._pending_state, state,
                )
                self._clear_pending()
            return False

        # `null` is always silent. It supersedes any pending non-null retry
        # because the user has just stopped showing whichever signal was
        # going to be triggered.
        if state == "null":
            self._last_state = state
            self._clear_pending()
            return False

        # `state` is non-null and differs from `_last_state`. If it matches
        # an existing pending retry, honour the backoff timer; otherwise
        # the new state replaces any prior pending and we POST immediately.
        if state == self._pending_state:
            if self._clock() < self._earliest_retry:
                return False
        else:
            self._clear_pending()

        prev = self._last_state
        body = {"event": "state_change", "from": prev, "to": state}
        if payload:
            body.update(payload)

        delivered, accepted = self._post(ENDPOINTS[state], body)

        if not delivered:
            self._pending_state = state
            self._earliest_retry = self._clock() + CONNECTION_ERROR_BACKOFF_SEC
            return False

        if accepted:
            self._last_state = state
            self._clear_pending()
            return True

        # Delivered but refused: ask /state how long the cooldown is.
        backoff = self._fetch_refusal_backoff()
        self._pending_state = state
        self._earliest_retry = self._clock() + backoff
        return False

    def _clear_pending(self) -> None:
        self._pending_state = None
        self._earliest_retry = 0.0

    def _post(self, path: str, body: dict) -> tuple[bool, bool]:
        """POST `body` as JSON. Returns (delivered, accepted).

        `delivered` is True if the server returned any response; the
        caller may then advance state without retrying. `accepted` is
        True only on 2xx with `{"ok": true}` in the body.
        """
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                if not (200 <= status < 300):
                    logger.warning("POST %s -> %s", url, status)
                    return True, False
                try:
                    parsed = json.loads(resp.read().decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    logger.warning("POST %s: invalid JSON body (%s)", url, exc)
                    return True, False
                if parsed.get("ok") is True:
                    return True, True
                logger.info("POST %s refused: %s", url, parsed)
                return True, False
        except urllib.error.HTTPError as exc:
            logger.warning("POST %s -> %s %s", url, exc.code, exc.reason)
            return True, False
        except urllib.error.URLError as exc:
            logger.warning("POST %s failed: %s", url, exc.reason)
            return False, False
        except OSError as exc:
            logger.warning("POST %s failed: %s", url, exc)
            return False, False

    def _fetch_refusal_backoff(self) -> float:
        """Read /state to determine how long until the next retry should fire.

        Falls back to DEFAULT_REFUSAL_BACKOFF_SEC if /state is unreachable
        or doesn't expose a meaningful cooldown_remaining (e.g. the server
        is mid-replay -- there's no cooldown timer running yet).
        """
        url = self.base_url + "/state"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                if not (200 <= resp.status < 300):
                    return DEFAULT_REFUSAL_BACKOFF_SEC
                parsed = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            logger.warning("GET %s failed: %s", url, exc)
            return DEFAULT_REFUSAL_BACKOFF_SEC

        if parsed.get("cooling_down"):
            remaining = parsed.get("cooldown_remaining")
            if isinstance(remaining, (int, float)) and remaining > 0:
                return float(remaining) + COOLDOWN_BUFFER_SEC
        return DEFAULT_REFUSAL_BACKOFF_SEC
