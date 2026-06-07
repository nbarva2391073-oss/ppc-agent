#!/usr/bin/env python3
"""Influencer Finder Agent"""

import os, json, time, requests
from datetime import datetime

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")

HASHTAGS = [
    "amazon","amazonfinds","amazonbeauty","amazonfragrance",
    "confidence","selfcare","personalstyle","morningroutine",
    "quietluxury","attraction","selflove","beauty","fragrance","perfume",
]

SHEETS_MAP = {
    "instagram": {"nano":"Instagram Нано","micro":"Instagram Мікро","macro":"Instagram Макро"},
    "tiktok":    {"nano":"TikTok Нано",   "micro":"TikTok Мікро",   "macro":"TikTok Макро"},
    "youtube":         {"nano":"YouTube Нано",        "micro":"YouTube Мікро",        "macro":"YouTube Макро"},
    "youtube_shorts":  {"nano":"YouTube Shorts Нано", "micro":"YouTube Shorts Мікро", "macro":"YouTube Shorts Макро"},
}

HEADERS = [
    "Дата збору","Платформа","Username","Повне імя",
    "Підписники","Підписки","ER%","Avg Likes","Avg Comments",
    "Останній пост","Верифікований","Amazon досвід","Спонсорський %",
    "Скор (1-100)","Рівень","Red Flags","Посилання",
]

APIFY_ACTORS = {
    "Instagram":      "reGe1ST3OBgYZSsZJ",
    "TikTok":         "clockworks/tiktok-hashtag-scraper",
    "YouTube":        "streamers/youtube-scraper",
    "YouTube Shorts": "streamers/youtube-shorts-scraper",
}

APIFY_BASE = "https://api.apify.com/v2"


def run_actor(actor_id, actor_input, timeout=300):
    r = requests.post(
        f"{APIFY_BASE}/acts/{actor_id}/runs",
        params={"token": APIFY_TOKEN}, json=actor_input, timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"  WARNING {actor_id}: {r.status_code}")
        return []
    run_id = r.json()["data"]["id"]
    print(f"  Actor запущено ({run_id[:8]}...)")
    waited = 0
    status_r = None
    while waited < timeout:
        time.sleep(15); waited += 15
        status_r = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}", params={"token": APIFY_TOKEN})
        status = status_r.json()["data"]["status"]
        if status == "SUCCEEDED": break
        if status in ("FAILED","ABORTED","TIMED-OUT"):
            print(f"  Actor {status}"); return []
        print(f"  {status} ({waited}s)...")
    if not status_r: return []
    dataset_id = status_r.json()["data"]["defaultDatasetId"]
    items = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN, "format": "json", "limit": 500},
    ).json()
    result = items if isinstance(items, list) else []
    print(f"  Отримано: {len(result)} записів")
    return result


def scrape_instagram(hashtags):
    print("\n Instagram...")
    profiles = {}
    for tag in hashtags[:6]:
        for item in run_actor(APIFY_ACTORS["Instagram"], {"hashtags":[tag],"resultsLimit":50}):
            u = item.get("ownerUsername") or item.get("owner",{}).get("username","")
            if u and u not in profiles:
                # actor reGe1ST3OBgYZSsZJ може повертати різні поля — перевіряємо всі варіанти
                followers = (
                    item.get("ownerFollowersCount") or
                    item.get("followersCount") or
                    item.get("owner", {}).get("followersCount") or
                    item.get("authorFollowersCount") or 0
                )
                profiles[u] = {
                    "username": u,
                    "full_name": (item.get("ownerFullName") or item.get("fullName") or ""),
                    "platform": "instagram",
                    "followers": int(followers),
                    "following": int(item.get("ownerFollowingCount") or item.get("followingCount") or 0),
                    "avg_likes": int(item.get("likesCount") or item.get("likes") or 0),
                    "avg_comments": int(item.get("commentsCount") or item.get("comments") or 0),
                    "last_post_date": item.get("timestamp") or item.get("takenAt") or "",
                    "bio": item.get("ownerBio") or item.get("biography") or "",
                    "verified": bool(item.get("ownerVerified") or item.get("verified") or False),
                    "profile_url": f"https://instagram.com/{u}",
                }
        time.sleep(3)
    return list(profiles.values())


