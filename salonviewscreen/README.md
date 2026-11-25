# salonviewscreen

The salon display: a Raspberry Pi 4 running a Chromium kiosk under lightdm
(labwc), on a Witty Pi 4 L3V7 UPS board, wired Ethernet. User and hostname
are both `salonviewscreen`.

| Repo file | Installed at |
|---|---|
| `audio/audiopi-tunnel.conf` | `~salonviewscreen/.config/pipewire/pipewire.conf.d/audiopi-tunnel.conf` |
| `display/hdmi-watchdog` | `/usr/local/sbin/hdmi-watchdog` (0755) |
| `display/hdmi-watchdog.service` | `/etc/systemd/system/hdmi-watchdog.service` |
| `wittypi/wittypi-powerloss` | `/usr/local/sbin/wittypi-powerloss` (0755) |
| `wittypi/wittypi-powerloss.service` | `/etc/systemd/system/wittypi-powerloss.service` |
| `wittypi/wittypi-powerloss.service.d-boot-grace.conf` | `/etc/systemd/system/wittypi-powerloss.service.d/boot-grace.conf` |
| `boot/config.txt` | `/boot/firmware/config.txt` |

## Audio

The kiosk's sound goes to **audiopi** (the Pi wired into the stereo) the same
way boatflix's does. A PipeWire pulse-tunnel sink, "audiopi (boat stereo)",
connects to `tcp:audiopi.local:4713` and retries every 5 s if audiopi is down.
It is the default sink (set once with `wpctl set-default`; WirePlumber
remembers it). The Pi's own headphone and HDMI sinks are still there.

After installing the tunnel config:

```sh
systemctl --user restart pipewire pipewire-pulse wireplumber
wpctl set-default "$(wpctl status | grep -m1 'audiopi (boat stereo)' | grep -oE '[0-9]+' | head -1)"
```

## Wi-Fi and Bluetooth are off

- Firmware: `dtoverlay=disable-bt` and `dtoverlay=disable-wifi` in
  `config.txt` (in place of `miniuart-bt`).
- Services: `bluetooth` and `hciuart` are disabled; the user `mpris-proxy`
  service is masked.
- Runtime: `rfkill block wifi bluetooth` and `nmcli radio wifi off`.

## Power-loss handling

`wittypi-powerloss` shuts the Pi down cleanly when the Witty Pi reports it is
running from battery and the charger sees no USB input. It requires 30 s of
continuous loss (`CONFIRM=60` at 0.5 s). With a 3 s window it shut the Pi down
repeatedly when nothing was wrong: `hdmi-watchdog` restarted lightdm after a
display stall, Chromium's startup pushed the draw to about 1 A, the Witty Pi's
input sagged below battery voltage for a few seconds, and the script read that
as a power loss. The battery is there to ride out those sags.
