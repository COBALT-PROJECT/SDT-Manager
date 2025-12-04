# File: sdt_manager_interface.py

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
import uvicorn
import logging
import json
import time

from fastapi import Request, FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse


LOGGER = logging.getLogger(__name__)

# Pydantic models defined outside the class to avoid linting warnings
class DeploymentResponse(BaseModel):
    """Response model for deployment operations"""
    success: bool
    message: str
    pod_name: Optional[str] = None
    identifier: Optional[str] = None

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
    # thing_id: Optional[str] = None

class MultipleFilesRequest(BaseModel):
    file_configs: List[FileConfig]


class SDT_Manager_Interface:
    """North Bound Interface for SDT Manager using FastAPI,it faces CCM Manager"""
    
    def __init__(self, manager_core):
        """Initialize with reference to the SDT Manager Core"""
        self.manager_core = manager_core
        self.sdt_to_ids_map = {}  # Maps SDT identifier to IDS-SDT connector_id
        self.app = FastAPI(
            title="SDT Deployment API",
            description="API for managing SDT deployments and IDS connectors in Kubernetes"
        )
        self._setup_routes()
        LOGGER.info("SDT Manager Interface initialized")
    
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
            """Deploy an SDT pod and service, then automatically deploy IDS-SDT connector"""
            try:
                # Deploy using the manager's lifecycle component
                pod_name, identifier = self.manager_core.lifecycle_manager.deploy()

                if pod_name and identifier:
                    LOGGER.info(f"SDT deployed successfully: {pod_name}, {identifier}")
                    
                    # Automatically deploy IDS-SDT connector
                    LOGGER.info("Deploying IDS-SDT connector...")
                    ids_deployment_name, ids_connector_id = self.manager_core.connector_manager.deploy_connector("ids_sdt")
                    
                    if ids_deployment_name and ids_connector_id:
                        LOGGER.info(f"IDS-SDT connector deployed: {ids_deployment_name}, {ids_connector_id}")
                        # Store the mapping
                        self.sdt_to_ids_map[identifier] = ids_connector_id
                    else:
                        LOGGER.warning("IDS-SDT connector deployment failed, but SDT is running")
                    
                    return DeploymentResponse(
                        success=True,
                        message="SDT deployment successful",
                        pod_name=pod_name,
                        identifier=identifier,
                    )
                else:
                    raise HTTPException(
                        status_code=500, detail="Deployment failed - no pod information available"
                    )

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

        @self.app.delete(
            "/api/SDTM/digital-twin/{twinId}",
            response_model=DeploymentResponse,
            summary="Delete an SDT instance by using its identifier",
            tags=["SDT deployment APIs"],
        )
        async def delete_sdt(twinId: str):
            """Delete an SDT deployment by identifier"""
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

                # Delete using the manager
                deletion_results = self.manager_core.lifecycle_manager.delete_deployment_by_id(
                    twinId
                )

                if deletion_results.get(twinId, False):
                    LOGGER.info(f"SDT deleted successfully: {twinId}")
                    
                    # Delete associated IDS-SDT connector
                    ids_connector_id = self.sdt_to_ids_map.get(twinId)
                    if ids_connector_id:
                        LOGGER.info(f"Deleting IDS-SDT connector: {ids_connector_id}")
                        self.manager_core.connector_manager.delete_connector(ids_connector_id)
                        del self.sdt_to_ids_map[twinId]
                        LOGGER.info(f"IDS-SDT connector deleted: {ids_connector_id}")
                    
                    return DeploymentResponse(
                        success=True,
                        message=f"Successfully deleted deployment with identifier {twinId}",
                        identifier=twinId,
                    )
                else:
                    raise HTTPException(
                        status_code=500, detail=f"Failed to delete deployment with identifier {twinId}"
                    )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

        @self.app.get(
            "/api/SDTM/digital-twin/{twinId}",
            summary="Retrieve a digital twin",
            response_model=None,  # Using None to allow custom response structure
            tags=["SDT deployment APIs"],
        )
        async def get_digital_twin(twinId: str):
            """
            Retrieve a digital twin by its hexadecimal identifier.

            Args:
                twinId (str): The hexadecimal identifier of the digital twin

            Returns:
                JSONResponse: Digital twin data if found, 404 error otherwise
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

                # Construct the response according to the schema
                response = {
                    "twinId": twinId,
                    "modelType": "SDT",  # Static as this is SDT Manager
                    "currentState": {
                        "podName": pod_name,
                        "deploymentName": deployment_name,
                        "status": pod_status,
                        "podIP": pod_ip,
                        "nodeName": node_name,
                        "containerReady": container_ready.lower() == "true",
                    },
                    "metadata": {"createdAt": creation_time, "lastUpdated": last_update},
                }

                return JSONResponse(content=response, status_code=200)

            except HTTPException:
                raise
            except Exception as e:
                LOGGER.error(f"Error retrieving digital twin {twinId}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to retrieve digital twin: {str(e)}")

        # Replace the existing list_deployments method in _setup_routes with this updated version

        @self.app.get(
            "/api/SDTM/deployments",
            summary="List all current SDT deployments",
            tags=["SDT deployment APIs"],
        )
        async def list_deployments():
            """
            List all current SDT deployments with detailed information.
            Returns the same structure as the individual digital twin endpoint.
            """
            try:
                deployments = []

                # Iterate through all pods in the pod_map
                for pod_name, twin_id in self.manager_core.lifecycle_manager.pod_map.items():
                    try:
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

                        # Construct the deployment info in the same payload_type as get_digital_twin
                        deployment_info = {
                            "twinId": twin_id,
                            "modelType": "SDT",  # Static as this is SDT Manager
                            "currentState": {
                                "podName": pod_name,
                                "deploymentName": deployment_name,
                                "status": pod_status,
                                "podIP": pod_ip,
                                "nodeName": node_name,
                                "containerReady": container_ready.lower() == "true",
                            },
                            "metadata": {"createdAt": creation_time, "lastUpdated": last_update},
                        }

                        deployments.append(deployment_info)

                    except Exception as e:
                        LOGGER.error(f"Error getting details for pod {pod_name}: {str(e)}")
                        # Add basic info even if detailed fetch fails
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
                # Deploy using the connector manager
                deployment_name, connector_id = self.manager_core.connector_manager.deploy_connector(connector_type)

                if deployment_name and connector_id:
                    return ConnectorResponse(
                        success=True,
                        message=f"IDS {connector_type} connector deployment successful",
                        deployment_name=deployment_name,
                        connector_id=connector_id,
                    )
                else:
                    raise HTTPException(status_code=500, detail="Connector deployment failed - no deployment information available")

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
                # Verify the connector exists
                connector_exists = self.manager_core.connector_manager.check_connector_exists(deletion_request.identifier)

                if not connector_exists:
                    raise HTTPException(status_code=404, detail=f"No connector found with identifier {deletion_request.identifier}")

                # Delete using the connector manager
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

        # ===== SYSTEM STATUS ROUTES =====

        @self.app.get("/status", tags=["SDT deployment APIs"]) 
        async def get_system_status():
            """Get overall system status including both SDT and IDS connector deployments"""
            try:
                sdt_deployments = self.manager_core.lifecycle_manager.list_available_deployments()
                ids_connectors = self.manager_core.connector_manager.list_connectors()

                return {
                    "sdt_deployments": {"count": len(sdt_deployments), "deployments": sdt_deployments},
                    "ids_connectors": {"count": len(ids_connectors), "connectors": ids_connectors},
                    "system_health": "healthy",
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")

        # @self.app.post(
        #     "/api/SDTM/create/",
        #     summary="Synchronize BOMS from CCM Manager",
        #     tags=["SDT Adaptor API"],
        # )
        # async def create_sdt(
        #     request: Request,
        #     toeid: str = Query(default="123456789", description="Target of Evaluation ID"),
        #     payload_type: str = Query(default="BOMS", description="Type of payload "),
        #     hash_value: str = Query(default="123456789", description="Hash value"),
        # ):
        #     """
        #     Endpoint to validate and convert a CycloneDX payload sent to SDT interface.

        #     Args:
        #         request (Request): The request object containing the CycloneDX payload.
        #         toeid (str): Target of Evaluation ID.
        #         payload_type (str): Type of payload (BOMS, AI, QDT, etc).

        #     Returns:
        #         JSONResponse: A JSON response containing the conversion status or an error message.
        #     """
        #     LOGGER.info(f"Received create request with toeid={toeid}, payload_type={payload_type}")
        #     try:
        #         # Get the adapter from the manager core
        #         sdt_adapter = self.manager_core.sdt_adapter

        #         # Receive the payload
        #         LOGGER.info("Receiving payload...")
        #         try:
        #             payload = await request.json()
        #             if not payload:
        #                 raise ValueError("Empty payload received")
        #         except Exception as e:
        #             LOGGER.error(f"Failed to parse request body as JSON: {e}")
        #             return JSONResponse(content={"error": "Invalid JSON payload"}, status_code=400)

        #         # Validate and process the payload
        #         LOGGER.info(f"Processing payload, validating CycloneDX...")
        #         conversion_time = 0
        #         controller_time = 0

        #         # Validate the CycloneDX payload
        #         if sdt_adapter.validate_cyclonedx_smart(payload, strict=False, thorough=False):
        #             LOGGER.info("Validation successful, converting to Thing structure...")
        #             json_payload_str = json.dumps(payload)

        #             # Convert CycloneDX to DT structure
        #             start_time = time.time()
        #             converted = sdt_adapter.from_cyclone(json_payload_str, hash_value=hash_value)
        #             conversion_time = time.time() - start_time
        #             LOGGER.info(f"Conversion completed in {conversion_time:.2f} seconds")

        #             # Send to controller
        #             LOGGER.info(f"Sending to controller with toeid={toeid}, payload_type={payload_type}...")
        #             start_time = time.time()
        #             response = sdt_adapter.send_to_controller(converted, toeid, payload_type)
        #             controller_time = time.time() - start_time
        #             LOGGER.info(f"Controller request completed in {controller_time:.2f} seconds")

        #             # Log the response
        #             if response is not None and hasattr(response, "text"):
        #                 LOGGER.info(f"Response from controller: {response.text[:200]}...")

        #                 # Check status code for success
        #                 if 200 <= response.status_code < 300:
        #                     return JSONResponse(
        #                         content={
        #                             "success": True,
        #                             "message": "Successfully processed and sent to Ditto",
        #                             "conversion_time": conversion_time,
        #                             "controller_time": controller_time,
        #                             "status_code": response.status_code,
        #                         }
        #                     )
        #                 else:
        #                     return JSONResponse(
        #                         content={
        #                             "success": False,
        #                             "message": f"Error from controller: {response.text}",
        #                             "status_code": response.status_code,
        #                         },
        #                         status_code=response.status_code,
        #                     )
        #             else:
        #                 LOGGER.error("No response received from controller")
        #                 return JSONResponse(
        #                     content={"success": False, "message": "No response received from controller"}, status_code=500
        #                 )
        #         else:
        #             LOGGER.error("Invalid CycloneDX payload")
        #             return JSONResponse(
        #                 content={"success": False, "message": "Invalid CycloneDX payload - validation failed"},
        #                 status_code=400,
        #             )

        #     except Exception as e:
        #         LOGGER.error(f"Error processing payload: {e}")
        #         import traceback
        #         LOGGER.error(traceback.format_exc())
        #         return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

        # @self.app.post("/create", tags=["SDT Adaptor API"]) 
        # async def cyclone2dt(
        #     request: Request,
        #     toeid: str = Query(default="123456789", description="Target of Evaluation ID"),
        #     payload_type: str = Query(default="BOMS", description="Type of payload (AI or QDT)"),
        #     hash_value: str = Query(default="123456789", description="Hash value"),
        # ):
        #     """
        #     Legacy endpoint to validate and convert a CycloneDX payload.
        #     Redirects to the /api/SDT/create/ endpoint for consistency.

        #     Args:
        #         request (Request): The request object containing the CycloneDX payload.
        #         toeid (str): Target of Evaluation ID.
        #         payload_type (str): Type of payload (BOMS, AI, QDT, etc).

        #     Returns:
        #         JSONResponse: A JSON response containing the conversion status or an error message.
        #     """
        #     LOGGER.info("Received request to /create - redirecting to /api/SDT/create/")
        #     return await create_sdt(request, toeid, payload_type, hash_value)

        @self.app.post("/api/SDTM/adapt", tags=["SDT Adaptor APIs"])
        async def adapt_payload(
            request: Request,
            # payload_type: str = Query(default="cyclonedx", description="Payload payload_type: cyclonedx|oscal|arm"),
            toeid: str = Query(default="00000000-0000-0000-0000-000000000000", description="Target of Evaluation ID"),
            payload_type: str = Query(default="BOMS", description="Type of payload"),
            # thing_id: Optional[str] = Query(default=None, description="Optional custom Thing ID"),
        ):
            """
            Unified endpoint to convert different payload formats (CycloneDX, OSCAL, ARM) to Thing payload_type

            - `payload_type` selects the input payload_type
            - body should contain the parsed JSON payload for the selected payload_type
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

                # Log response details
                if response is not None and hasattr(response, "text"):
                    logger.info(f"Response from controller: {response.text[:200]}...")
                else:
                    logger.info("No response received from controller")

                return JSONResponse(content={
                    "message": f"{payload_type} payload processed and sent to SDT",
                    # "thing_id": converted.get("attributes", {}).get("thingId"),
                    # "conversion_time": conversion_time,
                    # "controller_time": controller_time,
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

            Args:
                request: MultipleFilesRequest containing list of file configurations
            
            Returns:
                JSONResponse: Summary of processed Security Artifacts and their relationships
            """
            try:
                logger.info(f"Processing {len(request.file_configs)} files...")
                
                start_time = time.time()
                things = self.manager_core.sdt_adapter.process_multiple_files([config.dict() for config in request.file_configs])
                processing_time = time.time() - start_time
                
                # Send each Thing to controller
                results = []
                controller_start = time.time()
                
                for thing in things.items():
                    try:
                        response = self.manager_core.sdt_adapter.send_to_controller(thing)
                        results.append({
                            # "thing_id": thing_id,
                            "status": "success",
                            "source_type": thing.get("attributes", {}).get("sourceType"),
                            "response_status": response.status_code if response else None
                        })
                    except Exception as e:
                        results.append({
                            # "thing_id": thing_id,
                            "status": "failed",
                            "error": str(e)
                        })
                
                controller_time = time.time() - controller_start
                
                # Count cross-references
                cross_ref_count = sum(
                    len(thing.get("_cross_references", [])) for thing in things.values()
                )
                
                return JSONResponse(content={
                    "message": "Multiple files processed and sent to SDT",
                    "total_files": len(things),
                    # "cross_references": cross_ref_count,
                    # "processing_time": processing_time,
                    # "controller_time": controller_time,
                    # "results": results
                })
            
            except Exception as e:
                logger.error(f"Error processing multiple files: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.get("/api/SDTM/adapt/cyclonedx/detect/", tags=["SDT Adaptor APIs"])
        async def detect_bom_type(request: Request):
            """
            Endpoint to detect the BOM type of a CycloneDX payload.
            
            Args:
                request: Request containing CycloneDX payload
            
            Returns:
                JSONResponse: Detected BOM type information
            """
            try:
                payload = await request.json()
                
                # Basic validation
                if not isinstance(payload, dict):
                    raise ValueError("Invalid payload payload_type")
                
                bom_type = self.manager_core.sdt_adapter.detect_bom_type(payload)
                
                # Additional analysis
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
            """
            Endpoint to validate a CycloneDX payload without conversion.
            
            Args:
                request: Request containing CycloneDX payload
                strict: Whether to use strict validation
                thorough: Whether to perform complete schema validation
            
            Returns:
                JSONResponse: Validation results
            """
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