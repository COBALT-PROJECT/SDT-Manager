# File: sdt_credential_store.py
"""
SQLite-backed credential store for SDT authentication data.
Stores client credentials and access tokens mapped to SDT hex identifiers.
"""

import sqlite3
import json
import logging
import threading
import time
from typing import Optional, Dict, List

LOGGER = logging.getLogger(__name__)

DB_PATH = "sdt_credentials.db"


class SDTCredentialStore:
    """Thread-safe SQLite store for SDT credentials and access tokens."""

    def __init__(self, db_path: str = DB_PATH):
        """
        Initialize the credential store.

        Args:
            db_path (str): Path to the SQLite database file.
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        LOGGER.info(f"SDT Credential Store initialized (db={self.db_path})")

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new connection for the current thread."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Create the credentials table if it does not exist."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sdt_credentials (
                        sdt_id          TEXT PRIMARY KEY,
                        client_id       TEXT,
                        client_secret   TEXT,
                        access_token    TEXT,
                        token_scope     TEXT,
                        status          TEXT DEFAULT 'pending',
                        created_at      REAL,
                        updated_at      REAL
                    )
                """)
                conn.commit()
                LOGGER.info("Credential store database initialized")
            finally:
                conn.close()

    # ---- CRUD operations ----

    def store_credentials(self, sdt_id: str, client_id: str,
                          client_secret: str, token_scope: str = "") -> bool:
        """
        Store client credentials after wallet registration.

        Args:
            sdt_id:        Hexadecimal identifier of the SDT.
            client_id:     OAuth2 client_id from wallet controller.
            client_secret: OAuth2 client_secret from wallet controller.
            token_scope:   Requested OAuth scope.

        Returns:
            True on success.
        """
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO sdt_credentials
                        (sdt_id, client_id, client_secret, token_scope,
                         status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'registered', ?, ?)
                    ON CONFLICT(sdt_id) DO UPDATE SET
                        client_id     = excluded.client_id,
                        client_secret = excluded.client_secret,
                        token_scope   = excluded.token_scope,
                        status        = 'registered',
                        updated_at    = excluded.updated_at
                """, (sdt_id, client_id, client_secret, token_scope, now, now))
                conn.commit()
                LOGGER.info(f"Stored credentials for SDT {sdt_id}")
                return True
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to store credentials for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    def store_access_token(self, sdt_id: str, access_token: str) -> bool:
        """
        Store (or update) the access token for an SDT.

        Args:
            sdt_id:       Hexadecimal identifier of the SDT.
            access_token: OAuth2 access token.

        Returns:
            True on success.
        """
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    UPDATE sdt_credentials
                       SET access_token = ?, status = 'issued', updated_at = ?
                     WHERE sdt_id = ?
                """, (access_token, now, sdt_id)).rowcount
                conn.commit()
                if rows:
                    LOGGER.info(f"Stored access token for SDT {sdt_id}")
                    return True
                else:
                    LOGGER.warning(f"No credential row found for SDT {sdt_id}")
                    return False
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to store token for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    def get_credentials(self, sdt_id: str) -> Optional[Dict]:
        """
        Retrieve all stored credential data for an SDT.

        Args:
            sdt_id: Hexadecimal identifier of the SDT.

        Returns:
            Dictionary with credential fields, or None.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM sdt_credentials WHERE sdt_id = ?",
                    (sdt_id,)
                ).fetchone()
                if row:
                    return dict(row)
                return None
            finally:
                conn.close()

    def get_access_token(self, sdt_id: str) -> Optional[str]:
        """
        Retrieve only the access token for an SDT.

        Args:
            sdt_id: Hexadecimal identifier of the SDT.

        Returns:
            The access token string, or None.
        """
        creds = self.get_credentials(sdt_id)
        if creds:
            return creds.get("access_token")
        return None

    def delete_credentials(self, sdt_id: str) -> bool:
        """
        Remove all credential data for an SDT.

        Args:
            sdt_id: Hexadecimal identifier of the SDT.

        Returns:
            True if a row was deleted.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "DELETE FROM sdt_credentials WHERE sdt_id = ?",
                    (sdt_id,)
                ).rowcount
                conn.commit()
                if rows:
                    LOGGER.info(f"Deleted credentials for SDT {sdt_id}")
                    return True
                else:
                    LOGGER.warning(f"No credentials found for SDT {sdt_id}")
                    return False
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to delete credentials for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    def list_all(self) -> List[Dict]:
        """
        List all stored SDT credentials (tokens redacted).

        Returns:
            List of credential dictionaries.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT sdt_id, client_id, token_scope, status, "
                    "created_at, updated_at FROM sdt_credentials"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()