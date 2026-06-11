import os
import sqlite3

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "user_memory.db")


def init_db():
    """Initializes the SQLite database and creates the memories table and indexes if they don't exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scope       TEXT NOT NULL,          -- "user" o "group"
                scope_id    INTEGER NOT NULL,       -- user_id (se scope=user) o chat_id (se scope=group)
                category    TEXT NOT NULL,          -- es: preference, personal, gag, interest, dynamic, habit
                content     TEXT NOT NULL,          -- il dato vero e proprio
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_id);")
        
        # Migration: Add group_id column if not exists
        try:
            cursor.execute("ALTER TABLE memories ADD COLUMN group_id INTEGER;")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_group ON memories(group_id);")
        except sqlite3.OperationalError:
            pass

        conn.commit()
    finally:
        conn.close()


# Initialize the database immediately when the module is imported
init_db()


def save_user_memory(user_id: int, category: str, content: str, group_id: int = None) -> str:
    """Saves a notable memory or fact about a specific user.

    Args:
        user_id: The unique numeric ID of the user (e.g. 713164389).
        category: The category of the memory (e.g. 'preference', 'personal', 'interest', 'gag').
        content: The actual fact or memory to save (e.g. 'Colore preferito: blu', 'Studia informatica a Padova').
        group_id: Optional unique numeric ID of the group/chat where this memory was learned. Pass this if you are in a group chat.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (scope, scope_id, category, content, group_id) VALUES (?, ?, ?, ?, ?)",
            ("user", int(user_id), category.strip(), content.strip(), int(group_id) if group_id is not None else None)
        )
        conn.commit()
        return f"Successfully saved user memory (ID: {cursor.lastrowid}) for user {user_id}."
    except Exception as e:
        return f"Error saving user memory: {e}"
    finally:
        conn.close()


def get_user_memories(user_id: int) -> str:
    """Retrieves all stored memories and facts about a specific user.

    Args:
        user_id: The unique numeric ID of the user (e.g. 713164389).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, category, content, created_at FROM memories WHERE scope = ? AND scope_id = ? ORDER BY created_at DESC",
            ("user", int(user_id))
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No memories found for user {user_id}."

        memories_list = []
        for row in rows:
            mem_id, category, content, created_at = row
            memories_list.append(f"- [ID: {mem_id}] [{category}] {content} (saved at {created_at})")
        return f"Memories for user {user_id}:\n" + "\n".join(memories_list)
    except Exception as e:
        return f"Error retrieving user memories: {e}"
    finally:
        conn.close()


def save_group_memory(chat_id: int, category: str, content: str) -> str:
    """Saves a notable memory or group dynamic about a specific chat/group.

    Args:
        chat_id: The unique numeric ID of the chat/group (e.g. -100123456).
        category: The category of the memory (e.g. 'gag', 'dynamic', 'habit', 'preference').
        content: The actual fact, gag, or habit to save (e.g. 'Ogni venerdì si organizza la serata pizza').
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (scope, scope_id, category, content) VALUES (?, ?, ?, ?)",
            ("group", int(chat_id), category.strip(), content.strip())
        )
        conn.commit()
        return f"Successfully saved group memory (ID: {cursor.lastrowid}) for chat {chat_id}."
    except Exception as e:
        return f"Error saving group memory: {e}"
    finally:
        conn.close()


def get_group_memories(chat_id: int) -> str:
    """Retrieves all stored memories, gags, and dynamics about a specific chat/group.

    Args:
        chat_id: The unique numeric ID of the chat/group (e.g. -100123456).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, scope, scope_id, category, content, created_at FROM memories WHERE (scope = ? AND scope_id = ?) OR (group_id = ?) ORDER BY created_at DESC",
            ("group", int(chat_id), int(chat_id))
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No memories found for chat {chat_id}."

        memories_list = []
        for row in rows:
            mem_id, scope, scope_id, category, content, created_at = row
            if scope == "group":
                memories_list.append(f"- [ID: {mem_id}] [Group] [{category}] {content} (saved at {created_at})")
            else:
                memories_list.append(f"- [ID: {mem_id}] [User {scope_id}] [{category}] {content} (saved at {created_at})")
        return f"Memories for chat {chat_id}:\n" + "\n".join(memories_list)
    except Exception as e:
        return f"Error retrieving group memories: {e}"
    finally:
        conn.close()


def delete_memory(memory_id: int) -> str:
    """Deletes a specific memory by its unique database ID.

    Args:
        memory_id: The unique numeric ID of the memory to delete.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        # First verify if it exists
        cursor.execute("SELECT scope, scope_id, content FROM memories WHERE id = ?", (int(memory_id),))
        row = cursor.fetchone()
        if not row:
            return f"Memory with ID {memory_id} not found."

        scope, scope_id, content = row
        cursor.execute("DELETE FROM memories WHERE id = ?", (int(memory_id),))
        conn.commit()
        return f"Successfully deleted memory ID {memory_id} (Scope: {scope}, Scope ID: {scope_id}, Content: '{content}')."
    except Exception as e:
        return f"Error deleting memory: {e}"
    finally:
        conn.close()


def delete_all_user_memories(user_id: int) -> int:
    """Deletes all memories associated with a specific user ID.

    Returns:
        The number of deleted memories.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE scope = ? AND scope_id = ?", ("user", int(user_id)))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count
    except Exception:
        return 0
    finally:
        conn.close()
