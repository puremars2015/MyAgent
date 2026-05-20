import os
import sys
import json
import sqlite3
import importlib
import inspect
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

DB_PATH = "conversations.db"
SKILLS_DIR = Path(__file__).parent / "skills"

tools = []
tool_functions = {}


def parse_function_schema(func, func_name: str) -> dict:
    sig = inspect.signature(func)
    params = {}
    required = []
    for param_name, param in sig.parameters.items():
        if param_name in ('self', 'cls'):
            continue
        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            ann = str(param.annotation)
            if "int" in ann:
                param_type = "integer"
            elif "float" in ann:
                param_type = "number"
            elif "bool" in ann:
                param_type = "boolean"
            elif "list" in ann:
                param_type = "array"
            elif "dict" in ann:
                param_type = "object"
        params[param_name] = {"type": param_type}
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
        else:
            params[param_name]["default"] = param.default
    
    doc = func.__doc__ or ""
    description = doc.strip().split("\n")[0] if doc else ""
    
    schema = {
        "name": func_name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": params,
            "required": required
        }
    }
    return schema


def load_tools():
    global tools, tool_functions
    if not SKILLS_DIR.exists():
        return
    for skill_path in SKILLS_DIR.iterdir():
        if not skill_path.is_dir():
            continue
        skill_name = skill_path.name
        skill_md = skill_path / "skill.md"
        tool_py = skill_path / "tool.py"
        if not skill_md.exists() or not tool_py.exists():
            continue
        skill_desc = skill_md.read_text(encoding="utf-8")
        sys.path.insert(0, str(skill_path.parent))
        module = importlib.import_module(f"{skill_name}.tool")
        for func_name in dir(module):
            if func_name.startswith("_"):
                continue
            func = getattr(module, func_name)
            if not callable(func):
                continue
            if func_name in ("Optional", "async_playwright", "search_native", "search_bing"):
                continue
            tool_functions[func_name] = func
            schema = parse_function_schema(func, func_name)
            tools.append({
                "type": "function",
                "function": schema
            })
        sys.path.pop(0)


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


def get_tools_prompt():
    if not tools:
        return ""
    prompt = "\n\n## 可用工具：\n"
    for tool in tools:
        f = tool["function"]
        prompt += f"\n- {f['name']}: {f['description']}\n"
    return prompt


def chat(messages: list, conv_title: str):
    current_messages = messages.copy()
    system_prompt = "你是 AI 助手，請友善地回答用戶的問題。如果需要查詢網路資料，請使用可用的工具。"
    current_messages.insert(0, {"role": "system", "content": system_prompt})
    
    response = client.chat.completions.create(
        model="openai/gpt-5.5",
        messages=current_messages,
        tools=tools if tools else None
    )
    
    choice = response.choices[0]
    
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        assistant_msg = {
            "role": choice.message.role,
            "content": choice.message.content,
            "tool_calls": [
                {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        }
        current_messages.append(assistant_msg)
        
        tool_results = []
        for tc in choice.message.tool_calls:
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments)
            print(f"\n[工具調用: {func_name}({func_args})]")
            try:
                func = tool_functions.get(func_name)
                if func:
                    result = func(**func_args)
                    result_str = str(result)
                    print(f"[工具結果: {result_str[:500]}...]")
                    
                    is_empty = (
                        not result_str or 
                        result_str == "[]" or 
                        result_str == "{}" or
                        result_str == "{'title': '', 'url': '', 'snippet': ''}"
                    )
                    
                    tool_results.append({
                        "tool_name": func_name,
                        "result": result_str,
                        "is_empty": is_empty
                    })
                else:
                    tool_results.append({
                        "tool_name": func_name,
                        "result": f"Error: function {func_name} not found",
                        "is_empty": True
                    })
            except Exception as e:
                tool_results.append({
                    "tool_name": func_name,
                    "result": f"Error: {str(e)}",
                    "is_empty": True
                })
        
        empty_results = [r for r in tool_results if r["is_empty"]]
        if empty_results:
            reply = "抱歉，無法取得搜尋結果，請稍後再試或換個關鍵字。"
            save_message(0, conv_title, "assistant", reply)
            return reply
        
        summary_parts = []
        for r in tool_results:
            summary_parts.append(f"【{r['tool_name']}】\n{r['result']}")
        
        summary = "\n\n".join(summary_parts)
        reply = f"根據查詢結果，我為您整理如下：\n\n{summary}\n\n以上資訊僅供參考，如需更詳細的資料，建議直接訪問相關網站。"
        save_message(0, conv_title, "assistant", reply)
        return reply
    
    reply = choice.message.content
    save_message(0, conv_title, "assistant", reply)
    return reply


def cmd_new() -> tuple:
    print("\n=== 建立新對話 ===")
    title = input("請輸入對話標題: ").strip()
    if not title:
        title = f"對話 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(conv_id), 0) + 1 FROM conversations")
    conv_id = cursor.fetchone()[0]
    conn.close()
    tools_intro = get_tools_prompt()
    system_msg = f"你是 AI 助手，請友善地回答用戶的問題。{tools_intro}"
    save_message(conv_id, title, "system", system_msg)
    print(f"✅ 已建立新對話: {title} (ID: {conv_id})")
    if tool_functions:
        print(f"✅ 已載入 {len(tool_functions)} 個工具: {', '.join(tool_functions.keys())}")
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
    load_tools()
    print("=== AI 聊天機器人 ===")
    print("指令: /new - 新對話, /list - 對話紀錄, /tools - 工具列表, /chat <ID> - 進入對話, /exit - 離開")
    if tool_functions:
        print(f"✅ 已載入 {len(tool_functions)} 個工具: {', '.join(tool_functions.keys())}")

    while True:
        cmd = input("\n請輸入指令: ").strip()

        if cmd == "/new":
            conv_id, title = cmd_new()
            cmd_chat(conv_id, title)
        elif cmd == "/list":
            cmd_list()
        elif cmd == "/tools":
            if tool_functions:
                print("\n=== 已載入的工具 ===")
                for name, func in tool_functions.items():
                    desc = func.__doc__ or "無描述"
                    print(f"\n--- {name} ---")
                    print(desc[:500] + "..." if len(desc) > 500 else desc)
            else:
                print("尚無工具")
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