"""AP Central Contributions Tracker - 100% free, stdlib only.
Polls Google News RSS (incl. PIB), filters for Andhra Pradesh + central
sanction/approval news, optionally summarises with free Gemini tier,
and alerts via Telegram. Keeps a running ledger.csv."""
import os, re, time, json, csv, hashlib, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# (query, hl, gl, ceid)  -- edit freely
EN = ("en-IN", "IN", "IN:en")
TE = ("te-IN", "IN", "IN:te")
ACTIONS = "(sanctions OR approves OR allots OR releases OR grants)"
MINISTRIES = ["Finance Ministry", "Railways", "NHAI OR Gadkari highway", "Jal Shakti Polavaram",
    "Housing PMAY", "Rural Development", "Agriculture", "Health NHM", "Education Samagra Shiksha",
    "Steel Vizag", "Ports Sagarmala", "Civil Aviation airport", "Power", "Petroleum refinery",
    "Tourism", "Fisheries", "Skill Development", "Textiles", "Defence", "MSME", "Urban Affairs AMRUT",
    "Cabinet decision", "ISRO OR DRDO OR IIT OR AIIMS", "Tribal Affairs", "Environment"]
SCHEMES = ["Amaravati", "Polavaram", "Vizag Steel", "Visakhapatnam Metro", "Kadapa steel",
    "Rayalaseema", "Uttarandhra", "Bullet OR Amrit Bharat railway", "Tax devolution",
    "Special Assistance Capital Investment", "Jal Jeevan Mission", "PM Kisan", "PMGSY",
    "Swachh Bharat", "Smart City", "NDRF OR SDRF flood relief", "World Bank OR ADB loan"]
QUERIES = [("Andhra Pradesh Centre " + a + " crore when:1d", EN)
           for a in ("sanctions", "approves", "allots", "releases funds", "announces package")]
QUERIES += [(f"Andhra Pradesh {m} {ACTIONS} when:1d", EN) for m in MINISTRIES]
QUERIES += [(f"{x} Centre {ACTIONS} when:1d", EN) for x in SCHEMES]
QUERIES += [("site:pib.gov.in Andhra Pradesh when:1d", EN),
            ("site:pib.gov.in Visakhapatnam OR Amaravati OR Tirupati when:1d", EN),
            ("ఆంధ్రప్రదేశ్ కేంద్రం నిధులు మంజూరు when:2d", TE),
            ("కేంద్ర ప్రభుత్వం ఏపీ నిధులు విడుదల when:2d", TE),
            ("అమరావతి పోలవరం కేంద్రం ఆమోదం when:2d", TE)]

# ---- Central schemes: every one gets its own search (English + Telugu) ----
CENTRAL_SCHEMES = [
 "PM Kisan", "PM Kisan Samman Nidhi", "Jal Jeevan Mission", "PM Surya Ghar", "PM Surya Ghar Muft Bijli",
 "PMAY Gramin", "PMAY Urban", "Pradhan Mantri Awas Yojana", "Ayushman Bharat", "PM-JAY", "Ujjwala",
 "Swachh Bharat Mission", "PMGSY rural roads", "MGNREGA", "VB-G RAM G", "PM Fasal Bima", "PM Mudra Yojana",
 "PM Vishwakarma", "PM SVANidhi", "AMRUT 2.0", "Smart Cities Mission", "PM POSHAN mid day meal",
 "Samagra Shiksha", "PM SHRI schools", "National Health Mission", "Garib Kalyan Anna Yojana",
 "RDSS power distribution", "PM KUSUM solar pump", "Kisan Credit Card", "PM Matsya Sampada",
 "Rashtriya Krishi Vikas Yojana", "PM-AASHA MSP procurement", "e-NAM", "PM Gati Shakti", "Bharatmala",
 "Sagarmala", "UDAN airport", "Amrit Bharat Station", "Vande Bharat", "BharatNet", "Digital India",
 "PLI scheme", "Startup India", "PMKVY Skill India", "Atal Pension Yojana", "Jan Dhan", "Mission Shakti",
 "PM E-DRIVE electric bus", "Green Hydrogen Mission", "Swadesh Darshan tourism", "PRASHAD pilgrimage",
 "PM JANMAN tribal", "Eklavya Model Residential School", "Atal Bhujal Yojana", "PMKSY irrigation",
 "Flood Management Border Areas Programme", "PMFME food processing", "PM MITRA textile park",
 "Semiconductor Mission", "Natural Farming Mission", "Rashtriya Gokul Mission", "Agriculture Infrastructure Fund",
 "Aspirational District", "SASCI capital investment", "Finance Commission grant", "Revenue Deficit Grant",
 "Central Sector Scheme", "Centrally Sponsored Scheme", "NDRF relief", "Viksit Bharat", "Deen Dayal Upadhyaya Gram Jyoti",
 "National Highways Authority", "Railway budget Andhra", "Hydropower pumped storage", "Industrial corridor",
 "Defence manufacturing corridor", "Pharma park bulk drug", "Medical college seats", "Kendriya Vidyalaya", "Navodaya Vidyalaya",
]
TELUGU_SCHEMES = [
 "పీఎం కిసాన్", "జల్ జీవన్ మిషన్", "పీఎం సూర్య ఘర్", "ప్రధాన మంత్రి ఆవాస్ యోజన", "ఆయుష్మాన్ భారత్",
 "ఉజ్వల యోజన", "స్వచ్ఛ భారత్", "ఉపాధి హామీ", "ఫసల్ బీమా", "ముద్ర రుణాలు", "విశ్వకర్మ యోజన",
 "అమృత్ పథకం", "స్మార్ట్ సిటీ", "సమగ్ర శిక్ష", "జాతీయ ఆరోగ్య మిషన్", "ఉచిత బియ్యం కేంద్రం",
 "జాతీయ రహదారి మంజూరు", "రైల్వే ప్రాజెక్టు మంజూరు", "కేంద్ర కేబినెట్ ఆమోదం", "కేంద్ర నిధులు విడుదల",
 "పన్నుల వాటా కేంద్రం", "వరద సాయం కేంద్రం", "విమానాశ్రయం కేంద్రం ఆమోదం", "కేంద్రీయ విద్యాలయం",
 "మెడికల్ కాలేజీ కేంద్రం", "పోర్టు కేంద్రం మంజూరు", "సోలార్ పథకం కేంద్రం",
]
QUERIES += [(f"Andhra Pradesh {x} when:1d", EN) for x in CENTRAL_SCHEMES]
QUERIES += [(f"ఆంధ్రప్రదేశ్ {x} when:2d", TE) for x in TELUGU_SCHEMES]
QUERIES += [(f"site:{d} కేంద్రం నిధులు OR మంజూరు OR ఆమోదం when:2d", TE)
            for d in ("eenadu.net", "sakshi.com", "andhrajyothy.com")]
