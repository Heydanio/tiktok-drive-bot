#!/usr/bin/env python3
import os, io, json, base64, random, re, unicodedata, subprocess, sys
from pathlib import Path
from datetime import datetime, date
import pytz

# === ENV / Secrets ===
GDRIVE_SA_JSON_B64 = os.environ.get("GDRIVE_SA_JSON_B64", "")
GDRIVE_FOLDER_IDS  = os.environ.get("GDRIVE_FOLDER_IDS", "")  # CSV de folder IDs
TIKTOK_USER        = os.environ.get("TIKTOK_USERNAME", "").strip().lstrip("@")
COOKIE_B64         = os.environ.get("COOKIES_BASE64", "")
FORCE_POST         = os.environ.get("FORCE_POST") == "1"

# === Dossiers ===
STATE_DIR = Path("state"); STATE_DIR.mkdir(exist_ok=True)
COOKIES_DIR = Path("CookiesDir"); COOKIES_DIR.mkdir(exist_ok=True)
TMP_DIR = Path("/tmp"); TMP_DIR.mkdir(exist_ok=True)

# === Google Drive client ===
def build_drive():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    if not GDRIVE_SA_JSON_B64:
        raise RuntimeError("GDRIVE_SA_JSON_B64 manquant")
    sa_json = base64.b64decode(GDRIVE_SA_JSON_B64.encode("utf-8"))
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json.decode("utf-8")),
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

