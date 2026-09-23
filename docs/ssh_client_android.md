# OpenSSH client - instalat pe SM-A366B (toolchain Android)

Prefix toolchain : /data/local/tmp/tpm/usr
HOME ssh         : /data/local/tmp/tpm/home

## Cum se foloseste (ca SHELL, prin adbsh sau /run_su)

export PATH=/data/local/tmp/tpm/usr/bin:/system/bin
export HOME=/data/local/tmp/tpm/home

ssh user@host
scp fisier user@host:/path/
sftp user@host
ssh-keygen -t ed25519 -f ~/.ssh/noua_cheie
ssh-keyscan github.com

## Git prin SSH

export GIT_SSH=/data/local/tmp/tpm/usr/bin/git-ssh.sh
git clone git@github.com:user/repo.git

## Cheia generata

/publica : /data/local/tmp/tpm/home/.ssh/id_ed25519.pub
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICko4tYy9Q9je5SEsRSUVM7eR1yxlcyBDJ7TFFBNTiuY agent@SM-A366B

Copiaz-o in GitHub/GitLab (Settings > SSH keys) pentru acces la repo private.

## Config

/data/local/tmp/tpm/usr/etc/ssh/ssh_config
  ConnectTimeout 15, StrictHostKeyChecking accept-new,
  ServerAliveInterval 30, Compression yes,
  UserKnownHostsFile si IdentityFile cu cai absolute

## Limitare cunoscuta

ssh-agent NU functioneaza: SELinux (Enforcing, u:r:shell:s0) interzice
bind de socket unix oriunde -> foloseste chei fara passphrase
sau ssh-add pe alt device.

## Versiuni

OpenSSH_10.5p1 / OpenSSL 3.6.3
