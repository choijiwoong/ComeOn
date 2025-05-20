from flask import Flask, request, jsonify, render_template
import os
import requests
from bs4 import BeautifulSoup
from googlesearch import search as google_search
import re

app = Flask(__name__)

# ✅ 실시간 환율 가져오기
def get_exchange_rates():
    try:
        usd_resp = requests.get("https://api.frankfurter.app/latest?from=USD&to=KRW").json()
        usd_krw = usd_resp["rates"]["KRW"]

        cny_resp = requests.get("https://api.frankfurter.app/latest?from=CNY&to=KRW").json()
        cny_krw = cny_resp["rates"]["KRW"]

        return {"USD": usd_krw, "CNY": cny_krw}
    except Exception as e:
        print("❌ 환율 API 실패 (fallback 사용):", e)
        return {"USD": 1350.0, "CNY": 190.0}

exchange_rates = get_exchange_rates()

# 🎯 가격 문자열을 원화 float으로 변환
def extract_price_number(price_str, currency=None):
    try:
        # 통화 기호 및 불필요 문자 제거
        price_str = price_str.replace("약", "").replace("원", "").replace("엔", "").replace("￥", "")
        price_str = price_str.replace("USD", "").replace("US", "").replace("$", "").replace("₩", "")
        price_str = price_str.replace(",", ".")  # ✅ 유럽식 쉼표 → 점 변환

        numbers = re.findall(r"\d+(?:\.\d+)?", price_str)
        if not numbers:
            return float("inf")

        raw_value = float(numbers[0])
        if currency == "USD":
            return raw_value * exchange_rates["USD"]
        elif currency == "CNY":
            return raw_value * exchange_rates["CNY"]
        else:
            return raw_value
    except Exception as e:
        print("❌ 가격 파싱 오류:", e)
        return float("inf")


# ✅ 알리익스프레스 검색 함수
def search_aliexpress_static(keyword, max_items=10):
    url = f"https://ko.aliexpress.com/w/wholesale-{keyword}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("❌ Ali 요청 실패:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    product_blocks = soup.select('div.jr_t')

    results = []
    for block in product_blocks:
        try:
            title_tag = block.find("h3", class_="jr_kp")
            title = title_tag.get_text(strip=True) if title_tag else "제목 없음"

            a_tag = block.find_parent("a", class_="search-card-item")
            link, img_url = "(링크 없음)", ""
            if a_tag:
                href = a_tag.get("href", "")
                link = "https:" + href if href.startswith("//") else href
                img_tag = a_tag.find("img", class_="mm_be")
                img_url = img_tag.get("src") if img_tag else ""
                if img_url.startswith("//"):
                    img_url = "https:" + img_url

            price_spans = block.select("div.jr_kr span")
            price_parts = [span.get_text(strip=True) for span in price_spans]
            price_text = "".join(price_parts).strip()

            price_value = extract_price_number(price_text, currency="USD")
            formatted_price = f"약 ₩{int(price_value):,}" if price_value != float("inf") else "가격 정보 없음"

            results.append({
                "title": title,
                "price": formatted_price,
                "price_value": price_value,
                "image": img_url,
                "link": link,
                "source": "AliExpress"
            })

            if len(results) >= max_items:
                break
        except Exception as e:
            print(f"❌ Ali 파싱 오류: {e}")
    return results

# ✅ 타오바오 검색 함수
def get_taobao_category_url(query, max_results=5):
    search_query = f"site:www.taobao.com {query}"
    urls = []
    for url in google_search(search_query, stop=max_results):
        if "item.taobao.com" not in url and "login.taobao.com" not in url:
            urls.append(url)
            if len(urls) >= max_results:
                break
    return urls[0] if urls else None

def crawl_taobao_category(url, max_items=10):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print("❌ 타오바오 요청 실패:", res.status_code)
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    product_blocks = soup.select("a.item")

    results = []
    for a_tag in product_blocks:
        try:
            link = a_tag.get("href", "")
            if not link.startswith("http"):
                link = "https:" + link

            img_tag = a_tag.find("img", class_="item-img")
            img_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else ""
            if img_url.startswith("//"):
                img_url = "https:" + img_url

            title = a_tag.select_one("div.item-title")
            price = a_tag.select_one("div.disc-price")
            local_price = a_tag.select_one("div.local-price")

            title_text = title.get_text(strip=True) if title else "제목 없음"
            price_text = price.get_text(strip=True) if price else ""
            local_price_text = local_price.get_text(strip=True) if local_price else ""

            price_value = extract_price_number(local_price_text, currency="KRW")
            formatted_price = f"약 ₩{int(price_value):,}" if price_value != float("inf") else "가격 정보 없음"

            results.append({
                "title": title_text,
                "price": formatted_price,
                "price_value": price_value,
                "image": img_url,
                "link": link,
                "source": "Taobao"
            })

            if len(results) >= max_items:
                break
        except Exception as e:
            print(f"❌ 타오바오 파싱 오류: {e}")
    return results

# 🔄 price_value 안전 처리
def safe_json(items):
    for item in items:
        if item.get("price_value") in [float("inf"), float("-inf")]:
            item["price_value"] = None
    return items

# 🔍 API 연동
@app.route("/api/search")
def search_api():
    query = request.args.get("query")
    if not query:
        return jsonify([])

    ali_data = search_aliexpress_static(query)
    taobao_url = get_taobao_category_url(query)
    taobao_data = crawl_taobao_category(taobao_url) if taobao_url else []

    combined = ali_data + taobao_data
    combined_sorted = sorted([x for x in combined if x["price_value"] is not None], key=lambda x: x["price_value"])

    return jsonify(safe_json(combined_sorted))

# 기본 페이지
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/result")
def result():
    query = request.args.get("query")
    return render_template("result.html", query=query)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

