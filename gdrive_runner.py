# gdrive_runner.py — Google Drive + 5 créneaux/jour aléatoires (heure FR)
import base64, io, json, os, random, subprocess, sys, tempfile
from pathlib import Path
CLI_PATH = Path("upstream/cli.py") 
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- Secrets/vars d'env ---
FOLDER_IDS   = [s.strip() for s in os.environ["GDRIVE_FOLDER_IDS"].split(",") if s.strip()]
TIKTOK_USER  = os.environ["TIKTOK_USERNAME"]
COOKIE_B64   = os.environ["COOKIES_BASE64"]
SA_JSON_B64  = os.environ["GDRIVE_SA_JSON_B64"]

# --- Descriptions (mets les tiennes ici) ---
DESCRIPTIONS = [
    "Imaginez tu croises ce troubadour ASMR dans la rue #asmr #asterion #feldup",
    "Vous me le surveillez celui-là original #asterion #asmr #pokemon",
]

# --- Fichiers d'état (versionnés) ---
USED_FILE     = Path("state/used.json")      # vidéos déjà utilisées
SCHEDULE_FILE = Path("state/schedule.json")  # tirages horaires du jour

# --- Créneaux quotidiens Europe/Paris ---
PARIS_TZ = ZoneInfo("Europe/Paris")
SLOTS_HOURS   = [8, 11, 14, 17, 20]          # heures FR
MINUTES_GRID  = list(range(0, 60, 5))        # minutes possibles: 0,5,10,...,55

# ============ UTIL ÉTAT ============
def _load_json(path: Path, default):
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: return default
    return default

def _save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def load_used():        return _load_json(USED_FILE, {"used_ids": []})
def save_used(d):       _save_json(USED_FILE, d)
def load_schedule():    return _load_json(SCHEDULE_FILE, {"date": None, "slots": []})
def save_schedule(d):   _save_json(SCHEDULE_FILE, d)

# ============ PLANNING JOURNALIER ============
def ensure_today_schedule():
    today = datetime.now(PARIS_TZ).date().isoformat()
    sch = load_schedule()
    if sch.get("date") != today or not sch.get("slots"):
        random.seed()
        slots = []
        for h in SLOTS_HOURS:
            m = random.choice(MINUTES_GRID)         # minute aléatoire alignée sur */5
            slots.append({"hour": h, "minute": m, "posted": False})
        sch = {"date": today, "slots": slots}
        save_schedule(sch)
    return sch

def should_post_now(sch):
    now = datetime.now(PARIS_TZ)
    for slot in sch["slots"]:
        if not slot["posted"] and now.hour == slot["hour"] and now.minute == slot["minute"]:
            return slot
    return None

def mark_posted(sch, slot):
    slot["posted"] = True
    save_schedule(sch)

# ============ GOOGLE DRIVE ============
def drive_service():
    sa_json = json.loads(base64.b64decode(SA_JSON_B64).decode("utf-8"))
    creds = Credentials.from_service_account_info(sa_json, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_videos_in_folder(svc, folder_id: str) -> List[dict]:
    q = f"'{folder_id}' in parents and trashed=false"
    fields = "files(id,name,mimeType,size,modifiedTime),nextPageToken"
    page_token = None; out = []
    while True:
        resp = svc.files().list(q=q, spaces="drive", fields=f"nextPageToken,{fields}", pageToken=page_token).execute()
        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token: break
    return [f for f in out if f["name"].lower().endswith((".mp4",".mov",".m4v",".webm"))]

def list_all_videos(svc) -> List[dict]:
    allv = []
    for fid in FOLDER_IDS:
        allv.extend(list_videos_in_folder(svc, fid))
    return allv

def pick_one(files: List[dict], used_ids: List[str]) -> dict | None:
    remaining = [f for f in files if f["id"] not in used_ids]
    if not remaining:
        used_ids.clear()                  # tout épuisé -> on repart du début
        remaining = files[:]
    random.shuffle(remaining)
    return remaining[0] if remaining else None

def download_file(svc, file_id: str, dest: Path):
    req = svc.files().get_media(fileId=file_id)
    fh = io.FileIO(dest, "wb")
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"Téléchargement {int(status.progress()*100)}%")

# ============ COOKIES + UPLOAD ============
def restore_cookies():
    Path("CookiesDir").mkdir(exist_ok=True)
    raw = base64.b64decode(COOKIE_B64.encode("utf-8"))
    uname = TIKTOK_USER.strip().lstrip("@")
    # le tien généré par login:
    (Path("CookiesDir") / f"tiktok_session-{uname}.cookie").write_bytes(raw)
    # copié sous d'autres noms possibles:
    (Path("CookiesDir") / "main.cookie").write_bytes(raw)
    (Path("CookiesDir") / f"{uname}.cookie").write_bytes(raw)

def run_upload(local_path: Path, title_desc: str):
    cmd = [sys.executable, str(CLI_PATH), "upload", "--user", TIKTOK_USER, "-v", str(local_path), "-t", title_desc]
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)

# ============ MAIN ============
def main():
    sch = ensure_today_schedule()
    slot = should_post_now(sch)
    # Mode test : forcer le post même si ce n'est pas l'heure tirée
    if not slot and os.environ.get("FORCE_POST") == "1":
        slot = {"hour": 99, "minute": 99, "posted": False}  # créneau factice
    if not slot:
        now = datetime.now(PARIS_TZ)
        print(f"⏳ {now:%Y-%m-%d %H:%M} (Paris) — pas l'heure tirée aujourd'hui. Prochain passage…")
        return

    print(f"🕒 Créneau déclenché: {slot['hour']:02d}:{slot['minute']:02d} (Europe/Paris)")

    used = load_used()
    svc = drive_service()
    files = list_all_videos(svc)
    if not files:
        print("Aucune vidéo trouvée dans le(s) dossier(s) Drive.")
        return

    chosen = pick_one(files, used["used_ids"])
    print(f"🎯 Vidéo: {chosen['name']} ({chosen['id']})")

    tmpdir = Path(tempfile.mkdtemp())
    local = tmpdir / chosen["name"]
    print("⬇️ Téléchargement…"); download_file(svc, chosen["id"], local)

    restore_cookies()
    desc = random.choice(DESCRIPTIONS)
    print(f"📝 Description: {desc}")

    try:
        run_upload(local, desc)
        used["used_ids"].append(chosen["id"]); save_used(used)
        mark_posted(sch, slot)
        print("✅ Upload OK — état/plan du jour mis à jour.")
    except subprocess.CalledProcessError as e:
        print("❌ Upload échec:", e)

if __name__ == "__main__":
    random.seed()
    main()
