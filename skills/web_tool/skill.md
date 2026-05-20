# Web Tool - 網路資料查詢工具

## 功能描述

這是一個使用 Playwright 框架的網路資料查詢工具，主要用於搜尋網路資訊並擷取網頁內容。

## 函數列表

### 1. search(keyword: str, num_results: int = 5) -> list[dict]

**功能**：搜尋關鍵字並返回搜尋結果

**參數**：
| 參數 | 類型 | 說明 | 預設值 |
|------|------|------|--------|
| keyword | str | 搜尋關鍵字 | 必填 |
| num_results | int | 回傳結果數量 | 5 |

**回傳**：
```python
[
    {"title": "標題", "url": "連結", "snippet": "摘要"},
    ...
]
```

### 2. fetch_content(url: str) -> str

**功能**：擷取指定網頁的正文內容

**參數**：
| 參數 | 類型 | 說明 |
|------|------|------|
| url | str | 目標網頁網址 |

**回傳**：網頁的正文文字（純文字）

### 3. search_and_summarize(keyword: str) -> dict

**功能**：搜尋關鍵字並擷取第一筆結果的摘要

**參數**：
| 參數 | 類型 | 說明 |
|------|------|------|
| keyword | str | 搜尋關鍵字 |

**回傳**：
```python
{"title": "標題", "url": "連結", "snippet": "摘要"}
```

## 使用範例

```python
from skills.web_tool import search, fetch_content, search_and_summarize

# 搜尋
results = search("Python 教學", num_results=3)

# 擷取網頁內容
content = fetch_content("https://example.com")

# 搜尋+摘要
summary = search_and_summarize("AI 發展趨勢")
```

## 錯誤處理

- 網路超时：回傳空清單或空字串
- 無法訪問網頁：回傳 None 或拋出例外
- 搜尋無結果：回傳空清單

## 依賴套件

- playwright
- requests (輔助)