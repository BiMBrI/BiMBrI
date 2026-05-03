"""
Single-script controller for the BiMBrI biomarker pipeline.

Starts the selected sensor streamers (`backend_state.eeg.monitor` for the
OpenBCI Cyton+Daisy, `backend_state.polar.connect_polar` for a Polar BLE
HR sensor), fuses their threshold codes through Dempster-Shafer
combination (`dst`) and the HMM forward filter (`hmm`), and dispatches
state changes to the robot web app (`webapp`). Live logs are printed
once per tick so you can see exactly what is being sent.

Usage:
    python -m backend_state.controller \
        --eeg --eeg-port /dev/cu.usbserial-DP05INGN --eeg-alpha-thresh 20 \
        --polar --polar-threshold 100 \
        --webapp-url http://localhost:8000 \
        --tick 0.5 --tau 5.0

Omit --webapp-url for a dry run (no POSTs, just logs).
python -m backend_state.controller \
        --eeg --eeg-port /dev/cu.usbserial-DP05INGN --eeg-alpha-thresh 20 \
        --polar --polar-threshold 100 \
        --tick 0.5 --tau 5.0
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Callable, Optional

from .adapters import bandpower_mass, heart_rate_mass, resp_rate_mass
from .dst import IGNORANCE, Mass, combine, discount, trust_from_age
from .hmm import HMM
from .webapp import WebAppNotifier


BAND_LABEL = {0: "----", 1: "THETA", 2: "ALPHA", 3: "BETA"}


@dataclass
class Slot:
    """Latest sample from one source. Lock-protected for the main thread."""

    code: Optional[int] = None
    ts: Optional[float] = None
    extra: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, code: int, ts: float, extra: dict) -> None:
        with self._lock:
            self.code = code
            self.ts = ts
            self.extra = extra

    def snapshot(self) -> tuple[Optional[int], Optional[float], dict]:
        with self._lock:
            return self.code, self.ts, dict(self.extra)


class EEGWorker(threading.Thread):
    def __init__(
        self,
        monitor_fn: Callable,
        slot: Slot,
        stop_event: threading.Event,
        kwargs: dict,
    ) -> None:
        super().__init__(name="eeg-worker", daemon=True)
        self._monitor_fn = monitor_fn
        self._slot = slot
        self._stop_event = stop_event
        self._kwargs = kwargs

    def run(self) -> None:
        gen = self._monitor_fn(**self._kwargs)
        try:
            for code, powers in gen:
                if self._stop_event.is_set():
                    break
                self._slot.update(code, time.monotonic(), powers)
        except Exception as exc:
            print(f"[eeg] worker error: {exc!r}", file=sys.stderr, flush=True)
            self._stop_event.set()
        finally:
            with suppress(Exception):
                gen.close()


class PolarWorker(threading.Thread):
    def __init__(
        self,
        monitor_fn: Callable,
        slot: Slot,
        stop_event: threading.Event,
        kwargs: dict,
    ) -> None:
        super().__init__(name="polar-worker", daemon=True)
        self._monitor_fn = monitor_fn
        self._slot = slot
        self._stop_event = stop_event
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:
            print(f"[polar] worker error: {exc!r}", file=sys.stderr, flush=True)
            self._stop_event.set()

    async def _main(self) -> None:
        ait = self._monitor_fn(**self._kwargs).__aiter__()
        try:
            while not self._stop_event.is_set():
                try:
                    code, bpm = await asyncio.wait_for(ait.__anext__(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except StopAsyncIteration:
                    break
                self._slot.update(code, time.monotonic(), {"bpm": bpm})
        finally:
            with suppress(Exception):
                await ait.aclose()


def _format_eeg(snap: tuple[Optional[int], Optional[float], dict]) -> str:
    code, _ts, extra = snap
    if code is None:
        return "eeg=---"
    label = BAND_LABEL.get(code, "?")
    return (f"eeg={code}({label} θ={extra.get('theta', 0):.1f} "
            f"α={extra.get('alpha', 0):.1f} β={extra.get('beta', 0):.1f})")


def _format_polar(snap: tuple[Optional[int], Optional[float], dict]) -> str:
    code, _ts, extra = snap
    if code is None:
        return "hr=---"
    return f"hr={code}({extra.get('bpm', '?')}bpm)"


def _format_resp(snap: tuple[Optional[int], Optional[float], dict]) -> str:
    code, _ts, extra = snap
    if code is None:
        return "resp=---"
    return f"resp={code}({extra.get('bpm', '?')}bpm)"


def _classify_notify(
    state: str,
    prev_last: Optional[str],
    accepted: bool,
    notifier: WebAppNotifier,
) -> str:
    if state == "null":
        return "silent"
    if state == prev_last:
        return "stale"
    if accepted:
        return "ok"
    if notifier.pending_state == state:
        return "refused(retry)"
    return "fail"


def run_loop(
    *,
    eeg_slot: Optional[Slot],
    polar_slot: Optional[Slot],
    resp_slot: Optional[Slot],
    notifier: Optional[WebAppNotifier],
    hmm: HMM,
    tick_sec: float,
    tau_sec: float,
    stop_event: threading.Event,
) -> None:
    t0 = time.monotonic()
    required = [(name, slot) for name, slot in
                (("eeg", eeg_slot), ("polar", polar_slot), ("resp", resp_slot))
                if slot is not None]
    all_connected = False
    while not stop_event.is_set():
        now = time.monotonic()

        eeg_snap = eeg_slot.snapshot() if eeg_slot else None
        polar_snap = polar_slot.snapshot() if polar_slot else None
        resp_snap = resp_slot.snapshot() if resp_slot else None

        if not all_connected:
            snaps = {"eeg": eeg_snap, "polar": polar_snap, "resp": resp_snap}
            missing = [name for name, slot in required
                       if snaps[name] is None or snaps[name][0] is None]
            if missing:
                print(f"[t={now - t0:7.2f}s] waiting for: {', '.join(missing)}",
                      flush=True)
                stop_event.wait(tick_sec)
                continue
            all_connected = True
            print(f"[t={now - t0:7.2f}s] all sources connected, starting fusion.",
                  flush=True)

        masses: list[Mass] = []
        if eeg_snap and eeg_snap[0] is not None:
            age = now - eeg_snap[1]
            masses.append(discount(bandpower_mass(eeg_snap[0]),
                                   trust_from_age(age, tau_sec)))
        if polar_snap and polar_snap[0] is not None:
            age = now - polar_snap[1]
            masses.append(discount(heart_rate_mass(polar_snap[0]),
                                   trust_from_age(age, tau_sec)))
        if resp_snap and resp_snap[0] is not None:
            age = now - resp_snap[1]
            masses.append(discount(resp_rate_mass(resp_snap[0]),
                                   trust_from_age(age, tau_sec)))

        if not masses:
            stop_event.wait(tick_sec)
            continue

        combined = combine(masses)
        belief, state = hmm.step(combined)

        if notifier is not None:
            prev_last = notifier.last_state
            accepted = notifier.notify(state)
            outcome = _classify_notify(state, prev_last, accepted, notifier)
        else:
            outcome = "no-webapp"

        parts = [f"[t={now - t0:7.2f}s]"]
        if eeg_slot is not None:
            parts.append(_format_eeg(eeg_snap))
        if polar_slot is not None:
            parts.append(_format_polar(polar_snap))
            hr_bpm = polar_snap[2].get("bpm", "?") if polar_snap else "?"
            parts.append(f"hr_bpm={hr_bpm}")
        if resp_slot is not None:
            parts.append(_format_resp(resp_snap))
            br_bpm = resp_snap[2].get("bpm", "?") if resp_snap else "?"
            parts.append(f"br_bpm={br_bpm}")
        parts.append(f"| m=(r{combined.rest:.2f} a{combined.arousal:.2f} "
                     f"n{combined.null:.2f} θ{combined.theta:.2f})")
        parts.append(f"p=(r{belief[0]:.2f} a{belief[1]:.2f} n{belief[2]:.2f})")
        parts.append(f"state={state} notify={outcome}")
        print(" ".join(parts), flush=True)

        stop_event.wait(tick_sec)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="BiMBrI controller: stream sensors, fuse via DST+HMM, "
                    "dispatch to the robot web app.",
    )

    eeg = p.add_argument_group("EEG (OpenBCI Cyton+Daisy)")
    eeg.add_argument("--eeg", action="store_true", help="Enable EEG bandpower source.")
    eeg.add_argument("--eeg-port", help="Serial port for the Cyton+Daisy (required if --eeg).")
    eeg.add_argument("--eeg-theta-thresh", type=float, default=float("inf"))
    eeg.add_argument("--eeg-alpha-thresh", type=float, default=float("inf"))
    eeg.add_argument("--eeg-beta-thresh", type=float, default=float("inf"))
    eeg.add_argument("--eeg-window", type=float, default=2.0,
                     help="Sliding window seconds (default 2.0).")
    eeg.add_argument("--eeg-update", type=float, default=0.25,
                     help="Update period seconds (default 0.25).")
    eeg.add_argument("--eeg-mains", type=int, choices=[50, 60], default=60)
    eeg.add_argument("--eeg-no-filter", action="store_true")
    eeg.add_argument("--eeg-timeout", type=int, default=30)

    polar = p.add_argument_group("Polar HR sensor")
    polar.add_argument("--polar", action="store_true", help="Enable Polar HR source.")
    polar.add_argument("--polar-name", default="Polar H10",
                       help="Substring of BLE device name (default: 'Polar H10').")
    polar.add_argument("--polar-threshold", type=int, default=100,
                       help="BPM threshold for code=1 (default 100).")
    polar.add_argument("--polar-scan-timeout", type=float, default=10.0)

    polar.add_argument("--resp-high-threshold", type=float, default=24.0,
                   help="Resp rate upper threshold in bpm for code=1 (default 24).")
    polar.add_argument("--resp-low-threshold", type=float, default=8.0,
                   help="Resp rate lower threshold in bpm for code=2 (default 8).")

    fusion = p.add_argument_group("Fusion + HMM")
    fusion.add_argument("--tick", type=float, default=0.5,
                        help="HMM tick period in seconds (default 0.5).")
    fusion.add_argument("--tau", type=float, default=5.0,
                        help="Trust decay constant in seconds (default 5.0).")

    web = p.add_argument_group("Web app")
    web.add_argument("--webapp-url",
                     help="Robot server base URL (e.g. http://localhost:8000). "
                          "Omit for dry-run (no POSTs).")
    web.add_argument("--webapp-timeout", type=float, default=2.0)

    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.eeg or args.polar):
        sys.exit("error: enable at least one source with --eeg and/or --polar")
    if args.eeg and not args.eeg_port:
        sys.exit("error: --eeg requires --eeg-port")

    stop_event = threading.Event()
    workers: list[threading.Thread] = []
    eeg_slot: Optional[Slot] = None
    polar_slot: Optional[Slot] = None
    resp_slot: Optional[Slot] = None

    if args.eeg:
        try:
            from .eeg.monitor import monitor_bandpower
        except ImportError as exc:
            sys.exit(f"error: --eeg requires brainflow ({exc})")
        eeg_slot = Slot()
        workers.append(EEGWorker(
            monitor_bandpower, eeg_slot, stop_event,
            kwargs=dict(
                port=args.eeg_port,
                theta_thresh=args.eeg_theta_thresh,
                alpha_thresh=args.eeg_alpha_thresh,
                beta_thresh=args.eeg_beta_thresh,
                window_sec=args.eeg_window,
                update_sec=args.eeg_update,
                mains=args.eeg_mains,
                apply_filter=not args.eeg_no_filter,
                timeout=args.eeg_timeout,
            ),
        ))

    if args.polar:
        try:
            from .polar.connect_polar import monitor_hr, monitor_resp
        except ImportError as exc:
            sys.exit(f"error: --polar requires bleak ({exc})")
        polar_slot = Slot()
        workers.append(PolarWorker(
            monitor_hr, polar_slot, stop_event,
            kwargs=dict(
                threshold=args.polar_threshold,
                name=args.polar_name,
                scan_timeout=args.polar_scan_timeout,
            ),
        ))

        resp_slot = Slot()
        workers.append(PolarWorker(
            monitor_resp, resp_slot, stop_event,
            kwargs=dict(
                high_threshold=args.resp_high_threshold,
                low_threshold=args.resp_low_threshold,
                name=args.polar_name,
                scan_timeout=args.polar_scan_timeout,
            ),
        ))

    notifier = (WebAppNotifier(args.webapp_url, timeout=args.webapp_timeout)
                if args.webapp_url else None)

    hmm = HMM()

    enabled = []
    if args.eeg:
        enabled.append(f"eeg(port={args.eeg_port})")
    if args.polar:
        enabled.append(f"polar(thr={args.polar_threshold})")
    print(f"Starting: {', '.join(enabled)}  tick={args.tick}s tau={args.tau}s "
          f"webapp={args.webapp_url or 'DRY-RUN'}", flush=True)

    for w in workers:
        w.start()

    try:
        run_loop(
            eeg_slot=eeg_slot,
            polar_slot=polar_slot,
            resp_slot=resp_slot,
            notifier=notifier,
            hmm=hmm,
            tick_sec=args.tick,
            tau_sec=args.tau,
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        stop_event.set()
        for w in workers:
            w.join(timeout=5.0)
        print("Stopped.", flush=True)


if __name__ == "__main__":
    main()
