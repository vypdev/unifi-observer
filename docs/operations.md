# Operations

## Service lifecycle

```bash
unifi-observer start
unifi-observer stop
unifi-observer restart
unifi-observer status
```

The CLI delegates lifecycle operations to `systemctl --user` and refuses to operate before the native unit has been configured.

## Health checks

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
```

Use the configured host and port when they differ from the defaults.

## Logs

For the native service:

```bash
journalctl --user -u unifi-observer.service -f
```

The installer and CLI provide human-friendly colored output in a TTY and plain output when redirected. Set `NO_COLOR=1` or `UNIFI_OBSERVER_ASCII=1` for automation and restricted terminals.

## Troubleshooting

### Service is not active

```bash
unifi-observer status
systemctl --user status unifi-observer.service --no-pager
journalctl --user -u unifi-observer.service -n 100 --no-pager
```

### TLS failure in local mode

Confirm that the hostname in `UNIFI_API_BASE_URL` matches a certificate SAN, that `UNIFI_CA_CERT_PATH` points to the generated CA, and that the UniFi console has completed certificate activation. Do not solve a local certificate problem by permanently disabling TLS verification.

### MCP client cannot connect

Check the bind address, reverse-proxy route, firewall/private-network policy, and `/healthz` before testing `/mcp`. After changing Hermes tool configuration, start a fresh session so the toolset is reloaded.

### Update failed

The updater reports whether failure occurred while querying Git, downloading, installing, verifying the marker, restarting, or checking service activity. If installation fails before restart, the existing running service is not intentionally stopped. Inspect the native service and rerun after correcting the underlying issue.
