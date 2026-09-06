#!/bin/bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=polo \
    --dataset.repo_id=binkd/rubber-band-test-v1 \
    --dataset.episode=${1:-0}
