# 한남현대 공개 기록

한남현대공인중개사사무소가 서울부동산정보광장 공개 자료를 매일 아침 수집해 쌓는 한남더힐·나인원한남 실거래 신고와 용산구 토지거래허가 처리 내역입니다.

- 사이트: https://hannamhyundai.github.io/
- 매일 07:40(서울) GitHub Actions가 fetch.py로 수집하고 build.py로 페이지를 만듭니다.
- 원자료: data/deals.csv, data/permits.csv
- 동·호수는 싣지 않습니다.
- 기록 글: posts/ 에 html 파일 하나를 더하면 notes/ 아래 페이지로 올라가고 최근 기록·RSS·사이트맵에 함께 실립니다. 파일 머리에 title·date·slug·summary 줄, 그 아래 `---` 한 줄, 이어서 본문 HTML을 씁니다.
- 기사 기록: data/news.csv 에 한 줄씩 더하면 첫 화면과 news.html 에 실립니다. 본문·사진은 옮기지 않고 제목·언론사·입력일·원문 링크와 새로 쓴 요약만 둡니다.
- 접수 매물 수: data/listings.csv(단지, 매물 수, 기준일)를 고치면 listings.json으로 나가고 luxuryhome.kr 첫 화면 '한남현대 접수 매물' 칸이 두 단지 합계를 읽어 갑니다. 숫자만 싣고 동·호수·가격은 넣지 않습니다.
