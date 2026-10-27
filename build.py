"""한남현대 공개 기록 사이트 생성기.

data/*.csv(fetch.py가 쌓은 원자료)를 읽어 site/ 아래 정적 페이지를 만든다.
  index.html            첫 화면: 최근 공개분, 기사 기록, 두 단지 실거래, 허가 월별 건수, 매수 대기 등록
  news.html             기사 기록 전체(data/news.csv). 제목을 누르면 언론사 원문으로 넘어간다.
  news.json             최근 기사 6건. luxuryhome.kr 첫 화면 '한남동 기사' 칸이 읽어 간다.
  records/날짜.html     그날 새로 공개된 건이 있을 때만 만드는 날짜별 기록
  weekly/날짜.html      월요일 지난주 요약, 토요일 용산·성동 30억 이상 거래
  q/h/, q/n/            우편 QR 전용 단지별 페이지(검색 제외, 방문 수를 구글 폼에 기록)
  feed.xml sitemap.xml robots.txt llms.txt data/*.csv
기사 기록 원칙(2026.10.27): 본문·사진은 옮기지 않고 제목·언론사·입력일·원문 링크와 한남현대가 새로 쓴 두세 줄 요약만 싣는다.
원칙: 한남현대 명의만 쓴다. 동·호수는 쓰지 않는다. 한남더힐 26평형도 싣는다(2026.10.26 결정, 10.13 제외 결정을 바꿈).
"""
import csv
import datetime as dt
import html
import json
import os
import shutil
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "site")
SITE_URL = os.environ.get("SITE_URL", "https://hannamhyundai.github.io").rstrip("/")
KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).date()

OFFICE = {
    "name": "한남현대공인중개사사무소",
    "addr": "서울특별시 용산구 독서당로 74 (한남동 263-25)",
    "reg": "11170-2016-00010",
    "ceo": "임철우",
    "tel": "02-796-9393",
}
WAITLIST_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdyuX-rIqIyO15Kfr2mo7WgZ_PQJNJ5vPv7cFzY53A4DyEfag/viewform"
SRC_DEAL = "서울부동산정보광장 실거래가(아파트 매매)"
SRC_PERMIT = "서울부동산정보광장 토지거래허가 내역(국토교통부 K-Geo 연계)"
COMPLEXES = [("810", "한남더힐"), ("829", "나인원한남")]
WEEKDAY = "월화수목금토일"

# 우편 QR 전용 주소(2026.10.27). 우편물 QR은 단지별로 아래 주소를 가리킨다.
#   /q/h/ 한남더힐 소유주께 보낸 우편, /q/n/ 나인원한남 소유주께 보낸 우편
# 방문하면 구글 폼 "한남현대 우편 QR 방문 기록"에 '단지|동작|방문번호|회차' 한 줄이 쌓인다.
# 방문번호는 브라우저마다 무작위로 만든 값이라 개인을 알아볼 수 없다. 주소 끝에 ?test=1 을 붙이면 단지 대신 test로 남는다.
# 다음 우편부터는 MAIL_CAMPAIGN만 바꾸면 회차별로 나뉘어 집계된다.
QR_LOG_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe5ivAGs7MbzaoN6HfgnNDfxuW03u7kMcoa0e4UH7CvT64xjQ/formResponse"
QR_LOG_ENTRY = "entry.1180566483"
MAIL_CAMPAIGN = "2026-10"
QR_PAGES = [("h", "hill", "810", "한남더힐", "n"), ("n", "nine", "829", "나인원한남", "h")]

esc = html.escape


# ---------------------------------------------------------------- 자료 읽기

def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def excluded(d):
    # 2026.10.26부터 제외 없음. 다시 빼야 할 때를 위해 함수는 남겨 둔다.
    return False


def won(manwon):
    """만원 단위 정수를 '38억 4,000만 원'처럼 풀어 쓴다."""
    m = int(manwon)
    eok, rest = divmod(m, 10000)
    if eok and rest:
        return f"{eok}억 {rest:,}만 원"
    if eok:
        return f"{eok}억 원"
    return f"{rest:,}만 원"


def kdate(ymd):
    if not ymd or ymd == "seed":
        return "기록 개시분"
    if "-" in ymd:
        d = dt.date.fromisoformat(ymd)
    else:
        d = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
    return f"{d.year}년 {d.month}월 {d.day}일"


