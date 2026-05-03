"""
Connect to a Polar BLE heart rate sensor (H10, H9, H7, Verity Sense) and
stream beats per minute via the standard BLE Heart Rate Service.

Usage:
    python connect_polar.py                           # auto-discover any Polar
    python connect_polar.py --name "Polar H10 12345678"
    python connect_polar.py --duration 30 --save hr.csv

Install:
    pip install bleak

macOS note:
    Grant Bluetooth permission to your terminal/Python in
    System Settings → Privacy & Security → Bluetooth on first run.
    Devices are addressed by opaque CoreBluetooth UUIDs, not MACs, so we
    discover by name.
"""

import argparse
import asyncio
import csv
import time
from contextlib import suppress
from typing import AsyncIterator, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice


# Standard BLE Heart Rate Measurement characteristic (org.bluetooth.characteristic.heart_rate_measurement).
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stream HR from a Polar BLE sensor")
    p.add_argument("--name", help="Substring of device name to match (default: any 'Polar')")
    p.add_argument("--duration", type=float, default=None, help="Stop after N seconds (default: until Ctrl+C)")
    p.add_argument("--save", metavar="FILE", help="Append HR samples to CSV (timestamp_ns,bpm,rr_ms)")
    p.add_argument("--scan-timeout", type=float, default=10.0)
    return p.parse_args()


async def find_polar(name_substr: Optional[str], scan_timeout: float) -> BLEDevice:
    needle = (name_substr or "Polar").lower()
    print(f"Scanning for BLE device matching '{needle}'…")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _adv: d.name is not None and needle in d.name.lower(),
        timeout=scan_timeout,
    )
    if device is None:
        raise RuntimeError(f"No Polar device matching '{needle}' found within {scan_timeout}s")
    print(f"Found: {device.name}  ({device.address})")
    return device


def parse_hr_measurement(data: bytes) -> tuple[int, list[int]]:
    """Decode a BLE Heart Rate Measurement notification.

    Layout (Bluetooth SIG spec, GATT 0x2A37):
        flags (uint8): bit0 = HR uint16 (else uint8); bit4 = RR present
        HR value (uint8 or uint16 LE)
        [energy expended uint16 LE]  (skipped if present)
        [RR intervals: uint16 LE each, units of 1/1024 s]

    Returns (bpm, rr_intervals_ms).
    """
    flags = data[0]
    hr_uint16 = flags & 0x01
    energy_present = (flags >> 3) & 0x01
    rr_present = (flags >> 4) & 0x01

    i = 1
    if hr_uint16:
        bpm = int.from_bytes(data[i:i + 2], "little")
        i += 2
    else:
        bpm = data[i]
        i += 1

    if energy_present:
        i += 2  # uint16 kJ, ignored

    rr_ms: list[int] = []
    if rr_present:
        while i + 1 < len(data):
            rr_1024 = int.from_bytes(data[i:i + 2], "little")
            rr_ms.append(round(rr_1024 * 1000 / 1024))
            i += 2

    return bpm, rr_ms


async def monitor_hr(
    threshold: int = 100,
    name: Optional[str] = None,
    scan_timeout: float = 10.0,
    duration: Optional[float] = None,
) -> AsyncIterator[tuple[int, int]]:
    """Connect to a Polar HR sensor and yield (code, bpm) per heartbeat.

    Args:
        threshold: BPM threshold; code = 1 when bpm >= threshold else 0.
        name: substring of the device name (default: any 'Polar').
        scan_timeout: BLE scan timeout in seconds.
        duration: optional stop time in seconds; runs until cancelled if None.

    Yields:
        (code, bpm) per heartbeat notification.

    Usage:
        async for code, bpm in monitor_hr(threshold=100):
            if code == 1:
                do_something()
    """
    device = await find_polar(name, scan_timeout)
    queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue()

    def on_notify(_handle: int, data: bytearray) -> None:
        bpm, _rr = parse_hr_measurement(bytes(data))
        code = 1 if bpm >= threshold else 0
        queue.put_nowait((code, bpm))

    async with BleakClient(device) as client:
        await client.start_notify(HR_MEASUREMENT_UUID, on_notify)
        t_start = asyncio.get_event_loop().time()
        try:
            while True:
                if duration is not None:
                    remaining = duration - (asyncio.get_event_loop().time() - t_start)
                    if remaining <= 0:
                        return
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=remaining)
                    except asyncio.TimeoutError:
                        return
                else:
                    item = await queue.get()
                yield item
        finally:
            with suppress(Exception):
                await client.stop_notify(HR_MEASUREMENT_UUID)


async def stream_hr(client: BleakClient, save_path: Optional[str], stop: asyncio.Event) -> None:
    fh = open(save_path, "a", newline="") if save_path else None
    writer = csv.writer(fh) if fh else None
    if writer and fh.tell() == 0:
        writer.writerow(["timestamp_ns", "bpm", "rr_ms"])

    def on_notify(_handle: int, data: bytearray) -> None:
        t_ns = time.time_ns()
        bpm, rr_list = parse_hr_measurement(bytes(data))
        # Each notification carries one HR value plus 0..N RR samples.
        rr_str = ",".join(str(r) for r in rr_list) if rr_list else "-"
        print(f"HR  {bpm:>3} bpm   rr={rr_str:<14} t={t_ns}")
        if writer:
            if rr_list:
                for rr in rr_list:
                    writer.writerow([t_ns, bpm, rr])
            else:
                writer.writerow([t_ns, bpm, ""])

    try:
        await client.start_notify(HR_MEASUREMENT_UUID, on_notify)
        await stop.wait()
    finally:
        with suppress(Exception):
            await client.stop_notify(HR_MEASUREMENT_UUID)
        if fh:
            fh.close()


async def run(args: argparse.Namespace) -> None:
    device = await find_polar(args.name, args.scan_timeout)
    stop = asyncio.Event()

    async with BleakClient(device) as client:
        print(f"Connected: {client.is_connected}")

        streamer = asyncio.create_task(stream_hr(client, args.save, stop))

        try:
            if args.duration is not None:
                await asyncio.sleep(args.duration)
            else:
                await asyncio.Event().wait()
        finally:
            stop.set()
            await streamer


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
