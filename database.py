import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets

DB_PATH = Path("app.db")

def get_connection():
    """接続を取得（row_factoryで辞書風アクセス可能）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # 外部キー有効化
    return conn

def init_db():
    """テーブルを初期化（何度実行しても安全）"""
    with get_connection() as conn:
        conn.executescript("""
            -- ユーザー
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,                    -- 認証用（任意）
                name TEXT,
                plan TEXT DEFAULT 'free' CHECK(plan IN ('free', 'pro')),
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Proプラン / サブスクリプション
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'canceled', 'expired', 'past_due')),
                plan TEXT DEFAULT 'pro',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                canceled_at TIMESTAMP,
                auto_renew INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- 支払い履歴
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER,
                amount INTEGER NOT NULL,               -- 円単位（例: 980）
                currency TEXT DEFAULT 'jpy',
                status TEXT DEFAULT 'succeeded' CHECK(status IN ('pending', 'succeeded', 'failed', 'refunded')),
                provider TEXT,                         -- 'stripe', 'paypal' など
                provider_payment_id TEXT,              -- 外部決済ID
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            );

            -- インデックス（検索高速化）
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
        """)
    print("データベースを初期化しました:", DB_PATH)

# ====================== ユーザー関連 ======================

def create_user(email: str, password_hash: str = None, name: str = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            (email, password_hash, name)
        )
        return cursor.lastrowid

def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

# ====================== Proプラン関連 ======================

def start_pro(user_id: int, days: int = 30, auto_renew: bool = True) -> int:
    """Proプランを開始する"""
    expires_at = datetime.now() + timedelta(days=days)
    with get_connection() as conn:
        # 既存の有効なサブスクリプションがあればキャンセル扱い
        conn.execute(
            "UPDATE subscriptions SET status = 'canceled', canceled_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        # 新しいサブスクリプションを作成
        cursor = conn.execute(
            """
            INSERT INTO subscriptions (user_id, status, expires_at, auto_renew)
            VALUES (?, 'active', ?, ?)
            """,
            (user_id, expires_at, int(auto_renew))
        )
        sub_id = cursor.lastrowid
        # ユーザーのプランを更新
        conn.execute("UPDATE users SET plan = 'pro', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
        return sub_id

def cancel_pro(user_id: int):
    """Proプランをキャンセル（即時ではなく期限まで有効にする場合が多い）"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE subscriptions SET status = 'canceled', canceled_at = CURRENT_TIMESTAMP, auto_renew = 0 "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )

def is_pro_user(user_id: int) -> bool:
    """現在Proが有効かどうか"""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM subscriptions
            WHERE user_id = ? AND status = 'active' AND expires_at > CURRENT_TIMESTAMP
            """,
            (user_id,)
        ).fetchone()
        return row is not None

def get_active_subscription(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()

# ====================== 支払い関連 ======================

def record_payment(
    user_id: int,
    amount: int,
    subscription_id: int = None,
    provider: str = None,
    provider_payment_id: str = None,
    status: str = "succeeded"
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO payments (user_id, subscription_id, amount, provider, provider_payment_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, subscription_id, amount, provider, provider_payment_id, status)
        )
        return cursor.lastrowid

def get_payments(user_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY paid_at DESC",
            (user_id,)
        ).fetchall()

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"

def verify_password(password: str, password_hash: str) -> bool:
    """パスワードを検証"""
    try:
        salt, hashed = password_hash.split("$")
        return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
    except:
        return False

# ====================== 初期化用 ======================

if __name__ == "__main__":
    init_db()