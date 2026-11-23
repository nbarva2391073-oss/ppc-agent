# ============================================================
# ASIN COCKPIT — щоденні сигнали (Етап 1), Amazon Ads API (SP).
#  1. Ad SKU Status <M>: кампанія → група → оголошення → ASIN → SKU + state/servingStatus
#     + покази оголошення за D-1 і D-2.
#  2. Тривога Telegram: ENABLED кампанія/оголошення має 0 показів 2 дні поспіль.
#  3. Placement Daily <M>: щоденні плейсменти (Top / Rest / Product pages) по кампанії.
#  4. SP Targets Daily <M>: щоденний звіт по таргетах, включно з таргетами без кліків.
#  5. Suggested Bids: тривоги (бід нижче мінімуму коридору; коридор ±30% за тиждень).
# Нічого в Amazon не змінює. Нові вкладки; наявні не чіпає.
# Env: MARKET=USA, AS_OF=YYYY-MM-DD (бектест: без Telegram/логу/запису),
#      DRY_RUN=1, ONLY=status,placement,targets,bids
# ============================================================
import json, os, time, traceback
from datetime import datetime, timedelta
from collections import defaultdict
from config import ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA, is_excluded_campaign
from amazon_ads import get_access_token, submit_report, wait_and_download
from suggested_bids import _paged, ADS_BASE_URL
from sheet_util import ensure_tab, replace_dates, retry, ss

MARKET = os.getenv("MARKET", "USA")
AS_OF = os.getenv("AS_OF", "")
DRY = os.getenv("DRY_RUN", "") in ("1", "true", "True")
BACKTEST = bool(AS_OF)
ONLY = [x for x in os.getenv("ONLY", "").split(",") if x]
PROFILE = ADS_PROFILE_ID_USA if MARKET == "USA" else ADS_PROFILE_ID_CA
OUT = "diag/signals" + ("" if MARKET == "USA" else f"_{MARKET}"); os.makedirs(OUT, exist_ok=True)

TAB_STATUS = f"Ad SKU Status {MARKET}"
TAB_PLACE = f"Placement Daily {MARKET}"
TAB_TARGETS = f"SP Targets Daily {MARKET}"
TAB_LOG = f"Signal Log {MARKET}"

H_STATUS = ["Date", "CampaignId", "Campaign", "CampaignState", "CampaignServing", "AdGroupId", "AdGroup",
            "AdGroupState", "AdGroupServing", "AdId", "ASIN", "SKU", "AdState", "AdServing",
            "AdServingDetails", "AdCreated", "Impr_D1", "Impr_D2"]
H_PLACE = ["Date", "Campaign", "CampaignId", "Placement", "PlacementRaw", "Impressions", "Clicks",
           "Cost", "Sales7d", "Orders7d"]
H_TARGETS = ["Date", "Campaign", "CampaignId", "AdGroup", "AdGroupId", "KeywordId", "Targeting", "Keyword",
             "MatchType", "KeywordBid", "Impressions", "Clicks", "Cost", "Sales7d", "Orders7d", "TopOfSearchIS"]
H_LOG = ["Date", "Type", "Key", "Detail"]


def want(x):
    return not ONLY or x in ONLY


def today_utc():
    return datetime.strptime(AS_OF, "%Y-%m-%d") if AS_OF else datetime.utcnow()


def dstr(d):
    return d.strftime("%Y-%m-%d")


def ct(kind):
    return {"c": "application/vnd.spCampaign.v3+json", "g": "application/vnd.spAdGroup.v3+json",
            "a": "application/vnd.spProductAd.v3+json"}[kind]


def fetch_structure(token):
    pl = {"maxResults": 100, "includeExtendedDataFields": True,
          "stateFilter": {"include": ["ENABLED", "PAUSED"]}}
    camps = _paged(token, PROFILE, f"{ADS_BASE_URL}/sp/campaigns/list", ct("c"), pl, "campaigns")
    groups = _paged(token, PROFILE, f"{ADS_BASE_URL}/sp/adGroups/list", ct("g"), pl, "adGroups")
    ads = _paged(token, PROFILE, f"{ADS_BASE_URL}/sp/productAds/list", ct("a"), pl, "productAds")
    print(f"  ✅ Кампаній {len(camps)}, груп {len(groups)}, оголошень {len(ads)}")
    return camps, groups, ads