def kdate_w(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.year}년 {d.month}월 {d.day}일 {WEEKDAY[d.weekday()]}요일"


def area_txt(a):
    return f"{float(a):.2f}㎡".replace(".00㎡", "㎡")


def floor_txt(f):
    return f"{f}층" if f else "-"


# ---------------------------------------------------------------- 화면 틀

CSS = """
:root{--bg:#f6f5f2;--paper:#fffefb;--ink:#1c1b19;--muted:#68655f;--line:#dcd8cf;--soft:#efece5;--hn:#1f4fa8;--logo:#173c64;--cut:#8a3b2e;
--serif:"Noto Serif KR","Nanum Myeongjo",serif;--sans:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--paper:#1e1d1b;--ink:#ebe9e4;--muted:#a29f98;--line:#383632;--soft:#262522;--hn:#8fb0ee;--logo:#8fb0ee;--cut:#e09a8b;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 var(--sans);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.wrap{max-width:860px;margin:0 auto;padding-block:36px 64px;display:flex;flex-direction:column;gap:36px}
header{display:flex;flex-direction:column;gap:6px;border-bottom:1px solid var(--line);padding-bottom:20px}
.office{font-size:14px;color:var(--muted);letter-spacing:.02em}
.hn{color:var(--hn)}
.logo{display:inline-flex;flex-direction:column;align-items:flex-start;text-decoration:none;color:var(--ink);font-family:var(--serif);line-height:1.15;gap:2px;margin-bottom:6px}
.logo .lg-hn{font-size:30px;font-weight:600;color:var(--logo);letter-spacing:.04em}
.logo .lg-of{font-size:19px;font-weight:600;letter-spacing:.06em}
.logo .lg-en{font-size:11.5px;color:var(--muted);letter-spacing:.04em;font-family:Georgia,"Times New Roman",serif}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(26px,5vw,36px);line-height:1.3;margin:0;text-wrap:balance}
h2{font-family:var(--serif);font-weight:600;font-size:22px;margin:0 0 8px;text-wrap:balance}
h3{font-size:17px;margin:20px 0 6px}
p{margin:0 0 10px}
.lead{font-size:17px;color:var(--ink)}
.meta{font-size:13px;color:var(--muted)}
section{display:flex;flex-direction:column;gap:8px;min-width:0}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--paper)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:var(--soft);font-weight:600;font-size:13px}
tr:last-child td{border-bottom:0}
td.num{text-align:right}
.cut{color:var(--cut)}
.new{display:inline-block;font-size:12px;border:1px solid var(--ink);border-radius:999px;padding:0 8px;margin-left:6px}
.card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
.btn{display:inline-block;margin-top:6px;padding:10px 18px;border-radius:999px;background:var(--ink);color:var(--bg);text-decoration:none;font-size:15px}
.btn:focus-visible,a:focus-visible{outline:2px solid var(--muted);outline-offset:2px}
ul.list{margin:0;padding-left:20px}
a{color:inherit}
.news{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
.news li{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px 20px}
.news .nt{font-family:var(--serif);font-weight:600;font-size:18px;line-height:1.5;text-decoration:none;display:block}
.news .nt:hover{text-decoration:underline;text-underline-offset:3px}
.news .nt::after{content:" ↗";font-family:var(--sans);font-size:14px;color:var(--muted)}
.news p{margin:6px 0 0;font-size:15px}
footer{border-top:1px solid var(--line);padding-top:18px;font-size:13px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
"""


def page(title, body, desc, path, jsonld=None, extra_head="", tail=""):
    canon = f"{SITE_URL}/{path}".replace("/index.html", "/")
    ld = ""
    for obj in (jsonld or []):
        ld += f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>\n'
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
{extra_head}<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon}">
<link rel="alternate" type="application/rss+xml" title="한남현대 공개 기록" href="{SITE_URL}/feed.xml">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website"><meta property="og:url" content="{canon}"><meta property="og:locale" content="ko_KR">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600&family=Noto+Serif+KR:wght@600&display=swap">
<style>{CSS}</style>
{ld}</head><body><div class="wrap">
{body}
{footer()}
</div>{tail}</body></html>"""


def footer():
    return f"""<footer>
