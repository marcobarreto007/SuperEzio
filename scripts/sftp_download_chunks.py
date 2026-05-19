"""Download GGUF chunks via SFTP with SHA256 verification."""
import os
import hashlib
import sys
import time
import paramiko

HOST = "ssh6.vast.ai"
PORT = 15904
USER = "root"
REMOTE_DIR = "/root/SuperEzio/chunks"
LOCAL_DIR = "C:/Users/marco/Desktop/SuperEzio/models/chunks"
OUTPUT_FILE = "C:/Users/marco/Desktop/SuperEzio/models/qwen36-intent-f51.Q4_K_M.gguf"

CHUNKS = {
    "chunk_aa": "c6bedd2eec15d785df6c3c7e44888cfbf98b0d6c12913394fede5bf0a556dd56",
    "chunk_ab": "e5bdb6266165d49a6556f6edd58020b9aa3900635c6a184e48a8aaf84a97b700",
    "chunk_ac": "b715c4e167e726c4347dbd106ac93f334aa55aff572ac715bbdd5610f3af1df3",
    "chunk_ad": "fd86369fc245c43cb58c4898eed2ba26e30ae6039072099449cdb2efbda052d1",
}

FINAL_SHA256 = "568443202401176e5cc5e6b741924b23d1ee268886a7c9dd961cacffdb6c5a39"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(8 * 1024 * 1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def download_chunk(sftp, remote_path, local_path, expected_sha256, max_retries=3):
    remote_size = sftp.stat(remote_path).st_size
    print(f"  Remote: {remote_size} bytes | Expected SHA256: {expected_sha256[:16]}...")

    for attempt in range(1, max_retries + 1):
        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size == remote_size:
                print(f"  Already complete ({local_size} bytes), verifying...")
                local_sha = sha256_file(local_path)
                if local_sha == expected_sha256:
                    print(f"  SHA256 OK")
                    return True
                else:
                    print(f"  SHA256 MISMATCH, re-downloading...")
                    os.remove(local_path)
            else:
                print(f"  Partial {local_size}/{remote_size}, restarting...")
                os.remove(local_path)

        print(f"  Downloading (attempt {attempt}/{max_retries})...")
        start = time.time()
        try:
            sftp.get(remote_path, local_path)
        except Exception as e:
            print(f"  SFTP error: {e}")
            time.sleep(5)
            continue

        elapsed = time.time() - start
        local_size = os.path.getsize(local_path)
        speed = local_size / elapsed / (1024 * 1024) if elapsed > 0 else 0
        print(f"  Done: {local_size} bytes in {elapsed:.0f}s ({speed:.1f} MB/s)")

        if local_size != remote_size:
            print(f"  SIZE MISMATCH: local={local_size} remote={remote_size}, retrying...")
            os.remove(local_path)
            time.sleep(5)
            continue

        local_sha = sha256_file(local_path)
        if local_sha == expected_sha256:
            print(f"  SHA256 OK")
            return True
        else:
            print(f"  SHA256 MISMATCH: {local_sha[:16]}... != {expected_sha256[:16]}..., retrying...")
            os.remove(local_path)
            time.sleep(5)

    print(f"  FAILED after {max_retries} attempts")
    return False


def main():
    print("Connecting via SFTP...", flush=True)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_path = os.path.expanduser("~/.ssh/id_ed25519")
    key = paramiko.Ed25519Key.from_private_key_file(key_path)

    ssh.connect(
        HOST, port=PORT, username=USER,
        pkey=key,
        timeout=30,
        banner_timeout=60,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    sftp = ssh.open_sftp()
    print("Connected.\n", flush=True)

    os.makedirs(LOCAL_DIR, exist_ok=True)

    for chunk_name, expected_sha256 in CHUNKS.items():
        remote_path = f"{REMOTE_DIR}/{chunk_name}"
        local_path = os.path.join(LOCAL_DIR, chunk_name)
        print(f"[{chunk_name}]")
        ok = download_chunk(sftp, remote_path, local_path, expected_sha256)
        if not ok:
            print(f"FATAL: Could not download {chunk_name}")
            sftp.close()
            ssh.close()
            sys.exit(1)
        print()

    sftp.close()
    ssh.close()

    # Concatenate
    print("Concatenating chunks...")
    with open(OUTPUT_FILE, "wb") as out:
        for chunk_name in CHUNKS:
            chunk_path = os.path.join(LOCAL_DIR, chunk_name)
            with open(chunk_path, "rb") as f:
                while True:
                    data = f.read(8 * 1024 * 1024)
                    if not data:
                        break
                    out.write(data)

    total_size = os.path.getsize(OUTPUT_FILE)
    print(f"Output: {total_size} bytes")

    print("Verifying final SHA256...")
    final_sha = sha256_file(OUTPUT_FILE)
    if final_sha == FINAL_SHA256:
        print(f"SHA256 MATCH: {final_sha}")
        print("SUCCESS")
    else:
        print(f"SHA256 MISMATCH: {final_sha} != {FINAL_SHA256}")
        sys.exit(1)


if __name__ == "__main__":
    main()