def run_report(token, name, rtype, cols, group, start, end, unit="DAILY", fallback=None):
    for attempt, c in enumerate([cols] + ([fallback] if fallback else [])):
        try:
            rid = submit_report(token, PROFILE, name, rtype, c, group, start, end, time_unit=unit)
            return wait_and_download(get_access_token(), PROFILE, rid, max_wait=(900 if fallback and attempt == 0 else 2400), token_fn=get_access_token)
        except Exception as e:
            print(f"  ⚠️ {name}: спроба {attempt + 1} не вдалась: {str(e)[:200]}")
    return None


def tg(text):
    if BACKTEST or DRY:
        print("[TELEGRAM-DRY]\n" + text); return
    from telegram_bot import send_message
    send_message(text)


def recent_log_keys(days=7):
    try:
        ws = ss().worksheet(TAB_LOG)
        vals = retry(ws.get_all_values)
    except Exception:
        return set()
    cut = dstr(datetime.utcnow() - timedelta(days=days))
    return {(r[1], r[2]) for r in vals[1:] if len(r) > 2 and r[0][:10] >= cut}


def append_log(rows):
    if not rows or BACKTEST or DRY:
        return
    ws = ensure_tab(TAB_LOG, H_LOG)
    need = len(retry(ws.col_values, 1)) + len(rows) + 5
    if need > ws.row_count:
        retry(ws.resize, rows=need)
    retry(ws.append_rows, rows, value_input_option="RAW", table_range="A1")


def x(d, *path, default=""):
    for p in path:
        d = (d or {}).get(p) if isinstance(d, dict) else None
    return default if d is None else d


