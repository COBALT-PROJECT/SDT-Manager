# File: sdt_authentication_manager.py
"""
SDT Authentication Manager
---------------------------
Handles wallet-driven registration, SSI credential polling, and OAuth2 token
acquisition for Software-Defined Twins.  Designed to be called by
SDT_ManagerCore as part of the deploy / delete lifecycle — not as a
standalone CLI.

Flow (called during SDT deployment):
  1. Register SDT via wallet controller  ->  POST /wallet/digital-twins
  2. Poll AM until status == "issued"    ->  GET  /api/digital-twins/<sdt_id>
  3. Fetch OAuth2 access token           ->  POST /oauth/token (Basic Auth)
  4. Store credentials in SQLite via SDTCredentialStore
     - One row for the SDT itself        (component_type='sdt')
     - One row for the IDS-SDT connector (component_type='ids_connector',
                                          linked_sdt_id=sdt_id)
     - One row for the Watchtower        (component_type='watchtower',
                                          linked_sdt_id=sdt_id)

Flow (called during SDT deletion):
  1. Delete twin via wallet controller   ->  DELETE /wallet/digital-twins/<sdt_id>
  2. Remove ALL credential rows for this SDT (own row + linked components)
"""

import os
import time
import logging
import requests
from typing import Optional, Dict, Tuple

from sdt_credential_store import (
    SDTCredentialStore,
    COMPONENT_SDT,
    COMPONENT_IDS_CONNECTOR,
    # COMPONENT_WATCHTOWER,  # Watchtower workflow disabled
)

LOGGER = logging.getLogger(__name__)


