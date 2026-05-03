"""
Dispatcher layer that turns HMM state into web-app calls.

The robot server (`robot/server/server.py`) exposes two endpoints:

    POST /trigger_rest      -> run the rest subroutine
    POST /trigger_aroused   -> run the aroused subroutine

It returns 409 if the arm is already replaying, and 2xx on accept.
There is no endpoint for the `null` HMM state -- that one updates the
tracked last-state but sends nothing.

Notifications are edge-triggered: a POST fires only when the HMM-
reported state differs from the previously-delivered state, so a 4 Hz
HMM tick does not turn into 4 Hz of robot triggers. Connection errors
do not advance the tracked state, so the next tick retries; HTTP
status responses (including 409) do, so we don't hammer a busy arm.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

ENDPOINTS = {
    "rest": "/trigger_rest",
    "arousal": "/trigger_aroused",
}


class WebAppNotifier:
    """Edge-triggered HMM-state -> web-app dispatcher."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        initial_state: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._last_state: Optional[str] = initial_state

    @property
    def last_state(self) -> Optional[str]:
        return self._last_state

    def reset(self, state: Optional[str] = None) -> None:
        """Clear (or set) the tracked last-state.

        After `reset()` with no argument the next `notify` call always
        fires regardless of the new state.
        """
        self._last_state = state

    def notify(
        self,
        state: str,
        *,
        payload: Optional[dict] = None,
    ) -> bool:
        """Notify the web app if `state` differs from the last delivered state.

        Returns True iff a POST was sent and accepted (2xx). 409 (robot
        busy) is treated as delivered: last-state is advanced and we do
        not retry on the next tick. Connection failures are not
        delivered: last-state is left untouched so the next tick retries.
        """
        if state not in ("rest", "arousal", "null"):
            raise ValueError(f"unknown state {state!r}")

        if state == self._last_state:
            return False

        prev = self._last_state

        if state == "null":
            self._last_state = state
            return False

        body = {"event": "state_change", "from": prev, "to": state}
        if payload:
            body.update(payload)

        delivered, ok = self._post(ENDPOINTS[state], body)
        if delivered:
            self._last_state = state
        return ok

    def _post(self, path: str, body: dict) -> tuple[bool, bool]:
        """POST `body` as JSON to `base_url + path`.

        Returns (delivered, accepted) where:
          - delivered=True means the server responded (any HTTP status),
            so the caller should advance state and not retry.
          - accepted=True means a 2xx response.
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
                if 200 <= status < 300:
                    return True, True
                logger.warning("POST %s -> %s", url, status)
                return True, False
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                logger.info("POST %s -> 409 (robot busy)", url)
            else:
                logger.warning("POST %s -> %s %s", url, exc.code, exc.reason)
            return True, False
        except urllib.error.URLError as exc:
            logger.warning("POST %s failed: %s", url, exc.reason)
            return False, False
        except OSError as exc:
            logger.warning("POST %s failed: %s", url, exc)
            return False, False
