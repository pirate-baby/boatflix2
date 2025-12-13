# qBittorrent VPN - ARM64 Compatible

This is an ARM64-compatible Docker image that runs qBittorrent with built-in VPN support (OpenVPN or WireGuard). Based on [DyonR/docker-qbittorrentvpn](https://github.com/DyonR/docker-qbittorrentvpn) with modifications for Raspberry Pi 5 / ARM64.

## Features

- qBittorrent torrent client with WebUI
- Built-in OpenVPN and WireGuard support
- iptables killswitch to prevent IP leaks
- ARM64/aarch64 native support (Raspberry Pi 4/5)
- Health check with automatic container restart on VPN failure

## Building the Image

### On the Raspberry Pi (native build):
```bash
docker build -t qbittorrentvpn:arm64 ./qbittorrentvpn
```

### Cross-compile from x86 (using buildx):
```bash
# Set up buildx if not already done
docker buildx create --name mybuilder --use
docker buildx inspect --bootstrap

# Build for ARM64
docker buildx build --platform linux/arm64 -t qbittorrentvpn:arm64 --load ./qbittorrentvpn
```

**Note:** Building on the Pi takes significant time (~30-60 minutes) due to compiling libtorrent and qBittorrent from source. Consider using buildx on a more powerful machine.

## VPN Setup

### OpenVPN
1. Download your VPN provider's OpenVPN configuration file (.ovpn)
2. Place it in `./configs/qbittorrentvpn/openvpn/`
3. Set `VPN_TYPE=openvpn` in environment
4. Set `VPN_USERNAME` and `VPN_PASSWORD` if required

### WireGuard
1. Get your WireGuard configuration from your VPN provider
2. Save it as `wg0.conf` in `./configs/qbittorrentvpn/wireguard/`
3. Set `VPN_TYPE=wireguard` in environment

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VPN_ENABLED` | `yes` | Enable/disable VPN |
| `VPN_TYPE` | `openvpn` | `openvpn` or `wireguard` |
| `VPN_USERNAME` | - | VPN username (OpenVPN) |
| `VPN_PASSWORD` | - | VPN password (OpenVPN) |
| `LAN_NETWORK` | - | **Required.** Local network CIDR (e.g., `192.168.1.0/24`) |
| `NAME_SERVERS` | `1.1.1.1,8.8.8.8` | DNS servers to use |
| `PUID` | `99` | User ID for file permissions |
| `PGID` | `100` | Group ID for file permissions |
| `UMASK` | `002` | File permission mask |
| `HEALTH_CHECK_HOST` | `one.one.one.one` | Host to ping for health checks |
| `HEALTH_CHECK_INTERVAL` | `300` | Seconds between health checks |
| `RESTART_CONTAINER` | `yes` | Restart on health check failure |
| `ENABLE_SSL` | `no` | Enable HTTPS for WebUI |
| `LEGACY_IPTABLES` | `false` | Use legacy iptables |
| `DEBUG` | `false` | Enable debug logging |
| `ADDITIONAL_PORTS` | - | Extra ports to allow through firewall |

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 8080 | TCP | qBittorrent WebUI |
| 8999 | TCP/UDP | BitTorrent listening port |

## Volumes

| Container Path | Description |
|----------------|-------------|
| `/config` | qBittorrent config and VPN configs |
| `/downloads` | Download directory |

## Troubleshooting

### Container exits immediately
- Check logs: `docker logs qbittorrentvpn`
- Ensure VPN config file is present in the correct location
- Verify `LAN_NETWORK` is set correctly

### VPN not connecting
- Check your VPN credentials
- Ensure the .ovpn file is valid
- Try setting `DEBUG=true` for more verbose logging
- For WireGuard, ensure the config is named exactly `wg0.conf`

### WebUI not accessible
- Ensure port 8080 is exposed and not blocked by firewall
- Check that `LAN_NETWORK` includes your client's network
- Default credentials: admin / check container logs for password

### Killswitch blocking everything
- The killswitch drops all traffic if VPN is down
- Ensure `LAN_NETWORK` is correctly configured
- Add additional allowed ports via `ADDITIONAL_PORTS` if needed

## Credits

- Original project: [DyonR/docker-qbittorrentvpn](https://github.com/DyonR/docker-qbittorrentvpn)
- Inspired by: [binhex/arch-qbittorrentvpn](https://github.com/binhex/arch-qbittorrentvpn)