class SDTAuthenticationManager:
    """Manages registration, token acquisition, and deletion for SDTs."""

    def __init__(self, credential_store: SDTCredentialStore,
                 am_base_url: Optional[str] = None,
                 wallet_controller_url: Optional[str] = None,
                 wallet_controller_key: Optional[str] = None,
                 digital_twin_api_key: Optional[str] = None,
                 twin_owner: str = "sdt-manager",
                 twin_scope: str = "digital_twin profile",
                 poll_interval: int = 5,
                 poll_timeout: int = 180,
                 verify_ssl: bool = False):
        """
        Initialize the SDT Authentication Manager.

        All URL / key parameters fall back to environment variables when not
        provided explicitly.

        Args:
            credential_store:      Shared SDTCredentialStore instance.
            am_base_url:           Base URL for the Authentication Manager.
            wallet_controller_url: URL for the Wallet Controller.
            wallet_controller_key: API key for the Wallet Controller.
            digital_twin_api_key:  API key for the Digital Twin AM endpoint.
            twin_owner:            Default owner label for registered twins.
            twin_scope:            Default OAuth scope for twins.
            poll_interval:         Seconds between AM status polls.
            poll_timeout:          Max seconds to wait for credential issuance.
            verify_ssl:            Whether to verify TLS certificates.
        """
        self.credential_store = credential_store

        # Configuration from args -> env -> defaults
        self.am_base_url = (
            am_base_url
            or os.environ.get("AM_BASE_URL", "http://iam.cobalt.local:3100")
        )
        self.wallet_controller_url = (
            wallet_controller_url
            or os.environ.get("WALLET_CONTROLLER_URL", "http://iam.cobalt.local:3200")
        )
        self.wallet_controller_key = (
            wallet_controller_key
            or os.environ.get("WALLET_CONTROLLER_KEY", "atestkeytoremotelycontrolthewallet")
        )
        self.digital_twin_api_key = (
            digital_twin_api_key
            or os.environ.get("DIGITAL_TWIN_API_KEY", "IvPBXYOesvseJQ3u0mwLPFgvN3Ugy2-P35aW2WlSUvQ")
        )
        self.twin_owner = twin_owner
        self.twin_scope = twin_scope
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.verify_ssl = verify_ssl

        LOGGER.info(
            "SDT Authentication Manager initialized "
            f"(AM={self.am_base_url}, Wallet={self.wallet_controller_url})"
        )

    # ------------------------------------------------------------------
    # Public API — called by SDT_ManagerCore / SDT_Manager_Interface
    # ------------------------------------------------------------------

    def register_and_get_token(
        self,
        sdt_id: str,
        twin_name: Optional[str] = None,
        ids_connector_id: Optional[str] = None,
        watchtower_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Full registration + token flow for a newly deployed SDT.

        After obtaining the token the method stores credentials in SQLite for:
          - The SDT itself                          (component_type='sdt')
          - The IDS-SDT connector (if provided)     (component_type='ids_connector')
          - The Watchtower instance (if provided)   (component_type='watchtower')

        All three rows carry the same client_id, client_secret, and access_token
        because they operate under a single wallet registration. The IDS-SDT and
        Watchtower rows are linked back to the SDT via linked_sdt_id so they can
        be queried and cleaned up by SDT identifier alone.

        Args:
            sdt_id:           Hexadecimal identifier of the SDT.
            twin_name:        Human-readable name (defaults to "SDT-<sdt_id>").
            ids_connector_id: Hex identifier of the IDS-SDT connector (may be None).
            watchtower_id:    Hex identifier of the Watchtower instance (may be None).

        Returns:
            (success: bool, access_token: str | None)
        """
        twin_name = twin_name or f"SDT-{sdt_id}"
        LOGGER.info(f"Starting authentication flow for SDT {sdt_id}")

        # Step 1 — Register via wallet controller
        client_id, client_secret = self._register_twin(sdt_id, twin_name)
        if not client_id or not client_secret:
            LOGGER.error(f"Registration failed for SDT {sdt_id}")
            return False, None

        # Step 2 — Persist SDT client credentials in SQLite
        self.credential_store.store_credentials(
            sdt_id=sdt_id,
            client_id=client_id,
            client_secret=client_secret,
            token_scope=self.twin_scope,
            linked_sdt_id=None,
            component_type=COMPONENT_SDT,
        )

        # Step 3 — Poll AM until credential is issued
        if not self._poll_until_issued(sdt_id):
            LOGGER.error(f"Credential issuance timed out for SDT {sdt_id}")
            return False, None

        # Step 4 — Fetch OAuth2 token
        access_token = self._fetch_token(client_id, client_secret)
        if not access_token:
            LOGGER.error(f"Token acquisition failed for SDT {sdt_id}")
            return False, None

        # Step 5 — Store the token for the SDT
        self.credential_store.store_access_token(sdt_id, access_token)

        # Step 6 — Store credentials for the IDS-SDT connector (if present)
        if ids_connector_id:
            self.credential_store.store_credentials(
                sdt_id=ids_connector_id,
                client_id=client_id,
                client_secret=client_secret,
                token_scope=self.twin_scope,
                linked_sdt_id=sdt_id,
                component_type=COMPONENT_IDS_CONNECTOR,
            )
            self.credential_store.store_access_token(ids_connector_id, access_token)
            LOGGER.info(
                f"Stored credentials for IDS-SDT connector {ids_connector_id} "
                f"(linked to SDT {sdt_id})"
            )

        # Step 7 — Watchtower credential storage disabled
        # if watchtower_id:
        #     self.credential_store.store_credentials(
        #         sdt_id=watchtower_id,
        #         client_id=client_id,
        #         client_secret=client_secret,
        #         token_scope=self.twin_scope,
        #         linked_sdt_id=sdt_id,
        #         component_type=COMPONENT_WATCHTOWER,
        #     )
        #     self.credential_store.store_access_token(watchtower_id, access_token)
        #     LOGGER.info(
        #         f"Stored credentials for Watchtower {watchtower_id} "
        #         f"(linked to SDT {sdt_id})"
        #     )

        LOGGER.info(
            f"Authentication flow completed for SDT {sdt_id} — "
            f"IDS connector: {ids_connector_id or 'none'}"
            # f", Watchtower: {watchtower_id or 'none'}"
        )
        return True, access_token

    def delete_twin_auth(self, sdt_id: str) -> bool:
        """
        Delete twin registration from wallet controller and remove ALL
        credential rows for this SDT deployment (own row + IDS-SDT connector
        + Watchtower) from the local store.

        Args:
            sdt_id: Hexadecimal identifier of the SDT.

        Returns:
            True if cleanup succeeded (or twin was already gone).
        """
        LOGGER.info(f"Deleting authentication data for SDT {sdt_id}")

        # Delete from wallet controller
        wallet_ok = self._delete_from_wallet(sdt_id)

        # Remove the SDT row plus all linked component rows from SQLite
        store_ok = self.credential_store.delete_all_for_sdt(sdt_id)

        if wallet_ok and store_ok:
            LOGGER.info(f"Authentication data fully cleaned for SDT {sdt_id}")
        elif wallet_ok:
            LOGGER.warning(f"Wallet cleanup OK but no local credentials for SDT {sdt_id}")
        elif store_ok:
            LOGGER.warning(f"Local cleanup OK but wallet deletion failed for SDT {sdt_id}")
        else:
            LOGGER.error(f"Both wallet and local cleanup failed for SDT {sdt_id}")

        return wallet_ok or store_ok

    def get_token_for_sdt(self, sdt_id: str) -> Optional[str]:
        """
        Retrieve the stored access token for an SDT or any linked component.

        Args:
            sdt_id: Hexadecimal identifier of the component.

        Returns:
            The access token string, or None.
        """
        return self.credential_store.get_access_token(sdt_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_twin(self, sdt_id: str, twin_name: str
                       ) -> Tuple[Optional[str], Optional[str]]:
        """
        Register the SDT with the wallet controller.

        Returns:
            (client_id, client_secret) or (None, None) on failure.
        """
        url = f"{self.wallet_controller_url}/wallet/digital-twins"
        payload = {
            "twin_id": sdt_id,
            "name": twin_name,
            "owner": self.twin_owner,
            "scope": self.twin_scope,
        }
        headers = {
            "X-Api-Key": self.wallet_controller_key,
            "Content-Type": "application/json",
        }

        try:
            LOGGER.info(f"Registering SDT {sdt_id} with wallet controller")
            response = requests.post(
                url, json=payload, headers=headers,
                timeout=30, verify=self.verify_ssl,
            )
            response.raise_for_status()

            data = response.json()
            registration = data.get("registration", data)
            client_info = registration.get("client", {})
            client_id = client_info.get("client_id")
            client_secret = client_info.get("client_secret")

            if not client_id or not client_secret:
                LOGGER.error(
                    f"Wallet response missing client credentials: {data}"
                )
                return None, None

            LOGGER.info(
                f"SDT {sdt_id} registered — client_id={client_id}"
            )
            return client_id, client_secret

        except requests.exceptions.HTTPError as e:
            LOGGER.error(
                f"Wallet registration HTTP {e.response.status_code}: "
                f"{e.response.text}"
            )
        except requests.exceptions.RequestException as e:
            LOGGER.error(f"Wallet registration request failed: {e}")

        return None, None

    def _poll_until_issued(self, sdt_id: str) -> bool:
        """
        Poll the AM until the twin credential status is 'issued'.

        Returns:
            True if issued within the timeout.
        """
        url = f"{self.am_base_url}/api/digital-twins/{sdt_id}"
        headers = {"X-Api-Key": self.digital_twin_api_key}
        start = time.time()
        attempt = 0

        LOGGER.info(f"Polling AM for credential issuance (SDT {sdt_id})")

        while time.time() - start < self.poll_timeout:
            attempt += 1
            try:
                response = requests.get(
                    url, headers=headers,
                    timeout=10, verify=self.verify_ssl,
                )
                response.raise_for_status()
                status = response.json().get("status", "unknown")
                elapsed = int(time.time() - start)

                LOGGER.info(
                    f"SDT {sdt_id} credential status: {status} "
                    f"(attempt {attempt}, {elapsed}s elapsed)"
                )

                if status == "issued":
                    LOGGER.info(f"Credential issued for SDT {sdt_id}")
                    return True
                if status == "failed":
                    LOGGER.error(f"Credential issuance failed for SDT {sdt_id}")
                    return False

            except requests.exceptions.RequestException as e:
                LOGGER.warning(f"Poll attempt {attempt} failed: {e}")

            # Simple back-off: after 10 attempts double the interval
            interval = self.poll_interval if attempt <= 10 else self.poll_interval * 2
            time.sleep(interval)

        LOGGER.error(
            f"Credential polling timed out for SDT {sdt_id} "
            f"after {self.poll_timeout}s"
        )
        return False

    def _fetch_token(self, client_id: str, client_secret: str
                     ) -> Optional[str]:
        """
        Fetch an OAuth2 access token using client credentials.

        Returns:
            The access token string, or None.
        """
        url = f"{self.am_base_url}/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "scope": self.twin_scope,
        }

        try:
            LOGGER.info("Requesting OAuth2 token from AM")
            response = requests.post(
                url,
                auth=(client_id, client_secret),
                data=data,
                timeout=10,
                verify=self.verify_ssl,
            )
            response.raise_for_status()

            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                LOGGER.error("AM response did not contain an access_token")
                return None

            LOGGER.info("OAuth2 token acquired successfully")
            return access_token

        except requests.exceptions.RequestException as e:
            LOGGER.error(f"Token request failed: {e}")
            return None

    def _delete_from_wallet(self, sdt_id: str) -> bool:
        """
        Delete a twin registration from the wallet controller.

        Returns:
            True if deleted or already gone (404).
        """
        url = f"{self.wallet_controller_url}/wallet/digital-twins/{sdt_id}"
        headers = {"X-Api-Key": self.wallet_controller_key}

        try:
            LOGGER.info(f"Deleting SDT {sdt_id} from wallet controller")
            response = requests.delete(
                url, headers=headers,
                timeout=15, verify=self.verify_ssl,
            )

            if response.status_code == 404:
                LOGGER.warning(
                    f"SDT {sdt_id} not found in wallet — already deleted"
                )
                return True

            if response.status_code == 200:
                LOGGER.info(f"SDT {sdt_id} deleted from wallet controller")
                return True

            LOGGER.error(
                f"Wallet deletion failed — HTTP {response.status_code}: "
                f"{response.text}"
            )
            return False

        except requests.exceptions.RequestException as e:
            LOGGER.error(f"Wallet deletion request failed: {e}")
            return False