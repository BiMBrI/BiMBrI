# LeRobot Setup — SO-101 Arms

## Install

```bash
conda create -y -n lerobot python=3.10 && conda activate lerobot
git clone https://github.com/Seeed-Projects/lerobot.git ~/lerobot
conda install ffmpeg -c conda-forge
cd ~/lerobot && pip install -e ".[feetech]"
```

## Find Ports

```bash
lerobot-find-port
```

Plug/unplug each arm when prompted. On Linux the follower is typically `/dev/ttyACM0` and the leader `/dev/ttyACM1`. Grant access:

```bash
sudo chmod 666 /dev/ttyACM*
```

## Configure Motors

Run for each arm, connecting one motor at a time as prompted:

```bash
# Follower
lerobot-setup-motors --robot.type=so101_follower --robot.port=/dev/ttyACM0

# Leader
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=/dev/ttyACM1
```

## Calibrate

Move each arm to the middle of its range of motion when prompted, then move each joint through its full range.

```bash
# Follower
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=polo

# Leader
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=marco
```

> If you see `Magnitude XXXX exceeds 2047`, a motor's zero position is off. Manually center that joint and recalibrate.

## Teleoperate

```bash
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=polo \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=marco
```

## Record & Replay Subroutines

Use the provided scripts. During recording:
- **Right arrow** — save episode
- **Escape** — finalize and exit (wait for it to complete before doing anything else)

```bash
# Record a subroutine (requires HuggingFace login: huggingface-cli login)
./record.sh  <hf_username/dataset_name> ""

# Example
./record.sh 1 binkd/pick_and_place "Pick and place"
```

On success, a replay script is generated automatically:

```bash
./replay_binkd_pick_and_place.sh [episode_number]
```
