#!/usr/bin/env python3
"""Mit Dashboard v6 — drag/resize/reorder"""

import os
import html as html_module, json, re, sys
import urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ═══════════════════════════════════════════════════════
#  KONFIGURATION
# ═══════════════════════════════════════════════════════

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
UPNOTE_URL = "upnote://x-callback-url/openNote?noteId=c7369867-5ba5-4aa0-a3ae-75f152365d17"

CALENDARS = {
    "Gmail":   {"url": os.environ.get("CALENDAR_GMAIL_URL", ""),
                "color": "#a78bfa", "order": 0},
    "Arbejde": {"url": os.environ.get("CALENDAR_WORK_URL", ""),
                "color": "#60a5fa", "order": 1},
}

REDDIT_SUBS      = ["Denmark", "worldnews", "soccer"]
REDDIT_LIMIT     = 18
FOOTBALL_LEAGUES = {"Premier League": "PL", "Champions League": "CL"}
FOOTBALL_DAYS    = 14
NEWS_FEEDS = {
    "dk":     ["https://www.dr.dk/nyheder/service/feeds/allenyheder",
               "https://feeds.tv2.dk/nyheder/rss"],
    "verden": ["https://feeds.bbci.co.uk/news/world/rss.xml",
               "https://www.theguardian.com/world/rss"],
}
CAL_PREVIEW    = 4
REDDIT_PREVIEW = 8
MATCH_PREVIEW  = 6
DRTV_PREVIEW   = 8

LOCAL_TZ  = ZoneInfo("Europe/Copenhagen")
DATA_DIR  = Path("output")
HTML_FILE = DATA_DIR / "index.html"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}")
DK_WEEKDAYS = {0:"Mandag",1:"Tirsdag",2:"Onsdag",3:"Torsdag",
               4:"Fredag",5:"Lørdag",6:"Søndag"}
DK_MONTHS   = {1:"januar",2:"februar",3:"marts",4:"april",5:"maj",6:"juni",
               7:"juli",8:"august",9:"september",10:"oktober",11:"november",12:"december"}

# ═══════════════════════════════════════════════════════
#  HJÆLPERE
# ═══════════════════════════════════════════════════════

def esc(s): return html_module.escape(str(s) if s is not None else "")
def dk_date(d): return f"{DK_WEEKDAYS[d.weekday()]} d. {d.day}. {DK_MONTHS[d.month]}"

