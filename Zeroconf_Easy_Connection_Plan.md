# Zeroconf / mDNS Easy Connection Plan

## Goal

Make remote voice setup feel like AirPlay:

- the remote device appears in a "devices on network" list,
- the user clicks it once,
- the app connects securely without manually typing an IP address,
- the connection only opens when the wake phrase is detected.

## Recommendation

Yes, use Zeroconf / mDNS, but only for **discovery**.

mDNS is a good fit for the "show nearby devices" part. It does not replace TLS, token auth, or audio transport. The easy version should be:

1. remote device advertises itself on the LAN with mDNS,
2. main PC browses and shows the discovered devices,
3. user clicks a device,
4. the app stores the chosen endpoint and verifies it with TLS when audio starts.

This is simpler for users than manual IP entry, while keeping the secure connection model already in the codebase.

## What This Changes

Today the system assumes users know the main PC IP and manually configure host and certificate paths.

The new flow should replace that with:

- automatic device discovery,
- a visible "Connect" action,
- an explicit pairing step,
- the same secure audio session underneath.

## Proposed Architecture

### 1. Discovery layer

Use Zeroconf / mDNS to advertise and discover devices on the local network.

Suggested service pattern:

- service type: `_finance-voice._tcp.local.`
- advertised fields:
  - `device_name`
  - `source_id`
  - `role=remote-sender`
  - `port`
  - `protocol_version`

The remote device should publish itself when it is ready. The main PC should browse for these services and populate a device list.

### 2. Pairing layer

Discovery alone is not enough. The user should still explicitly approve the device once.

Use a simple pairing flow:

- device appears in the list,
- user clicks it,
- the main PC shows a short pairing code or confirmation dialog,
- the remote device displays the same code,
- if the codes match, save the trusted device record.

This avoids accidental connections and makes the setup feel intentional instead of automatic.

### 3. Secure transport layer

Keep TLS for the actual voice channel.

The discovery record should provide:

- host IP,
- port,
- service name,
- optional friendly name.

The connection itself should still use:

- TLS certificate verification,
- shared token authentication,
- the existing newline-delimited JSON voice protocol.

### 4. Connection UX

The main PC UI should have a small panel like:

- "Available devices on network"
- discovered devices list
- status: `discovered`, `paired`, `connected`, `offline`
- `Connect` / `Disconnect` buttons

The remote device should be even simpler:

- choose a friendly name,
- advertise itself,
- listen locally for wake word,
- connect only when needed.

## Implementation Phases

### Phase 1: Discovery proof of concept

Add mDNS advertisement and browsing without changing the audio protocol.

Work items:

- add a small discovery module to the remote sender,
- add a discovery browser to the main PC,
- list devices in the UI,
- log when devices appear or disappear.

Done when:

- remote device shows up automatically on the main PC,
- the app can display its name, IP, and port.

### Phase 2: Pairing and trust

Add one-click pairing and stored trusted devices.

Work items:

- generate a short pairing code on first contact,
- confirm the code on both sides,
- store the trusted device identity locally,
- reject unknown devices until paired.

Done when:

- user can click a discovered device and trust it once,
- future sessions reconnect without retyping IPs.

### Phase 3: Connect button flow

Make the main PC act like an AirPlay receiver list.

Work items:

- connect button in the device list,
- show connection state clearly,
- reconnect automatically if the sender restarts,
- keep the audio session dormant until wake phrase activation.

Done when:

- the user can click a discovered device and start using it immediately.

### Phase 4: Cleanup of manual setup

Once discovery works, remove or de-emphasize manual IP setup in the normal path.

Work items:

- keep manual host override as an advanced fallback only,
- move the current IP-based setup into troubleshooting docs,
- keep TLS/token settings but hide them behind sane defaults and setup prompts.

Done when:

- a normal user never needs to type an IP address,
- the setup reads more like AirPlay than a server configuration task.

## Suggested Python Library

Use `zeroconf`.

Why:

- it is the standard Python library choice for mDNS / service discovery,
- it works well for both advertisement and browsing,
- it keeps the implementation lightweight.

Likely dependency additions:

- `zeroconf`

## Files Most Likely To Change

- `finance_app/services/voice/network_transport.py`
- `finance_app/services/voice_pipeline.py`
- `finance_app/ui/main_window.py`
- `remote_voice_sender.py`
- a new discovery helper module under `finance_app/services/voice/`

## Practical Constraints

Zeroconf will make setup much easier, but it will not fix every network problem.

Still required:

- both devices must be on the same LAN segment,
- AP/client isolation must be off,
- the firewall must allow the transport port,
- TLS certificate verification still needs to succeed.

So the new UX should hide complexity, not remove the need for secure transport.

## Success Criteria

The new flow is successful if:

- the main PC shows a live list of nearby devices,
- the user clicks one device to connect,
- no manual IP address entry is needed,
- the connection remains TLS-secure,
- wake-word activation still controls when audio streams.

## Next Build Step

Implement discovery first, before any UI redesign.

The smallest useful first milestone is:

1. advertise the remote sender over mDNS,
2. browse for it on the main PC,
3. show it in a simple list,
4. connect using the already existing secure audio transport.