# Macbook

Apps: telegram, chrome, vscode, item2, bitwarden, wireguard

View → Show Path Bar

## brew & python

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python wireguard-tools rsync libfido2 openssh

pip3 install PyYAML requests ipykernel --break-system-packages

brew install miniserve

## GPG + YubiKey

brew install gnupg pinentry-mac ykman

# Verify YubiKey detected
ykman info
gpg --card-status

# Prepare YubiKey (repeat for each of 2 keys: daily + backup)
gpg --card-edit
# admin → kdf-setup → max-pin-trials 10 → quit

ykman openpgp access change-pin
ykman openpgp access change-admin-pin

# Touch: sig=always, enc+auth=cached (touch once per 15s session)
ykman openpgp keys set-touch sig on
ykman openpgp keys set-touch enc cached
ykman openpgp keys set-touch aut cached

# Key attributes: Ed25519 / Curve25519 (firmware ≥ 5.2)
gpg --card-edit
# admin → key-attr → 9 → 16 (Ed25519 for sig)
# → 9 → 18 (Curve 25519 for enc)
# → 9 → 16 (Ed25519 for auth) → quit

# Generate primary key (offline/Tails) — Certify only, Curve 25519
gpg --expert --full-gen-key
# (11) ECC custom → Certify only → (1) Curve 25519 → 0 expiry

# Add subkeys
gpg --expert --edit-key YOUR_KEY_ID
# addkey → (10) sign only → Curve 25519 → 2y
# addkey → (12) encrypt only → Curve 25519 → 2y
# addkey → (11) custom → Auth only → Curve 25519 → 2y
# save

# Backup BEFORE keytocard
gpg --export-secret-keys --armor YOUR_KEY_ID > master-backup.asc
gpg --export-secret-subkeys --armor YOUR_KEY_ID > subkeys-backup.asc
gpg --export --armor YOUR_KEY_ID > public-key.asc

# Move subkeys to YubiKey
gpg --edit-key YOUR_KEY_ID
# keytocard → 1 (sign) → keytocard → 2 (encrypt) → keytocard → 3 (auth)
# quit (NOT save)

# Verify
gpg -K --keyid-format long  # subkeys show ssb>
ykman openpgp info

# — Daily Mac setup —

gpg --import public-key.asc
gpg --edit-key YOUR_KEY_ID
# trust → 5 → quit

cat >> ~/.gnupg/gpg-agent.conf <<'EOF'
pinentry-program /opt/homebrew/bin/pinentry-mac
enable-ssh-support
default-cache-ttl 86400
max-cache-ttl 86400
EOF
gpgconf --kill gpg-agent

# SSH via gpg-agent — extract auth keygrip
gpg --with-keygrip -K | awk '/\[auth\]/{getline; print $NF}' > ~/.gnupg/sshcontrol

echo 'export SSH_AUTH_SOCK=$(gpgconf --list-dirs agent-ssh-socket)' >> ~/.zshrc
echo 'gpgconf --launch gpg-agent' >> ~/.zshrc

ssh-add -L  # → add to servers / GitHub

# Git signing — extract sign subkey
gpg -K --with-colons --keyid-format 0xlong YOUR_KEY_ID | awk -F: '/^ssb/ && $11 ~ /s/ {print $5; exit}'

git config --global user.signingkey YOUR_SIGN_SUBKEY
git config --global commit.gpgsign true
git config --global gpg.program gpg

# Public key → GitHub → Settings → SSH and GPG keys
gpg --armor --export YOUR_KEY_ID | pbcopy

# Publish
gpg --keyserver keys.openpgp.org --send-keys YOUR_KEY_ID

# — New machine —
brew install gnupg pinentry-mac ykman
gpg --import public-key.asc
# trust 5 → quit
# same gpg-agent.conf, sshcontrol, zshrc as above

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
