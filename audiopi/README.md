# audiopi

Raspberry Pi 3 (Raspberry Pi OS Lite, trixie), wired Ethernet, user and
hostname `audiopi`. Two jobs: the boat's audio server, and the Klaxon relay for
the anchor alarm.

| Repo file | Installed at |
|---|---|
| `audio/network.conf` | `~audiopi/.config/pipewire/pipewire-pulse.conf.d/network.conf` |
| `alarm/audiopi-alarm.py` | `/usr/local/sbin/audiopi-alarm` (0755) |
| `alarm/audiopi-alarm.service` | `/etc/systemd/system/audiopi-alarm.service` |
| `alarm/config.example.toml` | `/etc/audiopi-alarm/config.toml` (root:audiopi-alarm 0640; add the Signal K token) |
| `alarm/avnav-klaxon` | on each plotter: `/usr/local/bin/avnav-klaxon` (0755) |
| `volume/audiopi-volume.py` | `/usr/local/sbin/audiopi-volume` (0755) |
| `volume/audiopi-volume.service` | `/etc/systemd/system/audiopi-volume.service` |
| `system/journald.conf.d-overlay.conf` | `/etc/systemd/journald.conf.d/overlay.conf` |
| `system/rpi-swap.conf.d-overlay.conf` | `/etc/rpi/swap.conf.d/overlay.conf` |

## Audio server

PipeWire runs as the `audiopi` user (`loginctl enable-linger audiopi`) and
plays through the 3.5mm jack into the stereo's RCA input, via an RCA ground
loop isolator (the jack picks up the boat's ground noise without it).
`network.conf` lets other Pis on 192.168.50.0/24 play to it with the
PulseAudio protocol on tcp/4713: boatflix's MPD (`../audio/`) and
salonviewscreen (`../salonviewscreen/`).

Test from another machine: `PULSE_SERVER=tcp:audiopi.local:4713 paplay file.wav`.

**Volume page:** http://audiopi.local/ has a master slider and mute for the
stereo, and a slider and mute for each connected source (boatflix's MPD,
salonviewscreen). It is a separate service from the alarm, running as the
`audiopi` user so `pactl` reaches its PipeWire session. Volumes are capped at
100%. LAN only, no auth.

## Klaxon

Hardware: Waveshare RPi Relay Board (B) channel 1 on GPIO 5 (active low)
switches fused 12V to the Klaxon through its NO contact, so the Klaxon fails
silent. The forward bilge float drives the Klaxon directly, through steering
diodes, and through an input relay pulls GPIO 27 to ground. GPIO 17 is free
for a second float.

**Only the anchor alarm closes the relay.** False alarms are worse than
useless, so the service sounds the Klaxon only for alarms in the config's
`[klaxon]` allowlist: `http_alarms = ["anchor"]`, `signalk_paths = []`.
Other Signal K notifications, a missing plotter, unknown HTTP alarm names and
the float never close it. High water sounds the Klaxon through the float's
own hardwired path, with or without this Pi.

Anchor alarm path: AvNav on the plotter raises its `anchor` alarm and runs
`avnav-klaxon`, which POSTs `on` to `http://audiopi.local:8080/alarm/anchor`
every 5 s. When the alarm clears AvNav SIGTERMs it and it POSTs `off`. An `on`
lapses after `http_alarm_ttl` (30 s) without a refresh, so a lost `off` can't
leave the Klaxon stuck on. AvNav config on the plotter
(`/home/pi/avnav/data/avnav_server.xml`, inside `<Workers>`):

```xml
<AVNCommandHandler>
     ...
     <Command command="/usr/local/bin/avnav-klaxon" name="klaxon" repeat="1"/>
</AVNCommandHandler>
<AVNAlarmHandler>
     <Alarm name="anchor" command="klaxon" repeat="1"/>
</AVNAlarmHandler>
```

AvNav runs one alarm command at a time: if another critical alarm (e.g. `gps`)
is already running its command, the anchor command waits until that one ends.

HTTP API on port 8080 (LAN, no auth):

```sh
curl -X POST http://audiopi.local:8080/alarm/anchor -d on    # or -d off
curl -X POST http://audiopi.local:8080/silence               # until a new alarm starts
curl http://audiopi.local:8080/status
```

The float is published to Signal K as `notifications.bilge.forward`: an
`emergency` (visual+sound) when it lifts, cleared (null) when it drops. A clear
float is never announced on its own, at startup or on reconnect. That needs a
device token: approve audiopi's access request in each plotter's Signal K
admin (Security > Access Requests) and put the token in the config.

AvNav shows every Signal K notification that has a value as an alarm, even
state `normal`, and Signal K 2.25 turns a cleared notification into `normal`
rather than removing it. So AvNav's Signal K handler ignores `bilge.forward`
and the approval notice (`<AVNSignalKHandler notifyBlackList="server.newVersion,bilge.forward,security.accessRequest.readwrite.<clientId>" ...>`).
High water shows up in Signal K, not in AvNav; the Klaxon sounds through the
float's own wiring either way.

## Read-only (safe to cut power)

The root filesystem is an overlay (`overlayroot=tmpfs` on the kernel command
line, `overlayroot` package): the SD card is mounted read-only underneath at
`/media/root-ro`, and every write lands in RAM and is **discarded at reboot**.
The boot partition (`/boot/firmware`) is mounted read-only too. Pulling power
can't corrupt either.

Set up for it before enabling:
- journald keeps logs in RAM only, capped at 32 MB (`Storage=volatile`), so
  logs don't slowly fill RAM; they are gone after a reboot.
- Swap is zram only (`Mechanism=zram`), without the `/var/swap` writeback file.
- `apt-daily` and `apt-daily-upgrade` timers are disabled.
- `systemd-remount-fs.service` shows as failed at every boot: it tries to
  remount `/` from fstab, which is now the overlay. Harmless.

Volume changes (web page, `wpctl`) last until the next reboot; it boots at the
level saved on the card (100%).

To change anything permanently:

```sh
sudo raspi-config nonint disable_overlayfs   # then reboot
sudo raspi-config nonint disable_bootro      # only to edit /boot/firmware
# ...make changes, then:
sudo raspi-config nonint enable_bootro
sudo raspi-config nonint enable_overlayfs    # then reboot
```

For a quick one-off edit without the two reboots, `sudo overlayroot-chroot`
opens a shell on the real card (e.g. to add the second plotter's Signal K token
to `/etc/audiopi-alarm/config.toml`).