<div><span class="hn">한남현대</span>공인중개사사무소 · {esc(OFFICE['addr'])}</div>
<div>중개사무소 등록번호 {OFFICE['reg']} · 대표 {OFFICE['ceo']} · 전화 {OFFICE['tel']}</div>
<div>이 사이트는 공개된 기록을 정리한 것이며, 특정 매물의 표시나 광고가 아닙니다. 모든 숫자는 출처의 공개 자료 그대로이고 평가나 전망은 담지 않습니다.</div>
<div>기사 기록의 요약은 한남현대가 원문을 읽고 새로 적은 것이며, 기사의 저작권은 각 언론사에 있습니다. 제목을 누르시면 원문이 열립니다.</div>
<div><a href="{SITE_URL}/">처음으로</a> · <a href="{SITE_URL}/news.html">기사 기록</a> · <a href="{SITE_URL}/feed.xml">RSS</a> · <a href="{SITE_URL}/data/deals.csv">실거래 원자료 CSV</a> · <a href="{SITE_URL}/data/permits.csv">허가 원자료 CSV</a></div>
</footer>"""


def head_block(title, sub):
    return f"""<header><a class="logo" href="{SITE_URL}/" aria-label="한남현대공인중개사사무소 처음으로"><span class="lg-hn">한남현대</span><span class="lg-of">공인중개사사무소</span><span class="lg-en">Hannam Hyundai Real Estate Agency</span></a>
<div class="office">40여 년 한남동의 기록</div>
<h1>{esc(title)}</h1><div class="meta">{sub}</div></header>"""


def deal_table(rows, with_seen=False, with_complex=True):
    th = "<tr>" + ("<th>단지</th>" if with_complex else "") + "<th>전용면적</th><th>층</th><th>계약일</th><th>거래금액</th>" + ("<th>공개 확인일</th>" if with_seen else "") + "</tr>"
    trs = []
    for d in rows:
        cut = d.get("cancelled") == "1"
        name = f"{esc(d['complex'])} ({esc(d['dong'])} {esc(d['jibun'])})"
        price = won(d["price"]) + (' <span class="cut">해제 신고</span>' if cut else "")
        trs.append("<tr>" + (f"<td>{name}</td>" if with_complex else "") +
                   f"<td class='num'>{area_txt(d['area'])}</td><td class='num'>{floor_txt(d['floor'])}</td>"
                   f"<td>{kdate(d['ymd'])}</td><td class='num'>{price}</td>" +
                   (f"<td>{kdate(d['first_seen'])}</td>" if with_seen else "") + "</tr>")
    return f'<div class="tbl"><table>{th}{"".join(trs)}</table></div>'


def news_list(rows):
    li = []
    for n in rows:
        li.append(f"<li><a class='nt' href='{esc(n['url'])}' target='_blank' rel='noopener'>{esc(n['title'])}</a>"
                  f"<div class='meta'>{esc(n['outlet'])} · 입력 {kdate(n['published'])}</div>"
                  f"<p>{esc(n['summary'])}</p></li>")
    return f"<ul class='news'>{''.join(li)}</ul>"


# ---------------------------------------------------------------- 우편 QR 전용 페이지

QR_JS = """<script>
(function(){
  var F=%(url)s, E=%(entry)s, C=%(camp)s;
  var src=/[?&]test=1/.test(location.search)?"test":%(src)s;
  var vid;
  try{vid=localStorage.getItem("hh_vid");if(!vid){vid=Math.random().toString(36).slice(2,10)+Date.now().toString(36).slice(-4);localStorage.setItem("hh_vid",vid);}}
  catch(e){vid="x"+Math.random().toString(36).slice(2,10);}
  function log(ev){
    var b=new URLSearchParams();b.append(E,[src,ev,vid,C].join("|"));
    try{if(navigator.sendBeacon&&navigator.sendBeacon(F,b))return;}catch(e){}
    try{fetch(F,{method:"POST",mode:"no-cors",body:b,keepalive:true});}catch(e){}
  }
  log("view");
  var a=document.querySelectorAll("[data-ev]");
  for(var i=0;i<a.length;i++){(function(el){el.addEventListener("click",function(){log(el.getAttribute("data-ev"));});})(a[i]);}
})();
</script>"""


def mail_pages(hannam, hn_permits, collected):
    """우편 QR이 여는 단지별 페이지. 검색에는 올리지 않는다(noindex, 사이트맵 제외)."""
    for slug, src, jb, nm, other in QR_PAGES:
        rows = sorted([d for d in hannam if d["jibun"] == jb], key=lambda x: x["ymd"], reverse=True)
        prm = sorted([p for p in hn_permits if p["jibun"] == jb], key=lambda x: x["hndl_ymd"], reverse=True)
        other_nm = dict((s, n) for s, _, _, n, _ in QR_PAGES)[other]
        sub = f"마지막 수집 {esc(collected.replace('T', ' '))} · 매일 아침 7시 40분 갱신" if collected else "매일 아침 7시 40분 갱신"
        body = head_block(f"{nm}의 거래 기록", sub)
        body += f"""<section><p class="lead">우편을 받아 보시고 찾아 주셔서 감사합니다. 서울부동산정보광장에 신고된 {nm}의 실거래와 토지거래허가를 날짜순으로 정리해 두었습니다. 기록은 매일 아침 새로 이어집니다.</p></section>
