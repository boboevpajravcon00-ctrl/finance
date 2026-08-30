import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "finance.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                balance REAL DEFAULT 0.0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account_id INTEGER,
                type TEXT,
                amount REAL,
                category TEXT,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                person_name TEXT,
                amount REAL,
                type TEXT,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_user_accounts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def add_account(user_id: int, name: str, balance: float = 0.0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO accounts (user_id, name, balance) VALUES (?, ?, ?)", (user_id, name, balance))
        await db.commit()

async def update_account_balance(account_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, account_id))
        await db.commit()

async def add_transaction(user_id: int, account_id: int, tx_type: str, amount: float, category: str, comment: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO transactions (user_id, account_id, type, amount, category, comment) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, account_id, tx_type, amount, category, comment)
        )
        await db.commit()
        return cursor.lastrowid

async def get_transaction_by_id(tx_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def delete_transaction(tx_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        await db.commit()

async def get_recent_transactions(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT t.*, a.name as account_name
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            WHERE t.user_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_expense_stats(user_id: int, days: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND type = 'expense'
              AND created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, days)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_expenses_by_period(user_id: int, period: str = "week"):
    date_filter = "'-7 days'" if period == "week" else "'-30 days'"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"""
            SELECT t.amount, t.category, t.comment, t.created_at, a.name as account_name
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            WHERE t.user_id = ? AND t.type = 'expense'
              AND t.created_at >= datetime('now', {date_filter})
            ORDER BY t.created_at DESC
        """, (user_id,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_debts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM debts WHERE user_id = ? ORDER BY created_at DESC", (user_id,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def add_debt(user_id: int, person_name: str, amount: float, debt_type: str, comment: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO debts (user_id, person_name, amount, type, comment) VALUES (?, ?, ?, ?, ?)",
            (user_id, person_name, amount, debt_type, comment)
        )
        await db.commit()
        return cursor.lastrowid

async def set_account_balance(account_id: int, new_balance: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id))
        await db.commit()