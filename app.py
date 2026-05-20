import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

DB_PATH = "conversations.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_message(conv_id: int, title: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (conv_id, title, role, content) VALUES (?, ?, ?, ?)",
        (conv_id, title, role, content)
    )
    conn.commit()
    conn.close()


def get_conversations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT conv_id, title, created_at 
        FROM conversations 
        GROUP BY conv_id 
        ORDER BY MAX(created_at) DESC
    """)
    result = cursor.fetchall()
    conn.close()
    return result


def get_conversation_messages(conv_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, created_at 
        FROM conversations 
        WHERE conv_id = ? 
        ORDER BY created_at ASC
    """, (conv_id,))
    result = cursor.fetchall()
    conn.close()
    return result


def chat(messages: list, conv_title: str):
    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message.content
    save_message(0, conv_title, "assistant", reply)
    return reply


def cmd_new() -> tuple[int, str]:
    print("\n=== 建立新對話 ===")
    title = input("請輸入對話標題: ").strip()
    if not title:
        title = f"對話 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(conv_id), 0) + 1 FROM conversations")
    conv_id = cursor.fetchone()[0]
    conn.close()
    save_message(conv_id, title, "system", "你是 AI 助手，請友善地回答用戶的問題。")
    print(f"✅ 已建立新對話: {title} (ID: {conv_id})")
    return conv_id, title


def cmd_list():
    print("\n=== 對話紀錄 ===")
    convs = get_conversations()
    if not convs:
        print("尚無對話紀錄")
        return
    print(f"{'ID':<5} {'標題':<30} {'建立時間'}")
    print("-" * 60)
    for conv_id, title, created_at in convs:
        print(f"{conv_id:<5} {title:<30} {created_at}")


def cmd_load(conv_id: int):
    msgs = get_conversation_messages(conv_id)
    if not msgs:
        print("找不到此對話")
        return None, None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM conversations WHERE conv_id = ? LIMIT 1", (conv_id,))
    title = cursor.fetchone()[0]
    conn.close()
    return [(role, content) for role, content, _ in msgs], title


def cmd_chat(conv_id: int, title: str):
    print(f"\n=== 對話: {title} ===")
    print("輸入內容進行對話，輸入 /exit 結束對話")
    print("-" * 40)

    messages = [{"role": role, "content": content, "created_at": ts} for role, content, ts in get_conversation_messages(conv_id)]
    messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    while True:
        user_input = input("\n你: ").strip()
        if not user_input:
            continue
        if user_input == "/exit":
            print("✅ 對話已結束")
            break

        save_message(conv_id, title, "user", user_input)
        messages.append({"role": "user", "content": user_input})

        print("AI: ", end="", flush=True)
        reply = chat(messages, title)
        print(reply)
        messages.append({"role": "assistant", "content": reply})


def main():
    init_db()
    print("=== AI 聊天機器人 ===")
    print("指令: /new - 新對話, /list - 對話紀錄, /chat <ID> - 進入對話, /exit - 離開")

    while True:
        cmd = input("\n請輸入指令: ").strip()

        if cmd == "/new":
            conv_id, title = cmd_new()
            cmd_chat(conv_id, title)
        elif cmd == "/list":
            cmd_list()
        elif cmd.startswith("/chat "):
            try:
                conv_id = int(cmd.split()[1])
                msgs, title = cmd_load(conv_id)
                if msgs:
                    cmd_chat(conv_id, title)
            except (ValueError, IndexError):
                print("用法: /chat <ID>")
        elif cmd == "/exit":
            print("再見！")
            break
        else:
            print("未知指令，請使用: /new, /list, /chat <ID>, /exit")


if __name__ == "__main__":
    main()