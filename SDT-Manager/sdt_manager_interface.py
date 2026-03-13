# File: sdt_manager_interface.py

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
import uvicorn
import logging
import json
import time
import threading
import os

from fastapi import Request, FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
LOGGER = logging.getLogger(__name__)

# Pydantic models defined outside the class to avoid linting warnings
class DeploymentResponse(BaseModel):
    """Response model for deployment operations"""
    success: bool
    message: str
    pod_name: Optional[str] = None
    identifier: Optional[str] = None
    watchtower_id: Optional[str] = None
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


# methods SDT Adapter API request/response models
class FileConfig(BaseModel):
    path: str
    type: str

class MultipleFilesRequest(BaseModel):
    file_configs: List[FileConfig]


class SDT_Manager_Interface:
    """North Bound Interface for SDT Manager using FastAPI, it faces CCM Manager"""
    
    def __init__(self, manager_core):
        """Initialize with reference to the SDT Manager Core"""
        self.manager_core = manager_core
        self.sdt_to_ids_map = {}  # Maps SDT identifier to IDS-SDT connector_id
        self.app = FastAPI(
            title="SDT Deployment API",
            description="API for managing SDT deployments and IDS connectors in Kubernetes",
            version="2.0.0"
        )
        self._setup_routes()
        LOGGER.info("SDT Manager Interface initialized")
    
    def _run_auth_flow_async(self, sdt_identifier: str, ids_connector_id: Optional[str],
                              watchtower_id: Optional[str]):
        """
        Run the wallet registration and token acquisition in a background
        thread so the deploy endpoint can return quickly.

        Once the token is obtained it is distributed to the SDT, IDS-SDT
        connector and Watchtower via HTTP POST to their /auth/token endpoint.

        Args:
            sdt_identifier:   Hex identifier of the deployed SDT.
            ids_connector_id: Hex identifier of the IDS-SDT connector (may be None).
            watchtower_id:    Hex identifier of the Watchtower (may be None).
        """
        LOGGER.info(f"Background auth flow started for SDT {sdt_identifier}")

        try:
            success, access_token = (
                self.manager_core.auth_manager.register_and_get_token(
                    sdt_id=sdt_identifier
                )
            )

            if not success or not access_token:
                LOGGER.error(
                    f"Auth flow failed for SDT {sdt_identifier} — "
                    "components will run without token"
                )
                return

            # Distribute the token to all related components
            self._distribute_token(sdt_identifier, access_token,
                                   ids_connector_id, watchtower_id)

        except Exception as e:
            LOGGER.error(f"Auth flow exception for SDT {sdt_identifier}: {e}")

    def _distribute_token(self, sdt_identifier: str, access_token: str,
                          ids_connector_id: Optional[str],
                          watchtower_id: Optional[str]):
        """
        Send the full credentials JSON payload to the running SDT, IDS-SDT
        and Watchtower components via HTTP POST to their /auth/token endpoint.

        Each component exposes the same endpoint: POST /auth/token
        The SDT Manager resolves the target address using the Kubernetes
        service ClusterIP + the configured port for each component type.

        Args:
            sdt_identifier:   Hex identifier of the SDT.
            access_token:     The OAuth2 access token to distribute.
            ids_connector_id: Connector identifier (may be None).
            watchtower_id:    Watchtower identifier (may be None).
        """
        LOGGER.info(f"Distributing credentials to components for SDT {sdt_identifier}")

        # Build the full credentials payload
        creds = self.manager_core.credential_store.get_credentials(sdt_identifier)
        auth_payload = {
            "sdt_id": sdt_identifier,
            "client_id": creds.get("client_id") if creds else None,
            "client_secret": creds.get("client_secret") if creds else None,
            "access_token": access_token,
        }

        # --- SDT service ---
        sdt_service_name = self._get_sdt_service_name()
        sdt_port = int(os.environ.get("SDT_AUTH_PORT", "8080"))
        if sdt_service_name:
            self._send_token_to_service(sdt_service_name, sdt_port, auth_payload, "SDT")
        else:
            LOGGER.warning("Could not resolve SDT service — skipping token delivery to SDT")

        # --- IDS-SDT connector service ---
        if ids_connector_id:
            ids_service_name = self._get_ids_sdt_service_name()
            ids_port = int(os.environ.get("IDS_SDT_AUTH_PORT", "8080"))
            if ids_service_name:
                self._send_token_to_service(ids_service_name, ids_port, auth_payload, "IDS-SDT")
            else:
                LOGGER.warning("Could not resolve IDS-SDT service — skipping token delivery")

        # --- Watchtower service ---
        if watchtower_id:
            wt_service_name = "watchtower-service"
            wt_port = int(os.environ.get("WATCHTOWER_AUTH_PORT", "8080"))
            self._send_token_to_service(wt_service_name, wt_port, auth_payload, "Watchtower")

        LOGGER.info(f"Token distribution completed for SDT {sdt_identifier}")

    def _send_token_to_service(self, service_name: str, port: int,
                                auth_payload: dict, component_label: str):
        """
        POST the credentials JSON payload to a component's /auth/token
        endpoint using its Kubernetes service ClusterIP.

        Args:
            service_name:    Kubernetes service name.
            port:            Port the component listens on.
            auth_payload:    The full credentials dict to send.
            component_label: Human-readable label for logging.
        """
        import requests as req

        # Resolve ClusterIP from the service
        cluster_ip = self._get_service_cluster_ip(service_name)
        if not cluster_ip:
            LOGGER.error(f"Cannot resolve ClusterIP for {service_name} — token not delivered to {component_label}")
            return

        url = f"http://{cluster_ip}:{port}/auth/token"
        LOGGER.info(f"Sending credentials to {component_label} at {url}")

        try:
            response = req.post(
                url,
                json=auth_payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if response.status_code in (200, 201, 204):
                LOGGER.info(f"Credentials delivered to {component_label} ({service_name}) — HTTP {response.status_code}")
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

    def _get_service_cluster_ip(self, service_name: str) -> Optional[str]:
        """
        Resolve the ClusterIP of a Kubernetes service.

        Args:
            service_name: Name of the Kubernetes service.

        Returns:
            The ClusterIP string, or None if not found.
        """
        cmd = f"kubectl get service {service_name} -o jsonpath='{{.spec.clusterIP}}' --ignore-not-found=true"
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
        # Try ids-connector-sdt-service first
        cmd = "kubectl get service ids-connector-sdt-service -o jsonpath='{.metadata.name}' --ignore-not-found=true"
        result = self.manager_core.lifecycle_manager.run_command(cmd)
        if result:
            return result
        # Fall back to tc-consumer service
        cmd = "kubectl get services -l io.kompose.service=tc-consumer -o jsonpath='{.items[0].metadata.name}' --ignore-not-found=true"
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
              1. Deploy IDS-SDT connector and Watchtower
              2. Register the SDT with the wallet controller (using its hex ID)
              3. Obtain an OAuth2 access token
              4. Store credentials in SQLite
              5. Distribute the token to SDT, IDS-SDT and Watchtower
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
                    LOGGER.info(f"IDS-SDT connector deployed: {ids_deployment_name}, ID={ids_connector_id}")
                    self.sdt_to_ids_map[identifier] = ids_connector_id
                else:
                    LOGGER.warning("IDS-SDT connector deployment failed, SDT will run without connector")
                
                # --- 3. Deploy / discover Watchtower ---
                watchtower_id = None
                wt_pod_name, watchtower_id = (
                    self.manager_core.watchtower_manager.get_or_register_existing_watchtower()
                )
                
                if wt_pod_name and watchtower_id:
                    LOGGER.info(f"Watchtower exists: {wt_pod_name} (ID: {watchtower_id}), skipping deployment")
                else:
                    LOGGER.info("No existing Watchtower found, deploying...")
                    wt_pod_name, watchtower_id = (
                        self.manager_core.watchtower_manager.deploy_watchtower()
                    )
                    if wt_pod_name and watchtower_id:
                        LOGGER.info(f"Watchtower deployed: {wt_pod_name}, ID={watchtower_id}")
                    else:
                        LOGGER.warning("Watchtower deployment failed, SDT will run without monitoring")
                
                # --- 4. Start auth flow in background thread ---
                # Uses the hex identifier as twin_id for wallet registration.
                # The thread registers, polls, fetches token, stores in SQLite,
                # and distributes the token to all three components.
                auth_thread = threading.Thread(
                    target=self._run_auth_flow_async,
                    args=(identifier, ids_connector_id, watchtower_id),
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
                    watchtower_id=watchtower_id,
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
              2. Delete Watchtower
              3. Delete twin registration from wallet controller
              4. Remove credentials from SQLite
            """
            try:
                # Verify the identifier exists in the pod map
                identifier_exists = any(
                    id_val == twinId
                    for id_val in self.manager_core.lifecycle_manager.pod_map.values()
                )

                if not identifier_exists:
                    raise HTTPException(
                        status_code=404, detail=f"No deployment found with identifier {twinId}"
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
                
                # --- 3. Delete Watchtower if it exists ---
                wt_pod_name, watchtower_id = (
                    self.manager_core.watchtower_manager.get_or_register_existing_watchtower()
                )
                if watchtower_id:
                    LOGGER.info(f"Deleting Watchtower: {watchtower_id}")
                    self.manager_core.watchtower_manager.delete_watchtower_by_id(
                        watchtower_id, cleanup_service=True
                    )
                    LOGGER.info(f"Watchtower deleted: {watchtower_id}")
                
                # --- 4. Delete auth data (wallet + SQLite) ---
                LOGGER.info(f"Deleting authentication data for SDT {twinId}")
                self.manager_core.auth_manager.delete_twin_auth(twinId)
                LOGGER.info(f"Authentication data deleted for SDT {twinId}")
                
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
            Includes authentication status from credential store.
            """
            try:
                # Search for the pod with the given identifier in the pod_map
                matching_pod = None
                pod_name = None

                for pname, pid in self.manager_core.lifecycle_manager.pod_map.items():
                    if pid == twinId:
                        matching_pod = pid
                        pod_name = pname
                        break

                if not matching_pod:
                    raise HTTPException(
                        status_code=404, detail=f"Digital twin not found with identifier {twinId}"
                    )

                # Get deployment name from pod name
                deployment_name = self.manager_core.lifecycle_manager.get_deployment_name_from_pod_name(
                    pod_name
                )

                # Get current pod status using kubectl
                pod_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.phase}}'"
                pod_status = self.manager_core.lifecycle_manager.run_command(pod_status_cmd) or "Unknown"

                # Get pod creation timestamp
                creation_time_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.metadata.creationTimestamp}}'"
                creation_time = self.manager_core.lifecycle_manager.run_command(creation_time_cmd) or ""

                # Get last transition time (last update)
                last_update_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.conditions[-1].lastTransitionTime}}'"
                last_update = self.manager_core.lifecycle_manager.run_command(last_update_cmd) or creation_time

                # Get additional pod details for current state
                pod_ip_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.podIP}}'"
                pod_ip = self.manager_core.lifecycle_manager.run_command(pod_ip_cmd) or "N/A"

                node_name_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.spec.nodeName}}'"
                node_name = self.manager_core.lifecycle_manager.run_command(node_name_cmd) or "N/A"

                # Get container statuses
                container_status_cmd = f"kubectl get pods {pod_name} -o jsonpath='{{.status.containerStatuses[0].ready}}'"
                container_ready = self.manager_core.lifecycle_manager.run_command(container_status_cmd) or "false"

                # Get authentication status from credential store
                creds = self.manager_core.credential_store.get_credentials(twinId)
                auth_info = {}
                if creds:
                    auth_info = {
                        "status": creds.get("status", "unknown"),
                        "hasToken": creds.get("access_token") is not None,
                        "registeredAt": creds.get("created_at"),
                        "lastUpdated": creds.get("updated_at"),
                    }
                else:
                    auth_info = {"status": "not_registered", "hasToken": False}

                # Construct the response
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
                raise HTTPException(status_code=500, detail=f"Failed to retrieve digital twin: {str(e)}")

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

                        # Get auth status
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
                raise HTTPException(status_code=500, detail=f"Failed to list deployments: {str(e)}")

        # ===== IDS CONNECTOR ROUTES =====

        @self.app.post(
            "/connector/deploy",
            response_model=ConnectorResponse,
            tags=["Connector deployment APIs"],
        )
        async def deploy_connector(connector_type: str = Query(default="ids_sdt", description="Type of connector to deploy")):
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
                    raise HTTPException(status_code=500, detail="Connector deployment failed — no deployment information available")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Connector deployment failed: {str(e)}")

        @self.app.delete(
            "/connector/delete",
            response_model=ConnectorResponse,
            tags=["Connector deployment APIs"],
        )
        async def delete_connector(
            deletion_request: DeletionRequest,
            cleanup_resources: bool = Query(default=True, description="Whether to cleanup associated resources"),
        ):
            """Delete an IDS connector by identifier"""
            try:
                connector_exists = self.manager_core.connector_manager.check_connector_exists(deletion_request.identifier)

                if not connector_exists:
                    raise HTTPException(status_code=404, detail=f"No connector found with identifier {deletion_request.identifier}")

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
                    raise HTTPException(status_code=500, detail=f"Failed to delete connector with identifier {deletion_request.identifier}")

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Connector deletion failed: {str(e)}")

        @self.app.get("/connectors", tags=["Connector deployment APIs"])
        async def list_connectors():
            """List all current IDS connectors"""
            try:
                connectors = self.manager_core.connector_manager.list_connectors()
                return {"connectors": connectors}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to list connectors: {str(e)}")

        @self.app.get("/connector/{connector_id}", tags=["Connector deployment APIs"])
        async def get_connector_status(connector_id: str):
            """Get detailed status of a specific connector"""
            try:
                status = self.manager_core.connector_manager.get_connector_status(connector_id)

                if status:
                    return {"connector_status": status}
                else:
                    raise HTTPException(status_code=404, detail=f"No connector found with identifier {connector_id}")

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get connector status: {str(e)}")

        # ===== AUTHENTICATION ROUTES =====

        @self.app.get(
            "/api/SDTM/auth/{twinId}",
            summary="Get authentication status for an SDT",
            tags=["Authentication APIs"],
        )
        async def get_auth_status(twinId: str):
            """Retrieve the authentication / credential status for an SDT."""
            try:
                creds = self.manager_core.credential_store.get_credentials(twinId)
                if not creds:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No authentication data found for SDT {twinId}"
                    )

                return JSONResponse(content={
                    "sdt_id": twinId,
                    "status": creds.get("status"),
                    "has_token": creds.get("access_token") is not None,
                    "scope": creds.get("token_scope"),
                    "registered_at": creds.get("created_at"),
                    "updated_at": creds.get("updated_at"),
                })
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get auth status: {str(e)}")

        @self.app.get(
            "/api/SDTM/auth",
            summary="List all SDT credentials (tokens redacted)",
            tags=["Authentication APIs"],
        )
        async def list_credentials():
            """List all SDT credential records (access tokens are redacted)."""
            try:
                records = self.manager_core.credential_store.list_all()
                return {"credentials": records}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to list credentials: {str(e)}")

        # ===== SYSTEM STATUS ROUTES =====

        @self.app.get("/status", tags=["System"]) 
        async def get_system_status():
            """Get overall system status including SDT, Watchtower, IDS connector deployments, and auth"""
            try:
                sdt_deployments = self.manager_core.lifecycle_manager.list_available_deployments()
                watchtower_count = self.manager_core.watchtower_manager.get_watchtower_count()
                ids_connectors = self.manager_core.connector_manager.list_connectors()
                auth_records = self.manager_core.credential_store.list_all()

                return {
                    "sdt_deployments": {"count": len(sdt_deployments), "deployments": sdt_deployments},
                    "watchtower_instances": {"count": watchtower_count},
                    "ids_connectors": {"count": len(ids_connectors), "connectors": ids_connectors},
                    "authentication": {
                        "total_registered": len(auth_records),
                        "issued": sum(1 for r in auth_records if r.get("status") == "issued"),
                        "pending": sum(1 for r in auth_records if r.get("status") in ("pending", "registered")),
                    },
                    "system_health": "healthy",
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")

        @self.app.get("/health", tags=["System"])
        async def health_check():
            """Health check endpoint for the API"""
            return JSONResponse(content={
                "status": "healthy",
                "service": "SDT Manager API",
                "components": {
                    "sdt_manager": "active",
                    "watchtower_manager": "active",
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
            toeid: str = Query(default="00000000-0000-0000-0000-000000000000", description="Target of Evaluation ID"),
            payload_type: str = Query(default="BOMS", description="Type of payload"),
        ):
            """
            Unified endpoint to convert different payload formats (CycloneDX, OSCAL, ARM) to Thing payload_type
            """
            try:
                logger.info(f"Receiving payload (payload_type={payload_type})...")
                payload = await request.json()

                start_time = time.time()

                if payload_type.lower() == "boms":
                    logger.info("Validating CycloneDX payload...")
                    if not self.manager_core.sdt_adapter.validate_cyclonedx_smart(payload, strict=False, thorough=False):
                        raise ValueError("Invalid CycloneDX payload")

                    logger.info("Converting CycloneDX to Thing structure...")
                    json_payload_str = json.dumps(payload)
                    converted = self.manager_core.sdt_adapter.from_cyclone(json_payload_str)

                elif payload_type.lower() == "oscal":
                    logger.info("Validating OSCAL payload...")
                    if "component-definition" not in payload:
                        raise ValueError("Invalid OSCAL payload: missing 'component-definition'")

                    logger.info("Converting OSCAL to Thing structure...")
                    json_payload_str = json.dumps(payload)
                    converted = self.manager_core.sdt_adapter.from_oscal_component(json_payload_str)

                elif payload_type.lower() == "arm":
                    logger.info("Validating ARM payload...")
                    if "$schema" not in payload:
                        raise ValueError("Invalid ARM template: missing '$schema' field")

                    logger.info("Converting ARM template to Thing structure...")
                    json_payload_str = json.dumps(payload)
                    converted = self.manager_core.sdt_adapter.from_arm_template(json_payload_str)

                else:
                    raise ValueError(f"Unsupported payload_type: {payload_type}")

                conversion_time = time.time() - start_time

                logger.info("Sending to controller...")
                start_time = time.time()
                response = self.manager_core.sdt_adapter.send_to_controller(converted, toeid, payload_type)
                controller_time = time.time() - start_time
                logger.info(f"Request completed in {controller_time:.2f} seconds")

                if response is not None and hasattr(response, "text"):
                    logger.info(f"Response from controller: {response.text[:200]}...")
                else:
                    logger.info("No response received from controller")

                return JSONResponse(content={
                    "message": f"{payload_type} payload processed and sent to SDT",
                    "payload_type": payload_type,
                })

            except Exception as e:
                logger.error(f"Error processing payload: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse(content={"error": str(e)}, status_code=500)


        @self.app.post("/api/SDTM/adapt/multiple/", tags=["SDT Adaptor APIs"])
        async def adapt_multiple_files(request: MultipleFilesRequest):
            """
            Endpoint to adapt multiple files of different types and create cross-referenced Security Artifacts.
            """
            try:
                logger.info(f"Processing {len(request.file_configs)} files...")
                
                start_time = time.time()
                things = self.manager_core.sdt_adapter.process_multiple_files([config.dict() for config in request.file_configs])
                processing_time = time.time() - start_time
                
                results = []
                controller_start = time.time()
                
                for thing_id, thing in things.items():
                    try:
                        response = self.manager_core.sdt_adapter.send_to_controller(thing)
                        results.append({
                            "status": "success",
                            "source_type": thing.get("attributes", {}).get("sourceType"),
                            "response_status": response.status_code if response else None
                        })
                    except Exception as e:
                        results.append({
                            "status": "failed",
                            "error": str(e)
                        })
                
                controller_time = time.time() - controller_start
                
                return JSONResponse(content={
                    "message": "Multiple files processed and sent to SDT",
                    "total_files": len(things),
                })
            
            except Exception as e:
                logger.error(f"Error processing multiple files: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.get("/api/SDTM/adapt/cyclonedx/detect/", tags=["SDT Adaptor APIs"])
        async def detect_bom_type(request: Request):
            """Endpoint to detect the BOM type of a CycloneDX payload."""
            try:
                payload = await request.json()
                
                if not isinstance(payload, dict):
                    raise ValueError("Invalid payload payload_type")
                
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
                logger.error(f"Error detecting BOM type: {e}")
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
                
                start_time = time.time()
                is_valid = self.manager_core.sdt_adapter.validate_cyclonedx_smart(payload, strict=strict, thorough=thorough)
                validation_time = time.time() - start_time
                
                result = {
                    "valid": is_valid,
                    "validation_time": validation_time,
                    "strict_mode": strict,
                    "thorough_check": thorough
                }
                
                if is_valid:
                    result["bom_format"] = payload.get("bomFormat")
                    result["spec_version"] = payload.get("specVersion")
                    result["serial_number"] = payload.get("serialNumber")
                
                return JSONResponse(content=result)
            
            except Exception as e:
                logger.error(f"Error validating CycloneDX: {e}")
                return JSONResponse(content={"error": str(e), "valid": False}, status_code=400)
    
    def start_server(self, host="0.0.0.0", port=8008):
        """Start the FastAPI server"""
        LOGGER.info(f"Starting SDT Manager API server on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)
    
    def start_server_thread(self, host="0.0.0.0", port=8008):
        """Start the FastAPI server in a separate thread"""
        import threading
        server_thread = threading.Thread(
            target=self.start_server,
            args=(host, port),
            daemon=True
        )
        server_thread.start()
        return server_thread