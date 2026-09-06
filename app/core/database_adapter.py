import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

def _resolve_db_file() -> Path:
    # On Linux / Vercel / AWS Lambda / cloud serverless, always use /tmp
    if sys.platform != "win32" or os.environ.get("VERCEL") or os.environ.get("LAMBDA_TASK_ROOT") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp") / "sortdesk_local.db"
    default_path = Path(__file__).resolve().parent.parent.parent / "sortdesk_local.db"
    try:
        test_file = default_path.parent / ".write_test"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return default_path
    except (PermissionError, OSError):
        return Path("/tmp") / "sortdesk_local.db"


DB_FILE = _resolve_db_file()

class ExecuteResult:
    def __init__(self, data: Any = None, count: Optional[int] = None):
        self.data = data if data is not None else []
        self.count = count if count is not None else (len(self.data) if isinstance(self.data, list) else (1 if self.data else 0))


class StorageBucketMock:
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name

    def upload(self, path: str, file: bytes, file_options: Optional[Dict] = None):
        return {"Key": path}

    def get_public_url(self, path: str) -> str:
        return f"/storage/{self.bucket_name}/{path}"


class StorageClientMock:
    def from_(self, bucket_name: str):
        return StorageBucketMock(bucket_name)


class SQLiteQueryBuilder:
    def __init__(self, table_name: str, adapter: "LocalDatabaseAdapter"):
        self.table_name = table_name
        self.adapter = adapter
        self._select_columns = "*"
        self._where_clauses: List[tuple] = []
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._single: bool = False
        self._count_exact: bool = False
        self._action: str = "SELECT"
        self._insert_data: Any = None
        self._update_data: Optional[Dict[str, Any]] = None

    def select(self, columns: str = "*", count: Optional[str] = None):
        self._action = "SELECT"
        self._select_columns = columns
        if count == "exact":
            self._count_exact = True
        return self

    def insert(self, data: Any):
        self._action = "INSERT"
        self._insert_data = data
        return self

    def update(self, data: Dict[str, Any]):
        self._action = "UPDATE"
        self._update_data = data
        return self

    def delete(self):
        self._action = "DELETE"
        return self

    def eq(self, column: str, value: Any):
        self._where_clauses.append((column, "=", value))
        return self

    def gte(self, column: str, value: Any):
        self._where_clauses.append((column, ">=", value))
        return self

    def lte(self, column: str, value: Any):
        self._where_clauses.append((column, "<=", value))
        return self

    def ilike(self, column: str, value: Any):
        val = str(value).replace("%", "")
        self._where_clauses.append((column, "ILIKE", f"%{val}%"))
        return self

    def is_(self, column: str, value: Any):
        if value is None or str(value).lower() in ["null", "none"]:
            self._where_clauses.append((column, "IS", None))
        else:
            self._where_clauses.append((column, "IS", value))
        return self

    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def range(self, start: int, end: int):
        self._offset = start
        self._limit = (end - start) + 1
        return self

    def single(self):
        self._single = True
        self._limit = 1
        return self

    def execute(self) -> ExecuteResult:
        with self.adapter.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if self._action == "INSERT":
                items = self._insert_data if isinstance(self._insert_data, list) else [self._insert_data]
                inserted_rows = []
                for item in items:
                    item_copy = dict(item)
                    if "id" not in item_copy or not item_copy["id"]:
                        item_copy["id"] = str(uuid.uuid4())

                    # Serialize any dict/list fields into JSON string
                    for k, v in item_copy.items():
                        if isinstance(v, (dict, list)):
                            item_copy[k] = json.dumps(v)
                        elif isinstance(v, bool):
                            item_copy[k] = 1 if v else 0

                    cols = list(item_copy.keys())
                    placeholders = [f":{c}" for c in cols]
                    sql = f"INSERT INTO {self.table_name} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
                    cursor.execute(sql, item_copy)

                    # Retrieve inserted
                    cursor.execute(f"SELECT * FROM {self.table_name} WHERE id = ?", (item_copy["id"],))
                    row = cursor.fetchone()
                    if row:
                        inserted_rows.append(self.adapter.row_to_dict(self.table_name, row))

                conn.commit()
                return ExecuteResult(data=inserted_rows)

            elif self._action == "UPDATE":
                params: Dict[str, Any] = {}
                set_parts = []
                for k, v in (self._update_data or {}).items():
                    val = v
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    elif isinstance(val, bool):
                        val = 1 if val else 0
                    set_parts.append(f"{k} = :set_{k}")
                    params[f"set_{k}"] = val

                where_parts = []
                for i, (col, op, val) in enumerate(self._where_clauses):
                    col_name = col.split(".")[-1]
                    if op == "IS" and val is None:
                        where_parts.append(f"{col_name} IS NULL")
                    elif op == "ILIKE":
                        where_parts.append(f"LOWER({col_name}) LIKE LOWER(:w_{i})")
                        params[f"w_{i}"] = val
                    else:
                        where_parts.append(f"{col_name} {op} :w_{i}")
                        params[f"w_{i}"] = 1 if isinstance(val, bool) and val else (0 if isinstance(val, bool) else val)

                where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
                sql = f"UPDATE {self.table_name} SET {', '.join(set_parts)}{where_sql}"
                cursor.execute(sql, params)
                conn.commit()

                # Return updated rows
                select_sql = f"SELECT * FROM {self.table_name}{where_sql}"
                cursor.execute(select_sql, {k: v for k, v in params.items() if k.startswith("w_")})
                rows = cursor.fetchall()
                data = [self.adapter.row_to_dict(self.table_name, r) for r in rows]
                return ExecuteResult(data=data)

            elif self._action == "DELETE":
                where_parts = []
                params = {}
                for i, (col, op, val) in enumerate(self._where_clauses):
                    col_name = col.split(".")[-1]
                    if op == "IS" and val is None:
                        where_parts.append(f"{col_name} IS NULL")
                    else:
                        where_parts.append(f"{col_name} {op} :w_{i}")
                        params[f"w_{i}"] = val
                where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
                cursor.execute(f"DELETE FROM {self.table_name}{where_sql}", params)
                conn.commit()
                return ExecuteResult(data=[])

            else:  # SELECT
                params = {}
                where_parts = []
                join_sql = ""

                # Handle join for list_needs_attention: emails joined with email_categories
                if "email_categories" in self._select_columns or any("email_categories" in col for col, _, _ in self._where_clauses):
                    if self.table_name == "emails":
                        join_sql = " INNER JOIN email_categories ON emails.id = email_categories.email_id "

                for i, (col, op, val) in enumerate(self._where_clauses):
                    qualified_col = col
                    if "." not in qualified_col:
                        qualified_col = f"{self.table_name}.{col}"

                    if op == "IS" and val is None:
                        where_parts.append(f"{qualified_col} IS NULL")
                    elif op == "ILIKE":
                        where_parts.append(f"LOWER({qualified_col}) LIKE LOWER(:w_{i})")
                        params[f"w_{i}"] = val
                    else:
                        clean_val = 1 if isinstance(val, bool) and val else (0 if isinstance(val, bool) else val)
                        where_parts.append(f"{qualified_col} {op} :w_{i}")
                        params[f"w_{i}"] = clean_val

                where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
                order_sql = ""
                if self._order_by:
                    order_col = self._order_by.split(".")[-1]
                    order_sql = f" ORDER BY {self.table_name}.{order_col} {'DESC' if self._order_desc else 'ASC'}"

                limit_sql = ""
                if self._limit is not None:
                    limit_sql = f" LIMIT {self._limit}"
                    if self._offset is not None:
                        limit_sql += f" OFFSET {self._offset}"

                query_sql = f"SELECT {self.table_name}.* FROM {self.table_name}{join_sql}{where_sql}{order_sql}{limit_sql}"
                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
                data = [self.adapter.row_to_dict(self.table_name, r) for r in rows]

                count_val = len(data)
                if self._count_exact:
                    count_cursor = conn.cursor()
                    count_cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}{join_sql}{where_sql}", params)
                    count_val = count_cursor.fetchone()[0]

                if self._single:
                    return ExecuteResult(data=data[0] if data else None, count=count_val)
                return ExecuteResult(data=data, count=count_val)


