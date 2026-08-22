# Macbook

Apps: telegram, chrome, vscode, item2, bitwarden, wireguard

View → Show Path Bar

## brew & python

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python wireguard-tools rsync libfido2 openssh

pip3 install PyYAML requests ipykernel --break-system-packages

brew install miniserve

## GPG + YubiKey

### Pattern: Primary key offline, subkeys on YubiKey

Master (Certify-only) key stays on encrypted offline storage. Subkeys (Sign, Encrypt, Auth) live on YubiKey 5 series — private material never touches disk.

#### 0. Install tools

```bash
brew install gnupg pinentry-mac ykman

# Verify YubiKey is detected
ykman info
gpg --card-status
```

If `gpg --card-status` shows "Card error", restart `gpg-agent`:

```bash
gpgconf --kill gpg-agent
```

#### 1. Prepare YubiKey

Do this on **each** YubiKey (buy two: daily + backup).

```bash
gpg --card-edit
```

```
admin
# Enable KDF — PINs hashed instead of plaintext
kdf-setup
# Set PIN limits: 10 retries (prevents accidental lockout)
max-pin-trials 10
# Exit card-edit
quit
```

Change default PINs (123456 / 12345678) immediately:

```bash
ykman openpgp access change-pin
ykman openpgp access change-admin-pin
```

Set touch policy — `cached` = touch once per PIN session (15s grace):

```bash
# Touch required for every signature (Git signing, GPG sign)
ykman openpgp keys set-touch sig on
# Cached for encryption and auth (SSH, decrypt)
ykman openpgp keys set-touch enc cached
ykman openpgp keys set-touch aut cached
# Verify
ykman openpgp info
```

Set key algorithm to Ed25519 (firmware ≥ 5.2 required):

```bash
gpg --card-edit
```
```
admin
key-attr
# Signature key: (9) EdDSA (set your own capabilities) → (16) Ed25519
# Encryption key: (9) ECC (set your own capabilities) → (18) Curve 25519
# Authentication key: (9) EdDSA (set your own capabilities) → (16) Ed25519
quit
```

#### 2. Generate primary key (offline machine)

Use Tails, a disconnected VM, or a Raspberry Pi without network.

```bash
# Temp GPG home to avoid polluting daily config
export GNUPGHOME=$(mktemp -d)
chmod 700 "$GNUPGHOME"

gpg --expert --full-generate-key
```

```
Select: (11) ECC (set your own capabilities)
Toggle Sign/Encrypt/Auth OFF, leave only Certify
Curve: (1) Curve 25519
Expiry: 0 (never — subkeys expire instead)
Name/Email/Comment: your identity
Passphrase: strong, saved in password manager
```

Add three subkeys:

```bash
gpg --expert --edit-key YOUR_KEY_ID
```

```
# Sign subkey
addkey
(10) ECC (sign only) → (1) Curve 25519 → 2y expiry

# Encrypt subkey
addkey
(12) ECC (encrypt only) → (1) Curve 25519 → 2y expiry

# Auth subkey (SSH)
addkey
(11) ECC (set your own capabilities)
Toggle Sign/Encrypt OFF, Auth ON → (1) Curve 25519 → 2y expiry

save
```

#### 3. Backup before moving keys

```bash
# Full secret (primary + subkeys) — store encrypted, offline
gpg --export-secret-keys --armor YOUR_KEY_ID > master-backup.asc

# Subkeys only — used to load onto YubiKey / spare
gpg --export-secret-subkeys --armor YOUR_KEY_ID > subkeys-backup.asc

# Public key
gpg --export --armor YOUR_KEY_ID > public-key.asc
```

Store `master-backup.asc` on encrypted USB drives in **two physical locations**.

#### 4. Move subkeys to YubiKey

Insert primary YubiKey. Restore subkeys and move them:

```bash
gpg --import subkeys-backup.asc
gpg --edit-key YOUR_KEY_ID
```

```
keytocard  # select slot 1 (sign)
keytocard  # select slot 2 (encrypt)
keytocard  # select slot 3 (auth)
# DO NOT save — "save" deletes the local copy
quit
```

Verify — subkeys should show `ssb>` (on card):

```bash
gpg -K --keyid-format long
```

**For the spare YubiKey:** re-import `subkeys-backup.asc` and repeat `keytocard` steps.

After both YubiKeys are provisioned, wipe the offline machine's GPG home.

#### 5. Configure GPG on daily Mac

Copy `public-key.asc` to your Mac. Import and trust:

```bash
gpg --import public-key.asc
gpg --edit-key YOUR_KEY_ID
trust → 5 (ultimate) → quit
```

Configure pinentry and agent:

```bash
echo "pinentry-program /opt/homebrew/bin/pinentry-mac" >> ~/.gnupg/gpg-agent.conf
echo "enable-ssh-support" >> ~/.gnupg/gpg-agent.conf
echo "default-cache-ttl 86400" >> ~/.gnupg/gpg-agent.conf
echo "max-cache-ttl 86400" >> ~/.gnupg/gpg-agent.conf
gpgconf --kill gpg-agent
```

#### 6. SSH via gpg-agent

