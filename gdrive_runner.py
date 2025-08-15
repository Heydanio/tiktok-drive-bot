# gdrive_runner.py — Google Drive + 5 créneaux/jour aléatoires (heure FR) + planning log + heartbeat
import base64, io, json, os, random, subprocess, sys, tempfile
from pathlib import Path
CLI_PATH = Path("upstream/cli.py")
from typing import List
from datetime import datetime, timedelta
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
    "Ne l'appelez pas Kirby54 svp !! #asterion #live #gtgabi",
    "Non mais vous m'le surveillez lui svp #asmr #asterion",
    "Ceux qui savent ... #savoir #asterion #asmr",
    "Mais Asterion pourquoi tu fais ça ? #asmr #asterion",
    "Il est partout ce troubadour ASMR #asterion #asmr",
    "Trop tard, il est déjà là... #mystere #asterion #feldup",
    "Vous aussi vous avez peur ? #asterion #asmr #curieux",
    "Ça sent le complot #asterion #enquete #mystere",
    "Encore lui ?! #asterion #wtf #pokemon",
    "Le roi du ASMR sauvage #asterion #asmr #chuchotement",
    "Ne clignez pas des yeux... #asterion #asmr #hypnose",
    "Un phénomène inexpliqué #asterion #mystere #paranormal",
    "Si vous voyez ça, c'est trop tard #asterion #asmr #surprise",
    "Le pouvoir du son... #asmr #asterion #vibration",
    "Vous reconnaissez ce bruit ? #asterion #asmr #detective",
    "Ne sous-estimez jamais un troubadour #asterion #chanson #asmr",
    "Asterion en pleine performance ! #asterion #asmr #live",
    "Un air bien mystérieux... #asterion #asmr #enigme",
    "Ce n’est pas un rêve… #asterion #illusion #asmr",
    "Derrière chaque son se cache un secret… #asterion #mystere #asmr",
    "Le silence avant la tempête #asterion #tension #asmr",
    "Un chant venu d’ailleurs… #asterion #paranormal #asmr",
    "Si tu entends ça, fuis ! #asterion #warning #asmr",
    "La magie du son… #asterion #hypnose #asmr",
    "Peut-être que tu l’entends déjà… #asterion #fantome #asmr",
    "Tu crois connaître la vérité ? #asterion #illusion #asmr",
    "Un monde étrange, guidé par la musique #asterion #mystere #asmr",
    "Des bruits de l’au-delà… #asterion #fantomatique #asmr",
    "Le mystère se cache dans chaque vibration #asterion #surprise #asmr",
    "C’est le chant des anciens… #asterion #musique #asmr",
    "Un souffle de terreur #asterion #suspense #asmr",
    "Tu n’as aucune idée de ce qui t’attend… #asterion #mystere #asmr",
    "Ce son va te suivre toute ta vie #asterion #hypnose #asmr",
    "Si tu vois cette lumière, c’est déjà trop tard #asterion #warning #asmr",
    "Il est là, dans l’ombre… #asterion #suspense #asmr",
    "Qu’est-ce qui se cache derrière ce bruit ? #asterion #mystere #asmr",
    "Un étrange personnage, un étrange bruit… #asterion #fantome #asmr",
    "Chaque note de musique te rapproche du secret #asterion #musique #asmr",
    "Les bruits qui hantent ton esprit #asterion #psychose #asmr",
    "Un murmure dans l’obscurité #asterion #peur #asmr",
    "Faites attention à ce bruit… #asterion #surprise #asmr",
    "C’est tout un univers sonore qui s’ouvre devant toi #asterion #exploration #asmr",
    "Un son envoûtant #asterion #hypnose #asmr",
    "Le dernier avertissement #asterion #warning #asmr",
    "Un bruit mystérieux juste derrière toi… #asterion #peur #asmr",
    "Regarde bien, écoute bien… #asterion #mystere #asmr",
    "Un son qui éveille tes sens #asterion #exploration #asmr",
    "Suis la musique, si tu oses… #asterion #voyage #asmr",
    "Un ASMR venu du futur #asterion #voyageur #asmr",
    "Est-ce que tu entends ça aussi ? #asterion #curieux #asmr",
    "Ne laisse personne t’empêcher d’écouter ce son #asterion #liberté #asmr",
    "Les sons qui cachent des vérités #asterion #mystere #asmr",
    "Il y a quelque chose de spécial dans ce bruit… #asterion #enquête #asmr",
    "Un phénomène inexplicable #asterion #mystere #asmr",
    "Chaque vibration te guide vers la vérité #asterion #voyage #asmr",
    "Tu es sur le point de découvrir un secret #asterion #mystere #asmr",
    "Il te parle à travers les sons… #asterion #enquête #asmr",
    "Un moment hors du temps… #asterion #hypnose #asmr",
    "Fais attention, il pourrait te suivre… #asterion #peur #asmr",
    "Un murmure dans l’ombre #asterion #mystere #asmr",
    "Quelqu’un te regarde à travers les bruits #asterion #surveillance #asmr",
    "Les sons qui créent des mondes #asterion #immersion #asmr",
    "Un bruit, une menace #asterion #danger #asmr",
    "Un tourbillon sonore #asterion #hypnose #asmr",
    "Il n’y a pas de retour en arrière #asterion #mystere #asmr",
    "Une vibration étrange dans l’air… #asterion #suspense #asmr",
    "L’ASMR peut-il vraiment guérir ? #asterion #therapie #asmr",
    "Suivez les traces sonores #asterion #exploration #asmr",
    "Le mystère de l’ASMR révélé #asterion #enquête #asmr",
    "Un son que personne ne devrait entendre… #asterion #danger #asmr",
    "Une série de bruits qui te déstabilisent #asterion #psychose #asmr",
    "L’ASMR peut-il changer le cours des choses ? #asterion #question #asmr",
    "Il est venu te chercher… #asterion #suspense #asmr",
    "Les secrets des troubadours #asterion #musique #asmr",
    "Un bruit familier mais terrifiant #asterion #peur #asmr",
    "Les ombres se lèvent avec ce bruit #asterion #suspense #asmr",
    "Un chant étrange pour éveiller ton âme #asterion #mysticisme #asmr",
    "Quel est ce bruit qui te hante ? #asterion #mystere #asmr",
    "Les sons d’un autre monde #asterion #enquête #asmr",
    "Ce son a un pouvoir mystérieux #asterion #puissance #asmr",
    "Soudain, il n’y a plus de doute #asterion #révélation #asmr",
    "C’est la fin du silence #asterion #bruit #asmr",
    "Ce bruit te fait-il peur ? #asterion #surprise #asmr",
    "Chaque vibration te rapproche d’une vérité cachée #asterion #mystere #asmr",
    "Un phénomène que tu ne peux pas ignorer #asterion #mystère #asmr",
    "Il y a toujours un bruit avant la tempête #asterion #tension #asmr",
    "Un ASMR hypnotique, presque magique #asterion #hypnose #asmr",
    "Les réponses sont dans le son… #asterion #enquête #asmr",
    "Le chant du troubadour dans l’obscurité #asterion #mystere #asmr",
    "Ce bruit va te suivre jusqu’à ton dernier souffle… #asterion #danger #asmr",
    "Un écho dans la nuit #asterion #suspense #asmr",
    "Les sons qui transforment ton esprit #asterion #illusion #asmr",
    "La vérité se cache dans le son #asterion #mystere #asmr",
    "La vibration d’une nouvelle ère #asterion #exploration #asmr",
    "Il y a toujours une clé dans le bruit #asterion #solution #asmr",
    "Les murmures qui prévoient l’avenir #asterion #vision #asmr",
    "Un bruit, une énigme #asterion #mystere #asmr",
    "Les sons qui sculptent la réalité #asterion #perception #asmr",
    "Tout commence par une vibration #asterion #vibration #asmr",
    "Le calme avant le choc #asterion #tension #asmr",
    "Les murmures du passé #asterion #histoire #asmr",
    "Tu entends ce qu’il se passe là ? #asterion #curieux #asmr",
    "Ne sous-estime pas ce bruit #asterion #perception #asmr",
    "Tu es prêt pour la révélation ? #asterion #révélation #asmr",
    "Un son étrange, trop réel… #asterion #hypnose #asmr",
    "Les murmures qui transforment #asterion #psychose #asmr",
    "L’ASMR change tout… #asterion #changement #asmr",
    "Le pouvoir du son, plus fort que tout #asterion #vibration #asmr",
    "Un phénomène qui te dépasse #asterion #incompréhension #asmr",
    "Chaque bruit est une piste #asterion #détective #asmr",
    "Les sons qui révèlent la vérité cachée #asterion #mystere #asmr",
    "Une vibration qui te guide #asterion #intuition #asmr",
    "Le son d’un autre monde #asterion #autre #asmr",
    "Les bruits qui résonnent dans l’espace #asterion #voyage #asmr",
    "Un bruit étrange, mais réel #asterion #surprise #asmr",
    "Peu importe ce que tu crois… le son est là #asterion #réalité #asmr",
    "Un monde étrange, entre l’ombre et la lumière #asterion #exploration #asmr",
    "Ce bruit te lie à quelque chose d’invisible #asterion #mystere #asmr",
    "L'ASMR révèle des secrets bien cachés #asterion #secret #asmr",
    "Ne laisse pas ce son te perdre… #asterion #hypnose #asmr",
    "Les sons qui rendent fou #asterion #folie #asmr",
    "Les ombres murmurent à travers ce bruit #asterion #mystere #asmr",
    "L’ASMR a un pouvoir mystérieux… #asterion #magie #asmr",
    "C’est l’instant avant l'explosion de son #asterion #tension #asmr",
    "Un bruit venu d’ailleurs #asterion #autrefois #asmr",
    "Tant que tu n’entends pas ça, tu n’as rien compris… #asterion #révélation #asmr",
    "Le pouvoir de l’ombre se cache dans ce son… #asterion #mystère #asmr",
    "Un son qui t’éveille à la vérité #asterion #réalité #asmr",
    "Un bruit que tu ne peux pas ignorer #asterion #instinct #asmr",
    "Tu es sur le point de percer le mystère #asterion #exploration #asmr",
    "Les sons qui vont te hanter #asterion #peur #asmr",
    "C’est un voyage sonore comme tu n’en as jamais vécu #asterion #voyage #asmr",
    "Ce bruit te parle directement… #asterion #hypnose #asmr",
    "Ce n'est qu'un début… #asterion #mystere #asmr",
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
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def load_used():
    return _load_json(USED_FILE, {"used_ids": []})