class LocalDatabaseAdapter:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.storage = StorageClientMock()
        self.init_db()

    def get_connection(self):
        try:
            return sqlite3.connect(str(self.db_path), check_same_thread=False)
        except Exception:
            try:
                self.db_path = Path("/tmp") / "sortdesk_local.db"
                return sqlite3.connect(str(self.db_path), check_same_thread=False)
            except Exception:
                self.db_path = "file:sortdesk_shared?mode=memory&cache=shared"
                return sqlite3.connect(str(self.db_path), uri=True, check_same_thread=False)

    def table(self, table_name: str) -> SQLiteQueryBuilder:
        return SQLiteQueryBuilder(table_name, self)

    def rpc(self, func_name: str, params: Optional[Dict] = None) -> ExecuteResult:
        """Mock RPC function for match_emails vector search."""
        params = params or {}
        user_id = params.get("match_user_id")
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM emails WHERE user_id = ? ORDER BY received_at DESC LIMIT 5", (user_id,))
            else:
                cursor.execute("SELECT * FROM emails ORDER BY received_at DESC LIMIT 5")
            rows = cursor.fetchall()
            data = [self.row_to_dict("emails", r) for r in rows]
            return ExecuteResult(data=data)

    def row_to_dict(self, table_name: str, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for bool_col in ["has_attachment", "is_processed", "is_active", "is_duplicate_question"]:
            if bool_col in d and d[bool_col] is not None:
                d[bool_col] = bool(d[bool_col])
        if "skills_extracted" in d and isinstance(d["skills_extracted"], str):
            try:
                d["skills_extracted"] = json.loads(d["skills_extracted"])
            except Exception:
                pass
        return d

    def init_db(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT,
                    company_name TEXT,
                    password_hash TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    user_agent TEXT,
                    ip_address TEXT,
                    revoked_at TEXT,
                    replaced_by TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS gmail_connections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    gmail_address TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    connected_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS outlook_connections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    outlook_address TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    connected_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS emails (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    provider TEXT DEFAULT 'gmail',
                    gmail_message_id TEXT UNIQUE,
                    gmail_thread_id TEXT,
                    outlook_message_id TEXT UNIQUE,
                    outlook_conversation_id TEXT,
                    sender_email TEXT,
                    sender_name TEXT,
                    subject TEXT,
                    body_text TEXT,
                    received_at TEXT,
                    has_attachment INTEGER DEFAULT 0,
                    is_processed INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS email_categories (
                    id TEXT PRIMARY KEY,
                    email_id TEXT,
                    category TEXT NOT NULL,
                    confidence_score REAL,
                    priority TEXT,
                    priority_reason TEXT,
                    is_duplicate_question INTEGER DEFAULT 0,
                    duplicate_of_id TEXT,
                    resolved_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS email_drafts (
                    id TEXT PRIMARY KEY,
                    email_id TEXT,
                    draft_body TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    generated_at TEXT,
                    approved_at TEXT,
                    sent_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    email_id TEXT,
                    user_id TEXT,
                    full_name TEXT,
                    candidate_email TEXT,
                    role_applied_for TEXT,
                    skills_extracted TEXT,
                    resume_file_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS candidate_documents (
                    id TEXT PRIMARY KEY,
                    email_id TEXT,
                    file_url TEXT,
                    original_filename TEXT,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    question TEXT,
                    answer TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS job_postings (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    role_title TEXT NOT NULL,
                    posting_text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cursor.execute("PRAGMA table_info(users)")
                cols = [r[1] for r in cursor.fetchall()]
                if "company_name" not in cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN company_name TEXT")
                if "password_hash" not in cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                conn.commit()
            self._seed_initial_data()
        except Exception:
            # Fallback to shared in-memory SQLite if filesystem is read-only
            self.db_path = "file:sortdesk_shared?mode=memory&cache=shared"
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.executescript("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, full_name TEXT, company_name TEXT, password_hash TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS refresh_tokens (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, user_agent TEXT, ip_address TEXT, revoked_at TEXT, replaced_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS gmail_connections (
                        id TEXT PRIMARY KEY, user_id TEXT, gmail_address TEXT NOT NULL, refresh_token TEXT NOT NULL, is_active INTEGER DEFAULT 1, connected_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS outlook_connections (
                        id TEXT PRIMARY KEY, user_id TEXT, outlook_address TEXT NOT NULL, refresh_token TEXT NOT NULL, is_active INTEGER DEFAULT 1, connected_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS emails (
                        id TEXT PRIMARY KEY, user_id TEXT, provider TEXT DEFAULT 'gmail', gmail_message_id TEXT UNIQUE, gmail_thread_id TEXT, outlook_message_id TEXT UNIQUE, outlook_conversation_id TEXT, sender_email TEXT, sender_name TEXT, subject TEXT, body_text TEXT, received_at TEXT, has_attachment INTEGER DEFAULT 0, is_processed INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS email_categories (
                        id TEXT PRIMARY KEY, email_id TEXT, category TEXT NOT NULL, confidence_score REAL, priority TEXT, priority_reason TEXT, is_duplicate_question INTEGER DEFAULT 0, duplicate_of_id TEXT, resolved_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS email_drafts (
                        id TEXT PRIMARY KEY, email_id TEXT, draft_body TEXT NOT NULL, status TEXT DEFAULT 'pending', generated_at TEXT, approved_at TEXT, sent_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS candidates (
                        id TEXT PRIMARY KEY, email_id TEXT, user_id TEXT, full_name TEXT, candidate_email TEXT, role_applied_for TEXT, skills_extracted TEXT, resume_file_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS candidate_documents (
                        id TEXT PRIMARY KEY, email_id TEXT, file_url TEXT, original_filename TEXT, uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY, user_id TEXT, question TEXT, answer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS job_postings (
                        id TEXT PRIMARY KEY, user_id TEXT, role_title TEXT NOT NULL, posting_text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """)
                    conn.commit()
                self._seed_initial_data()
            except Exception:
                pass

    def _seed_initial_data(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM emails")
                count = cursor.fetchone()[0]
                if count > 0:
                    return

            demo_user_id = "00000000-0000-0000-0000-000000000001"
            cursor.execute("""
            INSERT OR IGNORE INTO users (id, email, full_name)
            VALUES (?, ?, ?)
            """, (demo_user_id, "demo.recruiter@sortdesk.ai", "Demo Recruiter"))

            email_1_id = "e1000000-0000-0000-0000-000000000001"
            draft_1_id = "d1000000-0000-0000-0000-000000000001"
            cand_1_id = "c1000000-0000-0000-0000-000000000001"
            cat_1_id = "a1000000-0000-0000-0000-000000000001"

            cursor.execute("""
            INSERT INTO emails (id, user_id, provider, outlook_message_id, outlook_conversation_id, sender_email, sender_name, subject, body_text, received_at, has_attachment, is_processed)
            VALUES (?, ?, 'outlook', 'MS_GRAPH_AAMkAGI2_SARAH', 'CONV_OUTLOOK_001', 'sarah.jenkins.candidate@outlook.com', 'Sarah Jenkins',
                    'Application for Senior Backend Engineer (Python / FastAPI)',
                    'Dear Hiring Team,\n\nI am writing to apply for the Senior Backend Engineer position. I have over 5 years of experience building scalable backend services with Python, FastAPI, and PostgreSQL.\n\nAttached is my resume in PDF format. Looking forward to hearing from you!\n\nBest regards,\nSarah Jenkins',
                    ?, 1, 1)
            """, (email_1_id, demo_user_id, datetime.now(timezone.utc).isoformat()))

            cursor.execute("""
            INSERT INTO email_categories (id, email_id, category, priority, confidence_score, resolved_at)
            VALUES (?, ?, 'New Applicant', 'High', 0.98, NULL)
            """, (cat_1_id, email_1_id))

            cursor.execute("""
            INSERT INTO email_drafts (id, email_id, draft_body, status, generated_at)
            VALUES (?, ?, ?, 'pending', ?)
            """, (
                draft_1_id,
                email_1_id,
                "Dear Sarah Jenkins,\n\nThank you for applying for the Senior Backend Engineer role. We have received your resume and our engineering recruitment team is currently reviewing your profile and qualifications in Python, FastAPI, and PostgreSQL.\n\nWe will reach out regarding the next steps in our technical interview process.\n\nBest regards,\nTalent Acquisition Team",
                datetime.now(timezone.utc).isoformat()
            ))

            cursor.execute("""
            INSERT INTO candidates (id, email_id, user_id, full_name, candidate_email, role_applied_for, skills_extracted, resume_file_url)
            VALUES (?, ?, ?, 'Sarah Jenkins', 'sarah.jenkins.candidate@outlook.com', 'Senior Backend Engineer', ?, '/storage/resumes/sarah_jenkins_cv.pdf')
            """, (cand_1_id, email_1_id, demo_user_id, json.dumps(["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"])))

            email_2_id = "e2000000-0000-0000-0000-000000000002"
            cat_2_id = "a2000000-0000-0000-0000-000000000002"

            cursor.execute("""
            INSERT INTO emails (id, user_id, provider, gmail_message_id, gmail_thread_id, sender_email, sender_name, subject, body_text, received_at, has_attachment, is_processed)
            VALUES (?, ?, 'gmail', 'GMAIL_MSG_ALEX_123', 'GMAIL_THRD_ALEX_123', 'alex.chen@gmail.com', 'Alex Chen',
                    'Re: First Round Technical Interview Availability',
                    'Hi Team,\n\nThursday at 3:00 PM EST works perfectly for me. Looking forward to speaking with the engineering team!\n\nBest,\nAlex',
                    ?, 0, 1)
            """, (email_2_id, demo_user_id, datetime.now(timezone.utc).isoformat()))

            cursor.execute("""
            INSERT INTO email_categories (id, email_id, category, priority, confidence_score, resolved_at)
            VALUES (?, ?, 'Interview Scheduling', 'Medium', 0.95, datetime('now'))
            """, (cat_2_id, email_2_id))

            conn.commit()
        except Exception:
            pass


_adapter_instance: Optional[LocalDatabaseAdapter] = None


def get_local_db_adapter() -> LocalDatabaseAdapter:
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LocalDatabaseAdapter()
    return _adapter_instance