<section><h2>실거래 신고</h2><p class="meta">2025년 1월 이후 계약분 {len(rows)}건, 계약일 최신순. 계약 뒤 30일 안에 신고되므로 최근 거래는 늦게 올라올 수 있습니다. (출처: {SRC_DEAL})</p>
{deal_table(rows, with_complex=False) if rows else "<p>공개된 신고가 없습니다.</p>"}</section>"""
        if prm:
            li = "".join(f"<li>허가일 {kdate(p['hndl_ymd'])}</li>" for p in prm[:12])
            body += f"""<section><h2>토지거래허가</h2><p class="meta">한남동 {jb} 지번의 주거용 허가 완료 건, 최근 {min(len(prm), 12)}건. 처리가 끝난 건만 공개되므로 심사 중인 건은 들어 있지 않습니다. (출처: {SRC_PERMIT})</p><ul class="list">{li}</ul></section>"""
        body += f"""<section class="card"><h2>한남현대 상담</h2><p>매매와 임대, 잔금과 세무 일정에 관한 말씀은 전화로 편히 건네 주십시오. 방문하실 때는 파리크라상 한남점 발렛에 "한남현대부동산 방문"이라고 말씀하시면 됩니다.</p>
<div><a class="btn" href="tel:{OFFICE['tel'].replace('-', '')}" data-ev="call">{OFFICE['tel']} 전화하기</a></div></section>
<section><p><a href="{SITE_URL}/" data-ev="home">{other_nm}까지 함께 담긴 전체 기록 보기</a></p>
<p class="meta">우편으로 찾아 주신 분이 몇 분인지 세기 위해, 개인을 알아볼 수 없는 무작위 방문 번호만 남깁니다. 이름이나 연락처는 기록하지 않습니다.</p></section>"""
        js = QR_JS % {"url": json.dumps(QR_LOG_URL), "entry": json.dumps(QR_LOG_ENTRY),
                      "camp": json.dumps(MAIL_CAMPAIGN), "src": json.dumps(src)}
        path = f"q/{slug}/index.html"
        os.makedirs(os.path.join(OUT, "q", slug), exist_ok=True)
        with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
            f.write(page(f"{nm}의 거래 기록 · 한남현대", body, f"{nm} 실거래 신고와 토지거래허가 공개 기록.", path,
                         extra_head='<meta name="robots" content="noindex,nofollow">\n', tail=js))


# ---------------------------------------------------------------- 모으기

def main():
    deals = [d for d in load("deals.csv") if not excluded(d)]
    permits = load("permits.csv")
    meta = {}
    mp = os.path.join(DATA, "last_run.json")
    if os.path.exists(mp):
        meta = json.load(open(mp, encoding="utf-8"))
    collected = meta.get("collected_at", "")

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for sub in ("records", "weekly", "data"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)

    hannam = [d for d in deals if d["dong"] == "한남동" and d["jibun"] in ("810", "829")]
    res_permits = [p for p in permits if p["use_purp"] == "주거용" and p["job"] == "허가"]
    hn_permits = [p for p in res_permits if p["dong"] == "한남동" and p["jibun"] in ("810", "829")]

    news = sorted([n for n in load("news.csv") if n.get("url") and n.get("title")],
                  key=lambda n: (n["published"], n.get("added", "")), reverse=True)

    pages = []  # (path, title, date_iso, summary)

    # ---- 날짜별 기록
    by_day = defaultdict(lambda: {"deals": [], "permits": [], "cancels": [], "yongsan": 0})
    for d in hannam:
        if d["first_seen"] not in ("", "seed"):
            by_day[d["first_seen"]]["deals"].append(d)
        if d.get("cancel_seen") not in ("", "seed", None) and d["cancel_seen"] != d["first_seen"]:
            by_day[d["cancel_seen"]]["cancels"].append(d)
    for p in res_permits:
        if p["first_seen"] in ("", "seed"):
            continue
        by_day[p["first_seen"]]["yongsan"] += 1
        if p in hn_permits:
            by_day[p["first_seen"]]["permits"].append(p)

    for day in sorted(by_day):
        b = by_day[day]
        if not (b["deals"] or b["permits"] or b["cancels"] or b["yongsan"]):
            continue
        parts = []
        if b["deals"]:
            parts.append(f"<h2>새로 공개된 실거래 신고</h2><p>한남더힐과 나인원한남에서 새로 공개된 실거래 신고는 {len(b['deals'])}건입니다. (출처: {SRC_DEAL}, {kdate(day)} 수집분)</p>"
                         + deal_table(sorted(b["deals"], key=lambda x: x["ymd"], reverse=True)))
        if b["cancels"]:
            parts.append(f"<h2>새로 붙은 해제 신고</h2><p>이미 공개되었던 거래 가운데 {len(b['cancels'])}건에 해제 신고가 새로 붙었습니다. (출처: {SRC_DEAL})</p>"
                         + deal_table(b["cancels"]))
        if b["permits"]:
            li = "".join(f"<li>{esc(p['address'])} · 허가일 {kdate(p['hndl_ymd'])}</li>" for p in b["permits"])
            parts.append(f"<h2>두 단지 토지거래허가</h2><p>한남더힐·나인원한남 지번의 주거용 허가 완료 건이 {len(b['permits'])}건 새로 공개되었습니다. (출처: {SRC_PERMIT})</p><ul class='list'>{li}</ul>")
        else:
            parts.append("<h2>두 단지 토지거래허가</h2><p>한남더힐·나인원한남 지번으로 새로 공개된 허가 완료 건은 없습니다.</p>")
        parts.append(f"<p>같은 날 용산구 전체로는 주거용 허가 완료 건 {b['yongsan']}건이 새로 공개되었습니다. (출처: {SRC_PERMIT})</p>")
        title = f"한남동 공개 기록, {kdate(day)}"
        summary = f"실거래 신고 {len(b['deals'])}건, 두 단지 허가 {len(b['permits'])}건, 용산구 허가 {b['yongsan']}건이 새로 공개된 날의 기록."
        body = head_block(title, f"{kdate_w(day)} 아침 수집분") + "<section>" + "".join(parts) + "</section>"
        path = f"records/{day}.html"
        with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
            f.write(page(title, body, summary, path))
        pages.append((path, title, day, summary))

    # ---- 주간글: 월요일 지난주 요약, 토요일 용산·성동 30억 이상
    seen_days = sorted(d for d in by_day)
    if seen_days:
        start = dt.date.fromisoformat(seen_days[0])
        cur = start
        while cur <= TODAY:
            if cur.weekday() == 0:  # 월요일: 직전 월~일
                ws, we = cur - dt.timedelta(days=7), cur - dt.timedelta(days=1)
                rng = [(ws + dt.timedelta(days=i)).isoformat() for i in range(7)]
                wd = [d for k in rng for d in by_day.get(k, {}).get("deals", [])]
                wp = [p for k in rng for p in by_day.get(k, {}).get("permits", [])]
                wy = sum(by_day.get(k, {}).get("yongsan", 0) for k in rng)
                if wd or wp or wy:
                    title = f"한남동 지난주 공개 기록, {ws.month}월 {ws.day}일부터 {we.month}월 {we.day}일까지"
                    body = head_block(title, f"{kdate_w(cur.isoformat())} 정리")
                    body += "<section>"
                    body += f"<p class='lead'>지난주 한남더힐·나인원한남에서 새로 공개된 실거래 신고는 {len(wd)}건, 두 단지 지번의 주거용 허가 완료 건은 {len(wp)}건이며, 용산구 전체 주거용 허가 완료 건은 {wy}건이 새로 공개되었습니다. (출처: {SRC_DEAL}, {SRC_PERMIT})</p>"
                    if wd:
                        body += deal_table(sorted(wd, key=lambda x: x["ymd"], reverse=True), with_seen=True)
                    body += "</section>"
                    path = f"weekly/{cur.isoformat()}.html"
                    summary = f"지난주 한남동 두 단지 실거래 {len(wd)}건, 허가 {len(wp)}건, 용산구 허가 {wy}건."
                    with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
                        f.write(page(title, body, summary, path))
                    pages.append((path, title, cur.isoformat(), summary))
            if cur.weekday() == 5:  # 토요일: 지난 7일 공개된 용산·성동 30억 이상
                rng = {(cur - dt.timedelta(days=i)).isoformat() for i in range(7)}
                big = [d for d in deals if d["first_seen"] in rng and int(d["price"]) >= 300000 and d["sgg"] in ("11170", "11200")]
                if big:
                    big.sort(key=lambda x: int(x["price"]), reverse=True)
                    title = f"용산·성동 30억 원 이상 거래, {cur.month}월 {cur.day}일까지 한 주"
                    body = head_block(title, f"{kdate_w(cur.isoformat())} 정리")
                    body += f"<section><p class='lead'>지난 7일 동안 용산구와 성동구에서 새로 공개된 30억 원 이상 아파트 매매 신고는 {len(big)}건입니다. (출처: {SRC_DEAL})</p>"
                    body += deal_table(big, with_seen=True) + "</section>"
                    path = f"weekly/{cur.isoformat()}.html"
                    summary = f"용산·성동 30억 원 이상 아파트 매매 신고 {len(big)}건."
                    with open(os.path.join(OUT, path), "w", encoding="utf-8") as f:
                        f.write(page(title, body, summary, path))
                    pages.append((path, title, cur.isoformat(), summary))
            cur += dt.timedelta(days=1)

    # ---- 첫 화면
    recent = sorted(pages, key=lambda x: x[2], reverse=True)[:12]
    recent_html = "".join(f"<li><a href='{SITE_URL}/{p}'>{esc(t)}</a> <span class='meta'>{esc(s)}</span></li>" for p, t, _, s in recent) \
        or "<li>매일 아침 수집이 쌓이면 이곳에 날짜별 기록이 이어집니다.</li>"

    complex_html = ""
    for jb, nm in COMPLEXES:
        rows = sorted([d for d in hannam if d["jibun"] == jb], key=lambda x: x["ymd"], reverse=True)
        note = ""
        complex_html += f"<h3>{nm} (한남동 {jb})</h3><p class='meta'>2025년 1월 이후 계약분 {len(rows)}건, 계약일 최신순.{note} (출처: {SRC_DEAL})</p>"
        complex_html += deal_table(rows, with_complex=False) if rows else "<p>공개된 신고가 없습니다.</p>"

    months = sorted({p["hndl_ymd"][:6] for p in res_permits if p["hndl_ymd"]}, reverse=True)
    cnt = Counter((p["hndl_ymd"][:6], p["jibun"]) for p in hn_permits)
    cnt_y = Counter(p["hndl_ymd"][:6] for p in res_permits)
    prow = "".join(f"<tr><td>{m[:4]}년 {int(m[4:])}월</td><td class='num'>{cnt[(m, '810')]}건</td><td class='num'>{cnt[(m, '829')]}건</td><td class='num'>{cnt_y[m]}건</td></tr>" for m in months)
    permit_html = f"<div class='tbl'><table><tr><th>허가 월</th><th>한남더힐</th><th>나인원한남</th><th>용산구 전체</th></tr>{prow}</table></div>" if prow else "<p>수집이 시작되면 월별 건수가 쌓입니다.</p>"

    org = {"@context": "https://schema.org", "@type": "RealEstateAgent", "name": OFFICE["name"], "telephone": OFFICE["tel"],
           "url": SITE_URL + "/", "address": {"@type": "PostalAddress", "streetAddress": "독서당로 74", "addressLocality": "용산구",
           "addressRegion": "서울특별시", "addressCountry": "KR"}, "areaServed": "서울특별시 용산구 한남동"}
    dataset = {"@context": "https://schema.org", "@type": "Dataset", "name": "한남더힐·나인원한남 실거래와 토지거래허가 공개 기록",
               "description": "서울부동산정보광장 공개 자료를 매일 수집해 쌓은 한남동 두 단지의 아파트 매매 실거래 신고와 용산구 토지거래허가 처리 내역.",
               "creator": {"@type": "Organization", "name": OFFICE["name"]}, "isAccessibleForFree": True,
               "temporalCoverage": f"2025-01-01/{TODAY.isoformat()}", "spatialCoverage": "서울특별시 용산구 한남동",
               "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE_URL}/data/deals.csv"},
                                {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE_URL}/data/permits.csv"}]}

    news_html = ""
    # luxuryhome.kr 첫 화면이 읽어 가는 최근 기사 목록(제목·언론사·입력일·원문 링크·요약)
    with open(os.path.join(OUT, "news.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": TODAY.isoformat(), "count": len(news),
                   "items": [{k: n.get(k, "") for k in ("published", "outlet", "title", "url", "summary")} for n in news[:6]]},
                  f, ensure_ascii=False)
    if news:
        more = f"<p class='meta'><a href='{SITE_URL}/news.html'>기사 기록 전체 {len(news)}건 보기</a></p>" if len(news) > 6 else ""
        news_html = f"<section><h2>한남동 기사 기록</h2><p class='meta'>한남더힐·나인원한남과 한남동 주거에 관한 기사입니다. 제목을 누르시면 언론사 원문이 열리고, 숫자와 내용의 출처는 해당 기사입니다.</p>{news_list(news[:6])}{more}</section>"
        nbody = head_block("한남동 기사 기록", f"{len(news)}건 · 입력일 최신순")
        nbody += f"<section><p class='lead'>한남더힐·나인원한남과 한남동 주거에 관한 기사를 모아 두었습니다. 제목을 누르시면 언론사 원문이 열리며, 요약은 한남현대가 원문을 읽고 짧게 옮겨 적은 것입니다.</p>{news_list(news)}</section>"
        with open(os.path.join(OUT, "news.html"), "w", encoding="utf-8") as f:
            f.write(page("한남동 기사 기록", nbody, "한남더힐·나인원한남과 한남동 주거에 관한 기사 제목, 언론사, 입력일, 원문 링크와 짧은 요약.", "news.html"))

    body = head_block("한남더힐과 나인원한남, 공개된 숫자 그대로의 기록",
                      f"마지막 수집 {esc(collected.replace('T', ' '))} · 매일 아침 7시 40분 갱신" if collected else "매일 아침 7시 40분 갱신")
    body += f"""<section><p class="lead">서울부동산정보광장에 올라오는 실거래 신고와 토지거래허가 처리 내역을 매일 아침 그대로 옮겨 적고, 처음 공개된 날짜와 함께 남겨 두겠습니다. 숫자마다 출처를 붙이며, 평가나 전망은 담지 않습니다.</p></section>
