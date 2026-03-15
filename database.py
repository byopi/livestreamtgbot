import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id    INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                rtmp_url    TEXT    NOT NULL,
                stream_key  TEXT    NOT NULL
            )
        """)
        await db.commit()


async def get_channels(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE owner_id = ?", (owner_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_channel(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE id = ?", (channel_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_channel(owner_id: int, name: str, rtmp_url: str, stream_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO channels (owner_id, name, rtmp_url, stream_key) VALUES (?,?,?,?)",
            (owner_id, name, rtmp_url, stream_key),
        )
        await db.commit()
        return cur.lastrowid


async def delete_channel(channel_id: int, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM channels WHERE id = ? AND owner_id = ?",
            (channel_id, owner_id),
        )
        await db.commit()
