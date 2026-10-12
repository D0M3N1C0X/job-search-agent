#!/usr/bin/env bash
# Prepares a fresh Ubuntu 24.04 server in the EU for the beta worker.
# Run as root:  bash setup.sh
# It installs nothing beyond Python and git: the engine is standard library only.
set -euo pipefail

REPO=https://github.com/D0M3N1C0X/job-search-agent.git
DIR=/opt/job-search-agent
ENV=/etc/jsa-worker.env

apt-get update -q
apt-get install -y -q python3 git unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

id jsa >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /usr/sbin/nologin jsa
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone --depth 1 "$REPO" "$DIR"
fi
chown -R root:root "$DIR"           # the worker reads the code, it never writes it
install -d -o jsa -g jsa -m 700 /var/cache/jsa

if [ ! -f "$ENV" ]; then
  install -m 600 -o root -g root /dev/null "$ENV"
  cat > "$ENV" <<'VARS'
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=paste-the-service-role-key-here
VARS
  echo "Fill in $ENV (nano $ENV), then run: systemctl restart jsa-worker"
fi

install -m 644 "$DIR/cloud/deploy/jsa-worker.service" /etc/systemd/system/jsa-worker.service
systemctl daemon-reload
systemctl enable jsa-worker
grep -q "YOUR-PROJECT" "$ENV" || systemctl restart jsa-worker
echo "Done. Logs: journalctl -u jsa-worker -f"
