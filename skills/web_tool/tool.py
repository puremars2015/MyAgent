import asyncio
import re
import json
from typing import Optional, Dict, Any

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Error: playwright not installed. Run: pip install playwright")


def get_weather_info(city: str = "Kaohsiung", lat: float = 22.63, lon: float = 120.30) -> Dict[str, Any]:
    """使用 Open-Meteo API 取得天氣資訊"""
    try:
        import requests
        
        url = f"https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "Asia/Taipei",
            "lang": "zh"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        current = data.get("current", {})
        temp = current.get("temperature_2m", "N/A")
        humidity = current.get("relative_humidity_2m", "N/A")
        apparent = current.get("apparent_temperature", "N/A")
        wind = current.get("wind_speed_10m", "N/A")
        weather_code = current.get("weather_code", 0)
        
        weather_desc = {
            0: "晴朗",
            1: "大致晴朗",
            2: "局部多雲",
            3: "陰天",
            45: "霧",
            48: "霧凇",
            51: "輕微毛毛雨",
            53: "毛毛雨",
            55: "密集毛毛雨",
            61: "輕微下雨",
            63: "下雨",
            65: "大雨",
            71: "輕微下雪",
            73: "下雪",
            75: "大雪",
            80: "輕微陣雨",
            81: "陣雨",
            82: "強烈陣雨",
            95: "雷雨",
            96: "雷暴伴輕冰",
            99: "雷暴伴重冰"
        }.get(weather_code, "未知")
        
        return {
            "title": f"{city} 目前天氣",
            "url": "https://open-meteo.com/",
            "snippet": f"溫度: {temp}°C (體感: {apparent}°C), 濕度: {humidity}%, 風速: {wind} km/h, 天氣狀況: {weather_desc}"
        }
    except Exception as e:
        return {"title": "", "url": "", "snippet": f"Error: {str(e)}"}


def is_weather_query(keyword: str) -> bool:
    """判斷是否為天氣查詢"""
    weather_keywords = ["天氣", "氣溫", "溫度", "下雨", "晴天", "雨", "風", "濕度", "預報", "氣象"]
    keyword_lower = keyword.lower()
    return any(k in keyword_lower for k in weather_keywords)


def search_weather(keyword: str) -> Dict[str, Any]:
    """專門處理天氣查詢"""
    keyword_lower = keyword.lower()
    
    locations = {
        "高雄": (22.63, 120.30, "高雄"),
        "台中": (24.15, 120.68, "台中"),
        "台北": (25.03, 121.56, "台北"),
        "台南": (22.99, 120.20, "台南"),
        "桃園": (25.00, 121.30, "桃園"),
        "新竹": (24.80, 120.97, "新竹"),
        "基隆": (25.13, 121.73, "基隆"),
        "宜蘭": (24.76, 121.75, "宜蘭"),
        "花蓮": (23.99, 121.60, "花蓮"),
        "台東": (22.75, 121.15, "台東"),
        "屏東": (22.55, 120.58, "屏東"),
        "彰化": (24.08, 120.52, "彰化"),
        "雲林": (23.71, 120.53, "雲林"),
        "嘉義": (23.48, 120.44, "嘉義"),
        "南投": (23.91, 120.66, "南投"),
        "苗栗": (24.56, 120.82, "苗栗"),
        "新北": (25.01, 121.45, "新北"),
    }
    
    for city, (lat, lon, name) in locations.items():
        if city in keyword_lower:
            return get_weather_info(name, lat, lon)
    
    return get_weather_info("高雄", 22.63, 120.30)


