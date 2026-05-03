# BiMBrI — Beer Me Brain Interface

BiMBrI is a real-time robotic intervention system that responds to biometric signals from a wearable monitor.
When a physiological event is detected (e.g. elevated arousal state), a signal is pushed to the robot server,
which triggers a pre-recorded arm movement subroutine.

## States

| State | Description |
|-------|-------------|
| `idle` | Arm is ready, waiting for a trigger |
| `replaying` | Arm is executing a recorded subroutine |

## Subroutines

- **rest** — returns the arm to a neutral resting position
- **aroused** — executes a pick-and-place intervention gesture

## System Architecture

$$
\text{Polar H10} \xrightarrow{\text{BLE}} \text{HR Monitor}
\qquad
\text{OpenBCI Cyton+Daisy} \xrightarrow{\text{Serial}} \text{EEG Monitor}
$$

$$
\text{HR Monitor} + \text{EEG Monitor} \xrightarrow{\text{raw streams}} \text{Inference Server}
$$

$$
\text{Inference Server} \xrightarrow{\text{HMM + state estimation}} P(\text{state}_t \mid \text{obs}_{1:t})
$$

$$
P(\text{state}_t) \xrightarrow{\text{POST /trigger on state change}} \text{Robot Server} \xrightarrow{\text{lerobot-replay}} \text{SO-101 Arm}
$$

## Tech Stack

BiMBrI integrates biometric sensing hardware with a robotic arm through a lightweight Python server stack.

### Biometric Sensing

Heart rate is streamed from a Polar H10 chest strap over BLE using `bleak`. EEG is acquired from an
OpenBCI Cyton + Daisy (16-channel) via `brainflow`. Band power (theta, alpha, beta) is computed in
real-time using Welch's method on a sliding window, and thresholded to emit discrete event codes.

### Robot Control

The SO-101 leader/follower arm pair is controlled via [LeRobot](https://github.com/huggingface/lerobot).
Subroutines are recorded through teleoperation, uploaded to Hugging Face, and replayed deterministically. 
The leader arm is used to demonstrate a gesture once; the follower arm replays it on demand.

### Server

A [FastAPI](https://fastapi.tiangolo.com) server bridges the biometric pipeline and the robot. It exposes
POST endpoints (`/trigger_rest`, `/trigger_aroused`) that accept events from the sensing machine and
dispatch the appropriate replay subroutine as an async subprocess. A live web UI is served from the same
process, updating via Server-Sent Events without polling.

### Networking

The biometric client and robot server communicate over [Tailscale](https://tailscale.com), which tunnels
through Eduroam's client isolation policy using WireGuard.

## Built at BeaverHacks 2026
