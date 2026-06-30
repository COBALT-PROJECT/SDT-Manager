# File: sdt_manager_interface.py

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import logging
import json
import time
import threading
import os

LOGGER = logging.getLogger(__name__)

# Pydantic models defined outside the class to avoid linting warnings
class DeploymentResponse(BaseModel):
    """Response model for deployment operations"""
    success: bool
    message: str
    pod_name: Optional[str] = None
    identifier: Optional[str] = None
    # watchtower_id: Optional[str] = None  # Watchtower workflow disabled
    ids_connector_id: Optional[str] = None
    auth_status: Optional[str] = None

class ConnectorResponse(BaseModel):
    """Response model for connector operations"""
    success: bool
    message: str
    deployment_name: Optional[str] = None
    connector_id: Optional[str] = None

class DeletionRequest(BaseModel):
    """Request model for deletion operations"""
    identifier: str


# SDT Adapter API request/response models
class FileConfig(BaseModel):
    path: str
    type: str
    thing_id: Optional[str] = None

class MultipleFilesRequest(BaseModel):
    file_configs: List[FileConfig]


class SDT_Manager_Interface:
    """North Bound Interface for SDT Manager using FastAPI, it faces CCM Manager"""
    
    def __init__(self, manager_core):
        """Initialize with reference to the SDT Manager Core"""
        self.manager_core = manager_core
        self.sdt_to_ids_map = {}        # Maps SDT identifier -> IDS-SDT connector_id
        # self.sdt_to_watchtower_map = {} # Watchtower workflow disabled
        self.app = FastAPI(
            title="SDT Deployment API",
            description="API for managing SDT deployments and IDS connectors in Kubernetes",
            version="2.0.0"
        )
        self._setup_routes()
        LOGGER.info("SDT Manager Interface initialized")

    def _get_v2_adapter(self):
        """Return the configured adapter and fail fast if a v1-only adapter is wired in."""
        adapter = self.manager_core.sdt_adapter
        missing = [
            method_name
            for method_name in ("validate_and_transform", "validate_payload")
            if not hasattr(adapter, method_name)
        ]
        if missing:
            raise RuntimeError(
                "SDT Manager requires DTModelAdapterV2; missing methods: "
                + ", ".join(missing)
            )
        return adapter
    
    def _run_auth_flow_async(self, sdt_identifier: str, ids_connector_id: Optional[str]):
        """
        Run the wallet registration and token acquisition in a background
        thread so the deploy endpoint can return quickly.

        Once the token is obtained it is:
          1. Stored in the credential store for the SDT (already done by
             register_and_get_token).
          2. Distributed via HTTP POST to the SDT and IDS-SDT connector.
          3. Also stored in the credential store for the IDS-SDT connector,
             carrying linked_sdt_id = sdt_identifier.

        Args:
            sdt_identifier:   Hex identifier of the deployed SDT.
            ids_connector_id: Hex identifier of the IDS-SDT connector (may be None).
        """
        LOGGER.info(f"Background auth flow started for SDT {sdt_identifier}")

        try:
            # Pass ids_connector_id so register_and_get_token stores credential
            # rows for the SDT and IDS-SDT connector in a single call.
            # No separate store_component_credentials() call is needed here.
            success, access_token = (
                self.manager_core.auth_manager.register_and_get_token(
                    sdt_id=sdt_identifier,
                    ids_connector_id=ids_connector_id,
                    # watchtower_id=watchtower_id,  # Watchtower workflow disabled
                )
            )

            if not success or not access_token:
                LOGGER.error(
                    f"Auth flow failed for SDT {sdt_identifier} — "
                    "components will run without token"
                )
                return

            # Credentials already stored in SQLite by register_and_get_token.
            # _distribute_token handles HTTP delivery only.
            self._distribute_token(sdt_identifier, access_token, ids_connector_id)

        except Exception as e:
            LOGGER.error(f"Auth flow exception for SDT {sdt_identifier}: {e}")

    def _distribute_token(self, sdt_identifier: str, access_token: str,
                          ids_connector_id: Optional[str]):
        """
        Send the full credentials JSON payload to the running SDT and IDS-SDT
        components via HTTP POST to their auth endpoints.

        Credential storage for all three components is already handled by
        register_and_get_token(). This method only performs HTTP delivery.

        Args:
            sdt_identifier:   Hex identifier of the SDT.
            access_token:     The OAuth2 access token to distribute.
            ids_connector_id: Connector identifier (may be None).
        """
        LOGGER.info(f"Distributing credentials to components for SDT {sdt_identifier}")

        # Build the full credentials payload from the already-stored SDT row
        creds = self.manager_core.credential_store.get_credentials(sdt_identifier)
        auth_payload = {
            "sdt_id": sdt_identifier,
            "client_id": creds.get("client_id") if creds else None,
            "client_secret": creds.get("client_secret") if creds else None,
            "access_token": access_token,
            "components": {
                "sdt": sdt_identifier,
                "ids_connector": ids_connector_id,
                # "watchtower": watchtower_id,  # Watchtower workflow disabled
            },
        }

        # --- SDT service ---
        sdt_service_name = self._get_sdt_service_name()
        sdt_port = int(os.environ.get("SDT_AUTH_PORT", "8080"))
        if sdt_service_name:
            sdt_token_sent = self._send_token_to_service(
                sdt_service_name, sdt_port, auth_payload, "SDT",
                endpoint="/api/SDT/auth/token"
            )
            if sdt_token_sent:
                self._send_template_to_sdt(sdt_service_name, sdt_port)
        else:
            LOGGER.warning("Could not resolve SDT service — skipping token delivery to SDT")

        # --- IDS-SDT connector service ---
        if ids_connector_id:
            ids_service_name = self._get_ids_sdt_service_name()
            ids_port = int(os.environ.get("IDS_SDT_AUTH_PORT", "8004"))
            if ids_service_name:
                self._send_token_to_service(
                    ids_service_name, ids_port, auth_payload, "IDS-SDT",
                    endpoint="/api/IDSconnector/SDT/configauth"
                )
            else:
                LOGGER.warning("Could not resolve IDS-SDT service — skipping token delivery")

        # --- Watchtower service disabled ---
        # if watchtower_id:
        #     wt_service_name = "watchtower-service"
        #     wt_port = int(os.environ.get("WATCHTOWER_AUTH_PORT", "8080"))
        #     self._send_token_to_service(
        #         wt_service_name, wt_port, auth_payload, "Watchtower",
        #         endpoint="/api/watchtower/configauth"
        #     )

        LOGGER.info(f"Token distribution completed for SDT {sdt_identifier}")

    def _send_token_to_service(self, service_name: str, port: int,
                                auth_payload: dict, component_label: str,
                                endpoint: str = "/auth/token") -> bool:
        """
        POST the credentials JSON payload to a component's auth endpoint
        using its Kubernetes service ClusterIP.

        Args:
            service_name:    Kubernetes service name.
            port:            Port the component listens on.
            auth_payload:    The full credentials dict to send.
            component_label: Human-readable label for logging.
            endpoint:        HTTP path to POST to (default: /auth/token).

        Returns:
            True when the target responds with a success status.
        """
        import requests as req

        cluster_ip = self._get_service_cluster_ip(service_name)
        if not cluster_ip:
            LOGGER.error(
                f"Cannot resolve ClusterIP for {service_name} — "
                f"token not delivered to {component_label}"
            )
            return False

        url = f"http://{cluster_ip}:{port}{endpoint}"
        LOGGER.info(f"Sending credentials to {component_label} at {url}")

        try:
            response = req.post(
                url,
                json=auth_payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if response.status_code in (200, 201, 204):
                LOGGER.info(
                    f"Credentials delivered to {component_label} ({service_name}) "
                    f"— HTTP {response.status_code}"
                )
                return True
            else:
                LOGGER.error(
                    f"Token delivery to {component_label} ({service_name}) failed — "
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
        except req.exceptions.ConnectionError as e:
            LOGGER.error(f"Connection to {component_label} ({url}) failed: {e}")
        except req.exceptions.Timeout:
            LOGGER.error(f"Timeout sending credentials to {component_label} ({url})")
        except req.exceptions.RequestException as e:
            LOGGER.error(f"Error sending credentials to {component_label} ({url}): {e}")
        return False

    def _send_template_to_sdt(self, service_name: str, port: int):
        """Upload the manager template.json to the SDT template endpoint."""
        import requests as req

        cluster_ip = self._get_service_cluster_ip(service_name)
        if not cluster_ip:
            LOGGER.error(
                f"Cannot resolve ClusterIP for {service_name} — template not delivered to SDT"
            )
            return False

        template_path = os.environ.get(
            "SDT_TEMPLATE_PATH",
            os.path.join(os.path.dirname(__file__), "template.json"),
        )
        if not os.path.isfile(template_path):
            LOGGER.error(f"Template file not found — cannot deliver to SDT: {template_path}")
            return False

        url = f"http://{cluster_ip}:{port}/api/SDT/upload-template"
        LOGGER.info(f"Sending template.json to SDT at {url}")

        try:
            with open(template_path, "rb") as template_file:
                response = req.post(
                    url,
                    files={
                        "file": ("template.json", template_file, "application/json")
                    },
                    timeout=15,
                )

            if response.status_code in (200, 201, 204):
                LOGGER.info(
                    f"Template delivered to SDT ({service_name}) — HTTP {response.status_code}"
                )
                return True

            LOGGER.error(
                f"Template delivery to SDT ({service_name}) failed — "
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
        except req.exceptions.ConnectionError as e:
            LOGGER.error(f"Connection to SDT template endpoint ({url}) failed: {e}")
        except req.exceptions.Timeout:
            LOGGER.error(f"Timeout sending template to SDT ({url})")
        except req.exceptions.RequestException as e:
            LOGGER.error(f"Error sending template to SDT ({url}): {e}")
        return False

    def _get_service_cluster_ip(self, service_name: str) -> Optional[str]:
        """
        Resolve the ClusterIP of a Kubernetes service.

        Args:
            service_name: Name of the Kubernetes service.

        Returns:
            The ClusterIP string, or None if not found.
        """
        cmd = (
            f"kubectl get service {service_name} "
            f"-o jsonpath='{{.spec.clusterIP}}' --ignore-not-found=true"
        )
        cluster_ip = self.manager_core.lifecycle_manager.run_command(cmd)
        if cluster_ip and cluster_ip != "None":
            LOGGER.info(f"Resolved {service_name} ClusterIP: {cluster_ip}")
            return cluster_ip
        LOGGER.warning(f"Could not resolve ClusterIP for service {service_name}")
        return None

    def _get_sdt_service_name(self) -> Optional[str]:
        """
        Resolve the SDT Kubernetes service name.
        Looks up the known service name 'sdt-service' directly since the
        service metadata does not carry the app=sdt label (only the
        selector does).

        Returns:
            The service name string, or None.
        """
        cmd = "kubectl get service sdt-service -o jsonpath='{.metadata.name}' --ignore-not-found=true"
        return self.manager_core.lifecycle_manager.run_command(cmd)

    def _get_ids_sdt_service_name(self) -> Optional[str]:
        """
        Resolve the IDS-SDT connector Kubernetes service name.
        Tries the dedicated ids-connector-sdt-service first, falls back to tc-consumer.

        Returns:
            The service name string, or None.
        """
        cmd = "kubectl get service ids-connector-sdt-service -o jsonpath='{.metadata.name}' --ignore-not-found=true"
        result = self.manager_core.lifecycle_manager.run_command(cmd)
        if result:
            return result
        cmd = (
            "kubectl get services -l io.kompose.service=tc-consumer "
            "-o jsonpath='{.items[0].metadata.name}' --ignore-not-found=true"
        )
        return self.manager_core.lifecycle_manager.run_command(cmd)

    def _setup_routes(self):
        """Setup the API routes"""

        # ===== SDT DEPLOYMENT ROUTES =====

        @self.app.post(
            "/api/SDTM/digital-twin",
            response_model=DeploymentResponse,
            summary="Deploy an SDT instance",
            tags=["SDT deployment APIs"],
        )
        async def deploy_sdt():
            """
            Deploy an SDT pod and service, then automatically:
              1. Deploy IDS-SDT connector
              2. Register the SDT with the wallet controller (using its hex ID)
              3. Obtain an OAuth2 access token
              4. Store credentials in SQLite for the SDT, IDS-SDT connector,
                 (IDS rows carry linked_sdt_id)
              5. Distribute the token to SDT and IDS-SDT via HTTP
            """
            try:
                # --- 1. Deploy SDT pod + service ---
                pod_name, identifier = self.manager_core.lifecycle_manager.deploy()

                if not pod_name or not identifier:
                    raise HTTPException(
                        status_code=500,
                        detail="SDT deployment failed — no pod information available"
                    )

                LOGGER.info(f"SDT deployed successfully: {pod_name}, ID={identifier}")

                # --- 2. Deploy IDS-SDT connector ---
                ids_connector_id = None
                LOGGER.info("Deploying IDS-SDT connector...")
                ids_deployment_name, ids_connector_id = (
                    self.manager_core.connector_manager.deploy_connector("ids_sdt")
                )

                if ids_deployment_name and ids_connector_id:
                    LOGGER.info(
                        f"IDS-SDT connector deployed: {ids_deployment_name}, "
                        f"ID={ids_connector_id}"
                    )
                    self.sdt_to_ids_map[identifier] = ids_connector_id
                else:
                    LOGGER.warning(
                        "IDS-SDT connector deployment failed, SDT will run without connector"
                    )

                # --- 3. Watchtower workflow disabled ---
                # watchtower_id = None
                # wt_pod_name, watchtower_id = (
                #     self.manager_core.watchtower_manager.get_or_register_existing_watchtower()
                # )
                # if wt_pod_name and watchtower_id:
                #     LOGGER.info(
                #         f"Watchtower exists: {wt_pod_name} (ID: {watchtower_id}), "
                #         "skipping deployment"
                #     )
                # else:
                #     LOGGER.info("No existing Watchtower found, deploying...")
                #     wt_pod_name, watchtower_id = (
                #         self.manager_core.watchtower_manager.deploy_watchtower()
                #     )
                #     if wt_pod_name and watchtower_id:
                #         LOGGER.info(f"Watchtower deployed: {wt_pod_name}, ID={watchtower_id}")
                #     else:
                #         LOGGER.warning(
                #             "Watchtower deployment failed, SDT will run without monitoring"
                #         )
                # if watchtower_id:
                #     self.sdt_to_watchtower_map[identifier] = watchtower_id

                # --- 4. Start auth flow in background thread ---
                # register_and_get_token stores credentials for the SDT,
                # IDS connector in one call.
                # _distribute_token handles HTTP delivery only.
                auth_thread = threading.Thread(
                    target=self._run_auth_flow_async,
                    args=(identifier, ids_connector_id),
                    daemon=True,
                    name=f"auth-{identifier}",
                )
                auth_thread.start()
                LOGGER.info(f"Auth flow started in background for SDT {identifier}")

                return DeploymentResponse(
                    success=True,
                    message="SDT deployment successful — authentication in progress",
                    pod_name=pod_name,
                    identifier=identifier,
                    # watchtower_id=watchtower_id,  # Watchtower workflow disabled
                    ids_connector_id=ids_connector_id,
                    auth_status="in_progress",
                )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

        @self.app.delete(
            "/api/SDTM/digital-twin/{twinId}",
            response_model=DeploymentResponse,
            summary="Delete an SDT instance by using its identifier",
            tags=["SDT deployment APIs"],
        )
        async def delete_sdt(twinId: str):
            """
            Delete an SDT deployment by identifier.  Also:
              1. Delete associated IDS-SDT connector
              2. Delete twin registration from wallet controller
              3. Remove credentials for the SDT AND all linked components
                 (IDS-SDT connector) from SQLite in one transaction
            """
            try:
                # Verify the identifier exists in the pod map
                identifier_exists = any(
                    id_val == twinId
                    for id_val in self.manager_core.lifecycle_manager.pod_map.values()
                )

                if not identifier_exists:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No deployment found with identifier {twinId}"
                    )

                # --- 1. Delete the SDT deployment ---
                deletion_results = self.manager_core.lifecycle_manager.delete_deployment_by_id(
                    twinId
                )

                if not deletion_results.get(twinId, False):
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to delete SDT deployment with identifier {twinId}"
                    )

                LOGGER.info(f"SDT deleted successfully: {twinId}")

                # --- 2. Delete associated IDS-SDT connector ---
                ids_connector_id = self.sdt_to_ids_map.get(twinId)
                if ids_connector_id:
                    LOGGER.info(f"Deleting IDS-SDT connector: {ids_connector_id}")
                    self.manager_core.connector_manager.delete_connector(ids_connector_id)
                    del self.sdt_to_ids_map[twinId]
                    LOGGER.info(f"IDS-SDT connector deleted: {ids_connector_id}")

                # --- 3. Watchtower deletion disabled ---
                # watchtower_id = self.sdt_to_watchtower_map.get(twinId)
                # if watchtower_id:
                #     LOGGER.info(f"Deleting Watchtower: {watchtower_id}")
                #     self.manager_core.watchtower_manager.delete_watchtower_by_id(
                #         watchtower_id, cleanup_service=True
                #     )
                #     del self.sdt_to_watchtower_map[twinId]
                #     LOGGER.info(f"Watchtower deleted: {watchtower_id}")

                # --- 4. Delete auth data (wallet + SQLite) ---
                # delete_twin_auth calls delete_sdt_and_linked_credentials which
                # removes the SDT row AND all rows where linked_sdt_id == twinId
                # (IDS-SDT connector) in a single transaction.
                LOGGER.info(
                    f"Deleting authentication data for SDT {twinId} "
                    "and all linked components"
                )
                self.manager_core.auth_manager.delete_twin_auth(twinId)
                LOGGER.info(f"Authentication data deleted for SDT {twinId} and linked components")

                return DeploymentResponse(
                    success=True,
                    message=f"Successfully deleted SDT {twinId} and all associated resources",
                    identifier=twinId,
                    auth_status="deleted",
                )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

        @self.app.get(
            "/api/SDTM/digital-twin/{twinId}",
            summary="Retrieve a digital twin",
            response_model=None,
            tags=["SDT deployment APIs"],
        )
        async def get_digital_twin(twinId: str):
            """
            Retrieve a digital twin by its hexadecimal identifier.
            Includes authentication status and linked component info from
            the credential store.
            """
            try:
                matching_pod = None
                pod_name = None

                for pname, pid in self.manager_core.lifecycle_manager.pod_map.items():
                    if pid == twinId:
                        matching_pod = pid
                        pod_name = pname
                        break

                if not matching_pod:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Digital twin not found with identifier {twinId}"
                    )

                deployment_name = self.manager_core.lifecycle_manager.get_deployment_name_from_pod_name(
                    pod_name
                )

                pod_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.phase}}'"
                pod_status = self.manager_core.lifecycle_manager.run_command(pod_status_cmd) or "Unknown"

                creation_time_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.metadata.creationTimestamp}}'"
                creation_time = self.manager_core.lifecycle_manager.run_command(creation_time_cmd) or ""

                last_update_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.conditions[-1].lastTransitionTime}}'"
                last_update = self.manager_core.lifecycle_manager.run_command(last_update_cmd) or creation_time

                pod_ip_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.podIP}}'"
                pod_ip = self.manager_core.lifecycle_manager.run_command(pod_ip_cmd) or "N/A"

                node_name_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.spec.nodeName}}'"
                node_name = self.manager_core.lifecycle_manager.run_command(node_name_cmd) or "N/A"

                container_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.containerStatuses[0].ready}}'"
                container_ready = self.manager_core.lifecycle_manager.run_command(container_status_cmd) or "false"

                # Get authentication status from credential store
                creds = self.manager_core.credential_store.get_credentials(twinId)
                if creds:
                    auth_info = {
                        "status": creds.get("status", "unknown"),
                        "hasToken": creds.get("access_token") is not None,
                        "registeredAt": creds.get("created_at"),
                        "lastUpdated": creds.get("updated_at"),
                    }
                else:
                    auth_info = {"status": "not_registered", "hasToken": False}

                # Include linked component credential statuses
                linked_components = self.manager_core.credential_store.get_linked_components(twinId)
                auth_info["linkedComponents"] = [
                    {
                        "componentId": comp.get("sdt_id"),
                        "status": comp.get("status", "unknown"),
                        "hasToken": comp.get("access_token") is not None,
                    }
                    for comp in linked_components
                ]

                response = {
                    "twinId": twinId,
                    "modelType": "SDT",
                    "currentState": {
                        "podName": pod_name,
                        "deploymentName": deployment_name,
                        "status": pod_status,
                        "podIP": pod_ip,
                        "nodeName": node_name,
                        "containerReady": container_ready.lower() == "true",
                    },
                    "authentication": auth_info,
                    "metadata": {"createdAt": creation_time, "lastUpdated": last_update},
                }

                return JSONResponse(content=response, status_code=200)

            except HTTPException:
                raise
            except Exception as e:
                LOGGER.error(f"Error retrieving digital twin {twinId}: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve digital twin: {str(e)}"
                )

        @self.app.get(
            "/api/SDTM/deployments",
            summary="List all current SDT deployments",
            tags=["SDT deployment APIs"],
        )
        async def list_deployments():
            """
            List all current SDT deployments with detailed information.
            """
            try:
                deployments = []

                for pod_name, twin_id in self.manager_core.lifecycle_manager.pod_map.items():
                    try:
                        deployment_name = self.manager_core.lifecycle_manager.get_deployment_name_from_pod_name(
                            pod_name
                        )

                        pod_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.phase}}'"
                        pod_status = self.manager_core.lifecycle_manager.run_command(pod_status_cmd) or "Unknown"

                        creation_time_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.metadata.creationTimestamp}}'"
                        creation_time = self.manager_core.lifecycle_manager.run_command(creation_time_cmd) or ""

                        last_update_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.conditions[-1].lastTransitionTime}}'"
                        last_update = self.manager_core.lifecycle_manager.run_command(last_update_cmd) or creation_time

                        pod_ip_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.podIP}}'"
                        pod_ip = self.manager_core.lifecycle_manager.run_command(pod_ip_cmd) or "N/A"

                        node_name_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.spec.nodeName}}'"
                        node_name = self.manager_core.lifecycle_manager.run_command(node_name_cmd) or "N/A"

                        container_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.containerStatuses[0].ready}}'"
                        container_ready = self.manager_core.lifecycle_manager.run_command(container_status_cmd) or "false"

                        creds = self.manager_core.credential_store.get_credentials(twin_id)
                        auth_status = "not_registered"
                        if creds:
                            auth_status = creds.get("status", "unknown")

                        deployment_info = {
                            "twinId": twin_id,
                            "modelType": "SDT",
                            "currentState": {
                                "podName": pod_name,
                                "deploymentName": deployment_name,
                                "status": pod_status,
                                "podIP": pod_ip,
                                "nodeName": node_name,
                                "containerReady": container_ready.lower() == "true",
                            },
                            "authStatus": auth_status,
                            "metadata": {"createdAt": creation_time, "lastUpdated": last_update},
                        }

                        deployments.append(deployment_info)

                    except Exception as e:
                        LOGGER.error(f"Error getting details for pod {pod_name}: {str(e)}")
                        deployments.append(
                            {
                                "twinId": twin_id,
                                "modelType": "SDT",
                                "currentState": {
                                    "podName": pod_name,
                                    "deploymentName": "unknown",
                                    "status": "error",
                                    "podIP": "N/A",
                                    "nodeName": "N/A",
                                    "containerReady": False,
                                },
                                "authStatus": "unknown",
                                "metadata": {"createdAt": "", "lastUpdated": ""},
                            }
                        )

                return {"deployments": deployments}

            except Exception as e:
                LOGGER.error(f"Failed to list deployments: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to list deployments: {str(e)}"
                )

        # ===== IDS CONNECTOR ROUTES =====

        @self.app.post(
            "/connector/deploy",
            response_model=ConnectorResponse,
            tags=["Connector deployment APIs"],
        )
        async def deploy_connector(
            connector_type: str = Query(default="ids_sdt", description="Type of connector to deploy")
        ):
            """Deploy an IDS connector"""
            try:
                deployment_name, connector_id = self.manager_core.connector_manager.deploy_connector(connector_type)

                if deployment_name and connector_id:
                    return ConnectorResponse(
                        success=True,
                        message=f"IDS {connector_type} connector deployment successful",
                        deployment_name=deployment_name,
                        connector_id=connector_id,
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Connector deployment failed — no deployment information available"
                    )

            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Connector deployment failed: {str(e)}"
                )

        @self.app.delete(
            "/connector/delete",
            response_model=ConnectorResponse,
            tags=["Connector deployment APIs"],
        )
        async def delete_connector(
            deletion_request: DeletionRequest,
            cleanup_resources: bool = Query(
                default=True, description="Whether to cleanup associated resources"
            ),
        ):
            """Delete an IDS connector by identifier"""
            try:
                connector_exists = self.manager_core.connector_manager.check_connector_exists(
                    deletion_request.identifier
                )

                if not connector_exists:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No connector found with identifier {deletion_request.identifier}"
                    )

                deletion_results = self.manager_core.connector_manager.delete_connector(
                    deletion_request.identifier, cleanup_resources
                )

                if deletion_results.get(deletion_request.identifier, False):
                    return ConnectorResponse(
                        success=True,
                        message=f"Successfully deleted connector with identifier {deletion_request.identifier}",
                        connector_id=deletion_request.identifier,
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to delete connector with identifier {deletion_request.identifier}"
                    )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Connector deletion failed: {str(e)}"
                )

        @self.app.get("/connectors", tags=["Connector deployment APIs"])
        async def list_connectors():
            """List all current IDS connectors"""
            try:
                connectors = self.manager_core.connector_manager.list_connectors()
                return {"connectors": connectors}
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to list connectors: {str(e)}"
                )

        @self.app.get("/connector/{connector_id}", tags=["Connector deployment APIs"])
        async def get_connector_status(connector_id: str):
            """Get detailed status of a specific connector"""
            try:
                status = self.manager_core.connector_manager.get_connector_status(connector_id)

                if status:
                    return {"connector_status": status}
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No connector found with identifier {connector_id}"
                    )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to get connector status: {str(e)}"
                )

        # ===== AUTHENTICATION ROUTES =====

        @self.app.get(
            "/api/SDTM/auth/{twinId}",
            summary="Get authentication status for an SDT or component",
            tags=["Authentication APIs"],
        )
        async def get_auth_status(twinId: str):
            """
            Retrieve the authentication / credential status for an SDT or
            any linked component (IDS-SDT connector).
            If the ID belongs to a linked component, the response includes
            the parent SDT identifier.
            """
            try:
                creds = self.manager_core.credential_store.get_credentials(twinId)
                if not creds:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No authentication data found for {twinId}"
                    )

                response_body = {
                    "sdt_id": twinId,
                    "status": creds.get("status"),
                    "has_token": creds.get("access_token") is not None,
                    "scope": creds.get("token_scope"),
                    "registered_at": creds.get("created_at"),
                    "updated_at": creds.get("updated_at"),
                }

                # If this is a linked component row, expose the parent SDT
                if creds.get("linked_sdt_id"):
                    response_body["linked_sdt_id"] = creds["linked_sdt_id"]

                return JSONResponse(content=response_body)

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to get auth status: {str(e)}"
                )

        @self.app.get(
            "/api/SDTM/auth",
            summary="List all SDT credentials (tokens redacted)",
            tags=["Authentication APIs"],
        )
        async def list_credentials():
            """
            List all credential records (access tokens are redacted).
            Includes linked_sdt_id to distinguish SDT rows from component rows.
            """
            try:
                records = self.manager_core.credential_store.list_all()
                return {"credentials": records}
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to list credentials: {str(e)}"
                )

        # ===== SYSTEM STATUS ROUTES =====

        @self.app.get("/status", tags=["System"])
        async def get_system_status():
            """Get overall system status including SDT, IDS connector deployments, and auth"""
            try:
                sdt_deployments = self.manager_core.lifecycle_manager.list_available_deployments()
                # watchtower_count = self.manager_core.watchtower_manager.get_watchtower_count()
                ids_connectors = self.manager_core.connector_manager.list_connectors()
                auth_records = self.manager_core.credential_store.list_all()

                # Split SDT rows from linked component rows for the status summary
                sdt_records = [r for r in auth_records if not r.get("linked_sdt_id")]
                component_records = [r for r in auth_records if r.get("linked_sdt_id")]

                return {
                    "sdt_deployments": {"count": len(sdt_deployments), "deployments": sdt_deployments},
                    # "watchtower_instances": {"count": watchtower_count},
                    "ids_connectors": {"count": len(ids_connectors), "connectors": ids_connectors},
                    "authentication": {
                        "total_registered": len(sdt_records),
                        "issued": sum(1 for r in sdt_records if r.get("status") == "issued"),
                        "pending": sum(
                            1 for r in sdt_records
                            if r.get("status") in ("pending", "registered")
                        ),
                        "linked_components": len(component_records),
                    },
                    "system_health": "healthy",
                }
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to get system status: {str(e)}"
                )

        @self.app.get("/health", tags=["System"])
        async def health_check():
            """Health check endpoint for the API"""
            return JSONResponse(content={
                "status": "healthy",
                "service": "SDT Manager API",
                "components": {
                    "sdt_manager": "active",
                    # "watchtower_manager": "active",
                    "connector_manager": "active",
                    "adapter": "active",
                    "auth_manager": "active",
                    "credential_store": "active",
                }
            })

        @self.app.get("/ready", tags=["System"])
        async def readiness_check():
            """Readiness check endpoint for the API"""
            return JSONResponse(content={
                "status": "ready",
                "service": "SDT Manager API"
            })

        # ===== SDT ADAPTER ROUTES =====

        @self.app.post("/api/SDTM/adapt", tags=["SDT Adaptor APIs"])
        async def adapt_payload(
            request: Request,
            toeid: str = Query(
                default="00000000-0000-0000-0000-000000000000",
                description="Target of Evaluation ID"
            ),
            payload_type: str = Query(default="BOMS", description="Type of payload"),
        ):
            """
            Unified endpoint to convert different payload formats
            (CycloneDX, OSCAL, ARM, MUD) to Thing payload_type
            """
            try:
                LOGGER.info(f"Receiving payload (payload_type={payload_type})...")
                payload = await request.json()
                adapter = self._get_v2_adapter()

                start_time = time.time()
                validation_result, converted = adapter.validate_and_transform(
                    payload,
                    payload_type,
                    strict=True,
                    thorough=True,
                )

                if not validation_result.valid:
                    LOGGER.warning(
                        "Validation failed for payload_type=%s: %s",
                        payload_type,
                        validation_result.to_dict(),
                    )
                    return JSONResponse(content=validation_result.to_dict(), status_code=400)

                validation_payload = validation_result.to_dict()

                conversion_time = time.time() - start_time

                LOGGER.info("Sending to controller...")
                start_time = time.time()
                access_token = self.manager_core.credential_store.get_most_recent_access_token()
                controller_result = adapter.send_to_controller(
                    converted,
                    toeid,
                    payload_type,
                    access_token=access_token,
                )
                controller_time = time.time() - start_time
                LOGGER.info(f"Request completed in {controller_time:.2f} seconds")

                sdt_response = controller_result.get("sdt_response") if controller_result else None
                ccmledger_result = controller_result.get("ccmledger") if controller_result else None

                if sdt_response is not None and hasattr(sdt_response, "text"):
                    LOGGER.info(f"Response from controller: {sdt_response.text[:200]}...")
                else:
                    LOGGER.info("No response received from controller")

                return JSONResponse(content={
                    "message": f"{payload_type} payload processed and sent to SDT",
                    "payload_type": payload_type,
                    "validation": validation_payload,
                    "conversion_time": conversion_time,
                    "controller_time": controller_time,
                    "sdt": {
                        "success": sdt_response is not None and getattr(sdt_response, "status_code", 500) < 400,
                        "status_code": getattr(sdt_response, "status_code", None),
                    },
                    "ccmledger": ccmledger_result,
                })

            except Exception as e:
                LOGGER.error(f"Error processing payload: {e}")
                import traceback
                LOGGER.error(traceback.format_exc())
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.post("/api/SDTM/adapt/multiple/", tags=["SDT Adaptor APIs"])
        async def adapt_multiple_files(request: MultipleFilesRequest):
            """
            Endpoint to adapt multiple files of different types and create
            cross-referenced Security Artifacts.
            """
            try:
                LOGGER.info(f"Processing {len(request.file_configs)} files...")
                adapter = self._get_v2_adapter()
                file_configs = [config.dict(exclude_none=True) for config in request.file_configs]
                file_config_by_path = {config.path: config for config in request.file_configs}

                start_time = time.time()
                things = adapter.process_multiple_files(file_configs)
                processing_time = time.time() - start_time

                results = []
                controller_start = time.time()
                access_token = self.manager_core.credential_store.get_most_recent_access_token()

                for file_path, thing in things.items():
                    try:
                        file_config = file_config_by_path.get(file_path)
                        payload_type_value = file_config.type if file_config else "BOMS"
                        thing_id = file_config.thing_id if file_config else None

                        if thing_id:
                            controller_result = adapter.send_to_controller(
                                thing,
                                toeid=thing_id,
                                payload_type=payload_type_value,
                                access_token=access_token,
                            )
                        else:
                            controller_result = adapter.send_to_controller(
                                thing,
                                payload_type=payload_type_value,
                                access_token=access_token,
                            )

                        sdt_response = controller_result.get("sdt_response") if controller_result else None
                        ccmledger_result = controller_result.get("ccmledger") if controller_result else None

                        results.append({
                            "status": "success" if sdt_response is not None and getattr(sdt_response, "status_code", 500) < 400 else "failed",
                            "path": file_path,
                            "payload_type": payload_type_value,
                            "source_type": thing.get("attributes", {}).get("sourceType"),
                            "response_status": getattr(sdt_response, "status_code", None),
                            "ccmledger": ccmledger_result,
                        })
                    except Exception as e:
                        results.append({
                            "status": "failed",
                            "path": file_path,
                            "error": str(e)
                        })

                controller_time = time.time() - controller_start

                return JSONResponse(content={
                    "message": "Multiple files processed and sent to SDT",
                    "total_files": len(things),
                    "processing_time": processing_time,
                    "controller_time": controller_time,
                    "results": results,
                })

            except Exception as e:
                LOGGER.error(f"Error processing multiple files: {e}")
                import traceback
                LOGGER.error(traceback.format_exc())
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.get("/api/SDTM/adapt/cyclonedx/detect/", tags=["SDT Adaptor APIs"])
        async def detect_bom_type(request: Request):
            """Endpoint to detect the BOM type of a CycloneDX payload."""
            try:
                payload = await request.json()

                if not isinstance(payload, dict):
                    raise ValueError("Invalid payload type")

                bom_type = self.manager_core.sdt_adapter.detect_bom_type(payload)

                analysis = {
                    "bom_type": bom_type,
                    "has_components": "components" in payload,
                    "has_services": "services" in payload,
                    "has_dependencies": "dependencies" in payload,
                    "has_vulnerabilities": "vulnerabilities" in payload,
                    "component_count": len(payload.get("components", [])),
                    "service_count": len(payload.get("services", [])),
                    "vulnerability_count": len(payload.get("vulnerabilities", []))
                }

                return JSONResponse(content=analysis)

            except Exception as e:
                LOGGER.error(f"Error detecting BOM type: {e}")
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.get("/api/SDTM/adapt/cyclonedx/validate/", tags=["SDT Adaptor APIs"])
        async def validate_cyclonedx(
            request: Request,
            strict: bool = Query(default=False, description="Use strict validation"),
            thorough: bool = Query(default=True, description="Perform thorough schema validation")
        ):
            """Endpoint to validate a CycloneDX payload without conversion."""
            try:
                payload = await request.json()
                adapter = self._get_v2_adapter()

                start_time = time.time()
                validation_result = adapter.validate_payload(
                    payload,
                    "cyclonedx",
                    strict=strict,
                    thorough=thorough,
                )
                validation_time = time.time() - start_time

                result = {
                    **validation_result.to_dict(),
                    "validation_time": validation_time,
                    "strict_mode": strict,
                    "thorough_check": thorough
                }

                if validation_result.valid and isinstance(payload, dict):
                    result["bom_format"] = payload.get("bomFormat")
                    result["spec_version"] = payload.get("specVersion")
                    result["serial_number"] = payload.get("serialNumber")

                return JSONResponse(content=result)

            except Exception as e:
                LOGGER.error(f"Error validating CycloneDX: {e}")
                return JSONResponse(content={"error": str(e), "valid": False}, status_code=400)

    def start_server(self, host="0.0.0.0", port=8008):
        """Start the FastAPI server"""
        LOGGER.info(f"Starting SDT Manager API server on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)

    def start_server_thread(self, host="0.0.0.0", port=8008):
        """Start the FastAPI server in a separate thread"""
        server_thread = threading.Thread(
            target=self.start_server,
            args=(host, port),
            daemon=True
        )
        server_thread.start()
        return server_thread