def scrape_tiktok(hashtags):
    print("\n TikTok...")
    profiles = {}
    for tag in hashtags[:6]:
        for item in run_actor(APIFY_ACTORS["TikTok"], {"hashtags":[tag],"resultsPerPage":50}):
            a = item.get("authorMeta",{})
            u = a.get("name","")
            if u and u not in profiles:
                profiles[u] = {
                    "username": u, "full_name": a.get("nickName",""),
                    "platform": "tiktok", "followers": a.get("fans",0),
                    "following": a.get("following",0),
                    "avg_likes": item.get("diggCount",0), "avg_comments": item.get("commentCount",0),
                    "last_post_date": str(item.get("createTime","")), "bio": a.get("signature",""),
                    "verified": a.get("verified",False),
                    "profile_url": f"https://tiktok.com/@{u}",
                }
        time.sleep(3)
    return list(profiles.values())


def scrape_youtube(hashtags):
    print("\n YouTube...")
    profiles = {}
    for tag in hashtags[:4]:
        for item in run_actor(APIFY_ACTORS["YouTube"], {"searchKeywords":tag,"maxResults":30}):
            cid = item.get("channelId","")
            if cid and cid not in profiles:
                profiles[cid] = {
                    "username": cid, "full_name": item.get("channelName",""),
                    "platform": "youtube", "followers": item.get("channelSubscriberCount",0),
                    "following": 0, "avg_likes": item.get("likes",0),
                    "avg_comments": item.get("commentsCount",0),
                    "last_post_date": item.get("date",""), "bio": item.get("channelDescription",""),
                    "verified": item.get("isVerified",False),
                    "profile_url": item.get("channelUrl", f"https://youtube.com/{cid}"),
                }
        time.sleep(3)
    return list(profiles.values())


def scrape_youtube_shorts(hashtags):
    print("\n YouTube Shorts...")
    profiles = {}
    for tag in hashtags[:4]:
        for item in run_actor(APIFY_ACTORS["YouTube Shorts"], {"searchKeywords":tag,"maxResults":30}):
            cid = item.get("channelId","")
            if cid and cid not in profiles:
                profiles[cid] = {
                    "username": cid, "full_name": item.get("channelName",""),
                    "platform": "youtube_shorts", "followers": item.get("channelSubscriberCount",0),
                    "following": 0, "avg_likes": item.get("likes",0),
                    "avg_comments": item.get("commentsCount",0),
                    "last_post_date": item.get("date",""), "bio": item.get("channelDescription",""),
                    "verified": item.get("isVerified",False),
                    "profile_url": item.get("channelUrl", f"https://youtube.com/{cid}"),
                }
        time.sleep(3)
    return list(profiles.values())


SPANISH_STOPWORDS = {
    "de","la","que","el","en","y","a","los","del","se","las","por","un","para",
    "con","no","una","su","al","lo","como","pero","sus","le","ya","este","soy",
    "mi","porque","está","entre","cuando","muy","sin","sobre","ser","tiene",
    "también","fue","hay","si","fue","hola","gracias","aquí","ahora","todo",
    "bien","más","sólo","años","quiero","puedo","hacer","tengo","cada","vez",
    "nueva","nuevo","siempre","mundo","amor","vida","trabajo","gente","mujer",
    "perfume","fragancia","belleza","maquillaje","ropa","moda","estilo",
}

SPANISH_CHARS = {"ñ","á","é","í","ó","ú","¿","¡"}

def _is_spanish(text: str) -> bool:
    """Перевіряє чи текст іспанський."""
    if not text:
        return False
    text_lower = text.lower()
    # Перевірка іспанських символів
    if any(ch in text_lower for ch in SPANISH_CHARS):
        return True
    # Перевірка іспанських стоп-слів
    words = set(text_lower.split())
    matches = words & SPANISH_STOPWORDS
    return len(matches) >= 3


def check_red_flags(p):
    flags = []
    f = p.get("followers",0); al = p.get("avg_likes",0); ac = p.get("avg_comments",0)
    er = (al+ac)/f*100 if f>0 else 0
    if f>0 and er<1.0: flags.append(f"ER {er:.1f}%")
    if al>10 and ac==0: flags.append("Лайки без коментарів")
    lp = p.get("last_post_date","")
    if lp:
        try:
            if "T" in str(lp):
                dt = datetime.fromisoformat(str(lp)[:19])
                if (datetime.now()-dt).days>60: flags.append("Пост > 60 днів")
        except: pass
    if f<100_000 and p.get("following",0)>f: flags.append("Підписок > підписників")
    # Перевірка мови — відхиляємо якщо іспанська
    bio = p.get("bio","") or ""
    if _is_spanish(bio): flags.append("Іспанська мова")
    return flags


