"""
Todo items parser and manager module.
Reads, modifies, and parses plain text / markdown todo list files.
"""

import os
from typing import List, Dict


def read_raw_lines(filepath: str) -> List[str]:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return f.readlines()


def write_raw_lines(filepath: str, lines: List[str]):
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)


def load_todos(filepath: str, max_items: int = 9) -> Dict:
    """
    读取并解析待办事项文件。
    支持格式：
      - [ ] 待办事项
      - [x] 已完成事项
      - 普通文本待办
    """
    if not os.path.exists(filepath):
        return {
            "items": [
                {"id": 1, "text": "编辑 todos.txt 或运行 ./todo.py add 添加待办", "done": False},
                {"id": 2, "text": "支持 ./todo.py done <序号> 标记完成", "done": False},
            ],
            "total": 2,
            "completed": 0,
            "pending": 2
        }

    items = []
    item_counter = 1
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            done = False
            text = stripped

            if stripped.startswith("- [x]") or stripped.startswith("[x]") or stripped.startswith("- [X]") or stripped.startswith("[X]"):
                done = True
                text = stripped.lstrip("- ").replace("[x]", "").replace("[X]", "").strip()
            elif stripped.startswith("- [ ]") or stripped.startswith("[ ]"):
                done = False
                text = stripped.lstrip("- ").replace("[ ]", "").strip()
            elif stripped.startswith("- "):
                text = stripped[2:].strip()

            items.append({"id": item_counter, "text": text, "done": done, "raw": stripped})
            item_counter += 1

    total = len(items)
    completed = sum(1 for it in items if it["done"])
    pending = total - completed

    # 优先显示未完成事项，随后显示已完成事项
    pending_items = [it for it in items if not it["done"]]
    done_items = [it for it in items if it["done"]]
    display_items = (pending_items + done_items)[:max_items]

    return {
        "items": display_items,
        "all_items": items,
        "total": total,
        "completed": completed,
        "pending": pending
    }


def add_todo_item(filepath: str, text: str) -> bool:
    """追加一条新待办"""
    new_line = f"- [ ] {text.strip()}\n"
    if not os.path.exists(filepath):
        write_raw_lines(filepath, ["# 每日待办事项\n", new_line])
        return True

    lines = read_raw_lines(filepath)
    # 如果最后一行没有换行符则补上
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append(new_line)
    write_raw_lines(filepath, lines)
    return True


def mark_todo_status(filepath: str, item_id: int, done: bool = True) -> bool:
    """修改指定序号的待办状态"""
    if not os.path.exists(filepath):
        return False

    lines = read_raw_lines(filepath)
    cur_idx = 1
    new_lines = []
    found = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        if cur_idx == item_id:
            # 提取文本
            t = stripped
            if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                t = stripped[5:].strip()
            elif stripped.startswith("- [ ]"):
                t = stripped[5:].strip()
            elif stripped.startswith("[x]") or stripped.startswith("[X]"):
                t = stripped[3:].strip()
            elif stripped.startswith("[ ]"):
                t = stripped[3:].strip()
            elif stripped.startswith("- "):
                t = stripped[2:].strip()

            prefix = "- [x]" if done else "- [ ]"
            new_lines.append(f"{prefix} {t}\n")
            found = True
        else:
            new_lines.append(line)

        cur_idx += 1

    if found:
        write_raw_lines(filepath, new_lines)
    return found


def delete_todo_item(filepath: str, item_id: int) -> bool:
    """删除指定序号的待办"""
    if not os.path.exists(filepath):
        return False

    lines = read_raw_lines(filepath)
    cur_idx = 1
    new_lines = []
    found = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        if cur_idx == item_id:
            found = True
            # 不加入 new_lines
        else:
            new_lines.append(line)

        cur_idx += 1

    if found:
        write_raw_lines(filepath, new_lines)
    return found


def clear_completed_todos(filepath: str) -> int:
    """清除所有已完成的待办"""
    if not os.path.exists(filepath):
        return 0

    lines = read_raw_lines(filepath)
    new_lines = []
    removed_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("- [X]") or stripped.startswith("[x]") or stripped.startswith("[X]"):
            removed_count += 1
            continue
        new_lines.append(line)

    write_raw_lines(filepath, new_lines)
    return removed_count
