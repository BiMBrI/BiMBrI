# BiMBrI

Beer me Brain Interface

To view a detailed description of the models, architecture, and robotics visit 
[here](https://bimbri.github.io/BiMBrI/) or the general project [writeup](writeup.md).

To view a detailed description of the how to setup Lerobot vist [lerobot](robot/lerobot.md).

It should be relatively self explanatory on how to run this software yourself, but since
it requires a good amount of specialized hardware please do not expect a step by step guide.

Robot movement datasets found [here](https://huggingface.co/binkd/datasets) (Nathaniel Chappelle, 2026).

EEG recording dataset found 
[here](https://ieee-dataport.org/open-access/regulation-arousal-online-neurofeedback-improves-human-performance-demanding-sensory)
(Joseph Faller, 2019).

## Setup

To clone make sure to recurse-submodules in order to receive the Lerobot scripts:

```
git clone --recurse-submodules <url>
```

If already cloned

```
git submodule update --init --recursive
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Heart rate | Polar H10 + `bleak` (BLE) |
| EEG | OpenBCI Cyton + Daisy + `brainflow` |
| Inference | Dempster-Shafer combination + HMM forward filter (`backend_state/`) |
| Robot control | LeRobot, SO-101 leader/follower arms |
| Server | FastAPI + uvicorn |
| Web UI | Server-Sent Events, mistune, MathJax |
| Networking | Tailscale over Eduroam |

## License

© 2026 Nathanael Parra and Nathaniel Chappelle.

Software is released under the [MIT License](LICENSE).
Documentation and written content is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Unless otherwise noted.
