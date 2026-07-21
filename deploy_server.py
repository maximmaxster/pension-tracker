"""
deploy_server.py — מעלה pension-tracker ל-Hetzner
"""
import paramiko, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOST    = "78.47.19.201"
USER    = "root"
PASSWORD = "MaximraP1982"
REMOTE  = "/opt/pension_tracker"
LOCAL   = os.path.dirname(os.path.abspath(__file__))

FILES = [
    "fetch_data.py",
    "notify.py",
    "pension.env",
]

def run(ssh, cmd):
    print(f"  $ {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(f"    {out}")
    if err and "warning" not in err.lower(): print(f"    ERR: {err}")
    return out

def deploy():
    print("=" * 50)
    print(f"DEPLOY pension-tracker → {USER}@{HOST}:{REMOTE}")
    print("=" * 50)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("\n1. מתחבר...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("   מחובר ✅")

    print("\n2. מכין תיקייה...")
    run(ssh, f"mkdir -p {REMOTE}/data")
    run(ssh, f"python3 -m venv {REMOTE}/venv 2>/dev/null || true")

    print("\n3. מעלה קבצים...")
    sftp = ssh.open_sftp()
    for fname in FILES:
        lp = os.path.join(LOCAL, fname)
        if os.path.exists(lp):
            sftp.put(lp, f"{REMOTE}/{fname}")
            print(f"   ✅ {fname}")
        else:
            print(f"   ⚠️  {fname} לא נמצא")
    sftp.close()

    print("\n4. מתקין dependencies...")
    run(ssh, f"source {REMOTE}/venv/bin/activate && pip install requests -q")
    print("   ✅")

    print("\n5. מגדיר git...")
    run(ssh, f"cd {REMOTE} && git config --global user.email 'maxim.maxster@gmail.com'")
    run(ssh, f"cd {REMOTE} && git config --global user.name 'Maxim Rapoport'")
    # clone אם עוד לא קיים
    result = run(ssh, f"test -d {REMOTE}/.git && echo yes || echo no")
    if "no" in result:
        run(ssh, f"cd {REMOTE} && git clone https://github.com/maximmaxster/pension-tracker . 2>&1 || true")

    print("\n6. מגדיר Cron (08:00 UTC בכל יום)...")
    cron_line = (
        f"0 8 * * * /bin/bash -c "
        f"'source {REMOTE}/venv/bin/activate && "
        f"cd {REMOTE} && "
        f"python3 {REMOTE}/fetch_data.py >> {REMOTE}/data/fetch_log.txt 2>&1'\n"
    )
    sftp = ssh.open_sftp()
    # קרא crontab קיים
    _, stdout, _ = ssh.exec_command("crontab -l 2>/dev/null || true")
    existing = stdout.read().decode()
    # הסר שורות pension_tracker ישנות
    lines = [l for l in existing.splitlines() if "pension_tracker" not in l]
    lines.append(cron_line.strip())
    new_cron = "\n".join(lines) + "\n"
    with sftp.open("/tmp/pension_cron", "w") as f:
        f.write(new_cron)
    sftp.close()
    run(ssh, "crontab /tmp/pension_cron")
    run(ssh, "crontab -l | grep pension")
    print("   ✅ Cron 08:00 UTC בכל יום")

    print("\n7. ריצת בדיקה (ללא git push / Telegram)...")
    out = run(ssh, f"source {REMOTE}/venv/bin/activate && cd {REMOTE} && python3 -c 'import fetch_data; print(\"import OK\")'")
    if "OK" in out:
        print("   ✅ imports תקינים")

    ssh.close()
    print("\n" + "=" * 50)
    print("DEPLOY COMPLETE ✅")
    print(f"לוג: ssh root@{HOST} 'tail -f {REMOTE}/data/fetch_log.txt'")
    print(f"ריצה ידנית: ssh root@{HOST} 'cd {REMOTE} && source venv/bin/activate && python3 fetch_data.py'")

if __name__ == "__main__":
    try:
        deploy()
    except Exception as e:
        print(f"\n❌ DEPLOY FAILED: {e}")
        sys.exit(1)
