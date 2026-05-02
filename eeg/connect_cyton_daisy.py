"""
BrainFlow connection script for OpenBCI Cyton + Daisy (16-channel EEG).

Usage:
    python connect_cyton_daisy.py --port /dev/ttyUSB0
    python connect_cyton_daisy.py --port COM3          # Windows

Install:
    pip install brainflow
"""

import argparse
import time
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowError
from brainflow.data_filter import DataFilter


BOARD_ID = BoardIds.CYTON_DAISY_BOARD  # 16-channel Cyton + Daisy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream EEG from OpenBCI Cyton + Daisy via BrainFlow")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--timeout", type=int, default=15, help="Board ready timeout in seconds (default: 15)")
    parser.add_argument("--duration", type=float, default=10.0, help="Recording duration in seconds (default: 10)")
    parser.add_argument("--save", metavar="FILE", help="Optional: save raw data to CSV (e.g. data.csv)")
    parser.add_argument("--log", action="store_true", help="Enable BrainFlow verbose logging")
    return parser.parse_args()


def build_params(args: argparse.Namespace) -> BrainFlowInputParams:
    params = BrainFlowInputParams()
    params.serial_port = args.port
    params.timeout = args.timeout
    return params


def print_board_info() -> None:
    fs = BoardShim.get_sampling_rate(BOARD_ID)
    eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
    print(f"Board        : Cyton + Daisy (ID {BOARD_ID})")
    print(f"EEG channels : {len(eeg_channels)}  →  {eeg_channels}")
    print(f"Sample rate  : {fs} Hz")


def stream(board: BoardShim, duration: float) -> np.ndarray:
    fs = BoardShim.get_sampling_rate(BOARD_ID)
    expected_samples = int(fs * duration)

    board.start_stream()
    print(f"\nStreaming for {duration}s  (expecting ~{expected_samples} samples)…")

    time.sleep(duration)

    data = board.get_board_data()
    board.stop_stream()
    return data


def summarise(data: np.ndarray) -> None:
    eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
    fs = BoardShim.get_sampling_rate(BOARD_ID)
    n_samples = data.shape[1]
    print(f"\n--- Summary ({n_samples} samples @ {fs} Hz = {n_samples / fs:.2f}s) ---")
    for ch in eeg_channels:
        ch_data = data[ch]
        print(f"  CH{ch:02d}  mean={ch_data.mean():+.2f} µV  std={ch_data.std():.2f} µV  "
              f"min={ch_data.min():+.2f}  max={ch_data.max():+.2f}")


def main() -> None:
    args = parse_args()

    if args.log:
        BoardShim.enable_dev_board_logger()
    else:
        BoardShim.disable_board_logger()

    print_board_info()

    params = build_params(args)
    board = BoardShim(BOARD_ID, params)

    try:
        print(f"\nConnecting on {args.port}…")
        board.prepare_session()
        print("Session ready.")

        data = stream(board, args.duration)
        summarise(data)

        if args.save:
            DataFilter.write_file(data, args.save, "w")
            print(f"\nData saved to {args.save}")

    except BrainFlowError as exc:
        print(f"\nBrainFlow error: {exc}")
        raise
    finally:
        if board.is_prepared():
            board.release_session()
            print("Session released.")


if __name__ == "__main__":
    main()