def save_used(d):
    _save_json(USED_FILE, d)

def load_schedule():
    return _load_json(SCHEDULE_FILE, {"date": None, "slots": []})

def save_schedule(d):
    _save_json(SCHEDULE_FILE, d)

# ============ PLANNING JOURNALIER ============
def ensure_today_schedule():
    today = datetime.now(PARIS_TZ).date().isoformat()
    sch = load_schedule()
    if sch.get("date") != today or not sch.get("slots"):
        random.seed()
        slots = []
        for h in SLOTS_HOURS:
            m = random.choice(MINUTES_GRID)  # minute aléatoire alignée sur */5
            slots.append({"hour": h, "minute": m, "posted": False})
        sch = {"date": today, "slots": slots}
        save_schedule(sch)
        # LOG du planning du jour (lisible)
        picked = ", ".join(f"{s['hour']:02d}:{s['minute']:02d}" for s in slots)
        print(f"📅 Planning du {today} (Europe/Paris) → {picked}")
    return sch

GRACE_MINUTES = 10  # tolérance pour le jitter GitHub Actions (5 min + marge)

def should_post_now(sch):
    now = datetime.now(PARIS_TZ)
    today = now.date()
    for slot in sch["slots"]:
        if slot.get("posted"):
            continue
        # datetime du slot aujourd'hui
        slot_dt = datetime(
            year=today.year, month=today.month, day=today.day,
            hour=slot["hour"], minute=slot["minute"], tzinfo=PARIS_TZ
        )
        # On poste si on est à l'heure OU dans la fenêtre de grâce
        if slot_dt <= now < (slot_dt + timedelta(minutes=GRACE_MINUTES)):
            # info utile si on est en léger retard
            delay = int((now - slot_dt).total_seconds() // 60)
            if delay > 0:
                print(f"⏱️ Créneau rattrapé avec {delay} min de retard (tolérance {GRACE_MINUTES} min).")
            return slot
    return None

def mark_posted(sch, slot):
    slot["posted"] = True
    save_schedule(sch)

# ============ GOOGLE DRIVE ============
def drive_service():
    sa_json = json.loads(base64.b64decode(SA_JSON_B64).decode("utf-8"))
    creds = Credentials.from_service_account_info(
        sa_json, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_videos_in_folder(svc, folder_id: str) -> List[dict]:
    q = f"'{folder_id}' in parents and trashed=false"
    fields = "files(id,name,mimeType,size,modifiedTime),nextPageToken"
    page_token = None
    out = []
    while True:
        resp = svc.files().list(
            q=q, spaces="drive", fields=f"nextPageToken,{fields}", pageToken=page_token
        ).execute()
        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return [f for f in out if f["name"].lower().endswith((".mp4", ".mov", ".m4v", ".webm"))]

def list_all_videos(svc) -> List[dict]:
    allv = []
    for fid in FOLDER_IDS:
        allv.extend(list_videos_in_folder(svc, fid))
    return allv

def pick_one(files: List[dict], used_ids: List[str]) -> dict | None:
    remaining = [f for f in files if f["id"] not in used_ids]
    if not remaining:
        used_ids.clear()  # tout épuisé -> on repart du début
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
            print(f"Téléchargement {int(status.progress() * 100)}%")

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

    # Heartbeat pour vérifier que le cron tourne (affiché à chaque run)
    now = datetime.now(PARIS_TZ)
    print(f"🫀 Passage cron: {now:%Y-%m-%d %H:%M:%S} (Europe/Paris)")

    slot = should_post_now(sch)
    # Mode test : forcer le post même si ce n'est pas l'heure tirée
    if not slot and os.environ.get("FORCE_POST") == "1":
        slot = {"hour": 99, "minute": 99, "posted": False}  # créneau factice

    if not slot:
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
    if not chosen:
        print("Toutes les vidéos disponibles ont déjà été utilisées aujourd'hui.")
        return

    print(f"🎯 Vidéo: {chosen['name']} ({chosen['id']})")

    tmpdir = Path(tempfile.mkdtemp())
    local = tmpdir / chosen["name"]
    print("⬇️ Téléchargement…")
    download_file(svc, chosen["id"], local)

    restore_cookies()
    desc = random.choice(DESCRIPTIONS)
    print(f"📝 Description: {desc}")

    try:
        run_upload(local, desc)
        used["used_ids"].append(chosen["id"])
        save_used(used)
        mark_posted(sch, slot)
        print("✅ Upload OK — état/plan du jour mis à jour.")
    except subprocess.CalledProcessError as e:
        print("❌ Upload échec:", e)

if __name__ == "__main__":
    random.seed()
    main()