<section><h2>최근 기록</h2><ul class="list">{recent_html}</ul></section>
{news_html}
<section><h2>두 단지 실거래 신고</h2>{complex_html}</section>
<section><h2>토지거래허가 처리 건수</h2><p class="meta">주거용 허가 완료 건만 셉니다. 공개 자료에는 처리가 끝난 건만 올라오므로 신청되어 심사 중인 건은 들어 있지 않습니다. (출처: {SRC_PERMIT})</p>{permit_html}</section>
<section class="card"><h2>매수 대기 등록</h2><p>한남더힐과 나인원한남의 매수를 기다리시는 분께서는 원하시는 평형과 시기를 남겨 두실 수 있습니다. 조건에 맞는 소식이 생기면 한남현대가 먼저 연락을 드리겠습니다.</p><a class="btn" href="{WAITLIST_URL}" rel="noopener">대기 명단에 이름 올리기</a></section>"""
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page("한남현대 공개 기록", body, "한남더힐·나인원한남 실거래 신고와 토지거래허가 처리 내역을 서울부동산정보광장 공개 자료 그대로 매일 쌓는 한남현대공인중개사사무소의 기록.", "index.html", [org, dataset]))

    # ---- 우편 QR 전용 페이지(검색 제외)
    mail_pages(hannam, hn_permits, collected)

    # ---- 부속 파일
    for name in ("deals.csv", "permits.csv"):
        src = os.path.join(DATA, name)
        if os.path.exists(src):
            if name == "deals.csv":
                with open(src, encoding="utf-8") as f_in, open(os.path.join(OUT, "data", name), "w", encoding="utf-8", newline="") as f_out:
                    r = csv.DictReader(f_in)
                    w = csv.DictWriter(f_out, fieldnames=r.fieldnames)
                    w.writeheader()
                    for row in r:
                        if not excluded(row):
                            w.writerow(row)
            else:
                shutil.copy(src, os.path.join(OUT, "data", name))

    urls = [SITE_URL + "/"] + [f"{SITE_URL}/{p}" for p, *_ in pages]
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write(f"<url><loc>{SITE_URL}/</loc><lastmod>{TODAY.isoformat()}</lastmod></url>\n")
        if news:
            f.write(f"<url><loc>{SITE_URL}/news.html</loc><lastmod>{news[0].get('added') or TODAY.isoformat()}</lastmod></url>\n")
        for p, _, day, _ in pages:
            f.write(f"<url><loc>{SITE_URL}/{p}</loc><lastmod>{day}</lastmod></url>\n")
        f.write("</urlset>\n")

    items = ""
    for p, t, day, s in sorted(pages, key=lambda x: x[2], reverse=True)[:40]:
        d = dt.datetime.fromisoformat(day + "T08:00:00+09:00")
        items += f"<item><title>{esc(t)}</title><link>{SITE_URL}/{p}</link><guid>{SITE_URL}/{p}</guid><pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0900')}</pubDate><description>{esc(s)}</description></item>\n"
    with open(os.path.join(OUT, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>한남현대 공개 기록</title><link>{SITE_URL}/</link><description>한남더힐·나인원한남 실거래와 토지거래허가 공개 기록</description><language>ko</language>\n{items}</channel></rss>\n')

    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nDisallow: /q/\n\n")
        for bot in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended", "Yeti", "Bingbot"):
            f.write(f"User-agent: {bot}\nAllow: /\n\n")
        f.write(f"Sitemap: {SITE_URL}/sitemap.xml\n")

    with open(os.path.join(OUT, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(f"""# 한남현대 공개 기록

