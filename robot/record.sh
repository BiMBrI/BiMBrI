#!/bin/bash

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <num_episodes> <repo_id> <task>"
    echo "  num_episodes  Number of episodes to record (e.g. 5)"
    echo "  repo_id       HuggingFace repo id (e.g. binkd/pick_and_place)"
    echo "  task          Task description (e.g. \"Pick and place\")"
    exit 1
fi

NUM_EPISODES=$1
REPO_ID=$2
TASK=$3

lerobot-record \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=polo \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=marco \
    --dataset.repo_id="$REPO_ID" \
    --dataset.num_episodes="$NUM_EPISODES" \
    --dataset.single_task="$TASK" \
    --dataset.push_to_hub=true

if [ $? -eq 0 ]; then
    REPLAY_SCRIPT="replay_${REPO_ID//\//_}.sh"
    cat > "$REPLAY_SCRIPT" <<EOF
#!/bin/bash
lerobot-replay \\
    --robot.type=so101_follower \\
    --robot.port=/dev/ttyACM0 \\
    --robot.id=polo \\
    --dataset.repo_id=$REPO_ID \\
    --dataset.episode=\${1:-0}
EOF
    chmod +x "$REPLAY_SCRIPT"
    echo "Replay script generated: $REPLAY_SCRIPT"
    echo "Usage: ./$REPLAY_SCRIPT [episode_number]"
fi
