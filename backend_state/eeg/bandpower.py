"""
Compute theta / alpha / beta bandpower from OpenBCI Cyton + Daisy via BrainFlow.

Uses Welch's method (DataFilter.get_psd_welch) and DataFilter.get_band_power
to integrate the PSD over each band. Reports per-channel power (µV²) and
relative power (% of total 1-45 Hz).

Usage:
    python bandpower.py --port /dev/cu.usbserial-DP05INGN --duration 20

Install:
    pip install brainflow numpy
"""

import argparse
import time
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowError
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
TOTAL_BAND = (1.0, 45.0)  # for relative power normalisation


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Theta/alpha/beta bandpower from Cyton+Daisy")
    p.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    p.add_argument("--duration", type=float, default=20.0, help="Recording duration in seconds (default: 20)")
    p.add_argument("--timeout", type=int, default=15, help="Board ready timeout (default: 15)")
    p.add_argument("--no-filter", action="store_true", help="Skip 50/60 Hz notch and 1-45 Hz bandpass")
    p.add_argument("--mains", type=int, choices=[50, 60], default=60, help="Mains frequency for notch (default: 60)")
    return p.parse_args()


def acquire(port: str, duration: float, timeout: int) -> np.ndarray:
    params = BrainFlowInputParams()
    params.serial_port = port
    params.timeout = timeout

    board = BoardShim(BOARD_ID, params)
    try:
        print(f"Connecting on {port}…")
        board.prepare_session()
        board.start_stream()
        print(f"Streaming for {duration}s…")
        time.sleep(duration)
        data = board.get_board_data()
        board.stop_stream()
        return data
    finally:
        if board.is_prepared():
            board.release_session()


def preprocess(channel_data: np.ndarray, fs: int, mains: int) -> None:
    """In-place detrend + notch + 1-45 Hz bandpass on a single channel."""
    DataFilter.detrend(channel_data, DetrendOperations.LINEAR.value)
    # Notch out mains
    DataFilter.perform_bandstop(
        channel_data, fs, mains - 2.0, mains + 2.0, 4,
        FilterTypes.BUTTERWORTH.value, 0,
    )
    # Bandpass 1-45 Hz
    DataFilter.perform_bandpass(
        channel_data, fs, 1.0, 45.0, 4,
        FilterTypes.BUTTERWORTH.value, 0,
    )


def compute_bandpowers(eeg: np.ndarray, fs: int) -> dict:
    """Returns {channel_index_in_array: {band: (abs_power, rel_power)}}."""
    nfft = DataFilter.get_nearest_power_of_two(fs)  # 128 for fs=125
    overlap = nfft // 2

    if eeg.shape[1] < nfft:
        raise RuntimeError(
            f"Need at least {nfft} samples for Welch (got {eeg.shape[1]}). "
            f"Increase --duration."
        )

    results = {}
    for ch_idx in range(eeg.shape[0]):
        psd = DataFilter.get_psd_welch(
            eeg[ch_idx], nfft, overlap, fs,
            WindowOperations.HANNING.value,
        )
        total = DataFilter.get_band_power(psd, *TOTAL_BAND)
        per_band = {}
        for name, (lo, hi) in BANDS.items():
            absolute = DataFilter.get_band_power(psd, lo, hi)
            relative = absolute / total if total > 0 else 0.0
            per_band[name] = (absolute, relative)
        results[ch_idx] = per_band
    return results


def print_table(results: dict, eeg_channels: list[int]) -> None:
    print("\nBandpower per channel  (absolute µV² | relative %)")
    print("-" * 78)
    header = f"{'CH':>4}  " + "  ".join(f"{b:>20}" for b in BANDS)
    print(header)
    print("-" * 78)
    for ch_idx, board_ch in enumerate(eeg_channels):
        row = f"CH{board_ch:02d}  "
        for band in BANDS:
            absolute, relative = results[ch_idx][band]
            row += f"  {absolute:>10.3f} | {relative * 100:>5.1f}%   "
        print(row)
    print("-" * 78)

    print("\nMean across channels:")
    for band in BANDS:
        abs_vals = [results[i][band][0] for i in results]
        rel_vals = [results[i][band][1] for i in results]
        print(f"  {band:<6} abs={np.mean(abs_vals):8.3f} µV²   "
              f"rel={np.mean(rel_vals) * 100:5.1f}%")


def main() -> None:
    args = parse_args()
    BoardShim.disable_board_logger()

    fs = BoardShim.get_sampling_rate(BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
    print(f"Board: Cyton+Daisy  |  fs={fs} Hz  |  {len(eeg_channels)} EEG channels")

    try:
        raw = acquire(args.port, args.duration, args.timeout)
    except BrainFlowError as exc:
        print(f"BrainFlow error: {exc}")
        raise

    eeg = raw[eeg_channels].copy()  # (n_channels, n_samples)
    print(f"Captured {eeg.shape[1]} samples ({eeg.shape[1] / fs:.2f}s)")

    if not args.no_filter:
        for ch_idx in range(eeg.shape[0]):
            preprocess(eeg[ch_idx], fs, args.mains)

    results = compute_bandpowers(eeg, fs)
    print_table(results, eeg_channels)


if __name__ == "__main__":
    main()
