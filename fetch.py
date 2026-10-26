"""한남현대 공개 기록 수집기.

서울부동산정보광장(land.seoul.go.kr)의 공개 자료 두 가지를 받아 data/ 아래 CSV에 쌓는다.
  1) 토지거래허가 내역: 용산구 처리 완료 건 (/land/wsklis/getContractList.do)
  2) 아파트 매매 실거래: 한남동 전체와, 토요일 주간글용 용산·성동 30억 이상 거래 (/land/rtms/getRtmsPriceList.do)

처음 보는 건에는 first_seen(수집 날짜)을 적는다. 이 날짜가 "새로 공개된 날"의 근거가 된다.
같은 건은 키로 묶어 다시 쓰지 않으며, 해제 신고가 새로 붙으면 cancelled와 cancel_seen만 갱신한다.
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://land.seoul.go.kr"
UA = "Mozilla/5.0 (compatible; HannamHyundaiRecord/1.0; +https://hannamhyundai.github.io/)"
KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).date()
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

YONGSAN = "11170"
SEONGDONG = "11200"
HANNAM_BJDONG = "13100"

PERMIT_FIELDS = ["key", "hndl_ymd", "address", "dong", "jibun", "use_purp", "job", "jimok", "first_seen"]
DEAL_FIELDS = ["key", "sgg", "dong", "complex", "jibun", "area", "ymd", "price", "floor", "cancelled", "first_seen", "cancel_seen"]


def post(path, params, tries=3):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": UA,
            "Referer": BASE + "/land/",
        },
    )
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 네트워크 오류는 잠시 쉬고 다시
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{path} 요청 실패: {last}")


def read_csv(name, fields):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {row["key"]: row for row in csv.DictReader(f)}


def write_csv(name, fields, rows):
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in sorted(rows.values(), key=lambda r: (r.get("ymd") or r.get("hndl_ymd") or "", r["key"]), reverse=True):
            w.writerow({k: row.get(k, "") for k in fields})


# ---------------------------------------------------------------- 토지거래허가

def split_address(addr):
    # "용산구 한남동 810 " -> ("한남동", "810")
    parts = addr.split()
    dong = parts[1] if len(parts) > 1 else ""
    jibun = parts[2] if len(parts) > 2 else ""
    return dong, jibun


def fetch_permits(rows, start, end):
    """start~end(date) 구간을 60일 창으로 나눠 용산구 허가 내역을 받는다."""
    added = 0
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=59), end)
        res = post("/land/wsklis/getContractList.do", {
            "sggCd": YONGSAN,
            "beginDate": cur.strftime("%Y%m%d"),
            "endDate": stop.strftime("%Y%m%d"),
        })
        for it in res.get("result", []) or []:
            key = f"{it.get('SGG_CD')}-{it.get('ACC_YEAR')}-{it.get('ACC_NO')}-{it.get('OBJ_SEQNO')}"
            if key in rows:
                continue
            addr = (it.get("ADDRESS") or "").strip()
            dong, jibun = split_address(addr)
            rows[key] = {
                "key": key,
                "hndl_ymd": it.get("HNDL_YMD", ""),
                "address": addr,
                "dong": dong,
                "jibun": jibun,
                "use_purp": it.get("USE_PURP", ""),
                "job": it.get("JOB_GBN_NM", ""),
                "jimok": it.get("JIMOK", ""),
                "first_seen": TODAY.isoformat(),
            }
            added += 1
        cur = stop + dt.timedelta(days=1)
        time.sleep(1)
    return added


# ---------------------------------------------------------------- 실거래

TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
TAG = re.compile(r"<[^>]+>")


def text(s):
    return TAG.sub("", s).replace("&nbsp;", " ").strip()


def land_to_jibun(land_cd):
    # 1117013100 1 0829 0000 -> 829 / 810 / 1-351
    if not land_cd or len(land_cd) < 19:
        return ""
    bon = int(land_cd[11:15])
    bu = int(land_cd[15:19])
    return f"{bon}-{bu}" if bu else str(bon)


def parse_price_html(html, year, start_month):
    """분기 표(HTML)를 거래 목록으로 바꾼다. 한 칸에 여러 건이면 <br>로 나뉘어 있다."""
    out = []
    name = jibun = ""
    for tr in TR.findall(html):
        cells = TD.findall(tr)
        data = []
        for attrs, inner in cells:
            if "bldgnmTD" in attrs:
                name = text(inner).split("[")[0].strip()
                m = re.search(r"landCd=['\"]?(\d+)", attrs)
                if m:
                    jibun = land_to_jibun(m.group(1))
                continue
            if "beonjiTD" in attrs:
                m = re.search(r"landCd=['\"]?(\d+)", attrs)
                jibun = land_to_jibun(m.group(1)) if m else text(inner)
                continue
            # 값 칸은 align 속성이 있고 tb_ 테두리 클래스가 없다.
            # (이어지는 줄의 빈 단지·번지 칸, 맨 끝 매물보기 버튼 칸은 여기서 걸러진다)
            if "align" not in attrs or "tb_" in attrs:
                continue
            data.append(inner)
        if len(data) < 10:
            continue
        try:
            area = float(text(data[0]).replace(",", ""))
        except ValueError:
            continue
        for k in range(3):
            day_c, price_c, floor_c = data[1 + 3 * k], data[2 + 3 * k], data[3 + 3 * k]
            days = re.split(r"<br\s*/?>", day_c)
            prices = re.split(r"<br\s*/?>", price_c)
            # 층 칸에는 "(109동)"처럼 동 표기가 섞여 있다. 동은 쓰지 않으므로 버린다.
            floors = [s for s in re.split(r"<br\s*/?>", floor_c) if not re.fullmatch(r"\(.*\)", text(s))]
            for i, dpart in enumerate(days):
                d = re.sub(r"\D", "", text(dpart))
                if not d:
                    continue
                ppart = prices[i] if i < len(prices) else ""
                p = re.sub(r"\D", "", text(ppart))
                if not p:
                    continue
                f = re.sub(r"[^\d-]", "", text(floors[i] if i < len(floors) else ""))
                month = start_month + k
                out.append({
                    "complex": name,
                    "jibun": jibun,
                    "area": f"{area:g}",
                    "ymd": f"{year}{month:02d}{int(d):02d}",
                    "price": p,
                    "floor": f,
                    "cancelled": "1" if "계약해제" in ppart else "0",
                })
    return out


def quarters(start, end):
    y, q = start.year, (start.month - 1) // 3
    while (y, q) <= (end.year, (end.month - 1) // 3):
        yield y, q * 3 + 1
        q += 1
        if q == 4:
            y, q = y + 1, 0


def bjdong_list(sgg):
    res = post("/land/common/getBjdongList.do", {"sggCd": sgg})
    return [(r["bjdongCd"], r["bjdongNm"]) for r in res.get("result", [])]


def fetch_deals(rows, sgg, bjdong, dong_name, start, end):
    added = 0
    for year, m0 in quarters(start, end):
        last_day = (dt.date(year + (m0 + 2) // 12, (m0 + 2) % 12 + 1, 1) - dt.timedelta(days=1))
        res = post("/land/rtms/getRtmsPriceList.do", {
            "sggCd": sgg,
            "rightGbnGrp": "RTMS",
            "bjdong10Cd": bjdong,
            "selectGubun": "1",
            "rnCd": "",
            "startDate": f"{year}{m0:02d}01",
            "endDate": last_day.strftime("%Y%m%d"),
            "bldgNm": "",
            "bldgGbn": "AP",
        })
        html = ""
        for it in res.get("result", []) or []:
            html += it.get("HTML", "") or ""
        for d in parse_price_html(html, year, m0):
            key = f"{sgg}-{dong_name}-{d['jibun']}-{d['area']}-{d['ymd']}-{d['price']}-{d['floor']}"
            if key in rows:
                if d["cancelled"] == "1" and rows[key].get("cancelled") != "1":
                    rows[key]["cancelled"] = "1"
                    rows[key]["cancel_seen"] = TODAY.isoformat()
                continue
            rows[key] = dict(d, key=key, sgg=sgg, dong=dong_name, first_seen=TODAY.isoformat(),
                             cancel_seen=TODAY.isoformat() if d["cancelled"] == "1" else "")
            added += 1
        time.sleep(1)
    return added


def main():
    permits = read_csv("permits.csv", PERMIT_FIELDS)
    deals = read_csv("deals.csv", DEAL_FIELDS)
    first_run = not permits and not deals

    # 처음에는 2025년 1월부터 채우고, 그다음부터는 최근 구간만 다시 본다.
    p_start = dt.date(2025, 1, 1) if first_run else TODAY - dt.timedelta(days=62)
    d_start = dt.date(2025, 1, 1) if first_run else TODAY - dt.timedelta(days=200)
    wide_start = TODAY - dt.timedelta(days=200)

    n_p = fetch_permits(permits, p_start, TODAY)
    n_d = fetch_deals(deals, YONGSAN, HANNAM_BJDONG, "한남동", d_start, TODAY)

    # 토요일 주간글(용산·성동 30억 이상)용: 두 구의 모든 동을 최근 두 분기만 본다.
    for sgg in (YONGSAN, SEONGDONG):
        for code, nm in bjdong_list(sgg):
            if sgg == YONGSAN and code == HANNAM_BJDONG:
                continue
            n_d += fetch_deals(deals, sgg, code, nm, wide_start, TODAY)

    # 첫 실행에 채운 과거분은 "새로 공개"로 보이지 않게 기록 개시일로 표시한다.
    if first_run:
        for r in list(permits.values()) + list(deals.values()):
            r["first_seen"] = "seed"
            if r.get("cancel_seen"):
                r["cancel_seen"] = "seed"

    write_csv("permits.csv", PERMIT_FIELDS, permits)
    write_csv("deals.csv", DEAL_FIELDS, deals)
    meta = {"collected_at": dt.datetime.now(KST).isoformat(timespec="minutes"),
            "new_permits": n_p, "new_deals": n_d, "first_run": first_run}
    with open(os.path.join(DATA, "last_run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
