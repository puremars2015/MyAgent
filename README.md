# 自製agent基礎教學

每一個commit是一個步驟,可以根據commit來觀看進度

## 1
基本的問話與回答

## 2

### 對話記憶與CLI流程說明

#### 1. 啟動程式
* 執行 main()，初始化資料庫（init_db），建立 conversations 資料表（若不存在）。
* 顯示主選單，等待使用者輸入指令。

#### 2. 建立新對話（/new）
* 執行 cmd_new()：
	- 輸入對話標題（可自訂，預設為當前時間）。
	- 取得新的 conv_id（目前最大 conv_id + 1）。
	- 儲存一筆 system 訊息（角色為 system，內容為「你是 AI 助手...」）到 conversations 資料表。
	- 回傳 conv_id 和標題。

#### 3. 進入對話模式
* 執行 cmd_chat(conv_id, title)：
	- 讀取該 conv_id 的所有訊息，組成 messages。
	- 進入 while 迴圈，持續等待使用者輸入。
	- 每次使用者輸入訊息（role: user）：
		- 儲存到 conversations 資料表。
		- 呼叫 chat()，將 messages 傳給 OpenAI API，取得 AI 回覆。
		- AI 回覆（role: assistant）同樣儲存到 conversations 資料表。
	- 若輸入 /exit，結束對話。

#### 4. 資料庫儲存邏輯
* 每一則訊息（不論 user、assistant、system）都會呼叫 save_message()，將 conv_id、title、role、content 寫入 conversations 資料表。
* conversations 資料表欄位：id, conv_id, title, role, content, created_at。

#### 5. 總結流程圖
1. 啟動 → 初始化 DB
2. /new → 建立新對話 conv_id → 寫入 system 訊息
3. 進入對話 → 每次互動都寫入 user/assistant 訊息到 DB
4. /exit → 離開對話