# ── 1+2. Статус оголошень і тривога «0 показів 2 дні» ─────────────────────
def job_status(token, camps, groups, ads):
    now = today_utc()
    d1, d2 = dstr(now - timedelta(days=1)), dstr(now - timedelta(days=2))
    rep = run_report(
        token, f"adv_sku {d2}..{d1}", "spAdvertisedProduct",
        ["date", "campaignName", "campaignId", "adGroupName", "adGroupId", "advertisedAsin", "advertisedSku",
         "impressions", "clicks", "cost"], ["advertiser"], d2, d1,
        fallback=["date", "campaignName", "campaignId", "adGroupId", "advertisedAsin", "impressions", "clicks", "cost"])
    if rep is None:
        print("  ❌ Звіт показів недоступний — тривоги не рахуємо"); return
    impr = defaultdict(int); impr_c = defaultdict(int)
    for r in rep:
        dt = r.get("date", ""); n = int(r.get("impressions") or 0)
        k = (str(r.get("campaignId")), str(r.get("adGroupId")), r.get("advertisedAsin", ""), r.get("advertisedSku", ""))
        impr[(k, dt)] += n; impr_c[(str(r.get("campaignId")), dt)] += n
        impr[((k[0], k[1], k[2], ""), dt)] += n  # без SKU (на випадок fallback-колонок)
    cmap = {str(c["campaignId"]): c for c in camps}
    gmap = {str(g["adGroupId"]): g for g in groups}
    rows, alerts_ad, alerts_camp = [], [], []
    for a in ads:
        cid, gid = str(a.get("campaignId")), str(a.get("adGroupId"))
        c, g = cmap.get(cid, {}), gmap.get(gid, {})
        if is_excluded_campaign(cid, c.get("name")):
            continue
        asin, sku = a.get("asin", ""), a.get("sku", "")
        key = (cid, gid, asin, sku)
        i1 = impr.get((key, d1), impr.get(((cid, gid, asin, ""), d1), 0))
        i2 = impr.get((key, d2), impr.get(((cid, gid, asin, ""), d2), 0))
        ed = a.get("extendedData") or {}
        det = ";".join(ed.get("servingStatusDetails") or []) if isinstance(ed.get("servingStatusDetails"), list) else str(ed.get("servingStatusDetails") or "")
        rows.append([dstr(now), cid, c.get("name", ""), c.get("state", ""), x(c, "extendedData", "servingStatus"),
                     gid, g.get("name", ""), g.get("state", ""), x(g, "extendedData", "servingStatus"),
                     a.get("adId", ""), asin, sku, a.get("state", ""), ed.get("servingStatus", ""), det,
                     str(ed.get("creationDateTime", ""))[:10], i1, i2])
        if (str(c.get("state")).upper() == "ENABLED" and str(g.get("state")).upper() == "ENABLED"
                and str(a.get("state")).upper() == "ENABLED" and i1 == 0 and i2 == 0):
            created = str(ed.get("creationDateTime", ""))[:10]
            if created and created > dstr(now - timedelta(days=3)):
                continue
            alerts_ad.append((c.get("name", ""), g.get("name", ""), asin, sku, ed.get("servingStatus", ""), cid))
    for cid, c in cmap.items():
        if str(c.get("state")).upper() != "ENABLED" or is_excluded_campaign(cid, c.get("name")):
            continue
        sd = str(c.get("startDate", ""))[:10]
        if sd and sd.replace("-", "") > d2.replace("-", ""):
            continue
        if impr_c.get((cid, d1), 0) == 0 and impr_c.get((cid, d2), 0) == 0:
            alerts_camp.append((c.get("name", ""), x(c, "extendedData", "servingStatus"), cid))
    print(f"  ℹ️ Оголошень у вкладці: {len(rows)}; 0 показів 2 дні: оголошень {len(alerts_ad)}, кампаній {len(alerts_camp)}")
    json.dump({"as_of": dstr(now), "d1": d1, "d2": d2, "alerts_ad": alerts_ad, "alerts_camp": alerts_camp},
              open(f"{OUT}/alerts_zero_impr{'_' + AS_OF if AS_OF else ''}.json", "w"), ensure_ascii=False, indent=1)
    if not BACKTEST and not DRY:
        print("  ✍️ Ad SKU Status:", replace_dates(TAB_STATUS, H_STATUS, rows, 0, [dstr(now)]))
    # тривоги з дедуплікацією (7 днів)
    seen = recent_log_keys(7)
    new_c = [a for a in alerts_camp if ("zero_impr_campaign", a[2]) not in seen]
    new_a = [a for a in alerts_ad if ("zero_impr_ad", f"{a[5]}|{a[2]}|{a[3]}") not in seen
             and (a[5],) not in {(c[2],) for c in new_c}]
    if new_c or new_a:
        lines = [f"🚨 <b>{MARKET}: 0 показів 2 дні поспіль ({d2} і {d1})</b>"]
        for n, st, cid in new_c[:15]:
            lines.append(f"• Кампанія <b>{n}</b> (ENABLED, {st or '—'})")
        for n, g, asin, sku, st, cid in new_a[:25]:
            lines.append(f"• Оголошення: {n} / {g} — ASIN {asin}, SKU <b>{sku or '?'}</b> ({st or '—'})")
        more = len(new_c) + len(new_a) - 40
        if more > 0:
            lines.append(f"… і ще {more} (див. вкладку Ad SKU Status {MARKET})")
        tg("\n".join(lines))
        append_log([[dstr(now), "zero_impr_campaign", a[2], f"{a[0]} {a[1]}"] for a in new_c] +
                   [[dstr(now), "zero_impr_ad", f"{a[5]}|{a[2]}|{a[3]}", f"{a[0]} / {a[1]} / {a[3]} {a[4]}"] for a in new_a])
    else:
        print("  ✅ Нових тривог «0 показів» немає")


# ── 3. Плейсменти по днях ─────────────────────────────────────────────────
def map_place(raw):
    s = (raw or "").lower()
    if "top" in s:
        return "Top of Search"
    if "detail" in s or "product" in s:
        return "Product pages"
    return "Rest of Search"


