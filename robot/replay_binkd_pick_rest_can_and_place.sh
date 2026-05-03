#!/bin/bash
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM1 \
    --robot.id=polo \
    --dataset.repo_id=binkd/pick_rest_can_and_place \
    --dataset.episode=${1:-0}
