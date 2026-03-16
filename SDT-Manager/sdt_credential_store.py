# File: sdt_credential_store.py
"""
SQLite-backed credential store for SDT authentication data.
Stores client credentials and access tokens mapped to SDT hex identifiers.

Each row represents one component (SDT, IDS-SDT connector, or Watchtower).
Components that share credentials with a parent SDT carry that parent's
identifier in the `linked_sdt_id` column. The SDT itself has linked_sdt_id=NULL.

Schema
------
sdt_id          - Primary key. Hex identifier of the component.
client_id       - OAuth2 client_id (shared across linked components).
client_secret   - OAuth2 client_secret (shared across linked components).
access_token    - OAuth2 access token (shared across linked components).
token_scope     - OAuth2 scope string.
linked_sdt_id   - NULL for the SDT itself; set to the parent SDT's sdt_id
                  for IDS-SDT connectors and Watchtower instances.
component_type  - Human-readable label: 'sdt', 'ids_connector', 'watchtower'.
status          - Lifecycle status: pending -> registered -> issued.
created_at      - Unix timestamp of row creation.
updated_at      - Unix timestamp of last update.
"""

import sqlite3
import logging
import threading
import time
from typing import Optional, Dict, List

LOGGER = logging.getLogger(__name__)

DB_PATH = "sdt_credentials.db"