def job_placement(token):
    now = today_utc(); s, e = dstr(now - timedelta(days=3)), dstr(now - timedelta(days=1))
    rep = run_report(token, f"placement_daily {s}..{e}", "spCampaigns",
                     ["date", "campaignName", "campaignId", "placementClassification", "impressions", "clicks",
                      "cost", "sales7d", "purchases7d"], ["campaignPlacement"], s, e)
    if rep is None:
        print("  ❌ Placement Daily: звіт недоступний"); return
    rows = [[r.get("date", ""), r.get("campaignName", ""), str(r.get("campaignId", "")),
             map_place(r.get("placementClassification")), r.get("placementClassification", ""),
             r.get("impressions", 0), r.get("clicks", 0), r.get("cost", 0), r.get("sales7d", 0),
             r.get("purchases7d", 0)] for r in rep if not is_excluded_campaign(r.get("campaignId"), r.get("campaignName"))]
    dates = sorted({r[0] for r in rows}) or [e]
    print(f"  ℹ️ Placement Daily: {len(rows)} рядків за {dates}")
    if not BACKTEST and not DRY:
        print("  ✍️ Placement Daily:", replace_dates(TAB_PLACE, H_PLACE, rows, 0, dates))


# ── 4. Таргети SP по днях ─────────────────────────────────────────────────
def job_targets(token):
    now = today_utc(); s, e = dstr(now - timedelta(days=3)), dstr(now - timedelta(days=1))
    base = ["date", "campaignName", "campaignId", "adGroupName", "adGroupId", "keywordId", "targeting",
            "keyword", "matchType", "impressions", "clicks", "cost", "sales7d", "purchases7d"]
    rep = run_report(token, f"targets_daily {s}..{e}", "spTargeting", base + ["keywordBid", "topOfSearchImpressionShare"],
                     ["targeting"], s, e, fallback=base)
    if rep is None:
        print("  ❌ SP Targets Daily: звіт недоступний"); return
    rows = [[r.get("date", ""), r.get("campaignName", ""), str(r.get("campaignId", "")), r.get("adGroupName", ""),
             str(r.get("adGroupId", "")), str(r.get("keywordId", "")), r.get("targeting", ""), r.get("keyword", ""),
             r.get("matchType", ""), r.get("keywordBid", ""), r.get("impressions", 0), r.get("clicks", 0),
             r.get("cost", 0), r.get("sales7d", 0), r.get("purchases7d", 0), r.get("topOfSearchImpressionShare", "")]
            for r in rep if not is_excluded_campaign(r.get("campaignId"), r.get("campaignName"))]
    dates = sorted({r[0] for r in rows}) or [e]
    noclick = sum(1 for r in rows if int(r[11] or 0) == 0)
    print(f"  ℹ️ SP Targets Daily: {len(rows)} рядків (без кліків: {noclick}) за {dates}")
    if not BACKTEST and not DRY:
        print("  ✍️ SP Targets Daily:", replace_dates(TAB_TARGETS, H_TARGETS, rows, 0, dates))


# ── 5. Тривоги по Suggested Bids ──────────────────────────────────────────
def f(v):
    try:
        return float(str(v).replace(",", ".")) if str(v).strip() != "" else None
    except ValueError:
        return None


