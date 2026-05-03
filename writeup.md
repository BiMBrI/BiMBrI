# BiMBrI — Beer Me Brain Interface

BiMBrI is a real-time robotic intervention system that responds to biometric signals from a wearable monitor.
When a physiological event is detected (e.g. elevated arousal state), a signal is pushed to the robot server,
which triggers a pre-recorded arm movement subroutine. 

From a thousand foot view, BiMBrI backend is a set of biomarker tools, with a multimodal logic layer on top. This backend passes bio-state information to a front end that acts as a control plane for robotic arms.
## States

| State | Description |
|-------|-------------|
| `idle` | Arm is ready, waiting for a trigger |
| `replaying` | Arm is executing a recorded subroutine |

## Data Set

EEG recording dataset found 
[here](https://ieee-dataport.org/open-access/regulation-arousal-online-neurofeedback-improves-human-performance-demanding-sensory), 
pertinent to the binary task of arousal and no arousal, where arousal is heightened activity and energy (Joseph Faler, 2019).

Robot movement dataset found [here](https://huggingface.co/binkd/datasets) (Nathaniel Chappelle, 2026).

## Subroutines

- **rest** — places an energy drink within reach of the user
- **aroused** — places an *exciting* beverage within reach of the user

## System Architecture

$$
\text{Polar H10} \xrightarrow{\text{BLE}} \text{HR Monitor}
\qquad
\text{OpenBCI Cyton+Daisy} \xrightarrow{\text{Serial}} \text{EEG Monitor}
$$

$$
\text{HR Monitor} + \text{EEG Monitor} \xrightarrow{\text{threshold codes}} \text{DST Adapters} \xrightarrow{\text{per-source } m(\cdot)} \text{Dempster's Rule}
$$

$$
\text{Dempster's Rule} \xrightarrow{\text{fused mass } m_{\oplus}} \text{HMM Forward Filter} \xrightarrow{} P(\text{state}_{t} \mid \text{obs}_{{1:t}})
$$

$$
\text{argmax}\,P(\text{state}_t) \xrightarrow{\text{POST }/\text{trigger_rest},/\text{trigger_aroused}\text{ on state change}} \text{Robot Server} \xrightarrow{\text{lerobot-replay}} \text{SO-101 Arm}
$$

## Tech Stack

BiMBrI integrates biometric sensing hardware with a robotic arm through a lightweight Python server stack.

### Biometric Sensing

Heart rate is streamed from a Polar H10 chest strap over BLE using `bleak`. EEG is acquired from an
OpenBCI Cyton + Daisy (16-channel) via `brainflow`. Band power (theta, alpha, beta) is computed in
real-time using Welch's method on a sliding window, and thresholded to emit discrete event codes.

### Inference & State Estimation

The `backend_state/` package implements the math layer that turns biomarker codes
into a posterior over `{rest, arousal, null}`.

Each source's threshold code is mapped to a Dempster-Shafer mass function over
the frame of discernment $\Theta = \{\text{rest}, \text{arousal}, \text{null}\}$
with an explicit ignorance slot $m(\Theta)$. Before fusion, each source is
discounted by sample age, $\alpha = \exp(-\Delta t / \tau)$, so a stale or dead
sensor gracefully fades to total ignorance instead of pinning the fused belief
on a dead reading. The discounted masses are then combined via Dempster's rule;
on total conflict the layer falls back to ignorance rather than crashing the
real-time loop.

The combined mass yields a pignistic probability vector
$\text{Bet}P = (P(\text{rest}), P(\text{arousal}), P(\text{null}))$ which is
fed as a soft emission likelihood into a 3-state hidden Markov model:

$$
\text{belief}_t \propto (T^{\!\top} \cdot \text{belief}_{t-1}) \odot \text{Bet}P_t
$$

The hand-tuned transition matrix encodes one prior fact-- a direct
rest $\leftrightarrow$ arousal jump is unlikely -- while leaving
all other intra-row transitions a priori equally likely. The initial belief
asserts certainty in `null`, matching "the system has just started, nothing
observed yet".

A small dispatcher (`webapp.py`) watches the argmax-ed posterior and, on a
state *change*, POSTs to the robot server's `/trigger_rest` or
`/trigger_aroused` endpoint. The `null` state advances the tracked state but
sends no request. When the server refuses a trigger -- either mid-replay or
during the 25s post-replay cooldown, signalled as `{"ok": false}` -- the
dispatcher holds the refused state as *pending*, queries the `/state`
endpoint to learn the exact `cooldown_remaining`, and waits that long before
retrying exactly once. A fresh state from the HMM in the meantime supersedes
the pending retry: reverting to the last-delivered state cancels it,
`null` cancels it, and a different non-null state replaces it. Connection
errors use a short fixed backoff so the next HMM tick can retry quickly
without hammering an unreachable server.

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