SCHEME_RE = re.compile("|".join(re.escape(x.split(" OR ")[0]) for x in CENTRAL_SCHEMES + TELUGU_SCHEMES), re.I)

# Direct RSS feeds (add more: any RSS URL). Items must still mention AP.
DIRECT_FEEDS = ["https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss"]
AP = re.compile(r"andhra|\bAP\b|amaravati|polavaram|visakhapatnam|vizag|tirupati|vijayawada|"
                r"guntur|kurnool|anantapur|nellore|kakinada|rajahmundry|ఆంధ్ర|ఏపీ|అమరావతి|పోలవరం", re.I)
CENTRE = re.compile(r"sanction|approv|allot|releas|grant|crore|cabinet|centre|union|central|"
                    r"funds|package|devolution|మంజూరు|నిధులు|కేంద్ర", re.I)

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")  # optional, free tier
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_ALERTS = 40

def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def fetch(query, loc):
    time.sleep(0.7)
    if query.startswith("http"):
        url = query
    else:
        hl, gl, ceid = loc
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
               + f"&hl={hl}&gl={gl}&ceid={ceid}")
    try:
        root = ET.fromstring(http(url))
    except Exception as e:
        print("feed error:", query, e); return []
    out = []
    for it in root.iter("item"):
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            pub = datetime.now(timezone.utc)
        out.append({"title": (it.findtext("title") or "").strip(),
                    "link": (it.findtext("link") or "").strip(),
                    "desc": re.sub(r"<[^>]+>", " ", it.findtext("description") or ""),
                    "pub": pub})
    return out

def key(title):
    t = re.sub(r"\s+-\s+[^-]+$", "", title.lower())      # drop " - Source"
    t = re.sub(r"[^a-z0-9\u0c00-\u0c7f ]", "", t)[:70]
    return hashlib.md5(t.encode()).hexdigest()

def gemini(item):
    prompt = ("You track Indian central government support to Andhra Pradesh. Given this news item, "
              "reply ONLY JSON: {\"relevant\": bool (true only if the Union/central govt has "
              "sanctioned/approved/allotted/released something for Andhra Pradesh), \"scheme\": str, "
              "\"amount\": str, \"ministry\": str, \"summary\": str (max 25 words)}.\n\n"
              f"Title: {item['title']}\nText: {item['desc'][:600]}")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json"}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    try:
        r = json.loads(http(url, body, {"Content-Type": "application/json"}))
        return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:
        print("gemini error:", e); return None

def telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        print("[no telegram]", text); return
    body = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    try:
        http(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", body,
             {"Content-Type": "application/x-www-form-urlencoded"})
    except Exception as e:
        print("telegram error:", e)

def main():
    seen = set(json.load(open("seen.json"))) if os.path.exists("seen.json") else set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
    new = {}
    for q, loc in QUERIES + [(u, EN) for u in DIRECT_FEEDS]:
        for it in fetch(q, loc):
            k = key(it["title"])
            blob = it["title"] + " " + it["desc"]
            if k in seen or k in new or it["pub"] < cutoff:
                continue
            pib = "pib.gov.in" in blob.lower() or "PIB" in it["title"]
            if AP.search(blob) and (pib or CENTRE.search(blob) or SCHEME_RE.search(blob)):
                new[k] = it
    items = sorted(new.values(), key=lambda x: x["pub"])[-MAX_ALERTS:]
    rows = []
    for it in items:
        info = gemini(it) if GEMINI_KEY else None
        info = info or {}
        possible = bool(GEMINI_KEY) and info and not info.get("relevant")
        msg = ("🔎 Possible (verify)\n" if possible else "🇮🇳 Centre → AP\n") + it["title"]
        if info.get("summary"):
            msg += f"\n\n{info['summary']}"
        meta = " | ".join(x for x in (info.get("amount"), info.get("scheme"), info.get("ministry")) if x)
        if meta:
            msg += f"\n💰 {meta}"
        telegram(msg + "\n" + it["link"])
        rows.append([it["pub"].strftime("%Y-%m-%d %H:%M"), it["title"], it["link"],
                     info.get("scheme", ""), info.get("amount", ""),
                     info.get("ministry", ""), info.get("summary", "")])
    if rows:
        new_file = not os.path.exists("ledger.csv")
        with open("ledger.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["published_utc", "title", "link", "scheme", "amount", "ministry", "summary"])
            w.writerows(rows)
    seen |= set(new.keys())
    json.dump(list(seen)[-3000:], open("seen.json", "w"))
    print(f"alerts sent: {len(rows)}")

if __name__ == "__main__":
    main()