```bash
# Get auth subkey keygrip
gpg --with-keygrip --list-secret-keys YOUR_KEY_ID

# Find the keygrip next to the [auth] line
# Add it to sshcontrol
echo "KEYGRIP_HERE" >> ~/.gnupg/sshcontrol

# Point SSH at gpg-agent
echo 'export SSH_AUTH_SOCK=$(gpgconf --list-dirs agent-ssh-socket)' >> ~/.zshrc
echo 'gpgconf --launch gpg-agent' >> ~/.zshrc

# Get SSH public key
ssh-add -L

# Add the output to ~/.ssh/authorized_keys on remote servers
```

#### 7. Git commit signing

```bash
# Get sign subkey ID
gpg -K --with-colons --keyid-format 0xlong YOUR_KEY_ID | \
  awk -F: '/^ssb/ && $12 ~ /s/ {print $5; exit}'

git config --global user.signingkey YOUR_SIGN_SUBKEY
git config --global commit.gpgsign true
git config --global gpg.program gpg
git config --global user.email "your@email"

# Export public key for GitHub
gpg --armor --export YOUR_KEY_ID | pbcopy
# Paste at GitHub → Settings → SSH and GPG keys → New GPG key
```

#### 8. Publish public key

```bash
# keys.openpgp.org (validates email)
gpg --keyserver keys.openpgp.org --send-keys YOUR_KEY_ID

# Or store key URL on the YubiKey itself (fetch on new machines)
gpg --card-edit
url https://example.com/gpg/public-key.asc
quit
```

#### 9. Set up new machine

```bash
brew install gnupg pinentry-mac ykman

# Import public key
gpg --import public-key.asc

# Or fetch from YubiKey card
gpg --card-edit | grep URL  # then:
gpg --card-edit → fetch → quit

# Config
echo "pinentry-program /opt/homebrew/bin/pinentry-mac" >> ~/.gnupg/gpg-agent.conf
echo "enable-ssh-support" >> ~/.gnupg/gpg-agent.conf
gpgconf --kill gpg-agent

# Trust
gpg --edit-key YOUR_KEY_ID → trust 5 → quit

# sshcontrol + git config (see steps 6, 7)
```

#### 10. Subkey rotation (every 2 years)

On offline machine with primary key:

```bash
# Revoke expiring subkeys
gpg --edit-key YOUR_KEY_ID
# (find subkey number, then) revkey N → y → save

# Add fresh subkeys (step 2 pattern)
# Export updated public key → re-publish
```

#### 11. Lost YubiKey recovery

Use the spare YubiKey immediately. If both lost:

```bash
# On offline machine:
# Revoke old subkeys → generate new ones → provision new YubiKey(s)
# Re-publish public key
```

### Quick reference

| PIN | Purpose | Default |
|-----|---------|---------|
| User PIN | Daily operations (sign, decrypt, SSH) | `123456` |
| Admin PIN | Card settings, change PINs, keytocard | `12345678` |

| Touch mode | Behavior |
|------------|----------|
| `on` | Touch required for every operation |
| `cached` | Touch once per PIN session (15s) |
| `fixed` | Like `on`, cannot be changed without reset |
| `off` | No touch (less secure) |

| Gotchas |
|---------|
| **Always** provision two YubiKeys, not one |
| `keytocard` is destructive — backup subkeys first |
| Ed25519 requires YubiKey firmware ≥ 5.2 (`ykman info`) |
| Never use `pool.sks-keyservers.net` — it's dead. Use `keys.openpgp.org` |
| Don't `save` after `keytocard` — it deletes the local key |

## screenshots

mkdir -p ~/Desktop/screenshots
defaults write com.apple.screencapture location ~/Desktop/screenshots
killall SystemUIServer

## git

git config --global user.name "Evgenii Novikov"
git config --global user.email "enovikov11@yandex.ru"

## sudo touch id

```
cd /etc/pam.d/
sudo chmod 644 sudo sudo_local.template
sudo vim sudo_local.template
# раскомменчиваем строку с pam_tid.so и копируем ее
sudo vim sudo
# добавляем эту строку в начало
sudo chmod 444 sudo sudo_local.template
```

## vscode

https://marketplace.visualstudio.com/items?itemName=jnoortheen.nix-ide

{
    "workbench.colorTheme": "Default Light Modern",
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "workbench.enableExperiments": false,
    "workbench.settings.enableNaturalLanguageSearch": false,

    "files.autoSave": "onFocusChange",

    "telemetry.telemetryLevel": "off",
    "telemetry.editStats.enabled": false,
    "telemetry.feedback.enabled": false,

    "update.showReleaseNotes": false,

    "extensions.ignoreRecommendations": true,
    "extensions.autoUpdate": false,
    "git.enableSmartCommit": true,
    "claudeCode.preferredLocation": "panel",
    "explorer.confirmDelete": false,
    "explorer.confirmDragAndDrop": false,
    "diffEditor.renderSideBySide": false,
    "claudeCode.selectedModel": "opus",
    "jupyter.askForKernelRestart": false,

    "workbench.editor.wrapTabs": true
}
