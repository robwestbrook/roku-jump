# Roku Jump

Navigate Roku Live TV (The Roku Channel) by channel number from a phone.

The guide has no number entry, so scrolling from channel 100 to channel 5000 takes
minutes. This small server sends the remote-button presses for you: type a number on
a phone page and it scrolls the guide to that channel and tunes it.

## Run

    python3 server.py

Open `http://<this-computer-ip>:8766` on a phone on the same Wi-Fi. Python 3 standard
library only, no installs. This computer must stay on and on the home network.

Environment variables: `TV_IP` (default `192.168.1.146`), `PORT` (default `8766`),
`DRY_RUN=1` (plan moves without sending keys).

### TV setup

Settings > System > Advanced system settings > Control by mobile apps >
Network access must be **Permissive** (or Default). In "Limited" mode the TV
rejects button presses with HTTP 403.

## Run on a Raspberry Pi or home server

The server is standard-library Python and only talks to the TV and your phone over
HTTP, so any always-on Linux machine on the same network works, including a Raspberry
Pi. That keeps it available without leaving a desktop computer on.

1. Clone the repo onto the machine and check that `python3 server.py` works.
2. Give the TV a fixed address: reserve it in your router's DHCP settings, or the
   jumper will lose it when the address changes. Set `TV_IP` to that address.
3. Install the service so it starts at boot and restarts if it stops. Edit the user,
   paths and `TV_IP` in [`deploy/roku-jump.service`](deploy/roku-jump.service), then:

       sudo cp deploy/roku-jump.service /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now roku-jump

4. Open `http://<machine-address>:8766` on your phone. Reserving the machine's address
   (or using its `.local` name) keeps the bookmark working. On the first run, set the
   current channel once on the page.

**Security:** the page has no password. Anyone on your home network can change the
channel. Do not expose the port to the internet; if you need remote access, use a VPN
such as Tailscale.

## How it works

- Sends keys over Roku's External Control Protocol (`POST http://<tv>:8060/keypress/<Key>`).
- `lineup.csv` maps each channel number to its row in the guide's All Channels list
  (775 channels, 100-9112). Numbers are sparse (for example 116 is followed by 400), so
  position is not the channel number.
- To open the guide: **Left** (overlay on "Top Picks"), then **Down** once, which
  highlights the channel playing now.
- Moves: **Fwd/Rev** page 6 rows per press, then **Down/Up** for the remainder, then
  **Select** to tune.
- It tracks the current channel in `state.json`. If you change channels with the
  remote, update the "The TV is on channel" box on the page.

## Things learned the hard way

- The TV drops key presses sent less than about 0.15 s apart. Step keys use 0.2 s,
  page keys 0.25 s (0.4 s was verified; 0.25 passed the stress tests).
- The guide overlay times out after roughly 40 s, which caps the length of a jump.
- **Select** during live video tries to pause ("Live TV Pause is not available");
  it does not open the guide.
- The numbered list ends at 9112 and does not wrap. After it come the Recommended
  and Add-ons sections. The 9600-series channels (Peacock, Paramount+, ...) belong
  to Add-ons and are not in `lineup.csv`.
- Channel 450 (and many other numbers) do not exist; the page suggests the nearest ones.

## Files

| File | Purpose |
|------|---------|
| `server.py` | HTTP server, move planner, key sender |
| `index.html` | Phone page |
| `lineup.csv` | row, number, name for the main guide list |
| `state.json` | Current channel and recent list (generated, ignored) |

## Known gaps

- 40 channels have placeholder names (`(name unknown)`); their numbers are correct.
- Only Roku Live TV is supported. Tubi, Pluto TV and others would each need their own
  lineup and opening sequence.
- The lineup is a snapshot. If Roku adds or removes channels, rows shift and jumps
  drift; re-verify with spot checks.

## License

MIT. See [LICENSE](LICENSE).
