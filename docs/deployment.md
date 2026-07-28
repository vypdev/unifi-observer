# Deployment

UniFi Observer has two supported deployment adapters over the same application layers.

## Native Linux service

Requirements: Linux, Python 3.11+, Git, `systemd --user`, and an interactive terminal for first configuration.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/vypdev/unifi-observer/master/install.sh)"
unifi-observer start
unifi-observer status
```

Installation locations:

- package and virtual environment: `~/.local/share/unifi-observer/`
- CLI link: `~/.local/bin/unifi-observer`
- configuration: `~/.config/unifi-observer/config.env`
- systemd unit: `~/.config/systemd/user/unifi-observer.service`
- installed commit marker: `~/.local/share/unifi-observer/.unifi-observer-commit`

The service defaults to loopback because the native MCP endpoint has no application authentication in the current release. Use an authenticated reverse proxy or a private network if it must be reached remotely.

For automatic start after login, enable the unit and user lingering deliberately:

```bash
systemctl --user enable unifi-observer.service
loginctl enable-linger "$USER"
```

## Native updates

```bash
unifi-observer update
```

The command queries `refs/heads/master`, compares the commit marker, clones a temporary checkout only when necessary, runs setup with configuration skipped, verifies the marker, restarts the service, and checks `systemctl --user is-active`. It does not rotate API keys or certificates.

## Coolify / Docker Compose

The repository includes `Dockerfile` and `docker-compose.yaml`.

1. Create a Compose application from the repository.
2. Set `UNIFI_API_KEY` through Coolify's secret mechanism.
3. Set API mode, base URL, site allow-list, and TLS variables through the runtime environment.
4. Keep `/mcp` private or protect it with an authenticated reverse proxy.
5. Use `/healthz` as the container health check.

The container is read-only, drops all capabilities, uses `no-new-privileges`, and provides `/tmp` as a tmpfs. The container default bind is broad because access control belongs at the Coolify/reverse-proxy boundary; native defaults remain loopback.