def fetch_url(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={**(headers or {}), "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()

def post_json(url, payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def gemini(prompt, temp=0.5):
    try:
        resp = post_json(GEMINI_URL, {
            "contents": [{"role":"user","parts":[{"text":prompt}]}],
            "generationConfig": {"temperature": temp},
        })
        text = "".join(p.get("text","") for p in
            resp.get("candidates",[{}])[0].get("content",{}).get("parts",[]))
        return re.sub(r"```.*?```","",text,flags=re.DOTALL).strip()
    except urllib.error.HTTPError as e:
        print(f"  Gemini {e.code}: {e.read().decode()[:80]}"); return ""

def gemini_grounded(prompt, temp=0.6):
    """Gemini med Google Search, så den kan finde aktuelle begivenheder."""
    try:
        resp = post_json(GEMINI_URL, {
            "contents": [{"role":"user","parts":[{"text":prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": temp},
        })
        text = "".join(p.get("text","") for p in
            resp.get("candidates",[{}])[0].get("content",{}).get("parts",[]))
        return re.sub(r"```.*?```","",text,flags=re.DOTALL).strip()
    except urllib.error.HTTPError as e:
        print(f"  Gemini (søg) {e.code}: {e.read().decode()[:80]}")
        return ""
    except Exception as e:
        print(f"  Gemini (søg): {e}")
        return ""
    except Exception as e:
        print(f"  Gemini: {e}"); return ""

def safe_prose(t):
    if not t: return ""
    # Konverter Markdown-fed **tekst** til <strong> (Gemini bruger nogle gange Markdown)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    def md_link(m):
        txt = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip()
        # Drop meningsløse links hvor teksten kun er tegnsætning/entity
        # (fx Geminis "[\'](url)" — en kodet apostrof)
        plain = re.sub(r'&[#a-zA-Z0-9]+;', '', txt)   # fjern HTML-entities
        plain = re.sub(r'[^\w\sÆØÅæøå]', '', plain).strip()
        if len(plain) < 2:
            return txt   # behold kun teksten, smid linket væk
        return f'<a href="{url}" target="_blank" rel="noopener">{txt}</a>'
    # Konverter Markdown-links [tekst](url) til <a> (Gemini bruger nogle gange Markdown)
    t = re.sub(r'\[([^\]]*)\]\((https?://[^\s)]+)\)', md_link, t)
    # Normalisér eksisterende <a>-tags (uden at dobbelt-escape)
    s = re.sub(r'<a\s+href=["\']([^"\'<>]+)["\'][^>]*>(.*?)</a>',
        lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(2)}</a>',
        t, flags=re.DOTALL)
    # Sidste sikkerhedsnet: fjern enhver resterende rå Markdown-link-syntaks
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    # Behold a, ul, li, span, strong, b; strip resten
    return re.sub(r'<(?!/?(?:a|ul|li|span|strong|b)\b)[^>]+>','',s)

# ═══════════════════════════════════════════════════════
#  DATA FETCHING
# ═══════════════════════════════════════════════════════

def fetch_rss(url, n=8):
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(fetch_url(url))
        items = []
        for item in root.findall(".//item"):
            t = re.sub(r"<[^>]+>","",re.sub(r"<!\[CDATA\[(.*?)\]\]>",r"\1",
                (item.findtext("title") or ""),flags=re.DOTALL)).strip()
            l = (item.findtext("link") or "").strip()
            if t: items.append((t,l))
            if len(items)>=n: break
        return items
    except: return []

def fetch_news():
    dk = sum([fetch_rss(u) for u in NEWS_FEEDS["dk"]], [])
    wo = sum([fetch_rss(u) for u in NEWS_FEEDS["verden"]], [])
    def clean_title(t):
        # Fjern eventuelle Markdown-rester (fx [tekst](url) eller løse [ ] ( ))
        t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)   # [tekst](url) -> tekst
        t = re.sub(r'[\[\]]', '', t)                         # løse klammer væk
        return t.strip()
    def headline_list(items):
        # Liste med klikbare overskrifter (dem der IKKE er nævnt i prosaen)
        rows = []
        for t,l in items:
            t = clean_title(t)
            if not t: continue
            if l:
                rows.append(f'<li><a href="{esc(l)}" target="_blank" rel="noopener">{esc(t)}</a></li>')
            else:
                rows.append(f'<li>{esc(t)}</li>')
        if not rows: return ""
        return f'<ul class="news-headlines">{"".join(rows)}</ul>'
    def summ(items, label, greet):
        if not items: return ""
        # Prosaen dækker de 5 vigtigste; listen viser de NÆSTE 6 (ingen dubletter)
        prose_items = items[:5]
        list_items  = items[5:11]
        block = "\n".join(f"{i+1}. {t} | LINK: {l}" for i,(t,l) in enumerate(prose_items))
        intro = "Begynd direkte med nyhederne, ingen hilsen"
        r = gemini(f"Dansk nyhedsassistent. Overskrifter fra {label}:\n{block}\n\n"
            f"Skriv 4-6 sætninger om de vigtigste nyheder med lidt mere uddybning. "
            f"Integrer kilde-links direkte i teksten som HTML-tags på formen "
            f'<a href="URL">tekst</a>. Brug ALDRIG Markdown-links som [tekst](url). '
            f"Fremhæv de vigtigste nøgleord (navne, steder, tal, centrale begreber) "
            f"ved at omkranse dem med <strong>...</strong>. Fremhæv kun nogle få ord "
            f"pr. sætning, ikke hele sætninger. "
            f"{intro}. Neutral tone. Kun ren tekst, <a>- og <strong>-tags, ingen overskrifter.", 0.4)
        summary = r or " · ".join(
            f'<a href="{esc(l)}" target="_blank">{esc(clean_title(t))}</a>' if l else esc(clean_title(t))
            for t,l in prose_items)
        # Opsummering først, derefter liste med ANDRE nyheder (ikke dem i prosaen)
        return f'<span class="news-summary">{summary}</span>{headline_list(list_items)}'
    print("  Nyheder OK")
    return summ(dk,"Danmark",True), summ(wo,"Verden",False)

# ═══════════════════════════════════════════════════════
#  📚 WIKIPEDIA — dagens artikel + "on this day"
# ═══════════════════════════════════════════════════════
def fetch_wikipedia_featured(now_local):
    """Henter dagens engelske Wikipedia-artikel + historiske begivenheder."""
    y, m, d = now_local.year, now_local.month, now_local.day
    url = (f"https://en.wikipedia.org/api/rest_v1/feed/featured/"
           f"{y:04d}/{m:02d}/{d:02d}")
    headers = {"Accept": "application/json"}
    result = {"tfa": None, "onthisday": []}
    try:
        data = json.loads(fetch_url(url, headers=headers))
    except Exception as e:
        print(f"  Wikipedia: {e}")
        return result

    # Dagens udvalgte artikel (Today's Featured Article)
    tfa = data.get("tfa") or {}
    if tfa:
        thumb = (tfa.get("thumbnail") or {}).get("source", "")
        result["tfa"] = {
            "title":   tfa.get("titles", {}).get("normalized") or tfa.get("title", ""),
            "extract": tfa.get("extract", ""),
            "url":     (tfa.get("content_urls", {}).get("desktop", {}).get("page", "")),
            "image":   thumb,
        }

    # Historiske begivenheder "on this day"
    for ev in (data.get("onthisday") or [])[:40]:
        year = ev.get("year")
        text = ev.get("text", "")
        # Find et Wikipedia-link til begivenheden (første tilknyttede side)
        link = ""
        for pg in (ev.get("pages") or []):
            u = (pg.get("content_urls", {}).get("desktop", {}).get("page", ""))
            if u:
                link = u; break
        if year and text:
            result["onthisday"].append({"year": year, "text": text, "url": link})
    # Sortér nyeste først, og behold et udvalg
    result["onthisday"].sort(key=lambda e: e["year"], reverse=True)

    print(f"  Wikipedia: artikel={'ja' if result['tfa'] else 'nej'}, "
          f"begivenheder={len(result['onthisday'])}")
    return result


# ═══════════════════════════════════════════════════════
#  🌙 ASTRONOMI — månefase + sol op/ned
# ═══════════════════════════════════════════════════════
def fetch_astronomy(now_local, lat=55.6761, lon=12.5683):
    """Henter solopgang/-nedgang fra Open-Meteo og beregner månefase lokalt."""
    info = {"sunrise": "", "sunset": "", "moon_phase": "", "moon_icon": ""}
    # Sol op/ned
    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               "&daily=sunrise,sunset&timezone=Europe%2FCopenhagen&forecast_days=1")
        data = json.loads(fetch_url(url))
        sr = data["daily"]["sunrise"][0]   # "2026-06-04T04:31"
        ss = data["daily"]["sunset"][0]
        info["sunrise"] = sr[11:16]
        info["sunset"]  = ss[11:16]
    except Exception as e:
        print(f"  Astronomi (sol): {e}")

    # Månefase — beregnes ud fra en kendt nymåne (matematisk, ingen API)
    try:
        # Kendt nymåne: 6. januar 2000, 18:14 UTC
        known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
        synodic = 29.530588853  # gennemsnitlig månecyklus i dage
        now_utc = now_local.astimezone(timezone.utc)
        days = (now_utc - known_new).total_seconds() / 86400.0
        phase = (days % synodic) / synodic  # 0..1
        # Oversæt til fasenavn + emoji
        phases = [
            (0.03, "Nymåne", "🌑"),
            (0.22, "Tiltagende segl", "🌒"),
            (0.28, "Første kvarter", "🌓"),
            (0.47, "Tiltagende måne", "🌔"),
            (0.53, "Fuldmåne", "🌕"),
            (0.72, "Aftagende måne", "🌖"),
            (0.78, "Sidste kvarter", "🌗"),
            (0.97, "Aftagende segl", "🌘"),
            (1.01, "Nymåne", "🌑"),
        ]
        for limit, name, icon in phases:
            if phase < limit:
                info["moon_phase"] = name
                info["moon_icon"]  = icon
                break
    except Exception as e:
        print(f"  Astronomi (måne): {e}")

    print(f"  Astronomi: sol {info['sunrise']}–{info['sunset']}, "
          f"måne {info['moon_phase']}")
    return info


# ═══════════════════════════════════════════════════════
#  ✨ SJOVE FAKTA om dagen (AI-genereret)
# ═══════════════════════════════════════════════════════
def fetch_fun_facts(now_local, onthisday=None):
    """Finder AKTUELLE interessante begivenheder der sker i dag (via søgning)."""
    dato = f"{now_local.day}. {DK_MONTHS[now_local.month]} {now_local.year}"
    r = gemini_grounded(
        f"I dag er det {dato}. Brug søgning til at finde 4-5 aktuelle, "
        f"interessante ting der sker eller er sket netop i dag eller for nylig "
        f"— både i Danmark og i verden. "
        f"Det kan fx være: politiske begivenheder (nye ministre, valg, lovforslag), "
        f"vigtige sportsbegivenheder (kampe der spilles i dag, resultater), "
        f"kultur, videnskab, økonomi, eller store internationale hændelser. "
        f"Fokusér på NUTIDEN — ting der er relevante lige nu, IKKE historiske "
        f"begivenheder fra tidligere år. "
        f"Skriv på letforståeligt dansk. Hver ting som ét kort punkt. "
        f"Brug punktopstilling med <li>-tags inde i en <ul>. "
        f"Ingen overskrift, kun listen. Ingen markdown, ingen kildehenvisninger.", 0.5)
    # Hvis søgning fejler, så lad feltet være tomt (ingen historiske dubletter)
    return r or ""

def translate_onthisday(events):
    """Oversætter Wikipedia 'on this day'-tekster til dansk via Gemini."""
    if not events:
        return events
    numbered = "\n".join(f"{i+1}. {e['text']}" for i, e in enumerate(events))
    r = gemini(
        f"Oversæt disse historiske begivenheder til klart, letforståeligt dansk. "
        f"Behold samme nummerering, én linje per begivenhed, ingen ekstra tekst:\n{numbered}",
        0.3)
    if not r:
        return events  # behold engelsk hvis oversættelse fejler
    # Parsér nummererede linjer tilbage
    lines = {}
    for line in r.split("\n"):
        mm = re.match(r"\s*(\d+)[.)]\s*(.+)", line)
        if mm:
            lines[int(mm.group(1))] = mm.group(2).strip()
    out = []
    for i, e in enumerate(events):
        txt = lines.get(i+1, e["text"])
        out.append({**e, "text": txt})
    return out


def summarize_day(cal_today, now_local, astro=None):
    if not cal_today: block = "Ingen begivenheder."
    else:
        rows = []
        for ev in cal_today:
            tid = ("Hele dagen" if ev["all_day"] else
                ev["start"].strftime("%H:%M") +
                ("–"+ev["end"].strftime("%H:%M")
                 if ev["end"] and isinstance(ev["end"],datetime) else ""))
            loc = f" ({ev['location']})" if ev.get("location") else ""
            rows.append(f"- {tid}: {ev['summary']}{loc} [{ev['calendar']}]")
        block = "\n".join(rows)
    # Sol og måne til at væve naturligt ind i teksten
    sky = ""
    astro = astro or {}
    sky_bits = []
    if astro.get("sunrise") and astro.get("sunset"):
        sky_bits.append(f"solen står op {astro['sunrise']} og går ned {astro['sunset']}")
    if astro.get("moon_phase"):
        sky_bits.append(f"månen er i fasen '{astro['moon_phase'].lower()}'")
    if sky_bits:
        sky = "Astronomi i dag: " + ", ".join(sky_bits) + "."
    r = gemini(f"Du er Philips assistent. I dag: {dk_date(now_local.date())} {now_local.year}.\n"
               f"Kalender:\n{block}\n{sky}\n\n3-4 sætninger. Nævn HVERT møde med præcist navn og tid. "
               "Væv også solopgang/solnedgang og månefasen naturligt ind i teksten som prosa. "
               "Begynd 'Hej Philip, '. Afslut opmuntrende. Ingen markdown.", 0.6)
    if r: return r
    if not cal_today:
        return f"Hej Philip, ingen begivenheder i dag. God {DK_WEEKDAYS[now_local.weekday()].lower()}!"
    parts = [f"{ev['summary']} ({'hele dagen' if ev['all_day'] else ev['start'].strftime('%H:%M')})"
             for ev in cal_today]
    return "Hej Philip, i dag har du: " + ", ".join(parts) + ". God arbejdslyst!"

def fetch_calendar_events():
    try:
        import icalendar, recurring_ical_events
    except ImportError:
        return [], ["icalendar ikke installeret"]
    now   = datetime.now(LOCAL_TZ)
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=LOCAL_TZ)
    end   = start + timedelta(days=3)
    all_events, errors = [], []
    for cal_name, info in CALENDARS.items():
        try:
            cal = icalendar.Calendar.from_ical(fetch_url(info["url"]))
            evs = recurring_ical_events.of(cal).between(start, end)
        except Exception as e:
            errors.append(f"{cal_name}: {e}"); continue
        for e in evs:
            dt_s = e.get("DTSTART")
            if dt_s is None: continue
            raw_s = dt_s.dt
            if isinstance(raw_s, datetime):
                if raw_s.tzinfo is None: raw_s = raw_s.replace(tzinfo=timezone.utc)
                sv, all_day = raw_s.astimezone(LOCAL_TZ), False
            elif isinstance(raw_s, date): sv, all_day = raw_s, True
            else: continue
            dt_e = e.get("DTEND"); ev_end = None
            if dt_e:
                re_ = dt_e.dt
                if isinstance(re_, datetime):
                    if re_.tzinfo is None: re_ = re_.replace(tzinfo=timezone.utc)
                    ev_end = re_.astimezone(LOCAL_TZ)
                elif isinstance(re_, date): ev_end = re_
            loc = re.sub(r"https?://\S+","",str(e.get("LOCATION",""))).strip(" ,;|·")[:80]
            all_events.append({
                "calendar":cal_name, "color":info["color"], "cal_order":info["order"],
                "summary":str(e.get("SUMMARY","")).strip() or "(uden titel)",
                "location":loc, "start":sv, "end":ev_end, "all_day":all_day,
            })
        print(f"  Kalender {cal_name}: OK")
    all_events.sort(key=lambda ev:(
        ev["start"] if isinstance(ev["start"],date) and not isinstance(ev["start"],datetime)
        else ev["start"].date(),
        0 if ev["all_day"] else 1, ev["cal_order"],
        datetime.min if ev["all_day"] else ev["start"]))
    return all_events, errors

def events_for_day(events, d):
    def ev_date(ev):
        s = ev["start"]
        return s if isinstance(s,date) and not isinstance(s,datetime) else s.date()
    return [e for e in events if ev_date(e)==d]

def fetch_football():
    now=datetime.now(LOCAL_TZ); df=now.date().isoformat()
    dt=(now.date()+timedelta(days=FOOTBALL_DAYS)).isoformat()
    hdrs={"X-Auth-Token":FOOTBALL_API_KEY}
    matches,errors=[],[]
    for name,code in FOOTBALL_LEAGUES.items():
        try:
            data=json.loads(fetch_url(
                f"https://api.football-data.org/v4/competitions/{code}/matches"
                f"?dateFrom={df}&dateTo={dt}",headers=hdrs))
            for m in data.get("matches",[]):
                try: dt2=datetime.fromisoformat(m.get("utcDate","").replace("Z","+00:00")).astimezone(LOCAL_TZ)
                except: dt2=None
                sc=m.get("score",{}).get("fullTime",{})
                matches.append({"league":name,"dt":dt2,
                    "home":(m.get("homeTeam") or {}).get("shortName") or (m.get("homeTeam") or {}).get("name","?"),
                    "away":(m.get("awayTeam") or {}).get("shortName") or (m.get("awayTeam") or {}).get("name","?"),
                    "status":m.get("status",""),"score_home":sc.get("home"),"score_away":sc.get("away")})
        except urllib.error.HTTPError as e: errors.append(f"{name}: HTTP {e.code}")
        except Exception as e: errors.append(f"{name}: {e}")
    matches.sort(key=lambda m: m["dt"] or datetime.max.replace(tzinfo=LOCAL_TZ))
    print(f"  Fodbold: {len(matches)}"); return matches,errors

def _parse_reddit_feed(raw, sub):
    """Parser ét Atom-feed til en liste af posts."""
    import xml.etree.ElementTree as ET
    ATOM  = "http://www.w3.org/2005/Atom"
    MEDIA = "http://search.yahoo.com/mrss/"
    posts = []
    root = ET.fromstring(raw)
    for entry in root.findall(f"{{{ATOM}}}entry"):
        title = (entry.findtext(f"{{{ATOM}}}title") or "").strip()
        link  = ""
        for a in entry.findall(f"{{{ATOM}}}link"):
            if a.get("rel", "alternate") == "alternate":
                link = a.get("href", ""); break
        if not link:
            link = entry.findtext(f"{{{ATOM}}}id") or ""
        updated = entry.findtext(f"{{{ATOM}}}updated") or ""
        try:
            created = datetime.fromisoformat(
                updated.replace("Z", "+00:00")).timestamp()
        except Exception:
            created = 0
        content = entry.findtext(f"{{{ATOM}}}content") or ""
        sm = re.search(r"(\d+) point", content)
        cm = re.search(r"(\d+) comment", content)
        score    = int(sm.group(1)) if sm else 0
        comments = int(cm.group(1)) if cm else 0
        # Billede: 1) media:thumbnail, 2) første <img> i content
        image = ""
        thumb = entry.find(f"{{{MEDIA}}}thumbnail")
        if thumb is not None:
            image = thumb.get("url", "")
        if not image:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if m:
                image = m.group(1)
        # Afkod HTML-entities (&amp; -> &) så billed-URL'er virker
        image = html_module.unescape(image)
        # Drop kun ægte placeholder/spoiler-billeder (behold external-preview!)
        if any(x in image for x in ["redd.it/erk", "nsfw", "spoiler", "default"]):
            image = ""
        # Eksternt link: første <a> i content der ikke er reddit.com
        ext_link = ""
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', content):
            href = m.group(1)
            if ("reddit.com" not in href and "redd.it" not in href
                    and href.startswith("http")):
                ext_link = html_module.unescape(href); break
        if title:
            posts.append({"sub": sub, "title": title[:120], "url": link,
                "score": score, "comments": comments,
                "created": created, "image": image, "ext_link": ext_link})
    return posts

def fetch_reddit():
    """Henter Reddit via Atom RSS — både nyeste og bedste. Trækker billeder fra media:thumbnail og content-img."""
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
    }
    by_sub = {}
    for sub in REDDIT_SUBS:
        sorts = {}
        for key, path in (("new", "new"), ("top", "top")):
            url = f"https://www.reddit.com/r/{sub}/{path}/.rss?limit={REDDIT_LIMIT}"
            if key == "top":
                url += "&t=day"  # bedste det seneste døgn
            try:
                raw = fetch_url(url, headers=headers)
                sorts[key] = _parse_reddit_feed(raw, sub)
            except Exception as e:
                print(f"  Reddit r/{sub} ({key}): {e}")
                sorts[key] = []
        by_sub[sub] = sorts
    total = sum(len(s.get("new", [])) for s in by_sub.values())
    print(f"  Reddit: {total} posts (nyeste) + bedste")
    return by_sub

def fetch_drtv():
    try:
        return json.loads(fetch_url("https://production-cdn.dr-massive.com/api/page?"+
            urllib.parse.urlencode({"device":"web_browser","item_detail_expand":"all",
                "lang":"da","max_list_prefetch":"3","path":"/kategorier/nyeste-programmer"})))
    except Exception as e: print(f"  DRTV: {e}"); return None

def find_newest_list(data):
    def walk(node):
        if isinstance(node,dict):
            if node.get("title")=="Netop tilføjet" and isinstance(node.get("items"),list): return node
            for v in node.values():
                r=walk(v)
                if r is not None: return r
        elif isinstance(node,list):
            for v in node:
                r=walk(v)
                if r is not None: return r
    return walk(data)

def parse_iso(s):
    if not s: return None
    try:
        if "." in s:
            h,_,t=s.partition("."); f=t.split("Z")[0][:6].ljust(6,"0"); s=f"{h}.{f}+00:00"
        elif s.endswith("Z"): s=s[:-1]+"+00:00"
        return datetime.fromisoformat(s)
    except: return None

def small_img(url,w=320,h=180):
    if not url: return ""
    return re.sub(r"Height=\d+",f"Height={h}",re.sub(r"Width=\d+",f"Width={w}",url))

def parse_drtv_item(raw):
    cf=raw.get("customFields") or {}; imgs=raw.get("images") or {}
    img=imgs.get("wallpaper") or imgs.get("tile") or imgs.get("default") or ""
    wp=raw.get("watchPath") or raw.get("path") or ""
    offers=raw.get("offers") or []
    return {"title":(raw.get("title") or "").strip(),"type":raw.get("type") or "",
        "desc":(raw.get("shortDescription") or raw.get("description") or "").strip(),
        "image":small_img(img),"url":f"https://www.dr.dk/drtv{wp}" if wp else "",
        "channel":cf.get("BrandingChannelDisplayName") or "",
        "available":parse_iso(cf.get("AvailableFrom")),
        "avail_status":(offers[0].get("availability") if offers else "")}

def filter_drtv(programs,today,yesterday):
    # Del programmer op i "i dag" og "i går" efter tilføjelsesdato, nyeste først.
    dated=[p for p in programs if p["available"] is not None]
    dated.sort(key=lambda p:p["available"],reverse=True)
    t=[p for p in dated if p["available"].astimezone(LOCAL_TZ).date()==today]
    y=[p for p in dated if p["available"].astimezone(LOCAL_TZ).date()==yesterday]
    return t,y


# ═══════════════════════════════════════════════════════
#  🌤  VEJR (Open-Meteo, gratis, ingen API-nøgle)
# ═══════════════════════════════════════════════════════

WX_CODES = {
    0:"Klart",1:"Næsten klart",2:"Delvist skyet",3:"Overskyet",
    45:"Tåge",48:"Rimtåge",
    51:"Let støvregn",53:"Støvregn",55:"Kraftig støvregn",
    61:"Let regn",63:"Regn",65:"Kraftig regn",
    71:"Let sne",73:"Sne",75:"Kraftig sne",
    80:"Let regnbyger",81:"Regnbyger",82:"Kraftige regnbyger",
    95:"Tordenvejr",99:"Tordenvejr med hagl",
}
WX_ICONS = {
    0:"☀️",1:"🌤",2:"⛅",3:"☁️",
    45:"🌫",48:"🌫",
    51:"🌦",53:"🌦",55:"🌧",
    61:"🌦",63:"🌧",65:"🌧",
    71:"🌨",73:"❄️",75:"❄️",
    80:"🌦",81:"🌧",82:"⛈",
    95:"⛈",99:"⛈",
}

def fetch_weather(lat=55.6761, lon=12.5683, city="København"):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,weathercode,"
        "windspeed_10m,relativehumidity_2m,precipitation_probability"
        "&daily=weathercode,temperature_2m_max,temperature_2m_min"
        "&hourly=temperature_2m,weathercode,precipitation_probability"
        "&timezone=Europe%2FCopenhagen&forecast_days=4"
    )
    try:
        raw  = fetch_url(url)
        data = json.loads(raw)
        c = data["current"]
        d = data["daily"]
        h = data["hourly"]
        now_iso = data["current"]["time"]   # e.g. "2026-05-30T14:00"

        now_wx = {
            "city":     city,
            "temp":     round(c["temperature_2m"]),
            "feels":    round(c["apparent_temperature"]),
            "wind":     round(c["windspeed_10m"]),
            "humidity": round(c["relativehumidity_2m"]),
            "rain_pct": round(c.get("precipitation_probability", 0)),
            "code":     c["weathercode"],
        }
        # Build daily forecast with hourly breakdown
        forecast = []
        for i in range(4):
            day_date = d["time"][i]
            # Collect hourly slots for this day (every 3 hours: 00,03,06,09,12,15,18,21)
            hourly_slots = []
            for j, ht in enumerate(h["time"]):
                if ht.startswith(day_date):
                    hour = int(ht[11:13])
                    if hour % 3 == 0:
                        hourly_slots.append({
                            "hour": f"{hour:02d}:00",
                            "temp": round(h["temperature_2m"][j]),
                            "code": h["weathercode"][j],
                            "rain": round(h["precipitation_probability"][j]),
                        })
            forecast.append({
                "date":    day_date,
                "code":    d["weathercode"][i],
                "hi":      round(d["temperature_2m_max"][i]),
                "lo":      round(d["temperature_2m_min"][i]),
                "hourly":  hourly_slots,
            })
        print(f"  Vejr: {now_wx['temp']}°C, {WX_CODES.get(now_wx['code'],'–')}")
        return now_wx, forecast
    except Exception as e:
        print(f"  Vejr fejl: {e}")
        return None, []


# ═══════════════════════════════════════════════════════
#  HTML RENDERING HELPERS
# ═══════════════════════════════════════════════════════

TYPE_LABEL = {"episode":"Afsnit","program":"Program","show":"Serie",
              "season":"Sæson","movie":"Film"}
SUB_CFG = {"Denmark":{"icon":"🇩🇰","color":"#f59e0b"},
           "worldnews":{"icon":"🌍","color":"#34d399"},
           "soccer":{"icon":"⚽","color":"#818cf8"}}

_uid=0
def uid(): global _uid; _uid+=1; return f"u{_uid}"

DRAG_HANDLE = '<span class="drag-handle" title="Flyt kort">⠿</span>'


def render_weather(wx_now, wx_forecast, now_local):
    if wx_now is None:
        return '<div class="dimtxt">Vejrdata utilgængelig</div>'
    code = wx_now["code"]
    icon = WX_ICONS.get(code, "🌡")
    desc = WX_CODES.get(code, "–")

    def day_label(date_str, idx):
        if idx == 0: return "I dag"
        if idx == 1: return "I morgen"
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return DK_WEEKDAYS[d.weekday()]
        except: return date_str

    def hourly_rows(slots):
        if not slots: return ""
        rows = "".join(
            f'<div class="wx-hour">' +
            f'<span class="wx-h-time">{s["hour"]}</span>' +
            f'<span class="wx-h-icon">{WX_ICONS.get(s["code"],"🌡")}</span>' +
            f'<span class="wx-h-temp">{s["temp"]}°</span>' +
            f'<span class="wx-h-rain">{s["rain"]}%</span>' +
            '</div>'
            for s in slots)
        return f'<div class="wx-hourly">{rows}</div>'

    forecast_rows = ""
    for i, f in enumerate(wx_forecast):
        dlbl  = esc(day_label(f["date"], i))
        dicon = WX_ICONS.get(f["code"], "🌡")
        ddesc = esc(WX_CODES.get(f["code"], "–"))
        uid_  = f"wxd{i}"
        hourly_html = hourly_rows(f.get("hourly", []))
        forecast_rows += f"""<div class="wx-day" onclick="toggleWxDay('{uid_}')" id="{uid_}-btn">
  <span class="wx-day-name">{dlbl}</span>
  <span class="wx-day-icon">{dicon}</span>
  <span class="wx-day-desc">{ddesc}</span>
  <div class="wx-day-temps"><span class="wx-hi">{f["hi"]}°</span><span class="wx-lo">{f["lo"]}°</span></div>
  <svg class="wx-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>
</div>
<div class="wx-hourly-wrap" id="{uid_}-detail">
  {hourly_html}
</div>"""

    return f'''<div class="wx-grid">
  <div class="wx-now">
    <div class="wx-city">{esc(wx_now["city"])}</div>
    <div class="wx-big">{esc(icon)} <span class="wx-temp">{wx_now["temp"]}<sup>°</sup></span></div>
    <div class="wx-desc">{esc(desc)}</div>
    <div class="wx-details">
      <div class="wx-detail"><span class="wx-dl">Føles som</span><span class="wx-dv">{wx_now["feels"]}°</span></div>
      <div class="wx-detail"><span class="wx-dl">Vind</span><span class="wx-dv">{wx_now["wind"]} km/t</span></div>
      <div class="wx-detail"><span class="wx-dl">Regn</span><span class="wx-dv">{wx_now["rain_pct"]}%</span></div>
      <div class="wx-detail"><span class="wx-dl">Luftfugt.</span><span class="wx-dv">{wx_now["humidity"]}%</span></div>
    </div>
  </div>
  <div class="wx-forecast">{forecast_rows}</div>
</div>'''

def render_event(ev, now_local):
    if ev["all_day"]: time_str,past="Hele dagen",False
    else:
        s,e=ev["start"],ev["end"]
        time_str=s.strftime("%H:%M")
        if e and isinstance(e,datetime): time_str+="–"+e.strftime("%H:%M")
        past=s<now_local and (not e or e<now_local)
    loc=f'<div class="ev-loc">📍 {esc(ev["location"])}</div>' if ev["location"] else ""
    dot_color = ev.get("color","#8088b0")
    opacity = "opacity:.45;" if ev.get("past") else ""
    return f'''<div class="ev" style="{opacity}">
  <span class="ev-dot" style="background:{dot_color}"></span>
  <span class="ev-time">{esc(time_str)}</span>
  <span class="ev-title">{esc(ev["summary"])}{loc}</span>
</div>'''
def render_day_col(d, events, now_local, label, is_today=False):
    sorted_evs = sorted(events, key=lambda ev:(
        0 if ev["all_day"] else 1, ev["cal_order"],
        datetime.min if ev["all_day"] else ev["start"]))
    rendered = [render_event(ev,now_local) for ev in sorted_evs]
    preview  = "".join(rendered[:CAL_PREVIEW])
    more_evs = "".join(rendered[CAL_PREVIEW:])
    i=uid()
    expand=""
    if more_evs:
        expand=f"""<div class="inline-expand" id="ix{i}">
  <button class="expand-btn" onclick="toggleInline('ix{i}',this)"
    data-more="▾ {len(sorted_evs)-CAL_PREVIEW} mere"
    data-less="▴ Vis færre">▾ {len(sorted_evs)-CAL_PREVIEW} mere</button>
  <div class="expand-body">{more_evs}</div>
</div>"""
    body = (preview or '<div class="empty-day">Ingen begivenheder</div>') + expand
    tc=" today-col day-open" if is_today else " day-open"
    cid=uid()
    return f"""<div class="day-col{tc}" id="dc{cid}">
  <div class="day-head" onclick="toggleDay('dc{cid}')">
    <span class="day-lbl">{esc(label)}</span>
    <span class="day-sub">{esc(dk_date(d))}</span>
    <svg class="day-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="5 8 10 13 15 8"/>
    </svg>
  </div>
  <div class="day-body-wrap"><div class="day-body">{body}</div></div>
</div>"""

def render_match(m, now_local):
    if m["dt"] is None: return ""
    delta=(m["dt"].date()-now_local.date()).days
    dlbl="I dag" if delta==0 else "I morgen" if delta==1 else DK_WEEKDAYS[m["dt"].weekday()]
    st=m["status"]
    if st in ("FINISHED","PAUSED","IN_PLAY") and m["score_home"] is not None:
        score=f'<span class="score">{m["score_home"]}–{m["score_away"]}</span>'
        if st=="IN_PLAY": score=f'<span class="live">LIVE</span>{score}'
    else:
        score=f'<span class="mwhen">{dlbl} {m["dt"].strftime("%H:%M")}</span>'
    return f"""<div class="match">
  <span class="lleag">{esc(m['league'])}</span>
  <span class="lteams">{esc(m['home'])} <span class="vs">vs</span> {esc(m['away'])}</span>
  {score}
</div>"""

def render_reddit_post(p, now_local):
    age  = int(now_local.timestamp()) - int(p["created"])
    ages = f"{age//60}m" if age<3600 else f"{age//3600}t" if age<86400 else f"{age//86400}d"
    image = p.get("image","")
    if image:
        img_html = f'''<div class="rimg-wrap">
  <img src="{esc(image)}" alt="" loading="lazy" onerror="this.parentElement.remove()">
</div>'''
        ext = p.get("ext_link","")
        ext_html = ""
        if ext:
            ext_html = f'<div class="rlink">🔗 <span class="rlink-domain">{esc(re.sub(r"https?://", "", ext))}</span></div>'
        return f"""<a class="rpost rpost-img"
  href="{esc(p['url'])}" target="_blank" rel="noopener">
  <div class="rpost-text">
    <span class="rtitle">{esc(p['title'])}</span>
    {ext_html}
    <span class="rmeta">▲ {p['score']} · 💬 {p['comments']} · {esc(ages)}</span>
  </div>
  {img_html}
</a>"""
    ext = p.get("ext_link","")
    ext_html = ""
    if ext:
        ext_html = f'<div class="rlink">🔗 <span class="rlink-domain">{esc(re.sub(r"https?://", "", ext))}</span></div>'
    return f"""<a class="rpost"
  href="{esc(p['url'])}" target="_blank" rel="noopener">
  <div class="rpost-text">
    <span class="rtitle">{esc(p['title'])}</span>
    {ext_html}
    <span class="rmeta">▲ {p['score']} · 💬 {p['comments']} · {esc(ages)}</span>
  </div>
</a>"""

def render_dr_card(p):
    badge=""
    img=(f'<img src="{esc(p["image"])}" alt="" loading="lazy">'
         if p["image"] else '<div class="noimg">DR</div>')
    tl=TYPE_LABEL.get(p["type"],p["type"])
    ch=f" · {p['channel']}" if p["channel"] else ""
    ts=p["available"].astimezone(LOCAL_TZ).strftime("%H:%M") if p["available"] else ""
    return f"""<a class="drcard" href="{esc(p['url'])}" target="_blank" title="{esc(p['title'])}">
  <div class="drthumb">{img}{badge}</div>
  <div class="drinfo">
    <div class="drmeta">{esc(tl+ch)}</div>
    <div class="drtitle">{esc(p['title'])}</div>
    <div class="drtime">{esc(ts)}</div>
  </div>
</a>"""

def make_card(card_id, icon, title, body, collapsible=True, open_=True, raw_title=False):
    chev=""
    if collapsible:
        chev="""<svg class="card-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor"
  stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="5 8 10 13 15 8"/></svg>"""
    toggle=f'onclick="toggleCard(\'{card_id}\')"' if collapsible else ""
    open_cls=" open" if open_ else ""
    cursor_cls="" if collapsible else " no-cursor"
    title_html = title if raw_title else esc(title)
    return f"""<div class="dash-card{open_cls}" id="{card_id}" draggable="true"
  ondragstart="onDragStart(event)" ondragover="onDragOver(event)"
  ondrop="onDrop(event)" ondragend="onDragEnd(event)">
  <div class="card-head{cursor_cls}" {toggle}>
    {DRAG_HANDLE}
    <span class="card-icon">{icon}</span>
    <span class="card-title">{title_html}</span>
    {chev}
  </div>
  <div class="card-body-wrap">
    <div class="card-body">{body}</div>
  </div>
  <div class="resize-handle" onmousedown="onResizeStart(event)"></div>
</div>"""

# ═══════════════════════════════════════════════════════
#  PAGE ASSEMBLY
# ═══════════════════════════════════════════════════════

def render_wx_top(wx_now):
    """Render compact weather for the top bar."""
    if wx_now is None:
        return '<div class="dimtxt">Vejrdata utilgængelig</div>'
    icon = WX_ICONS.get(wx_now["code"], "🌡")
    desc = WX_CODES.get(wx_now["code"], "–")
    return f"""<div class="wx-row">
  <span class="wx-icon">{esc(icon)}</span>
  <span class="wx-temp">{wx_now["temp"]}<sup>°</sup></span>
</div>
<div class="wx-desc">{esc(desc)}</div>
<div class="wx-stats">
  <div class="wx-stat"><span class="wx-stat-lbl">Føles som</span><span class="wx-stat-val">{wx_now["feels"]}°</span></div>
  <div class="wx-stat"><span class="wx-stat-lbl">Vind</span><span class="wx-stat-val">{wx_now["wind"]} km/t</span></div>
  <div class="wx-stat"><span class="wx-stat-lbl">Regn</span><span class="wx-stat-val">{wx_now["rain_pct"]}%</span></div>
</div>"""


def render_wx_forecast(wx_forecast, prefix="wxd"):
    """Render collapsible forecast days."""
    def hourly_rows(slots):
        if not slots: return ""
        items = "".join(
            f'<div class="wx-hour">'
            f'<span class="wx-h-time">{s["hour"]}</span>'
            f'<span class="wx-h-icon">{WX_ICONS.get(s["code"],"🌡")}</span>'
            f'<span class="wx-h-temp">{s["temp"]}°</span>'
            f'<span class="wx-h-rain">{s["rain"]}%</span>'
            f'</div>'
            for s in slots)
        return f'<div class="wx-hourly">{items}</div>'

    def day_label(date_str, idx):
        if idx == 0: return "I dag"
        if idx == 1: return "I morgen"
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return DK_WEEKDAYS[d.weekday()]
        except: return date_str

    rows = ""
    for i, f in enumerate(wx_forecast):
        uid_ = f"{prefix}{i}"
        dlbl = esc(day_label(f["date"], i))
        dicon = WX_ICONS.get(f["code"], "🌡")
        ddesc = esc(WX_CODES.get(f["code"], "–"))
        hourly = hourly_rows(f.get("hourly", []))
        chev = '<svg class="wx-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>'
        rows += f"""<div class="wx-day" onclick="toggleWxDay('{uid_}')" id="{uid_}-btn">
  <span class="wx-day-name">{dlbl}</span>
  <span class="wx-day-icon">{dicon}</span>
  <span class="wx-day-desc">{ddesc}</span>
  <div class="wx-day-temps"><span class="wx-hi">{f["hi"]}°</span><span class="wx-lo">{f["lo"]}°</span></div>
  {chev}
</div>
<div class="wx-hourly-wrap" id="{uid_}-detail">{hourly}</div>"""
    return rows



def render_wx_top(wx_now):
    if wx_now is None:
        return '<div class="dimtxt">Vejrdata utilgængelig</div>'
    icon = WX_ICONS.get(wx_now["code"], "🌡")
    desc = WX_CODES.get(wx_now["code"], "–")
    return f"""<div class="wx-row">
  <span class="wx-icon">{esc(icon)}</span>
  <span class="wx-temp">{wx_now["temp"]}<sup>°</sup></span>
</div>
<div class="wx-desc">{esc(desc)}</div>
<div class="wx-stats">
  <div class="wx-stat"><span class="wx-stat-lbl">Føles som</span><span class="wx-stat-val">{wx_now["feels"]}°</span></div>
  <div class="wx-stat"><span class="wx-stat-lbl">Vind</span><span class="wx-stat-val">{wx_now["wind"]} km/t</span></div>
  <div class="wx-stat"><span class="wx-stat-lbl">Regn</span><span class="wx-stat-val">{wx_now["rain_pct"]}%</span></div>
</div>"""


def render_wx_forecast(wx_forecast, prefix="wxd"):
    def hourly_rows(slots):
        if not slots: return ""
        items = "".join(
            f'<div class="wx-hour">'
            f'<span class="wx-h-time">{s["hour"]}</span>'
            f'<span class="wx-h-icon">{WX_ICONS.get(s["code"],"🌡")}</span>'
            f'<span class="wx-h-temp">{s["temp"]}°</span>'
            f'<span class="wx-h-rain">{s["rain"]}%</span>'
            f'</div>'
            for s in slots)
        return f'<div class="wx-hourly">{items}</div>'

    def day_label(date_str, idx):
        if idx == 0: return "I dag"
        if idx == 1: return "I morgen"
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return DK_WEEKDAYS[d.weekday()]
        except: return date_str

    rows = ""
    for i, f in enumerate(wx_forecast):
        uid_ = f"{prefix}{i}"
        dlbl = esc(day_label(f["date"], i))
        dicon = WX_ICONS.get(f["code"], "🌡")
        ddesc = esc(WX_CODES.get(f["code"], "–"))
        hourly = hourly_rows(f.get("hourly", []))
        chev = '<svg class="wx-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>'
        rows += (f'<div class="wx-day" onclick="toggleWxDay(\'{uid_}\')" id="{uid_}-btn">'
                 f'<span class="wx-day-name">{dlbl}</span>'
                 f'<span class="wx-day-icon">{dicon}</span>'
                 f'<span class="wx-day-desc">{ddesc}</span>'
                 f'<div class="wx-day-temps"><span class="wx-hi">{f["hi"]}°</span><span class="wx-lo">{f["lo"]}°</span></div>'
                 f'{chev}</div>'
                 f'<div class="wx-hourly-wrap" id="{uid_}-detail">{hourly}</div>')
    return rows


RESW = ('<div class="resize-sw" onmousedown="onResizeSW(event)"><svg viewBox="0 0 14 14" fill="none">'
        '<line x1="13" y1="13" x2="1" y2="1" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="9" y1="13" x2="1" y2="5" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="5" y1="13" x2="1" y2="9" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '</svg></div>')
RESE = ('<div class="resize-se" onmousedown="onResizeSE(event)"><svg viewBox="0 0 14 14" fill="none">'
        '<line x1="1" y1="13" x2="13" y2="1" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="5" y1="13" x2="13" y2="5" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="9" y1="13" x2="13" y2="9" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '</svg></div>')


def render_wx_top(wx_now):
    if wx_now is None:
        return '<div class="dimtxt">Vejrdata utilgyngelig</div>'
    icon = WX_ICONS.get(wx_now["code"], "\U0001f321")
    desc = WX_CODES.get(wx_now["code"], "\u2013")
    return (f'<div class="wx-row">'
            f'<span class="wx-icon">{esc(icon)}</span>'
            f'<span class="wx-temp">{wx_now["temp"]}<sup>\u00b0</sup></span>'
            f'</div>'
            f'<div class="wx-desc">{esc(desc)}</div>'
            f'<div class="wx-stats">'
            f'<div class="wx-stat"><span class="wx-stat-lbl">F\u00f8les som</span><span class="wx-stat-val">{wx_now["feels"]}\u00b0</span></div>'
            f'<div class="wx-stat"><span class="wx-stat-lbl">Vind</span><span class="wx-stat-val">{wx_now["wind"]} km/t</span></div>'
            f'<div class="wx-stat"><span class="wx-stat-lbl">Regn</span><span class="wx-stat-val">{wx_now["rain_pct"]}%</span></div>'
            f'</div>')


def render_wx_forecast(wx_forecast, prefix="wxd"):
    def hourly_rows(slots):
        if not slots: return ""
        items = "".join(
            f'<div class="wx-hour">'
            f'<span class="wx-h-time">{s["hour"]}</span>'
            f'<span class="wx-h-icon">{WX_ICONS.get(s["code"],"\U0001f321")}</span>'
            f'<span class="wx-h-temp">{s["temp"]}\u00b0</span>'
            f'<span class="wx-h-rain">{s["rain"]}%</span>'
            f'</div>'
            for s in slots)
        return f'<div class="wx-hourly">{items}</div>'

    def day_label(date_str, i):
        if i == 0: return "I dag"
        if i == 1: return "I morgen"
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return DK_WEEKDAYS[d.weekday()]
        except: return date_str

    rows = ""
    chev = '<svg class="wx-chev" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>'
    for i, f in enumerate(wx_forecast):
        uid_ = f"{prefix}{i}"
        dlbl = esc(day_label(f["date"], i))
        dicon = WX_ICONS.get(f["code"], "\U0001f321")
        ddesc = esc(WX_CODES.get(f["code"], "\u2013"))
        hourly = hourly_rows(f.get("hourly", []))
        rows += (f'<div class="wx-day" onclick="toggleWxDay(\'{uid_}\')" id="{uid_}-btn">'
                 f'<span class="wx-day-name">{dlbl}</span>'
                 f'<span class="wx-day-icon">{dicon}</span>'
                 f'<span class="wx-day-desc">{ddesc}</span>'
                 f'<div class="wx-day-temps"><span class="wx-hi">{f["hi"]}\u00b0</span><span class="wx-lo">{f["lo"]}\u00b0</span></div>'
                 f'{chev}</div>'
                 f'<div class="wx-hourly-wrap" id="{uid_}-detail">{hourly}</div>')
    return rows


RESW = ('<div class="resize-sw" onmousedown="onResizeSW(event)"><svg viewBox="0 0 14 14" fill="none">'
        '<line x1="13" y1="13" x2="1" y2="1" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="9" y1="13" x2="1" y2="5" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="5" y1="13" x2="1" y2="9" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '</svg></div>')
RESE = ('<div class="resize-se" onmousedown="onResizeSE(event)"><svg viewBox="0 0 14 14" fill="none">'
        '<line x1="1" y1="13" x2="13" y2="1" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="5" y1="13" x2="13" y2="5" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '<line x1="9" y1="13" x2="13" y2="9" stroke="var(--dim)" stroke-width="1" stroke-linecap="round"/>'
        '</svg></div>')


def generate_html(day_summary, dk_prose, w_prose,
                  wx_now, wx_forecast,
                  cal_events, cal_errors,
                  matches, football_errors,
                  reddit_by_sub, drtv_today, drtv_yesterday, now_local,
                  wiki=None, astro=None, funfacts=""):
    today=now_local.date(); yesterday=today-timedelta(1)
    tomorrow=today+timedelta(1); day2=today+timedelta(2)
    date_label=dk_date(today); time_str=now_local.strftime("%H:%M")

    cal_errs = "".join(f'<div class="errbar">&#x26A0; {esc(e)}</div>' for e in cal_errors)
    legend = "".join(
        f'<span class="legitem"><span class="legdot" style="background:{esc(info["color"])}"></span>{esc(n)}</span>'
        for n,info in CALENDARS.items())
    cols = (render_day_col(today,    events_for_day(cal_events,today),    now_local,"I dag",True)
          + render_day_col(tomorrow, events_for_day(cal_events,tomorrow), now_local,"I morgen")
          + render_day_col(day2,     events_for_day(cal_events,day2),     now_local,DK_WEEKDAYS[day2.weekday()]))
    cal_body = f'{cal_errs}<div class="legrow">{legend}</div><div class="threecol">{cols}</div>'

    wx_top_html      = render_wx_top(wx_now)
    wx_forecast_html = render_wx_forecast(wx_forecast, prefix="twxd")

    fb_errs = "".join(f'<div class="errbar">{esc(e)}</div>' for e in football_errors)
    if matches:
        groups={}
        for m in matches:
            if m["dt"]: groups.setdefault(m["dt"].date(),[]).append(m)
        rows=[]
        for d in sorted(groups):
            delta=(d-today).days
            dlbl="I dag" if delta==0 else "I morgen" if delta==1 else dk_date(d)
            rows.append(f'<div class="ddiv">{esc(dlbl)}</div>')
            rows.extend(render_match(m,now_local) for m in groups[d])
        fb_content="".join(rows)
    else:
        fb_content='<div class="dimtxt">Ingen kampe i perioden</div>'
    fb_body=fb_errs+fb_content

    def build_reddit_body(posts, cid, sort_key):
        if not posts:
            return '<div class="dimtxt">Ingen posts</div>'
        body="".join(render_reddit_post(p,now_local) for p in posts[:REDDIT_PREVIEW])
        more="".join(render_reddit_post(p,now_local) for p in posts[REDDIT_PREVIEW:])
        if more:
            i=uid(); fc=len(posts)-REDDIT_PREVIEW
            body+=(f'<div class="inline-expand" id="re{i}">'
                f'<button class="expand-btn" onclick="toggleInline(\'re{i}\',this)"'
                f' data-more="&#9662; {fc} mere" data-less="&#9652; Vis f&aelig;rre">'
                f'&#9662; {fc} mere</button>'
                f'<div class="expand-body">{more}</div></div>')
        return body

    reddit_cards_html = ""
    for sub in REDDIT_SUBS:
        cfg=SUB_CFG.get(sub,{"icon":"\U0001f4ac","color":"#8892b0"})
        sorts=reddit_by_sub.get(sub,{})
        new_posts=sorts.get("new",[])
        top_posts=sorts.get("top",[])
        cid=f"reddit-{sub}"
        body_new=build_reddit_body(new_posts,cid,"new")
        body_top=build_reddit_body(top_posts,cid,"top")
        _rcol={"Denmark":"1/span 4","worldnews":"5/span 4","soccer":"9/span 4"}.get(sub,"auto/span 4")
        toggle=(f'<div class="rsort" onmousedown="event.stopPropagation()">'
            f'<button class="rsort-btn active" data-sort="new" onclick="setRedditSort(\'{cid}\',\'new\')">Nyeste</button>'
            f'<button class="rsort-btn" data-sort="top" onclick="setRedditSort(\'{cid}\',\'top\')">Bedste</button>'
            f'</div>')
        bodies=(f'<div class="rsort-list" data-sort="new">{body_new}</div>'
                f'<div class="rsort-list" data-sort="top" style="display:none">{body_top}</div>')
        reddit_cards_html += (
            f'<div class="dash-card open" id="{cid}" style="grid-column:{_rcol};min-width:0">'
            f'<div class="card-head" onmousedown="onHeaderMD(event,\'{cid}\')">'
            f'<span class="drag-handle">&#x283F;</span>'
            f'<span class="card-icon">{cfg["icon"]}</span>'
            f'<span class="card-title" style="color:{esc(cfg["color"])}">r/{esc(sub)}</span>'
            f'{toggle}'
            f'<svg class="card-chev" onclick="toggleCard(\'{cid}\')" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>'
            f'</div>'
            f'<div class="card-body-wrap"><div class="card-body">{bodies}</div></div>'
            f'{RESW}{RESE}</div>')

    def drtv_group(label, sub_lbl, items):
        if not items: return ""
        rendered=[render_dr_card(p) for p in items]
        grid=f'<div class="drgrid">{"".join(rendered[:DRTV_PREVIEW])}</div>'
        expand=""
        if len(rendered)>DRTV_PREVIEW:
            i=uid(); fc=len(items)-DRTV_PREVIEW; more_items=rendered[DRTV_PREVIEW:]
            expand=(f'<div class="inline-expand" id="dr{i}">'
                f'<button class="expand-btn" onclick="toggleInline(\'dr{i}\',this)"'
                f' data-more="&#9662; {fc} mere" data-less="&#9652; Vis f&aelig;rre">'
                f'&#9662; {fc} mere</button>'
                f'<div class="expand-body"><div class="drgrid">{"".join(more_items)}</div></div></div>')
        return f'<div class="drgroup"><div class="drlbl">{esc(label)} <span class="muted">{esc(sub_lbl)}</span></div>{grid}{expand}</div>'

    drtv_body=(drtv_group("I dag",dk_date(today),drtv_today)
             + drtv_group("I g\u00e5r",dk_date(yesterday),drtv_yesterday))
    if not drtv_body: drtv_body='<div class="dimtxt">Ingen tilf\u00f8jelser</div>'

    news_dk_html = safe_prose(dk_prose) if dk_prose else '<span class="dimtxt">Ingen nyheder</span>'
    news_w_html  = safe_prose(w_prose)  if w_prose  else '<span class="dimtxt">Ingen nyheder</span>'

    # ── Astronomi nævnes nu i prosaen, så ingen separat række ──
    astro = astro or {}
    astro_html = ""

    # ── Interessante fakta (AI) til "Din dag" ──
    funfacts_html = ""
    if funfacts:
        ff = safe_prose(funfacts)
        funfacts_html = f'<div class="funfacts"><div class="mini-label">&#x2728; Sker i dag &mdash; Danmark &amp; verden</div>{ff}</div>'

    # ── "Skete på denne dag" — placeres under vejret, med klikbare links ──
    wiki = wiki or {"tfa": None, "onthisday": []}
    otd_html = ""
    otd = wiki.get("onthisday", [])[:7]
    if otd:
        rows = ""
        for e in otd:
            txt = esc(e["text"])
            inner = (f'<span class="otd-year">{e["year"]}</span> {txt}')
            if e.get("url"):
                rows += (f'<li><a class="otd-link" href="{esc(e["url"])}" '
                         f'target="_blank" rel="noopener">{inner}</a></li>')
            else:
                rows += f'<li>{inner}</li>'
        otd_html = (f'<div class="onthisday"><div class="mini-label">&#x1F4DC; Skete p&aring; denne dag</div>'
                    f'<ul class="otd-list">{rows}</ul></div>')

    # ── Dagens Wikipedia-artikel (engelsk) ──
    wiki_html = '<span class="dimtxt">Kunne ikke hente artikel</span>'
    tfa = wiki.get("tfa")
    if tfa:
        img = (f'<img class="wiki-img" src="{esc(tfa["image"])}" alt="" loading="lazy">'
               if tfa.get("image") else "")
        extract = esc(tfa.get("extract","")[:320])
        if len(tfa.get("extract","")) > 320: extract += "&hellip;"
        wiki_html = (
            f'<a class="wiki-card" href="{esc(tfa.get("url",""))}" target="_blank" rel="noopener">'
            f'{img}'
            f'<div class="wiki-body">'
            f'<div class="wiki-title">{esc(tfa.get("title",""))}</div>'
            f'<div class="wiki-extract">{extract}</div>'
            f'</div></a>')

    # ── Dagens ord (ordnet.dk) — hentes klient-side i browseren ──
    # (ordet er ikke i serverens HTML, så vi loader det med JS via en proxy)
    word_html = ('<div id="word-box"><span class="dimtxt">Henter dagens ord&hellip;</span></div>')


    CSS = "\n:root{\n  --bg:#252838;--c1:#2e3248;--c2:#343858;--c3:#3a3e5c;--c4:#404568;\n  --border:#3d4265;--text:#dde1f0;--muted:#8088b0;--dim:#555e88;\n  --acc:#a78bfa;--acc2:#60a5fa;--green:#34d399;\n  --r:12px;--rs:8px;\n}\n*{box-sizing:border-box;margin:0;padding:0}\nhtml,body{\n  background:var(--bg);color:var(--text);\n  font-family:'Plus Jakarta Sans',system-ui,sans-serif;\n  font-size:13px;line-height:1.6;min-height:100vh;\n}\n\n/* ── HEADER ──────────────────────────────────────────────── */\nheader{\n  padding:10px 28px;background:var(--c1);\n  border-bottom:0.5px solid var(--border);\n  display:flex;align-items:center;gap:14px;\n}\n.logo{font-size:15px;font-weight:600;letter-spacing:-.3px}\n.logo em{font-style:normal;color:var(--acc)}\n.hdate{color:var(--muted);font-size:11px;margin-left:auto}\n.reset-btn{\n  background:transparent;border:0.5px solid var(--border);\n  border-radius:var(--rs);color:var(--muted);\n  padding:5px 12px;font-size:11px;font-weight:500;\n  cursor:pointer;font-family:inherit;\n  transition:background .15s,color .15s;\n}\n.reset-btn:hover{background:var(--c3);color:var(--text)}\n.upbtn{\n  display:flex;align-items:center;gap:5px;\n  background:#35305c;border:0.5px solid #4e4590;\n  border-radius:var(--rs);color:#c4b5fd;\n  text-decoration:none;padding:5px 12px;font-size:11px;font-weight:500;\n}\n.upbtn:hover{filter:brightness(1.2)}\n\n/* ── TOP BAR (søg + dag + vejr + nyheder) ────────────────── */\n#top-bar{\n  padding:20px 28px 0;\n  display:flex;flex-direction:column;gap:20px;\n}\n\n/* Søgefelter */\n#top-search{\n  display:grid;\n  grid-template-columns:repeat(5,1fr);\n  gap:10px;\n}\n.s-item{display:flex;flex-direction:column;gap:5px;position:relative}\n.s-lbl{\n  display:flex;align-items:center;gap:6px;\n  font-size:10px;font-weight:600;color:var(--muted);\n}\n.s-logo{\n  width:20px;height:20px;border-radius:4px;flex-shrink:0;\n  display:flex;align-items:center;justify-content:center;\n  font-size:10px;font-weight:800;\n}\n.s-logo.g{background:#fff;color:#4285f4}\n.s-logo.r{background:#ff4500;color:#fff;font-size:9px}\n.s-logo.yt{background:#ff0000;color:#fff;font-size:11px}\n.s-logo.imdb{background:#f5c518;color:#000;font-size:8px;width:28px}\n.s-form{display:flex}\n.s-input{\n  width:100%;background:var(--c2);border:0.5px solid var(--border);\n  border-radius:var(--rs);color:var(--text);\n  padding:7px 11px;font-size:12px;font-family:inherit;outline:none;\n  transition:border-color .15s;\n}\n.s-input::placeholder{color:var(--dim)}\n.s-input:focus{border-color:var(--acc)}\n.search-results{\n  position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:500;\n  background:var(--c1);border:0.5px solid var(--border);\n  border-radius:var(--rs);box-shadow:0 8px 24px #00000060;\n  max-height:340px;overflow-y:auto;display:none;flex-direction:column;\n}\n.sr-item{\n  display:flex;align-items:center;gap:10px;padding:7px 10px;\n  text-decoration:none;color:var(--text);\n  border-bottom:0.5px solid var(--border);transition:background .12s;\n}\n.sr-item:last-child{border-bottom:none}\n.sr-item:hover{background:var(--c3)}\n.sr-thumb{width:54px;height:30px;border-radius:3px;object-fit:cover;flex-shrink:0;background:var(--c3)}\n.sr-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}\n.sr-title{font-size:12px;font-weight:500;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.sr-meta{font-size:10px;color:var(--muted)}\n.sr-loading{color:var(--muted);font-size:11px;font-style:italic;padding:8px 10px}\n.sr-error{color:#f87171;font-size:11px;padding:8px 10px}\n\n/* Din dag + Vejr + Nyheder */\n#top-info{\n  display:flex;flex-direction:column;gap:20px;\n  padding-bottom:22px;\n  border-bottom:0.5px solid var(--border);\n}\n#top-row1{\n  display:grid;\n  grid-template-columns:2fr 1fr 2fr;\n  gap:28px;align-items:start;\n}\n.top-section-label{\n  font-size:14px;font-weight:700;text-transform:uppercase;\n  letter-spacing:.5px;color:var(--text);margin-bottom:10px;\n}\n#top-sum .sumtxt{font-size:15px;line-height:1.85}\n#top-sum{font-size:13px}\n.astro-row{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;padding-top:10px;border-top:0.5px solid var(--border)}\n.astro-item{font-size:13px;color:var(--text);display:flex;align-items:center;gap:5px}\n.mini-label{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--text);margin:16px 0 7px}\n.funfacts ul,.onthisday ul{list-style:disc;margin:0;padding-left:20px;display:flex;flex-direction:column;gap:3px}\n.funfacts li,.otd-list li{font-size:13px;line-height:1.5}\n.otd-year{font-weight:700;color:var(--acc);margin-right:4px}\n.otd-link{color:var(--text);text-decoration:none;border-bottom:none}\n.otd-link:hover{color:var(--acc)}\n.otd-link:hover .otd-year{color:#ede9ff}\n.word-tagline{font-size:13px;color:var(--muted);margin-bottom:8px}\n#top-row2{display:grid;grid-template-columns:2fr 1fr;gap:28px;align-items:start;padding-top:18px;border-top:0.5px solid var(--border)}\n.wiki-card{display:flex;gap:14px;text-decoration:none;color:var(--text);align-items:flex-start}\n.wiki-img{width:120px;height:90px;object-fit:cover;border-radius:8px;flex-shrink:0;background:var(--c3)}\n.wiki-body{flex:1;min-width:0}\n.wiki-title{font-size:15px;font-weight:600;margin-bottom:5px;color:#ede9ff}\n.wiki-card:hover .wiki-title{color:var(--acc)}\n.wiki-extract{font-size:13px;line-height:1.6;color:var(--muted)}\n#word-box{font-size:14px;line-height:1.6}\n.word-headword{font-size:20px;font-weight:700;color:#ede9ff;margin-bottom:2px}\n.word-pos{font-size:11px;color:var(--acc);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}\n.word-def{font-size:13px;line-height:1.55;color:var(--text)}\n.word-link{display:inline-block;margin-top:8px;font-size:12px;color:var(--acc);text-decoration:none}\n.word-link:hover{text-decoration:underline}\n#top-wx .wx-row{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}\n#top-wx .wx-temp{font-size:32px;font-weight:300;letter-spacing:-1px}\n#top-wx .wx-temp sup{font-size:15px;font-weight:400;vertical-align:top;margin-top:4px}\n#top-wx .wx-icon{font-size:24px}\n#top-wx .wx-desc{font-size:12px;color:var(--muted);margin-bottom:10px}\n#top-wx .wx-stats{display:flex;gap:14px;flex-wrap:wrap}\n#top-wx .wx-stat{display:flex;flex-direction:column;gap:1px}\n#top-wx .wx-stat-lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px}\n#top-wx .wx-stat-val{font-size:12px;font-weight:500}\n\n.top-wx-grid{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start}\n#top-wx .wx-big{display:flex;align-items:center;gap:8px;line-height:1;margin-bottom:4px}\n#top-wx .wx-temp{font-size:34px;font-weight:300;letter-spacing:-1px}\n#top-wx .wx-temp sup{font-size:15px;font-weight:400;vertical-align:top;margin-top:4px}\n#top-wx .wx-desc{font-size:12px;color:var(--muted)}\n#top-news .news2{display:grid;grid-template-columns:1fr 1fr;gap:40px}\n#top-news .catlbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:6px}\n#top-news .newsp{font-size:14px;line-height:1.85}\n#top-news .newsp a{color:var(--acc);text-decoration:none;border-bottom:1px solid #a78bfa28}\n#top-news .newsp a:hover{border-bottom-color:var(--acc)}\n#top-news .newsp strong,#top-news .news-summary strong{font-weight:700;color:#ede9ff}\n.news-summary{display:block;margin-bottom:14px}\n.news-headlines{list-style:disc;margin:0;padding-left:20px;display:flex;flex-direction:column;gap:2px}\n.news-headlines li{padding:3px 0;border-top:none;line-height:1.45;font-size:13px;list-style-position:outside}\n.news-headlines li a{color:var(--text);border-bottom:none}\n.news-headlines li a:hover{color:var(--acc)}\n\n/* ── BOARD ───────────────────────────────────────────────── */\n#board{\n  padding:16px 28px 56px;\n  display:grid;\n  grid-template-columns:repeat(12,1fr);\n  grid-auto-rows:min-content;\n  grid-auto-flow:row;\n  gap:10px;\n  align-items:start;\n}\n\n/* ── CARDS ───────────────────────────────────────────────── */\n.dash-card{\n  background:var(--c1);border:0.5px solid var(--border);\n  border-radius:var(--r);overflow:visible;\n  position:relative;min-width:0;\n  transition:border-color .15s;\n}\n.card-head{\n  display:flex;align-items:center;gap:7px;\n  padding:9px 13px;background:var(--c2);\n  border-bottom:0.5px solid var(--border);\n  border-radius:var(--r) var(--r) 0 0;\n  cursor:grab;user-select:none;transition:background .15s;\n}\n.card-head:hover{background:var(--c3)}\n.drag-handle{color:var(--dim);font-size:14px;padding-right:2px;flex-shrink:0}\n.card-icon{font-size:13px;flex-shrink:0}\n.card-title{font-size:12px;font-weight:600;flex:1;letter-spacing:.1px}\n.card-chev{\n  width:20px;height:20px;color:var(--dim);flex-shrink:0;cursor:pointer;\n  padding:2px;border-radius:5px;\n  transition:transform .3s cubic-bezier(.4,0,.2,1),background .15s;\n}\n.card-chev:hover{background:var(--c4);color:var(--text)}\n.card-chev *{pointer-events:none}\n.dash-card.open .card-chev{transform:rotate(180deg)}\n.card-body-wrap{\n  display:grid;grid-template-rows:0fr;\n  transition:grid-template-rows .3s cubic-bezier(.4,0,.2,1);\n  border-radius:0 0 var(--r) var(--r);overflow:visible;\n}\n.dash-card.open .card-body-wrap{grid-template-rows:1fr}\n.card-body{overflow:hidden;padding:0 14px}\n.dash-card.open .card-body{padding:13px 14px}\n\n.resize-se,.resize-sw{\n  position:absolute;bottom:2px;width:16px;height:16px;z-index:20;\n}\n.resize-se{right:2px;cursor:nwse-resize}\n.resize-sw{left:2px;cursor:nesw-resize}\n.resize-se svg,.resize-sw svg{\n  width:16px;height:16px;opacity:.2;transition:opacity .15s;\n}\n.resize-se:hover svg,.resize-sw:hover svg{opacity:.7}\n\n.drop-placeholder{\n  background:#a78bfa0d;border:1.5px dashed #a78bfa55;\n  border-radius:12px;pointer-events:none;\n  transition:grid-column .12s;\n}\n\n/* ── INLINE EXPAND ───────────────────────────────────────── */\n.inline-expand{margin-top:5px}\n.expand-btn{\n  width:100%;background:var(--c2);border:0.5px solid var(--border);\n  color:var(--muted);border-radius:var(--rs);padding:5px 10px;\n  font-size:10px;cursor:pointer;font-family:inherit;font-weight:600;\n  letter-spacing:.3px;text-transform:uppercase;\n  transition:background .15s,color .15s;\n}\n.expand-btn:hover{background:var(--c3);color:var(--text)}\n.expand-body{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1)}\n.inline-expand.open .expand-body{max-height:3000px}\n\n/* ── CALENDAR ────────────────────────────────────────────── */\n.legrow{display:flex;gap:11px;margin-bottom:11px}\n.legitem{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--muted)}\n.legdot{width:7px;height:7px;border-radius:50%;flex-shrink:0}\n.threecol{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;align-items:start}\n.day-col{background:var(--c2);border:0.5px solid var(--border);border-radius:var(--rs);overflow:hidden;align-self:start}\n.day-col.today-col{border-color:#6b7299;background:#2e3254}\n.day-col.today-col .day-head{background:#363c60;border-bottom-color:#4a5080}\n.day-head{\n  display:flex;align-items:center;gap:6px;padding:7px 9px;\n  background:var(--c3);border-bottom:0.5px solid var(--border);\n  cursor:pointer;transition:background .15s;user-select:none;\n}\n.day-head:hover{background:var(--c4)}\n.day-lbl{font-size:11px;font-weight:600;flex:1}\n.day-sub{font-size:9px;color:var(--muted)}\n.today-badge{font-size:9px;font-weight:600;background:#484f7a;color:#c0c6e0;padding:1px 6px;border-radius:4px;flex-shrink:0}\n.day-chev{width:12px;height:12px;color:var(--dim);flex-shrink:0;transition:transform .27s cubic-bezier(.4,0,.2,1)}\n.day-col.day-open .day-chev{transform:rotate(180deg)}\n.day-body-wrap{display:grid;grid-template-rows:0fr;transition:grid-template-rows .27s cubic-bezier(.4,0,.2,1)}\n.day-col.day-open .day-body-wrap{grid-template-rows:1fr}\n.day-body{overflow:hidden;padding:3px 7px 5px}\n.empty-day{color:var(--dim);font-style:italic;font-size:11px;padding:9px 2px}\n.ev{display:grid;grid-template-columns:5px 50px 1fr;gap:6px;align-items:start;padding:5px 2px;border-radius:6px}\n.ev+.ev{border-top:0.5px solid var(--border)}\n.ev:hover{background:var(--c3)}\n.ev-dot{width:5px;height:5px;border-radius:50%;margin-top:4px;flex-shrink:0}\n.ev-time{font-size:9px;color:var(--muted);font-variant-numeric:tabular-nums;padding-top:1px}\n.ev-title{font-size:11px;font-weight:500;line-height:1.3}\n\n/* ── WEATHER CARD ────────────────────────────────────────── */\n.wx-grid{display:grid;grid-template-columns:1fr 1.6fr;gap:14px;align-items:start}\n.wx-now{display:flex;flex-direction:column;gap:4px}\n.wx-city{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);margin-bottom:2px}\n.wx-big{display:flex;align-items:center;gap:8px;line-height:1}\n.wx-temp{font-size:36px;font-weight:300;letter-spacing:-1px}\n.wx-temp sup{font-size:16px;font-weight:400;vertical-align:top;margin-top:5px}\n.wx-desc{font-size:12px;color:var(--muted);margin-top:3px}\n.wx-details{display:flex;gap:12px;margin-top:9px;flex-wrap:wrap}\n.wx-detail{display:flex;flex-direction:column;gap:1px}\n.wx-dl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px}\n.wx-dv{font-size:12px;font-weight:500}\n.wx-forecast{display:flex;flex-direction:column;gap:3px;margin-left:18px}\n.wx-day{\n  display:flex;align-items:center;gap:6px;padding:3px 8px;\n  border-radius:6px;background:var(--c2);border:0.5px solid var(--border);\n  cursor:pointer;transition:background .15s;user-select:none;min-height:28px;\n}\n.wx-day:hover{background:var(--c3)}\n.wx-day-name{font-size:10px;color:var(--muted);width:42px;flex-shrink:0}\n.wx-day-icon{font-size:13px;width:18px;text-align:center}\n.wx-day-desc{font-size:10px;color:var(--muted);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n.wx-day-temps{display:flex;gap:5px;font-size:10px;font-weight:500}\n.wx-hi{color:var(--text)}.wx-lo{color:var(--dim)}\n.wx-chev{width:11px;height:11px;color:var(--dim);transition:transform .25s;flex-shrink:0}\n.wx-day.wx-open .wx-chev{transform:rotate(180deg)}\n.wx-hourly-wrap{max-height:0;overflow:hidden;transition:max-height .3s cubic-bezier(.4,0,.2,1)}\n.wx-hourly-wrap.wx-open{max-height:300px}\n.wx-hourly{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;padding:6px 4px 4px}\n.wx-hour{display:flex;flex-direction:column;align-items:center;gap:3px;padding:7px 4px;border-radius:7px;background:var(--c2);border:0.5px solid var(--border)}\n.wx-h-time{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums}\n.wx-h-icon{font-size:16px}.wx-h-temp{font-size:12px;font-weight:600}\n.wx-h-rain{font-size:10px;color:var(--acc2);font-weight:500}\n\n/* ── FOOTBALL ────────────────────────────────────────────── */\n.ddiv{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);padding:6px 0 3px;border-bottom:0.5px solid var(--border);margin-bottom:2px}\n.ddiv:not(:first-child){margin-top:10px}\n.match{display:flex;align-items:center;gap:7px;padding:5px 2px;border-radius:6px;font-size:12px}\n.match:hover{background:var(--c3)}\n.lleag{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:.3px;width:82px;flex-shrink:0;font-weight:600}\n.lteams{flex:1;font-weight:500}.vs{color:var(--dim);font-weight:400;margin:0 2px}\n.mwhen{font-size:10px;color:var(--muted)}.score{font-weight:700;font-size:13px}\n\n/* ── REDDIT ──────────────────────────────────────────────── */\n.rpost{display:flex;align-items:center;gap:9px;padding:7px 4px;border-radius:7px;border-bottom:0.5px solid var(--border);text-decoration:none;color:var(--text);min-width:0;overflow:hidden}\n.rpost:last-of-type{border-bottom:none}\n.rpost:hover{background:var(--c3)}\n.rimg-wrap{flex-shrink:0;width:52px;height:52px;border-radius:5px;overflow:hidden;background:var(--c3);display:flex;align-items:center;justify-content:center;font-size:22px}\n.rimg-wrap img{width:100%;height:100%;object-fit:cover;display:block}\n.rsort{display:flex;gap:2px;margin-right:6px;flex-shrink:0}\n.rsort-btn{background:transparent;border:0.5px solid var(--border);color:var(--muted);border-radius:5px;padding:2px 8px;font-size:9px;font-weight:600;cursor:pointer;font-family:inherit;text-transform:uppercase;letter-spacing:.3px;transition:background .15s,color .15s}\n.rsort-btn:hover{background:var(--c3);color:var(--text)}\n.rsort-btn.active{background:var(--acc);border-color:var(--acc);color:#1a1a2e}\n.rpost-text{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0;overflow:hidden}\n.rtitle{font-size:11px;font-weight:500;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}\n.rlink{font-size:10px;color:var(--acc);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;min-width:0}\\n.rlink-domain{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n.rmeta{font-size:10px;color:var(--dim)}\n\n/* ── DRTV ────────────────────────────────────────────────── */\n.drgroup+.drgroup{margin-top:14px}\n.drlbl{font-size:12px;font-weight:600;margin-bottom:9px;display:flex;align-items:center;gap:6px}\n.muted{color:var(--muted);font-weight:400}\n.drgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(156px,1fr));gap:9px}\n.drcard{background:var(--c2);border-radius:var(--rs);overflow:hidden;text-decoration:none;color:var(--text);border:0.5px solid var(--border);transition:transform .15s,border-color .15s;display:flex;flex-direction:column}\n.drcard:hover{transform:translateY(-2px);border-color:var(--acc)}\n.drthumb{aspect-ratio:16/9;background:var(--c3)}\n.drthumb img{width:100%;height:100%;object-fit:cover;display:block}\n.drthumb{position:relative}\n.noimg{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--dim);font-size:13px;font-weight:700;letter-spacing:.5px}\n.drinfo{padding:5px 7px 7px}\n.drmeta{font-size:9px;color:var(--acc);font-weight:600;text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px}\n.drtitle{font-size:11px;font-weight:500;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}\n.drtime{font-size:9px;color:var(--dim);margin-top:2px}\n\n/* ── MISC ────────────────────────────────────────────────── */\n.news-list{display:flex;flex-direction:column;gap:6px}\n.news-item{display:flex;flex-direction:column;gap:1px;padding:5px 0;border-bottom:0.5px solid var(--border)}\n.news-item:last-child{border-bottom:none}\n.news-item a{color:var(--text);text-decoration:none;font-size:12px;font-weight:500;line-height:1.4}\n.news-item a:hover{color:var(--acc)}\n.news-item-src{font-size:10px;color:var(--dim)}\n.news-loading{color:var(--muted);font-size:11px;font-style:italic}\n\n.dimtxt{color:var(--dim);font-style:italic;font-size:12px}\n.sumtxt{font-size:15px;line-height:1.85;font-weight:400}\n"
    JS  = '\nconst GAP=10, ROW=40;\nconst YT_KEY=\'AIzaSyA44tu5lawpttQ0gTrvAUJeke5j-azjObw\';\n\nfunction brd(){return document.getElementById(\'board\');}\nfunction cw(){const b=brd().getBoundingClientRect();return(b.width-GAP*11)/12;}\nfunction xToCol(x){const b=brd().getBoundingClientRect();return Math.max(1,Math.min(12,Math.floor((x-b.left)/(cw()+GAP))+1));}\nfunction snapH(h){return Math.max(60,Math.round(h/ROW)*ROW);}\nfunction getCols(el){const m=(el.style.gridColumn||\'\').match(/(\\d+)\\s*\\/\\s*span\\s*(\\d+)/);return m?[+m[1],+m[2]]:[1,4];}\nfunction setCols(el,s,sp){sp=Math.max(1,Math.min(13-s,sp));s=Math.max(1,Math.min(12,s));el.style.gridColumn=s+\'/span \'+sp;}\n\n\n// ── Live news from RSS ────────────────────────────────────────\nconst NEWS_FEEDS = {\n  dk: [\n    \'https://www.dr.dk/nyheder/service/feeds/allenyheder\',\n    \'https://feeds.tv2.dk/nyheder/rss\'\n  ],\n  world: [\n    \'https://feeds.bbci.co.uk/news/world/rss.xml\',\n    \'https://www.theguardian.com/world/rss\'\n  ]\n};\nconst PROXY = \'https://corsproxy.io/?url=\';\n\nasync function fetchRSS(url) {\n  try {\n    const r = await fetch(PROXY + encodeURIComponent(url));\n    if(!r.ok) throw new Error(r.status);\n    const text = await r.text();\n    const parser = new DOMParser();\n    const doc = parser.parseFromString(text, \'text/xml\');\n    const items = [...doc.querySelectorAll(\'item\')];\n    return items.map(it => ({\n      title: it.querySelector(\'title\')?.textContent?.replace(/<!\\[CDATA\\[(.*?)\\]\\]>/s,\'$1\').trim() || \'\',\n      link:  it.querySelector(\'link\')?.textContent?.trim() || \'\'\n    })).filter(i => i.title);\n  } catch(e) { return []; }\n}\n\nasync function loadNews() {\n  const status = document.getElementById(\'news-status\');\n  status.textContent = \'— henter…\';\n  \n  async function renderFeed(feeds, elId, max=8) {\n    const el = document.getElementById(elId);\n    let items = [];\n    for(const url of feeds) {\n      const res = await fetchRSS(url);\n      items = items.concat(res);\n      if(items.length >= max) break;\n    }\n    items = items.slice(0, max);\n    if(!items.length) {\n      el.innerHTML = \'<div class="news-loading">Kunne ikke hente nyheder</div>\';\n      return;\n    }\n    el.innerHTML = items.map(i => `<div class="news-item">\n      <a href="${i.link}" target="_blank" rel="noopener">${i.title}</a>\n    </div>`).join(\'\');\n  }\n\n  await Promise.all([\n    renderFeed(NEWS_FEEDS.dk, \'news-dk\'),\n    renderFeed(NEWS_FEEDS.world, \'news-world\')\n  ]);\n  \n  const now = new Date();\n  status.textContent = `— opdateret ${now.getHours().toString().padStart(2,\'0\')}:${now.getMinutes().toString().padStart(2,\'0\')}`;\n}\n\nloadNews();\nsetInterval(loadNews, 10 * 60 * 1000); // opdater hvert 10 min\n\n// ── Dagens ord fra ordnet.dk ──\n// Ordet indlæses dynamisk på ordnet og kan ikke hentes pålideligt udefra,\n// så vi viser et rent opslag-link i stedet for at gætte forkert.\nfunction loadWord(){\n  const box=document.getElementById(\'word-box\');\n  if(!box)return;\n  box.innerHTML=\'<div class=\"word-tagline\">Dagens ord opdateres dagligt p&aring; ordnet.dk</div>\'+\n    \'<a class=\"word-link\" href=\"https://ordnet.dk/ddo/\" target=\"_blank\" rel=\"noopener\">&#x1F517; Se dagens ord p&aring; ordnet.dk &rarr;</a>\';\n}\nloadWord();\n\n\n// ── Collapse ─────────────────────────────────────────────────\nfunction toggleCard(id){const el=document.getElementById(id);if(!el)return;el.classList.toggle(\'open\');save();}\nfunction toggleDay(id){const el=document.getElementById(id);if(!el)return;el.classList.toggle(\'day-open\');save();}\nfunction toggleWxDay(u){const b=document.getElementById(u+\'-btn\');const d=document.getElementById(u+\'-detail\');if(!b||!d)return;const o=b.classList.toggle(\'wx-open\');d.classList.toggle(\'wx-open\',o);}\nfunction toggleInline(id,btn){const w=document.getElementById(id);if(!w)return;const o=w.classList.toggle(\'open\');btn.textContent=o?btn.dataset.less:btn.dataset.more;}\nfunction setRedditSort(cid,sort){const card=document.getElementById(cid);if(!card)return;card.querySelectorAll(\'.rsort-btn\').forEach(b=>b.classList.toggle(\'active\',b.dataset.sort===sort));card.querySelectorAll(\'.rsort-list\').forEach(l=>l.style.display=(l.dataset.sort===sort)?\'\':\'none\');}\n\n// ── Search ───────────────────────────────────────────────────\nfunction doSearch(e,base){e.preventDefault();const q=e.target.querySelector(\'input\').value.trim();if(q)window.open(base+encodeURIComponent(q),\'_blank\');}\nfunction searchReddit(e){doSearch(e,\'https://www.reddit.com/search/?q=\');}\n\nlet ytTimer=null;\nfunction debounceYT(val){\n  clearTimeout(ytTimer);\n  const box=document.getElementById(\'yt-results\');\n  if(!val.trim()){box.innerHTML=\'\';box.style.display=\'none\';return;}\n  ytTimer=setTimeout(()=>runYT(val),400);\n}\nfunction searchYT(e){e.preventDefault();runYT(e.target.querySelector(\'input\').value.trim());}\nasync function runYT(q){\n  if(!q)return;\n  const box=document.getElementById(\'yt-results\');\n  box.style.display=\'flex\';\n  box.innerHTML=\'<div class="sr-loading">Søger…</div>\';\n  try{\n    const data=await fetch(`https://www.googleapis.com/youtube/v3/search?part=snippet&q=${encodeURIComponent(q)}&maxResults=6&type=video&key=${YT_KEY}`).then(r=>r.json());\n    if(data.error){box.innerHTML=`<div class="sr-error">${data.error.message}</div>`;return;}\n    box.innerHTML=data.items.map(it=>`<a class="sr-item" href="https://www.youtube.com/watch?v=${it.id.videoId}" target="_blank">\n      <img class="sr-thumb" src="${it.snippet.thumbnails.default.url}" alt="">\n      <div class="sr-body"><div class="sr-title">${it.snippet.title}</div><div class="sr-meta">${it.snippet.channelTitle}</div></div>\n    </a>`).join(\'\');\n  }catch(e){box.innerHTML=`<div class="sr-error">${e.message}</div>`;}\n}\n\n// ── Drag ─────────────────────────────────────────────────────\nfunction onHeaderMD(e,id){\n  if(e.button!==0)return;\n  if(e.target.closest(\'.card-chev,button,a,.day-head,.wx-day\'))return;\n  startDrag(e,id);\n}\nlet DS=null;\nfunction startDrag(e,id){\n  e.preventDefault();\n  const card=document.getElementById(id);\n  if(!card)return;\n  const rect=card.getBoundingClientRect();\n  DS={card,startX:e.clientX,startY:e.clientY,\n      ox:e.clientX-rect.left, oy:e.clientY-rect.top,\n      origCol:card.style.gridColumn,origNext:card.nextSibling,\n      started:false,cancelled:false,ghost:null,ph:null};\n  document.addEventListener(\'mousemove\',onDragMove);\n  document.addEventListener(\'mouseup\',onDragUp);\n  document.addEventListener(\'keydown\',onDragKey);\n}\nfunction onDragMove(e){\n  if(!DS)return;\n  if(!DS.started){\n    if(Math.hypot(e.clientX-DS.startX,e.clientY-DS.startY)<5)return;\n    const card=DS.card;\n    const rect=card.getBoundingClientRect();\n    const ghost=card.cloneNode(true);\n    ghost.removeAttribute(\'id\');\n    ghost.style.cssText=`position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;min-height:${rect.height}px;z-index:1000;pointer-events:none;opacity:.88;border-radius:12px;box-shadow:0 12px 40px #00000070;background:#2e3248;border:1.5px solid #a78bfa;overflow:hidden;transition:none;`;\n    document.body.appendChild(ghost);\n    const ph=document.createElement(\'div\');\n    ph.id=\'_ph\'; ph.className=\'drop-placeholder\';\n    ph.style.gridColumn=DS.origCol;\n    ph.style.minHeight=card.offsetHeight+\'px\';\n    card.parentNode.insertBefore(ph,card);\n    card.remove();\n    DS.ghost=ghost; DS.ph=ph; DS.started=true;\n  }\n  const {ghost,ph,ox,oy,origCol}=DS;\n  ghost.style.left=(e.clientX-ox)+\'px\';\n  ghost.style.top=(e.clientY-oy)+\'px\';\n  const sp=+origCol.match(/span\\s*(\\d+)/)[1];\n  const b=brd();\n  const br=b.getBoundingClientRect();\n  const colW=cw()+GAP;\n  const ghostLeft=e.clientX-ox;\n  let newStart=Math.round((ghostLeft-br.left)/colW)+1;\n  newStart=Math.max(1,Math.min(13-sp,newStart));\n  ph.style.gridColumn=newStart+\'/span \'+sp;\n  const cards=[...b.children].filter(c=>c!==ph&&c.classList.contains(\'dash-card\'));\n  const ghostTop=e.clientY-oy;\n  let bestIns=null;\n  for(const c of cards){\n    const cr=c.getBoundingClientRect();\n    const sameRow=Math.abs(cr.top-ghostTop)<cr.height*0.6;\n    if(sameRow) continue;\n    if(e.clientY < cr.top+cr.height*0.5){ bestIns=c; break; }\n  }\n  if(bestIns) b.insertBefore(ph,bestIns);\n  else b.appendChild(ph);\n}\nfunction onDragUp(){\n  if(!DS)return;\n  const {card,ghost,ph,origCol,origNext,started,cancelled}=DS;\n  if(!started){cleanup();return;}\n  if(!cancelled){\n    card.style.gridColumn=ph.style.gridColumn;\n    ph.before(card);\n    // Remove smartReflow — let user control placement manually\n  } else {\n    card.style.gridColumn=origCol;\n    if(origNext)brd().insertBefore(card,origNext);else brd().appendChild(card);\n  }\n  ghost.remove();ph.remove();\n  cleanup();save();\n}\nfunction cleanup(){\n  document.removeEventListener(\'mousemove\',onDragMove);\n  document.removeEventListener(\'mouseup\',onDragUp);\n  document.removeEventListener(\'keydown\',onDragKey);\n  DS=null;\n}\nfunction onDragKey(e){if(e.key===\'Escape\'&&DS){DS.cancelled=true;onDragUp();}}\n\n// ── Resize corner ─────────────────────────────────────────────\nlet RS=null;\nfunction onResizeSE(e){startR(e,\'se\');}\nfunction onResizeSW(e){startR(e,\'sw\');}\nfunction startR(e,dir){\n  e.preventDefault();e.stopPropagation();\n  const card=e.currentTarget.closest(\'.dash-card\');\n  const [s,sp]=getCols(card);\n  RS={card,dir,x0:e.clientX,y0:e.clientY,sp0:sp,s0:s,h0:card.offsetHeight};\n  document.addEventListener(\'mousemove\',onRM);document.addEventListener(\'mouseup\',onRE);\n}\nfunction onRM(e){\n  if(!RS)return;\n  const {card,dir,x0,y0,sp0,s0,h0}=RS;\n  const dc=Math.round((e.clientX-x0)/(cw()+GAP));\n  if(dir===\'se\')setCols(card,s0,sp0+dc);\n  else{const ns=Math.max(1,Math.min(s0+sp0-1,s0+dc));setCols(card,ns,sp0+(s0-ns));}\n  card.style.minHeight=snapH(h0+(e.clientY-y0))+\'px\';\n}\nfunction onRE(){document.removeEventListener(\'mousemove\',onRM);document.removeEventListener(\'mouseup\',onRE);RS=null;save();}\n\n// ── Reset & Persist ───────────────────────────────────────────\nconst DEF={\n  cal:{col:\'1/span 7\',h:\'\'},fb:{col:\'8/span 5\',h:\'\'},\n  \'reddit-Denmark\':{col:\'1/span 4\',h:\'\'},\'reddit-worldnews\':{col:\'5/span 4\',h:\'\'},\'reddit-soccer\':{col:\'9/span 4\',h:\'\'},\n  drtv:{col:\'1/span 12\',h:\'\'},\n};\nconst DEF_ORDER=[\'cal\',\'fb\',\'reddit-Denmark\',\'reddit-worldnews\',\'reddit-soccer\',\'drtv\'];\nconst DEF_OPEN=[\'cal\',\'fb\',\'reddit-Denmark\',\'reddit-worldnews\',\'reddit-soccer\',\'drtv\'];\n\nfunction resetLayout(){\n  const b=brd();\n  DEF_ORDER.forEach(id=>{\n    const el=document.getElementById(id);if(!el)return;\n    el.style.gridColumn=DEF[id].col;el.style.minHeight=\'\';b.appendChild(el);\n  });\n  document.querySelectorAll(\'.dash-card\').forEach(el=>el.classList.toggle(\'open\',DEF_OPEN.includes(el.id)));\n  document.querySelectorAll(\'.day-col\').forEach(el=>el.classList.toggle(\'day-open\',el.classList.contains(\'today-col\')));\n  [\'db8_l\',\'db8_o\',\'db8_d\',\'db8_s\'].forEach(k=>localStorage.removeItem(k));\n}\nfunction save(){\n  const b=brd();const layout={};\n  [...b.children].forEach((el,i)=>{if(!el.classList.contains(\'dash-card\'))return;layout[el.id]={col:el.style.gridColumn,h:el.style.minHeight||\'\',i};});\n  const open=[];document.querySelectorAll(\'.dash-card.open\').forEach(el=>open.push(el.id));\n  const day=[];document.querySelectorAll(\'.day-col.day-open\').forEach(el=>day.push(el.id));\n  localStorage.setItem(\'db8_l\',JSON.stringify(layout));\n  localStorage.setItem(\'db8_o\',JSON.stringify(open));\n  localStorage.setItem(\'db8_d\',JSON.stringify(day));\n  localStorage.setItem(\'db8_s\',\'1\');\n}\nfunction restore(){\n  if(localStorage.getItem(\'db8_s\')!==\'1\')return;\n  try{const l=JSON.parse(localStorage.getItem(\'db8_l\')||\'{}\');const b=brd();Object.entries(l).sort((a,c)=>(a[1].i||0)-(c[1].i||0)).forEach(([id,s])=>{const el=document.getElementById(id);if(!el)return;if(s.col)el.style.gridColumn=s.col;if(s.h)el.style.minHeight=s.h;b.appendChild(el);});}catch(e){}\n  try{const o=JSON.parse(localStorage.getItem(\'db8_o\')||\'[]\');document.querySelectorAll(\'.dash-card\').forEach(el=>el.classList.toggle(\'open\',o.includes(el.id)));}catch(e){}\n  try{const d=JSON.parse(localStorage.getItem(\'db8_d\')||\'[]\');document.querySelectorAll(\'.day-col\').forEach(el=>el.classList.toggle(\'day-open\',d.includes(el.id)));}catch(e){}\n}\nrestore();\n'

    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard &mdash; {esc(date_label)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="logo">Mit <em>Dashboard</em></div>
  <div class="hdate">{esc(date_label)} &middot; {esc(time_str)}</div>
  <button class="reset-btn" onclick="resetLayout()">&#x21BA; Nulstil</button>
  <a class="upbtn" href="{esc(UPNOTE_URL)}">&#x1F4DD; UpNote</a>
</header>
<div id="top-bar">
  <div id="top-search">
    <div class="s-item"><div class="s-lbl"><span class="s-logo g">G</span> Google</div>
      <form class="s-form" onsubmit="doSearch(event,'https://www.google.com/search?q=')">
        <input class="s-input" type="text" placeholder="S&oslash;g p&aring; Google&hellip;" autocomplete="off"></form></div>
    <div class="s-item"><div class="s-lbl"><span class="s-logo r">r/</span> Reddit</div>
      <form class="s-form" onsubmit="doSearch(event,'https://www.reddit.com/search/?q=')">
        <input class="s-input" type="text" placeholder="S&oslash;g p&aring; Reddit&hellip;" autocomplete="off"></form></div>
    <div class="s-item"><div class="s-lbl"><span class="s-logo yt">&#x25BA;</span> YouTube</div>
      <form class="s-form" onsubmit="searchYT(event)">
        <input class="s-input" id="yt-input" type="text" placeholder="S&oslash;g p&aring; YouTube&hellip;" autocomplete="off"
          oninput="debounceYT(this.value)"
          onfocus="document.getElementById('yt-results').style.display='flex'"
          onblur="setTimeout(()=>document.getElementById('yt-results').style.display='none',200)">
      </form>
      <div class="search-results" id="yt-results"></div></div>
    <div class="s-item"><div class="s-lbl"><span class="s-logo imdb">IMDb</span></div>
      <form class="s-form" onsubmit="doSearch(event,'https://www.imdb.com/find/?q=')">
        <input class="s-input" type="text" placeholder="Film, serier&hellip;" autocomplete="off"></form></div>
    <div class="s-item"><div class="s-lbl"><img src="https://ssl.gstatic.com/images/branding/product/1x/drive_2020q4_32dp.png" style="width:20px;height:20px;object-fit:contain;flex-shrink:0"> Google Drive</div>
      <form class="s-form" onsubmit="doSearch(event,'https://drive.google.com/drive/search?q=')">
        <input class="s-input" type="text" placeholder="S&oslash;g i Drive&hellip;" autocomplete="off"></form></div>
  </div>
  <div id="top-info">
    <div id="top-row1">
      <div id="top-sum">
        <div class="top-section-label">&#x1F305; Din dag</div>
        <p class="sumtxt">{esc(day_summary)}</p>
        {funfacts_html}
      </div>
      <div></div>
      <div id="top-wx">
        <div class="top-section-label">&#x1F324; Vejr &mdash; K&oslash;benhavn</div>
        <div class="top-wx-grid">
          <div class="wx-now">{wx_top_html}</div>
          <div class="wx-forecast" style="margin-left:18px">{wx_forecast_html}</div>
        </div>
        {otd_html}
      </div>
    </div>
    <div id="top-row2">
      <div id="top-wiki">
        <div class="top-section-label">&#x1F4DA; Dagens Wikipedia-artikel</div>
        {wiki_html}
      </div>
      <div id="top-word">
        <div class="top-section-label">&#x1F1E9;&#x1F1F0; Dagens ord &mdash; ordnet.dk</div>
        {word_html}
      </div>
    </div>
    <div id="top-news">
      <div class="top-section-label">&#x1F4F0; Nyheder</div>
      <div class="news2">
        <div><div class="catlbl">&#x1F1E9;&#x1F1F0; Danmark</div><p class="newsp">{news_dk_html}</p></div>
        <div><div class="catlbl">&#x1F30D; Verden</div><p class="newsp">{news_w_html}</p></div>
      </div>
    </div>
  </div>
</div>
<div id="board">
<div class="dash-card open" id="cal" style="grid-column:1/span 7">
  <div class="card-head" onmousedown="onHeaderMD(event,'cal')">
    <span class="drag-handle">&#x283F;</span><span class="card-icon">&#x1F4C5;</span>
    <span class="card-title">Kalender</span>
    <svg class="card-chev" onclick="toggleCard('cal')" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>
  </div>
  <div class="card-body-wrap"><div class="card-body">{cal_body}</div></div>
  {RESW}{RESE}
</div>
<div class="dash-card open" id="fb" style="grid-column:8/span 5">
  <div class="card-head" onmousedown="onHeaderMD(event,'fb')">
    <span class="drag-handle">&#x283F;</span><span class="card-icon">&#x26BD;</span>
    <span class="card-title">Fodboldkampe</span>
    <svg class="card-chev" onclick="toggleCard('fb')" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>
  </div>
  <div class="card-body-wrap"><div class="card-body">{fb_body}</div></div>
  {RESW}{RESE}
</div>
{reddit_cards_html}
<div class="dash-card open" id="drtv" style="grid-column:1/span 12">
  <div class="card-head" onmousedown="onHeaderMD(event,'drtv')">
    <span class="drag-handle">&#x283F;</span><span class="card-icon">&#x1F4FA;</span>
    <span class="card-title">Netop tilf&oslash;jet p&aring; DRTV</span>
    <svg class="card-chev" onclick="toggleCard('drtv')" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"/></svg>
  </div>
  <div class="card-body-wrap"><div class="card-body">{drtv_body}</div></div>
  {RESW}{RESE}
</div>
</div>
<script>{JS}</script>
</body>
</html>"""

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_local=datetime.now(LOCAL_TZ)
    today=now_local.date(); yesterday=today-timedelta(days=1)

    print("📅 Henter kalendre …")
    cal_events,cal_errors=fetch_calendar_events()
    print("🌙 Henter astronomi …")
    astro=fetch_astronomy(now_local)
    print("🌅 Dagsopsummering …")
    day_summary=summarize_day(events_for_day(cal_events,today),now_local,astro)
    print("📰 Henter nyheder …")
    dk_prose,w_prose=fetch_news()
    print("📚 Henter Wikipedia …")
    wiki=fetch_wikipedia_featured(now_local)
    # Oversæt "skete på denne dag" til dansk
    # Vælg et spredt udsnit på tværs af historien (ikke kun de nyeste)
    _otd_all = wiki.get("onthisday", [])
    if len(_otd_all) > 7:
        # Sorteret nyeste->ældste; tag jævnt fordelte stik så vi får både gammelt og nyt
        step = len(_otd_all) / 7.0
        _otd_sel = [_otd_all[int(i*step)] for i in range(7)]
    else:
        _otd_sel = _otd_all
    wiki["onthisday"]=translate_onthisday(_otd_sel)
    print("✨ Henter interessante fakta …")
    funfacts=fetch_fun_facts(now_local)
    print("🌤  Henter vejr …")
    wx_now,wx_forecast=fetch_weather()
    print("⚽ Henter fodbold …")
    matches,football_errors=fetch_football()
    print("💬 Henter Reddit …")
    reddit_by_sub=fetch_reddit()
    print("📺 Henter DRTV …")
    drtv_today,drtv_yesterday=[],[]
    drtv_data=fetch_drtv()
    if drtv_data:
        container=find_newest_list(drtv_data)
        if container:
            programs=[parse_drtv_item(r) for r in container.get("items",[])]
            programs=[p for p in programs if p["title"]]
            drtv_today,drtv_yesterday=filter_drtv(programs,today,yesterday)
            print(f"  I dag: {len(drtv_today)}  I går: {len(drtv_yesterday)}")

    print("🖥️  Genererer …")
    html=generate_html(day_summary,dk_prose,w_prose,
        wx_now,wx_forecast,
        cal_events,cal_errors,matches,football_errors,
        reddit_by_sub,drtv_today,drtv_yesterday,now_local,
        wiki,astro,funfacts)
    with HTML_FILE.open("w",encoding="utf-8") as f: f.write(html)
    print(f"\n✅ Gemt: {HTML_FILE}")
    if not os.environ.get("CI") and os.environ.get("OPEN_BROWSER","1")=="1":
        try: webbrowser.open(HTML_FILE.resolve().as_uri())
        except Exception: pass

if __name__=="__main__": main()