def job_bids(camps):
    ws = ss().worksheet(f"Suggested Bids {MARKET}")
    vals = retry(ws.get_all_values)
    h = vals[0]; ix = {n: h.index(n) for n in ("CampaignName", "Keyword", "MatchType", "BidRangeMin", "BidRangeMax",
                                                 "SnapshotDate", "KeywordId", "CurrentBid", "Status", "CampaignId") if n in h}
    sd = ix["SnapshotDate"]
    snaps = defaultdict(dict)
    for r in vals[1:]:
        if len(r) <= sd or not r[sd] or len(r) <= ix["KeywordId"] or not r[ix["KeywordId"]]:
            continue
        snaps[r[sd]][r[ix["KeywordId"]]] = r
    dates = sorted(snaps)
    if not dates:
        print("  ⚠️ Suggested Bids: знімків із SnapshotDate немає"); return
    last = dates[-1]
    target = dstr(datetime.strptime(last, "%Y-%m-%d") - timedelta(days=7))
    prev = min(dates, key=lambda d: abs((datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(target, "%Y-%m-%d")).days))
    prev_ok = prev != last and abs((datetime.strptime(prev, "%Y-%m-%d") - datetime.strptime(target, "%Y-%m-%d")).days) <= 2
    adj = {}
    for c in camps:
        top = 0
        for a in ((c.get("dynamicBidding") or {}).get("placementBidding") or []):
            if str(a.get("placement", "")).upper() == "PLACEMENT_TOP":
                top = a.get("percentage", 0) or 0
        adj[str(c["campaignId"])] = top
    below, jumped = [], []
    for kid, r in snaps[last].items():
        if str(r[ix["Status"]]).upper() != "ENABLED":
            continue
        cb, mn, mx = f(r[ix["CurrentBid"]]), f(r[ix["BidRangeMin"]]), f(r[ix["BidRangeMax"]])
        if cb is not None and mn is not None and cb < mn:
            eff_top = round(cb * (1 + adj.get(r[ix["CampaignId"]], 0) / 100), 2)
            below.append((r[ix["CampaignName"]], r[ix["Keyword"]], r[ix["MatchType"]], cb, mn, mx, eff_top, kid))
        if prev_ok and kid in snaps[prev]:
            p = snaps[prev][kid]; pm, px = f(p[ix["BidRangeMin"]]), f(p[ix["BidRangeMax"]])
            for lab, old, new in (("min", pm, mn), ("max", px, mx)):
                if old and new is not None and old > 0 and abs(new - old) / old > 0.30:
                    jumped.append((r[ix["CampaignName"]], r[ix["Keyword"]], r[ix["MatchType"]], lab, old, new,
                                   round((new - old) / old * 100), kid)); break
    print(f"  ℹ️ Bids: знімок {last} (порівняння з {prev if prev_ok else '—'}): нижче мінімуму {len(below)}, "
          f"коридор ±30% {len(jumped)}")
    json.dump({"snapshot": last, "prev": prev if prev_ok else None, "below_min": below, "corridor_jump": jumped},
              open(f"{OUT}/bid_alerts{'_' + AS_OF if AS_OF else ''}.json", "w"), ensure_ascii=False, indent=1)
    seen = recent_log_keys(7)
    nb = [b for b in below if ("bid_below_min", b[7]) not in seen]
    nj = [j for j in jumped if ("corridor_jump", j[7]) not in seen]
    if nb or nj:
        lines = [f"💡 <b>{MARKET}: Suggested Bids (знімок {last})</b>"]
        if nb:
            lines.append(f"Бід нижчий за мінімум коридору: <b>{len(nb)}</b>")
            for c, k, m, cb, mn, mx, et, _ in sorted(nb, key=lambda b: (b[3] - b[4]) / b[4])[:10]:
                lines.append(f"• {c} / {k} [{m}]: бід {cb} < мін {mn} (коридор {mn}–{mx})")
        if nj:
            lines.append(f"Коридор змінився >30% за тиждень: <b>{len(nj)}</b>")
            for c, k, m, lab, old, new, pct, _ in sorted(nj, key=lambda j: -abs(j[6]))[:10]:
                lines.append(f"• {c} / {k} [{m}]: {lab} {old}→{new} ({pct:+d}%)")
        tg("\n".join(lines))
        append_log([[last, "bid_below_min", b[7], f"{b[0]} / {b[1]} [{b[2]}] бід {b[3]} мін {b[4]} макс {b[5]}"] for b in nb] +
                   [[last, "corridor_jump", j[7], f"{j[0]} / {j[1]} [{j[2]}] {j[3]} {j[4]}→{j[5]} ({j[6]:+d}%)"] for j in nj])


def main():
    print(f"=== COCKPIT SIGNALS {MARKET} as_of={AS_OF or 'today'} dry={DRY} only={ONLY or 'all'} ===")
    token = get_access_token()
    camps = groups = ads = []
    if want("status") or want("bids"):
        camps, groups, ads = fetch_structure(token)
    for name, fn, args in (("status", job_status, (token, camps, groups, ads)), ("placement", job_placement, (token,)),
                           ("targets", job_targets, (token,)), ("bids", job_bids, (camps,))):
        if want(name):
            print(f"\n--- {name} ---")
            try:
                fn(*args)
            except Exception as e:
                print(f"  ❌ {name}: {e}"); traceback.print_exc()


if __name__ == "__main__":
    main()