# Valid component type labels
COMPONENT_SDT           = "sdt"
COMPONENT_IDS_CONNECTOR = "ids_connector"
COMPONENT_WATCHTOWER    = "watchtower"


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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new connection for the current thread."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Create the credentials table if it does not exist, and migrate
        existing databases that are missing the new columns."""
        with self._lock:
            conn = self._get_connection()
            try:
                # Create table with full schema (new installations)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sdt_credentials (
                        sdt_id          TEXT PRIMARY KEY,
                        client_id       TEXT,
                        client_secret   TEXT,
                        access_token    TEXT,
                        token_scope     TEXT,
                        linked_sdt_id   TEXT,
                        component_type  TEXT DEFAULT 'sdt',
                        status          TEXT DEFAULT 'pending',
                        created_at      REAL,
                        updated_at      REAL
                    )
                """)

                # Migration: add columns to existing databases that lack them
                existing_cols = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(sdt_credentials)")
                }
                if "linked_sdt_id" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE sdt_credentials ADD COLUMN linked_sdt_id TEXT"
                    )
                    LOGGER.info("Migrated sdt_credentials: added linked_sdt_id column")

                if "component_type" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE sdt_credentials "
                        "ADD COLUMN component_type TEXT DEFAULT 'sdt'"
                    )
                    LOGGER.info("Migrated sdt_credentials: added component_type column")

                conn.commit()
                LOGGER.info("Credential store database initialized")
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # CRUD — primary operations
    # ------------------------------------------------------------------

    def store_credentials(
        self,
        sdt_id: str,
        client_id: str,
        client_secret: str,
        token_scope: str = "",
        linked_sdt_id: Optional[str] = None,
        component_type: str = COMPONENT_SDT,
    ) -> bool:
        """
        Store client credentials for a component after wallet registration.

        For the SDT itself, leave linked_sdt_id as None.
        For IDS-SDT connectors and Watchtower instances, pass the parent
        SDT's identifier as linked_sdt_id so the relationship is tracked.

        Args:
            sdt_id:         Hex identifier of the component.
            client_id:      OAuth2 client_id from wallet controller.
            client_secret:  OAuth2 client_secret from wallet controller.
            token_scope:    Requested OAuth scope.
            linked_sdt_id:  Parent SDT identifier (None for the SDT itself).
            component_type: One of 'sdt', 'ids_connector', 'watchtower'.

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
                         linked_sdt_id, component_type,
                         status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'registered', ?, ?)
                    ON CONFLICT(sdt_id) DO UPDATE SET
                        client_id      = excluded.client_id,
                        client_secret  = excluded.client_secret,
                        token_scope    = excluded.token_scope,
                        linked_sdt_id  = excluded.linked_sdt_id,
                        component_type = excluded.component_type,
                        status         = 'registered',
                        updated_at     = excluded.updated_at
                """, (
                    sdt_id, client_id, client_secret, token_scope,
                    linked_sdt_id, component_type,
                    now, now,
                ))
                conn.commit()
                LOGGER.info(
                    f"Stored credentials for {component_type} {sdt_id}"
                    + (f" (linked to SDT {linked_sdt_id})" if linked_sdt_id else "")
                )
                return True
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to store credentials for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    def store_access_token(self, sdt_id: str, access_token: str) -> bool:
        """
        Store (or update) the access token for a component.

        Args:
            sdt_id:       Hex identifier of the component.
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
                    LOGGER.info(f"Stored access token for component {sdt_id}")
                    return True
                else:
                    LOGGER.warning(f"No credential row found for component {sdt_id}")
                    return False
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to store token for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    def get_credentials(self, sdt_id: str) -> Optional[Dict]:
        """
        Retrieve all stored credential data for a component.

        Args:
            sdt_id: Hex identifier of the component.

        Returns:
            Dictionary with all credential fields, or None if not found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM sdt_credentials WHERE sdt_id = ?",
                    (sdt_id,)
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_access_token(self, sdt_id: str) -> Optional[str]:
        """
        Retrieve only the access token for a component.

        Args:
            sdt_id: Hex identifier of the component.

        Returns:
            The access token string, or None.
        """
        creds = self.get_credentials(sdt_id)
        return creds.get("access_token") if creds else None

    def delete_credentials(self, sdt_id: str) -> bool:
        """
        Remove credential data for a single component by its identifier.

        Args:
            sdt_id: Hex identifier of the component.

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
                    LOGGER.info(f"Deleted credentials for component {sdt_id}")
                    return True
                else:
                    LOGGER.warning(f"No credentials found for component {sdt_id}")
                    return False
            except sqlite3.Error as e:
                LOGGER.error(f"Failed to delete credentials for {sdt_id}: {e}")
                return False
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Linked-component operations
    # ------------------------------------------------------------------

    def get_linked_components(self, sdt_id: str) -> List[Dict]:
        """
        Retrieve all components whose credentials are linked to a parent SDT.

        This covers IDS-SDT connector and Watchtower instances that share
        the same client_id / client_secret / access_token as the given SDT.

        Args:
            sdt_id: Hex identifier of the parent SDT.

        Returns:
            List of credential dictionaries for all linked components.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM sdt_credentials WHERE linked_sdt_id = ?",
                    (sdt_id,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def delete_linked_credentials(self, sdt_id: str) -> int:
        """
        Remove credentials for all components linked to a parent SDT.

        Call this during SDT deletion to clean up IDS-SDT connector and
        Watchtower credential rows without needing to know their identifiers.

        Args:
            sdt_id: Hex identifier of the parent SDT.

        Returns:
            Number of rows deleted (0 if no linked components were found).
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "DELETE FROM sdt_credentials WHERE linked_sdt_id = ?",
                    (sdt_id,)
                ).rowcount
                conn.commit()
                if rows:
                    LOGGER.info(
                        f"Deleted credentials for {rows} component(s) "
                        f"linked to SDT {sdt_id}"
                    )
                else:
                    LOGGER.info(f"No linked components found for SDT {sdt_id}")
                return rows
            except sqlite3.Error as e:
                LOGGER.error(
                    f"Failed to delete linked credentials for SDT {sdt_id}: {e}"
                )
                return 0
            finally:
                conn.close()

    def delete_all_for_sdt(self, sdt_id: str) -> bool:
        """
        Remove ALL credential rows associated with an SDT deployment:
        the SDT's own row plus all linked component rows (IDS-SDT, Watchtower).

        This is the preferred method to call during full SDT teardown.

        Args:
            sdt_id: Hex identifier of the parent SDT.

        Returns:
            True if at least the SDT's own row was deleted.
        """
        linked_deleted = self.delete_linked_credentials(sdt_id)
        sdt_deleted    = self.delete_credentials(sdt_id)

        LOGGER.info(
            f"Full credential cleanup for SDT {sdt_id}: "
            f"SDT row={'deleted' if sdt_deleted else 'not found'}, "
            f"{linked_deleted} linked component row(s) deleted"
        )
        return sdt_deleted

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_all(self) -> List[Dict]:
        """
        List all stored credential records (access tokens and secrets redacted).

        Returns:
            List of credential dictionaries with sensitive fields omitted.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT sdt_id, client_id, token_scope, linked_sdt_id, "
                    "component_type, status, created_at, updated_at "
                    "FROM sdt_credentials"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def list_by_component_type(self, component_type: str) -> List[Dict]:
        """
        List all credential records for a specific component type.

        Args:
            component_type: One of 'sdt', 'ids_connector', 'watchtower'.

        Returns:
            List of credential dictionaries with sensitive fields omitted.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT sdt_id, client_id, token_scope, linked_sdt_id, "
                    "component_type, status, created_at, updated_at "
                    "FROM sdt_credentials WHERE component_type = ?",
                    (component_type,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()