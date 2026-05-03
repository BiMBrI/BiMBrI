# BiMBrI — Biometric Monitoring for Robotic Intervention

BiMBrI is a real-time robotic intervention system that responds to biometric signals from a wearable monitor.
When a physiological event is detected (e.g. elevated arousal state), a signal is pushed to the robot server,
which triggers a pre-recorded arm movement subroutine.

## System Architecture

$$
\text{Biometric Monitor} \rightarrow \text{POST /trigger} \rightarrow \text{Robot Server} \rightarrow \text{SO-101 Arm}
$$

## States

| State | Description |
|-------|-------------|
| `idle` | Arm is ready, waiting for a trigger |
| `replaying` | Arm is executing a recorded subroutine |

## Subroutines

- **rest** — returns the arm to a neutral resting position
- **aroused** — executes a pick-and-place intervention gesture

## Built at BeaverHacks 2026
