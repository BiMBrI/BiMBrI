# Webserver to Control Arm

To run:

```sh
pip install fastapi uvicorn mistune
uvicorn server:app --host 0.0.0.0 --port 8000
```

To trigger arm (one event type currently):

```sh
# For rest
curl -X POST http://<robot-ip>:8000/trigger_rest -H "Content-Type: application/json" -d '{"event": "threshold_exceeded"}'

# For arousal
curl -X POST http://<robot-ip>:8000/trigger_arousal -H "Content-Type: application/json" -d '{"event": "threshold_exceeded"}'
```

## Networking (Eduroam)

Eduroam blocks peer-to-peer traffic between devices, so direct LAN communication between the biometrics client and the robot server won't work. We use [Tailscale](https://tailscale.com) to create a private VPN tunnel between machines.

### Setup:

**Note**: Fedora and Void are assumed as that's what we used.

On the robot server (Fedora):
```bash
sudo systemctl enable --now tailscaled
sudo tailscale up
```

On the biometrics client (or any remote machine):
```bash
# Void Linux
sudo xbps-install tailscale
sudo ln -s /etc/sv/tailscaled /var/service/
sudo tailscale up
```

Once both machines are connected, use the robot's Tailscale IP to send events:
```bash
curl -X POST http://fedora:8000/trigger \
  -H "Content-Type: application/json" \
  -d '{"event": "threshold_exceeded"}'
```