# === Utilitaires état ===
def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# === 4) Nom de fichier safe ===
def safe_filename(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = re.sub(r"[^\w\-. ]", "_", n)
    return n[:150] if len(n) > 150 else n

# === 3) Spintax + hashtags + limite 2200 ===
HASHTAGS_BUCKETS = [
    ["#asterion", "#asmr", "#fr", "#drole"],
    ["#humour", "#fyp", "#france", "#tiktokfr"],
    ["#gaming", "#clips", "#twitch", "#fr"]
]
SPINTAX = [
    "Imagine tu croises ce troubadour {dans la rue|au marché|dans le métro}…",
    "Tu valides ? {oui|non} 👇",
    "J’essaie un {nouveau|autre} format, dis-moi !",
]

def spin_text() -> str:
    s = random.choice(SPINTAX)
    def repl(m):
        return random.choice(m.group(1).split("|"))
    return re.sub(r"\{([^}]+)\}", repl, s)

def build_caption(base_caption: str, desc_hash_set) -> str:
    cap = (base_caption or "").strip()
    # évite doublon exact (via hash)
    if is_desc_duplicate(cap, desc_hash_set):
        cap = f"{spin_text()} {cap}".strip()
    tags = " ".join(random.choice(HASHTAGS_BUCKETS))
    cap = (cap + " " + tags).strip()
    return cap[:2200]

# === 2) Anti-doublons (fichiers + desc) ===
USED_PATH = STATE_DIR / "used.json"
def load_used():
    return load_json(USED_PATH, default={"files": [], "desc_hash": []})

def save_used(u):
    save_json(USED_PATH, u)

def is_desc_duplicate(desc: str, desc_hash_set=None) -> bool:
    import hashlib
    h = hashlib.sha1((desc or "").encode("utf-8")).hexdigest()
    if desc_hash_set is not None:
        return h in desc_hash_set
    u = load_used()
    return h in u.get("desc_hash", [])

def mark_used(file_id: str, desc: str):
    import hashlib
    u = load_used()
    if file_id and file_id not in u["files"]:
        u["files"].append(file_id)
    h = hashlib.sha1((desc or "").encode("utf-8")).hexdigest()
    if h not in u["desc_hash"]:
        u["desc_hash"].append(h)
    save_used(u)

def pick_unique_from_drive(files, used_ids):
    # files: list of {id,name}
    random.shuffle(files)
    for f in files:
        if f["id"] not in used_ids:
            return f
    return None

# === 1) Backoff (saute prochain créneau si 2 fails) ===
FAILS_PATH = STATE_DIR / "fails.json"
def get_fail_state():
    return load_json(FAILS_PATH, default={"consecutive": 0})

def set_fail_state(n):
    save_json(FAILS_PATH, {"consecutive": int(n)})

def backoff_skip_next_slot(schedule):
    # marque le prochain slot non posté comme "posted": True
    for s in schedule.get("slots", []):
        if not s.get("posted"):
            s["posted"] = True
            break
    save_json(STATE_DIR / "schedule.json", schedule)

# === Planning (création si absent) ===
TZ = pytz.timezone("Europe/Paris")
SLOTS_WINDOWS = [(8,9), (11,12), (14,15), (17,18), (20,21)]  # inclusifs sur l'heure de départ, exclusifs sur fin

def today_key():
    return date.today().isoformat()

def gen_today_schedule():
    slots = []
    for h0, h1 in SLOTS_WINDOWS:
        hour = random.randint(h0, h1 - 1)
        minute = random.randint(0, 59)
        slots.append({"hour": hour, "minute": minute, "posted": False})
    return {"day": today_key(), "slots": slots}

def load_schedule():
    sch_path = STATE_DIR / "schedule.json"
    sch = load_json(sch_path, default=None)
    if not sch or sch.get("day") != today_key():
        sch = gen_today_schedule()
        save_json(sch_path, sch)
    return sch

def should_post_now(schedule):
    now = datetime.now(TZ)
    # trouve un slot qui matche heure/minute
    for idx, s in enumerate(schedule.get("slots", [])):
        if not s["posted"] and s["hour"] == now.hour and s["minute"] == now.minute:
            return idx
    return None

# === Cookies ===
def restore_cookies():
    raw = base64.b64decode(COOKIE_B64.encode("utf-8"))
    # nom principal généré par "login -n <user>"
    (COOKIES_DIR / f"tiktok_session-{TIKTOK_USER}.cookie").write_bytes(raw)
    # alias
    (COOKIES_DIR / "main.cookie").write_bytes(raw)
    (COOKIES_DIR / f"{TIKTOK_USER}.cookie").write_bytes(raw)

# === Drive : lister & télécharger ===
def list_drive_files(drive):
    # agrège tous les fichiers des folders donnés
    parents = [p.strip() for p in GDRIVE_FOLDER_IDS.split(",") if p.strip()]
    out = []
    for pid in parents:
        page_token = None
        while True:
            resp = drive.files().list(
                q=f"'{pid}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType,size)",
                pageSize=1000,
                pageToken=page_token
            ).execute()
            out.extend([{"id": f["id"], "name": f["name"]} for f in resp.get("files", [])])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return out

def download_drive_file(drive, file_id, name) -> Path:
    from googleapiclient.http import MediaIoBaseDownload
    request = drive.files().get_media(fileId=file_id)
    # nom local safe
    local = TMP_DIR / safe_filename(name)
    with io.FileIO(local, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024*1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    return local

# === Description de base (ton ancien dictionnaire peut rester) ===
def pick_base_caption() -> str:
    # TODO: branche ton dictionnaire/algorithme à la place si besoin
    candidates = [
        "Vous me le surveillez celui-là original",
        "Imaginez tu croises ce troubadour ASMR dans la rue",
        "On tente un nouveau format, tu valides ?"
    ]
    return random.choice(candidates)

# === Upload via upstream CLI ===
def run_upload(local_path: Path, caption: str):
    # appelle le CLI de l'uploader
    cmd = [
        sys.executable, "upstream/cli.py", "upload",
        "--user", TIKTOK_USER,
        "-v", str(local_path),
        "-t", caption
    ]
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)

# === Main ===
def main():
    # plan du jour + check créneau
    sch = load_schedule()
    slot_idx = should_post_now(sch)
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    if not slot_idx and FORCE_POST:
        # Mode test: forcer un créneau factice
        slot_idx = -1
        print("🧪 FORCE_POST actif — on poste maintenant (test).")
    elif slot_idx is None:
        print(f"⏳ {now} (Paris) — pas l'heure tirée aujourd'hui. Prochain passage…")
        return

    # cookies
    restore_cookies()

    # états anti-doublon / backoff
    used = load_used()
    used_ids = set(used.get("files", []))
    desc_hash_set = set(used.get("desc_hash", []))
    fails = get_fail_state()

    # GDrive → choix d'une vidéo jamais utilisée
    drive = build_drive()
    files = list_drive_files(drive)
    if not files:
        print("⚠️ Aucune vidéo trouvée sur Drive.")
        return
    chosen = pick_unique_from_drive(files, used_ids)
    if not chosen:
        print("ℹ️ Toutes les vidéos ont déjà été utilisées (anti-doublon).")
        return

    print(f"🎯 Vidéo: {chosen['id']} — {chosen['name']}")
    local_path = download_drive_file(drive, chosen["id"], chosen["name"])
    # 4) nom safe déjà appliqué au download
    # description finale 3)
    base_cap = pick_base_caption()
    caption = build_caption(base_cap, desc_hash_set)
    print("📝 Description:", caption)

    try:
        # upload
        run_upload(local_path, caption)

        # succès → marque slot + reset fail + anti-doublons
        if slot_idx != -1:
            sch["slots"][slot_idx]["posted"] = True
            save_json(STATE_DIR / "schedule.json", sch)
        set_fail_state(0)
        mark_used(chosen["id"], caption)
        print("✅ Upload OK — état/plan du jour mis à jour.")
    except subprocess.CalledProcessError as e:
        # échec → backoff si 2 fails d'affilée
        fails["consecutive"] = fails.get("consecutive", 0) + 1
        set_fail_state(fails["consecutive"])
        if fails["consecutive"] >= 2:
            print("🛑 2 échecs consécutifs — on saute le prochain créneau (backoff).")
            backoff_skip_next_slot(sch)
        print(f"❌ Upload échec: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