async def _search_with_playwright(keyword: str, num_results: int = 5) -> list[dict]:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(f"https://duckduckgo.com/?q={keyword}", timeout=20000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            result_divs = await page.query_selector_all("div[data-testid='result']")
            
            for result in result_divs[:num_results]:
                try:
                    title_elem = await result.query_selector("a[data-testid='result-title']")
                    snippet_elem = await result.query_selector("a[data-testid='result-excerpt']")
                    
                    title = await title_elem.inner_text() if title_elem else ""
                    url = await title_elem.get_attribute("href") if title_elem else ""
                    snippet = await snippet_elem.inner_text() if snippet_elem else ""
                    
                    if title:
                        results.append({
                            "title": title[:200],
                            "url": url[:500] if url else "",
                            "snippet": snippet[:300]
                        })
                except Exception:
                    continue
                    
            if not results:
                links = await page.query_selector_all("a[href^='http']")
                for link in links[:num_results]:
                    try:
                        title = await link.inner_text()
                        url = await link.get_attribute("href")
                        if title and url and len(title) > 5:
                            results.append({
                                "title": title[:200],
                                "url": url[:500],
                                "snippet": ""
                            })
                    except Exception:
                        continue
                        
        except Exception as e:
            print(f"Search error: {e}")
        finally:
            await browser.close()
    return results[:num_results]


def search(keyword: str, num_results: int = 5) -> list[dict]:
    """搜尋關鍵字並返回搜尋結果"""
    if is_weather_query(keyword):
        return [search_weather(keyword)]
    
    try:
        return asyncio.run(_search_with_playwright(keyword, num_results))
    except Exception as e:
        print(f"Search failed: {e}")
        return []


def search_native(keyword: str, num_results: int = 5) -> list[dict]:
    """使用原生 HTTP 請求搜尋"""
    if is_weather_query(keyword):
        return [search_weather(keyword)]
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        url = f"https://html.duckduckgo.com/html/?q={keyword}"
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        results = []
        for result in soup.select("div.result")[:num_results]:
            try:
                title_elem = result.select_one("a.result__a")
                snippet_elem = result.select_one("a.result__snippet")
                
                if title_elem and snippet_elem:
                    results.append({
                        "title": title_elem.text[:200],
                        "url": title_elem.get("href", "")[:500],
                        "snippet": snippet_elem.text[:300]
                    })
            except Exception:
                continue
        return results
    except Exception as e:
        print(f"Native search failed: {e}")
        return []


def search_bing(keyword: str, num_results: int = 5) -> list[dict]:
    """使用 Bing 搜尋"""
    if is_weather_query(keyword):
        return [search_weather(keyword)]
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        url = f"https://www.bing.com/search?q={keyword}"
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        results = []
        for li in soup.select("li.b_algo")[:num_results]:
            try:
                title_elem = li.select_one("h2 a")
                snippet_elem = li.select_one("p")
                
                if title_elem:
                    results.append({
                        "title": title_elem.text[:200],
                        "url": title_elem.get("href", "")[:500],
                        "snippet": snippet_elem.text[:300] if snippet_elem else ""
                    })
            except Exception:
                continue
        return results
    except Exception as e:
        print(f"Bing search failed: {e}")
        return []


def search_and_summarize(keyword: str) -> dict:
    """搜尋關鍵字並擷取第一筆結果的摘要"""
    if is_weather_query(keyword):
        return search_weather(keyword)
    
    results = search_native(keyword, num_results=1)
    if results and results[0].get("title"):
        return results[0]
    
    results = search_bing(keyword, num_results=1)
    if results and results[0].get("title"):
        return results[0]
    
    results = search(keyword, num_results=1)
    if results and results[0].get("title"):
        return results[0]
    
    return {"title": "", "url": "", "snippet": ""}


if __name__ == "__main__":
    print("=== Web Tool Test ===")
    print()
    print("1. Weather search:")
    print(json.dumps(search_weather("高雄天氣"), ensure_ascii=False, indent=2))
    print()
    print("2. is_weather_query test:")
    print("'高雄今天氣溫':", is_weather_query("高雄今天氣溫"))
    print("'Python教學':", is_weather_query("Python教學"))
    print()
    print("3. search_and_summarize (weather):")
    print(json.dumps(search_and_summarize("高雄今天氣溫幾度"), ensure_ascii=False, indent=2))
    print()
    print("4. search_and_summarize (general):")
    print(json.dumps(search_and_summarize("Python教程"), ensure_ascii=False, indent=2))