#!/bin/bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=polo \
    --dataset.repo_id=binkd/pick_aroused_can_and_place_toyota_v1 \
    --dataset.episode=${1:-0}