> {OFFICE['name']}({OFFICE['addr']}, 등록번호 {OFFICE['reg']})가 서울부동산정보광장 공개 자료를 매일 아침 수집해 쌓는 한남더힐(한남동 810)·나인원한남(한남동 829) 아파트 매매 실거래 신고와 용산구 토지거래허가 처리 내역입니다. 숫자는 출처 그대로이며 평가나 전망은 없습니다. 동·호수는 싣지 않습니다.

## 자료
- [첫 화면]({SITE_URL}/): 두 단지 실거래 표, 허가 월별 건수, 최근 기록
- [실거래 원자료 CSV]({SITE_URL}/data/deals.csv): 단지, 지번, 전용면적, 계약일, 거래금액(만원), 층, 해제 여부, 처음 공개 확인일
- [허가 원자료 CSV]({SITE_URL}/data/permits.csv): 허가일, 주소(지번), 이용목적, 처리 구분, 처음 공개 확인일
- [RSS]({SITE_URL}/feed.xml): 날짜별 기록과 주간 정리
- [기사 기록]({SITE_URL}/news.html): 한남동 주거 관련 기사 제목·언론사·입력일·원문 링크와 짧은 요약

## 출처
- {SRC_DEAL}: https://land.seoul.go.kr/land/rtms/rtmsApartment.do
- {SRC_PERMIT}: https://land.seoul.go.kr/land/other/contractStatus.do
""")
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    # 검색엔진 소유 확인 파일(구글·네이버 등)은 verify/ 에 두면 사이트 맨 위에 그대로 올라간다.
    vdir = os.path.join(HERE, "verify")
    if os.path.isdir(vdir):
        for name in os.listdir(vdir):
            shutil.copy(os.path.join(vdir, name), os.path.join(OUT, name))
    print(f"pages={len(pages)} deals={len(hannam)} permits={len(hn_permits)}/{len(res_permits)}")


if __name__ == "__main__":
    main()
