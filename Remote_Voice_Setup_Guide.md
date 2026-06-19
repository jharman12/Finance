# Remote Voice Setup Guide

This guide shows how to set up a separate device so it can listen for the wake phrase locally and send audio securely to the main Finance app PC.

This setup is based on the code currently in this repository.

Important current behavior:

- the remote device does local wake-word listening,
- it does not continuously stream audio to the main PC,
- it opens a secure connection only after wake is detected,
- it closes the connection again after the command finishes.

## What the TLS cert and key are

You asked what the TLS certificate and key mean. This is the simplest practical explanation:

- `TLS certificate`: the public identity file for the main PC server
- `TLS private key`: the secret file that proves the server really owns that identity

Think of it like this:

- the certificate is the public badge,
- the private key is the secret that must never leave the main PC.

Rules:

- The `cert.pem` file can be copied to the remote device.
- The `key.pem` file must stay only on the main PC.
- If someone gets the private key, they can impersonate your server.

For this project today:

- main PC uses `FINANCE_APP_REMOTE_AUDIO_TLS_CERT` and `FINANCE_APP_REMOTE_AUDIO_TLS_KEY`
- remote sender uses `FINANCE_APP_REMOTE_AUDIO_CA_CERT`

If you create a self-signed certificate, the remote sender can use that same `.pem` certificate file as its `CA_CERT` file.

## Overview

You will do this in order:

1. Pick the main PC's local network IP address.
2. Generate a TLS certificate and private key on the main PC.
3. Generate a long random shared token.
4. Enable remote audio on the main PC.
5. Copy only the certificate to the remote device.
6. Install the remote sender dependencies.
7. Configure and run the remote sender.
8. Test the wake phrase flow.

## What you need

Main PC:

- this Finance app repo
- Python environment for the app
- a microphone already working locally in the app
- OpenSSL installed

Remote device:

- Python 3.10+
- a microphone
- network access to the main PC on your LAN
- a local copy of a Vosk model if using `phrase_vosk`

## Step 1: Find the main PC IP address

On the main PC, open PowerShell and run:

```powershell
ipconfig
```

Look for the IPv4 address on your local network. It will usually look something like:

```text
192.168.1.20
```

Write that down. The remote device will connect to it.

In the rest of this guide, I will assume your main PC IP is:

```text
192.168.1.20
```

## Step 2: Generate the TLS certificate and key on the main PC

You need two files:

- `finance-voice-cert.pem`
- `finance-voice-key.pem`

Create a folder for them on the main PC, for example:

```powershell
New-Item -ItemType Directory -Force -Path C:\FinanceVoiceTls
Set-Location C:\FinanceVoiceTls
```

Then generate a self-signed certificate with OpenSSL.

Important: the earlier example used `^`, which works in `cmd.exe` but not in PowerShell. In PowerShell, use a single-line command like this:

```powershell
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes -keyout finance-voice-key.pem -out finance-voice-cert.pem -subj "/CN=192.168.20.1" -addext "subjectAltName=IP:192.168.20.1"
```

If you want a multi-line PowerShell version, use the backtick character instead:

```powershell
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes `
  -keyout finance-voice-key.pem `
  -out finance-voice-cert.pem `
  -subj "/CN=192.168.1.20" `
  -addext "subjectAltName=IP:192.168.1.20"
```

What this does:

- creates a new private key file: `finance-voice-key.pem`
- creates a server certificate file: `finance-voice-cert.pem`
- makes the certificate valid for the IP `192.168.1.20`

If you want to connect using a local hostname instead of an IP, use that hostname in the certificate and make sure the remote device can resolve it.

## Step 3: Generate a long random token

Right now, the current implementation uses:

- TLS for encrypted transport and server verification
- a shared token for sender authentication

Generate a token on the main PC:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output somewhere safe. Example:

```text
0YjvK7KxV8R7d1yUZ6Xh8mGfKxJ4Yv1SxX6uTQzjQ8Q
```

You will use the same token on:

- the main PC
- the remote device

## Step 4: Configure the main PC

On the main PC, set these environment variables in PowerShell before launching the Finance app:

```powershell
$env:FINANCE_APP_REMOTE_AUDIO_ENABLED="1"
$env:FINANCE_APP_REMOTE_AUDIO_TOKEN="PASTE_YOUR_RANDOM_TOKEN_HERE"
$env:FINANCE_APP_REMOTE_AUDIO_BIND_HOST="0.0.0.0"
$env:FINANCE_APP_REMOTE_AUDIO_PORT="45881"
$env:FINANCE_APP_REMOTE_AUDIO_TLS_CERT="C:\FinanceVoiceTls\finance-voice-cert.pem"
$env:FINANCE_APP_REMOTE_AUDIO_TLS_KEY="C:\FinanceVoiceTls\finance-voice-key.pem"
```

