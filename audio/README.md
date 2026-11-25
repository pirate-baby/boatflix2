# boatflix audio

boatflix has no audio hardware of its own in use. MPD (driven by myMPD) plays
music from `/mnt/media` and sends it to **audiopi**, the Pi 3 wired into the
stereo's RCA input. audiopi runs PipeWire with the PulseAudio TCP module on
port 4713, accepting anonymous clients from 192.168.50.0/24.

| Repo file | Installed at |
|---|---|
| `mpd.conf` | `/etc/mpd.conf` |
| `mpd.service.d-boatflix.conf` | `/etc/systemd/system/mpd.service.d/boatflix.conf` |
| `../boot/config.txt` | `/boot/firmware/config.txt` |

If audiopi is down, MPD's output fails and playback stops; press play again
once audiopi is back.

## Wi-Fi and Bluetooth are off

boatflix is wired (eth0), and the old Bluetooth A2DP output to the stereo's
receiver is gone. The radios are disabled at three levels:

- Firmware: `dtoverlay=disable-bt-pi5` and `dtoverlay=disable-wifi-pi5` in
  `config.txt` (in place of the old `miniuart-bt`).
- Services: `bluetooth`, `bluealsa`, `bluealsa-aplay` and
  `bt-audio-autoconnect` are disabled, and the user `mpris-proxy` service is
  masked (`systemctl --user mask mpris-proxy`).
- Runtime: `rfkill block wifi bluetooth` and `nmcli radio wifi off`.

To bring Bluetooth audio back, see the history before this file was added
(`bt-audio-autoconnect`, the BlueALSA MPD output).
