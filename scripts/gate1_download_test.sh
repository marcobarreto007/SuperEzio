#!/bin/bash
# Gate 1: Validate download BEFORE pipeline
# Creates 1GB dummy file, serves via HTTP, verifies download with resume
set -euo pipefail

INSTANCE_HOST="$1"
INSTANCE_PORT="$2"

echo "=== GATE 1: DOWNLOAD VALIDATION ==="
echo "Target: $INSTANCE_HOST:$INSTANCE_PORT"
echo ""

# Step 1: Create 1GB dummy file on instance
echo "[1/4] Creating 1GB test file on instance..."
ssh -o StrictHostKeyChecking=no -i $HOME/.ssh/id_ed25519 -p "$INSTANCE_PORT" "root@$INSTANCE_HOST" "
dd if=/dev/urandom of=/tmp/testfile_1gb.bin bs=1M count=1024 2>/dev/null
echo 'Size:'
ls -lh /tmp/testfile_1gb.bin
echo 'MD5:'
md5sum /tmp/testfile_1gb.bin | cut -d' ' -f1
"

# Step 2: Get remote checksum
REMOTE_MD5=$(ssh -o StrictHostKeyChecking=no -i $HOME/.ssh/id_ed25519 -p "$INSTANCE_PORT" "root@$INSTANCE_HOST" "md5sum /tmp/testfile_1gb.bin | cut -d' ' -f1")
echo "Remote MD5: $REMOTE_MD5"

# Step 3: Start HTTP server on instance (background)
echo "[2/4] Starting HTTP server on instance..."
ssh -o StrictHostKeyChecking=no -i $HOME/.ssh/id_ed25519 -p "$INSTANCE_PORT" "root@$INSTANCE_HOST" "
pkill -f 'python -m http.server' 2>/dev/null || true
cd /tmp
nohup python -m http.server 8080 --bind 0.0.0.0 > /tmp/httpserver.log 2>&1 &
echo \"HTTP server PID: \$!\"
"

# Step 4: Create SSH tunnel
echo "[3/4] Creating SSH tunnel..."
ssh -o StrictHostKeyChecking=no -i $HOME/.ssh/id_ed25519 -f -N -L 18080:localhost:8080 -p "$INSTANCE_PORT" "root@$INSTANCE_HOST" 2>/dev/null
TUNNEL_PID=$!
echo "Tunnel PID: $TUNNEL_PID"
sleep 2

# Step 5: Download with resume
echo "[4/4] Downloading with curl (resume enabled)..."
START_TIME=$(date +%s)
curl -L -C - --retry 5 --retry-delay 10 -o /tmp/testfile_downloaded.bin http://localhost:18080/testfile_1gb.bin 2>&1
CURL_EXIT=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Step 6: Verify
LOCAL_MD5=$(md5sum /tmp/testfile_downloaded.bin 2>/dev/null | cut -d' ' -f1)
LOCAL_SIZE=$(wc -c < /tmp/testfile_downloaded.bin 2>/dev/null)
SPEED=$((1024 / (DURATION > 0 ? DURATION : 1)))

echo ""
echo "=== GATE 1 RESULT ==="
echo "Download: $CURL_EXIT (0=success)"
echo "Duration: ${DURATION}s"
echo "Speed: ~${SPEED} MB/s"
echo "Local size: $LOCAL_SIZE bytes"
echo "Remote MD5: $REMOTE_MD5"
echo "Local MD5:  $LOCAL_MD5"

# Cleanup tunnel
kill $TUNNEL_PID 2>/dev/null || true

if [ "$CURL_EXIT" = "0" ] && [ "$REMOTE_MD5" = "$LOCAL_MD5" ]; then
    echo ""
    echo ">>> GATE 1 PASSED <<<"
    echo "Download is reliable. Proceed to pipeline."
    exit 0
else
    echo ""
    echo ">>> GATE 1 FAILED <<<"
    echo "KILL SWITCH: Delete instance immediately."
    exit 1
fi