def calculate_score(p):
    score = 0
    f = p.get("followers",0); al = p.get("avg_likes",0); ac = p.get("avg_comments",0)
    bio = (p.get("bio","") or "").lower()
    er = (al+ac)/f*100 if f>0 else 0
    if er>=6: score+=25
    elif er>=3: score+=18
    elif er>=1: score+=10
    niche = ["perfume","fragrance","pheromone","beauty","skincare","selfcare","amazon","lifestyle","wellness","scent"]
    score += min(20, sum(1 for kw in niche if kw in bio)*5)
    if al>0 and ac>0:
        r = ac/al
        if r>=0.05: score+=15
        elif r>=0.02: score+=10
        else: score+=5
    lp = p.get("last_post_date",""); days=999
    try:
        if "T" in str(lp): days=(datetime.now()-datetime.fromisoformat(str(lp)[:19])).days
    except: pass
    if days<=7: score+=15
    elif days<=30: score+=10
    elif days<=60: score+=5
    if f>0:
        rate=(al+ac)/f
        if rate>=0.08: score+=15
        elif rate>=0.03: score+=10
        elif rate>=0.01: score+=5
    if any(kw in bio for kw in ["amazon","storefront"]): score+=10
    return min(100,score)


def get_tier(f):
    if f == 0:
        return None  # відхиляємо — невідома аудиторія
    if f < 10_000:  return "nano"
    if f < 100_000: return "micro"
    return "macro"


def profile_to_row(p, flags, score):
    f=p.get("followers",0); al=p.get("avg_likes",0); ac=p.get("avg_comments",0)
    er=round((al+ac)/f*100,2) if f>0 else 0
    bio=(p.get("bio","") or "").lower()
    return [
        datetime.now().strftime("%Y-%m-%d"), p.get("platform",""),
        p.get("username",""), p.get("full_name",""),
        f, p.get("following",0), er, round(al), round(ac),
        str(p.get("last_post_date",""))[:10],
        "YES" if p.get("verified") else "",
        "YES" if any(kw in bio for kw in ["amazon","storefront"]) else "",
        "", score, get_tier(f),
        ", ".join(flags) if flags else "OK",
        p.get("profile_url",""),
    ]


def write_to_sheets(results):
    print("\n Записуємо в Sheets...")
    from google.oauth2.service_account import Credentials
    import gspread
    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"],
    )
    ss = gspread.Client(auth=creds).open_by_key(SPREADSHEET_ID)
    for platform, tiers in results.items():
        for tier, rows in tiers.items():
            name = SHEETS_MAP[platform][tier]
            try:
                try: sh = ss.worksheet(name)
                except: sh = ss.add_worksheet(title=name, rows=200, cols=25)
                sh.clear()
                top30 = sorted(rows, key=lambda x: x[13], reverse=True)[:30]
                sh.update("A1", [HEADERS]+top30)
                print(f"  {name}: {len(top30)}")
            except Exception as e:
                print(f"  ERROR {name}: {e}")


def main():
    print("="*60)
    print(f"INFLUENCER FINDER: {datetime.now()}")
    print("="*60)
    all_p = scrape_instagram(HASHTAGS)+scrape_tiktok(HASHTAGS)+scrape_youtube(HASHTAGS)+scrape_youtube_shorts(HASHTAGS)
    print(f"\nЗнайдено: {len(all_p)}")
    results = {pl:{t:[] for t in ["nano","micro","macro"]} for pl in ["instagram","tiktok","youtube","youtube_shorts"]}
    passed = 0
    for p in all_p:
        flags = check_red_flags(p)
        if flags: continue
        score = calculate_score(p)
        if score<20: continue
        pl = p.get("platform",""); tier = get_tier(p.get("followers",0))
        if pl in results and tier is not None:
            results[pl][tier].append(profile_to_row(p,flags,score))
            passed+=1
    print(f"Пройшли: {passed}/{len(all_p)}")
    write_to_sheets(results)
    print("\nГотово!")

if __name__=="__main__":
    main()
