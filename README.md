# BiMBrI

Beer me Brain Interface

To view a detailed description visit [here](https://bimbri.github.io/BiMBrI/) or the general
project [writeup](writeup.md). To view a detailed description of the Lerobot setup head to the 
[lerobot](robot/lerobot.md) page.

## Setup

To clone make sure to recurse-submodules:

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
| Robot control | LeRobot, SO-101 leader/follower arms |
| Server | FastAPI + uvicorn |
| Web UI | Server-Sent Events, mistune, MathJax |
| Networking | Tailscale over Eduroam |

## License

© 2026 Nathanael Parra and Nathaniel Chappelle.

Software is released under the [MIT License](LICENSE).
Documentation and written content is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Unless otherwise noted.
