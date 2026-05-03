"""
Real-time bandpower monitor for OpenBCI Cyton + Daisy.

Streams continuously, computes theta/alpha/beta bandpower on a sliding window,
and emits a code when any band exceeds its threshold:

    1 → theta over theta_thresh
    2 → alpha over alpha_thresh
    3 → beta  over beta_thresh
    0 → none over threshold

If multiple bands cross at once, the band with the largest over-threshold
margin (power / threshold) wins.

Usage:
    python monitor.py --port /dev/ttyUSB0 --alpha-thresh 50
    python monitor.py --port /dev/ttyUSB0 --theta-thresh 40 --alpha-thresh 50 --beta-thresh 30

Programmatic:
    for code, powers in monitor_bandpower(port="/dev/ttyUSB0", alpha_thresh=50):
        if code == 2:
            do_something()
"""

import argparse
import time
from typing import Iterator
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import (
    DataFilter,
    DetrendOperations,
    FilterTypes,
    WindowOperations,
)


BOARD_ID = BoardIds.CYTON_DAISY_BOARD

BANDS = {
    "theta": (4.0, 7.0),
    "alpha": (8.0, 12.0),
    "beta":  (12.0, 30.0),
}
BAND_CODE = {"theta": 1, "alpha": 2, "beta": 3}


def _preprocess(channel_data: np.ndarray, fs: int, mains: int) -> None:
    DataFilter.detrend(channel_data, DetrendOperations.LINEAR.value)
    DataFilter.perform_bandstop(
        channel_data, fs, mains - 2.0, mains + 2.0, 4,
        FilterTypes.BUTTERWORTH.value, 0,
    )
    DataFilter.perform_bandpass(
        channel_data, fs, 1.0, 45.0, 4,
        FilterTypes.BUTTERWORTH.value, 0,
    )


def _bandpower_mean(eeg: np.ndarray, fs: int, nfft: int) -> dict:
    """Mean bandpower across channels for each band (µV²)."""
    overlap = nfft // 2
    accum = {b: 0.0 for b in BANDS}
    for ch in range(eeg.shape[0]):
        psd = DataFilter.get_psd_welch(
            eeg[ch], nfft, overlap, fs, WindowOperations.HANNING.value,
        )
        for name, (lo, hi) in BANDS.items():
            accum[name] += DataFilter.get_band_power(psd, lo, hi)
    n = eeg.shape[0]
    return {b: accum[b] / n for b in BANDS}


def monitor_bandpower(
    port: str,
    theta_thresh: float = float("inf"),
    alpha_thresh: float = float("inf"),
    beta_thresh: float = float("inf"),
    window_sec: float = 2.0,
    update_sec: float = 0.25,
    mains: int = 60,
    apply_filter: bool = True,
    timeout: int = 15,
    duration: float | None = None,
) -> Iterator[tuple[int, dict]]:
    """Stream from the board and yield (code, powers) once per update.

    Args:
        port: serial port, e.g. "/dev/ttyUSB0".
        theta_thresh / alpha_thresh / beta_thresh: µV² thresholds. Defaults
            to +inf so a band only fires if you set its threshold.
        window_sec: sliding-window length used for each PSD.
        update_sec: how often to recompute and yield.
        duration: optional stop time in seconds; runs forever if None.

    Yields:
        (code, powers) where code is 0/1/2/3 and powers is
        {"theta": x, "alpha": y, "beta": z}.
    """
    fs = BoardShim.get_sampling_rate(BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
    nfft = DataFilter.get_nearest_power_of_two(fs)
    win_samples = max(int(window_sec * fs), nfft)

    thresholds = {"theta": theta_thresh, "alpha": alpha_thresh, "beta": beta_thresh}

    params = BrainFlowInputParams()
    params.serial_port = port
    params.timeout = timeout
    board = BoardShim(BOARD_ID, params)

    BoardShim.disable_board_logger()
    board.prepare_session()
    board.start_stream()
    t_start = time.time()

    try:
        # Wait until the buffer has enough samples for one window.
        while board.get_board_data_count() < win_samples:
            time.sleep(0.05)

        while True:
            if duration is not None and (time.time() - t_start) >= duration:
                return

            # Peek at the latest window without consuming the buffer.
            raw = board.get_current_board_data(win_samples)
            eeg = raw[eeg_channels].copy()

            if apply_filter:
                for ch in range(eeg.shape[0]):
                    _preprocess(eeg[ch], fs, mains)

            powers = _bandpower_mean(eeg, fs, nfft)

            # Pick the band most over its threshold (ratio > 1).
            ratios = {b: powers[b] / thresholds[b] if thresholds[b] > 0 else 0.0
                      for b in BANDS}
            triggered = {b: r for b, r in ratios.items() if r > 1.0}
            if triggered:
                winner = max(triggered, key=triggered.get)
                code = BAND_CODE[winner]
            else:
                code = 0

            yield code, powers
            time.sleep(update_sec)
    finally:
        if board.is_prepared():
            board.stop_stream()
            board.release_session()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time theta/alpha/beta monitor")
    p.add_argument("--port", required=True)
    p.add_argument("--theta-thresh", type=float, default=float("inf"))
    p.add_argument("--alpha-thresh", type=float, default=float("inf"))
    p.add_argument("--beta-thresh", type=float, default=float("inf"))
    p.add_argument("--window", type=float, default=2.0, help="Sliding window seconds (default 2.0)")
    p.add_argument("--update", type=float, default=0.25, help="Update period seconds (default 0.25)")
    p.add_argument("--mains", type=int, choices=[50, 60], default=60)
    p.add_argument("--no-filter", action="store_true")
    p.add_argument("--timeout", type=int, default=30, help="Board ready timeout in seconds (default: 30)")
    p.add_argument("--duration", type=float, default=None, help="Stop after N seconds (default: run until Ctrl+C)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    label = {0: "----", 1: "THETA", 2: "ALPHA", 3: "BETA"}

    print(f"Monitoring  thresh: theta={args.theta_thresh}  alpha={args.alpha_thresh}  beta={args.beta_thresh}")
    print(f"{'t (s)':>6}  {'code':>4}  {'band':>5}  "
          f"{'theta µV²':>10}  {'alpha µV²':>10}  {'beta µV²':>10}")
    t0 = time.time()
    try:
        for code, p in monitor_bandpower(
            port=args.port,
            theta_thresh=args.theta_thresh,
            alpha_thresh=args.alpha_thresh,
            beta_thresh=args.beta_thresh,
            window_sec=args.window,
            update_sec=args.update,
            mains=args.mains,
            apply_filter=not args.no_filter,
            timeout=args.timeout,
            duration=args.duration,
        ):
            print(f"{time.time() - t0:6.2f}  {code:>4}  {label[code]:>5}  "
                  f"{p['theta']:>10.3f}  {p['alpha']:>10.3f}  {p['beta']:>10.3f}")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