Notes:

- `0.0.0.0` means the main PC listens on the LAN, not just localhost.
- The certificate path points to the public certificate.
- The key path points to the private key and must remain on the main PC only.

Then start the Finance app normally.

## Step 5: Copy only the certificate to the remote device

Copy this file from the main PC to the remote device:

```text
C:\FinanceVoiceTls\finance-voice-cert.pem
```

Do not copy this file:

```text
C:\FinanceVoiceTls\finance-voice-key.pem
```

That key file stays only on the main PC.

On the remote device, place the copied certificate somewhere like:

```text
C:\FinanceVoice\finance-voice-cert.pem
```

## Step 6: Install the remote sender dependencies

On the remote device, you do not need the full desktop app UI just to run the sender script, but the simplest setup is to use this repo and install the needed packages.

At minimum install:

```powershell
pip install sounddevice vosk
```

Optional, only if you have a custom wake model:

```powershell
pip install openwakeword numpy
```

If you are using the full repo environment, you can also do:

```powershell
pip install -r requirements.txt
```

## Step 7: Put a Vosk model on the remote device

If you are using the default `phrase_vosk` wake mode, the remote device needs a local Vosk model.

Example path:

```text
C:\FinanceVoice\models\vosk-model-en-us-0.22-lgraph
```

## Step 8: Configure the remote device

On the remote device, set these environment variables in PowerShell:

```powershell
$env:FINANCE_APP_REMOTE_AUDIO_HOST="192.168.1.20"
$env:FINANCE_APP_REMOTE_AUDIO_PORT="45881"
$env:FINANCE_APP_REMOTE_AUDIO_TOKEN="PASTE_YOUR_RANDOM_TOKEN_HERE"
$env:FINANCE_APP_REMOTE_AUDIO_CA_CERT="C:\FinanceVoice\finance-voice-cert.pem"
$env:FINANCE_APP_REMOTE_AUDIO_TLS_SERVER_NAME="192.168.1.20"
$env:FINANCE_APP_REMOTE_SOURCE_ID="kitchen-node"
$env:FINANCE_APP_REMOTE_WAKE_MODE="phrase_vosk"
$env:FINANCE_APP_REMOTE_VOSK_MODEL_PATH="C:\FinanceVoice\models\vosk-model-en-us-0.22-lgraph"
```

What these mean:

- `HOST`: the main PC IP
- `PORT`: the remote audio server port
- `TOKEN`: the same shared token from the main PC
- `CA_CERT`: the certificate copied from the main PC
- `TLS_SERVER_NAME`: the same identity used in the certificate
- `SOURCE_ID`: the friendly name of this remote device
- `WAKE_MODE`: `phrase_vosk` or `openwakeword`
- `VOSK_MODEL_PATH`: local wake-detection model path on the remote device

Because the certificate was created for `192.168.1.20`, the server name should also be `192.168.1.20`.

## Step 9: Run the sender script on the remote device

From the repo folder on the remote device, run:

```powershell
python remote_voice_sender.py
```

You should see a message showing that it is listening locally for the wake phrase and not yet streaming.

Expected behavior:

- idle: local wake listening only
- wake detected: TLS connection opens to the main PC
- active command: audio streams to the main PC
- silence/end: connection closes again

## Step 10: Test the full flow

1. Start the Finance app on the main PC.
2. Start voice mode in the Finance app.
3. Start `remote_voice_sender.py` on the remote device.
4. Say the wake phrase near the remote device.
5. Speak a short command.

Example:

```text
Hey Steven, show me my spending summary
```

If everything is working:

- the remote device should report wake detected and streaming started
- the main app should show the wake/voice pipeline activity
- the assistant should receive the recognized command

## Common mistakes

### 1. Using the private key on the remote device

Do not copy the private key to the remote device.

Only copy:

- `finance-voice-cert.pem`

Never copy:

- `finance-voice-key.pem`

### 2. Certificate identity does not match host

If your certificate was created for `192.168.1.20`, then the remote device must connect using:

- host `192.168.1.20`
- TLS server name `192.168.1.20`

If those do not match, TLS verification can fail.

### 3. No Vosk model on the remote device

The remote sender needs a local model for `phrase_vosk` wake detection.

### 4. Main PC still bound to localhost only

If the main PC uses `127.0.0.1`, remote devices cannot reach it.

Use:

```powershell
$env:FINANCE_APP_REMOTE_AUDIO_BIND_HOST="0.0.0.0"
```

### 5. Windows firewall blocks the port

If needed, allow inbound TCP on port `45881` for your private network.

## If you do not have OpenSSL

You can install it, or use a package such as `mkcert`.

If you want, I can next add:

1. a helper script that generates the TLS cert and key for you
2. a Windows firewall setup command
3. a one-command launcher for the remote device
