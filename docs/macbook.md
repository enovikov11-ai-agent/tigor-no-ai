# Macbook

Apps: telegram, chrome, vscode, item2, bitwarden, wireguard

View → Show Path Bar

## brew & python

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python wireguard-tools rsync libfido2 openssh

pip3 install PyYAML requests ipykernel --break-system-packages

brew install miniserve

## PGP

brew install gnupg pinentry-mac ykman

ykman info
gpg --card-status

gpg --card-edit

admin
generate

ykman openpgp access change-pin
ykman openpgp access change-admin-pin

ykman openpgp keys set-touch sig on

tigor-git-sign <tigor@tgr.rs>

echo "pinentry-program $(which pinentry-mac)" >> ~/.gnupg/gpg-agent.conf

gpgconf --kill gpg-agent

pub rsa2048/4D98D893317CA780

gpg --list-keys --keyid-format long

git config user.signingkey 4D98D893317CA780
git config commit.gpgsign true
git config gpg.program gpg

gpg --armor --export 4D98D893317CA780 | pbcopy

git config user.email tigor@tgr.rs

~/.gnupg/gpg-agent.conf
pinentry-program /opt/homebrew/bin/pinentry-mac
default-cache-ttl 86400
max-cache-ttl 86400

gpgconf --kill gpg-agent

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