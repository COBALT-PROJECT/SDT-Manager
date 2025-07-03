# File: ccm_manager_interface.py

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

class CCM_Manager_Interface:
    """North Bound Interface for SDT Manager using FastAPI"""
    
    class DeploymentResponse(BaseModel):
        """Response model for deployment operations"""
        success: bool
        message: str
        pod_name: Optional[str] = None
        identifier: Optional[str] = None

    class DeletionRequest(BaseModel):
        """Request model for deletion operations"""
        identifier: str
    
    def __init__(self, manager_core):
        """Initialize with reference to the SDT Manager Core"""
        self.manager_core = manager_core
        self.app = FastAPI(
            title="SDT Deployment API",
            description="API for managing SDT deployments in Kubernetes"
        )
        self._setup_routes()
        LOGGER.info("CCM Manager Interface initialized")
    
    def _setup_routes(self):
        """Setup the API routes"""
        
        @self.app.post("/deploy", response_model=self.DeploymentResponse)
        async def deploy_sdt():
            """Deploy an SDT pod and service"""
            try:
                # Deploy using the manager's lifecycle component
                pod_name, identifier = self.manager_core.lifecycle_manager.deploy()
                
                if pod_name and identifier:
                    return self.DeploymentResponse(
                        success=True,
                        message="SDT deployment successful",
                        pod_name=pod_name,
                        identifier=identifier
                    )
                else:
                    raise HTTPException(status_code=500, detail="Deployment failed - no pod information available")
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

        @self.app.post("/delete", response_model=self.DeploymentResponse)
        async def delete_sdt(deletion_request: self.DeletionRequest):
            """Delete an SDT deployment by identifier"""
            try:
                # Verify the identifier exists in the pod map
                identifier_exists = any(
                    id_val == deletion_request.identifier 
                    for id_val in self.manager_core.lifecycle_manager.pod_map.values()
                )
                
                if not identifier_exists:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"No deployment found with identifier {deletion_request.identifier}"
                    )
                
                # Delete using the manager
                deletion_results = self.manager_core.lifecycle_manager.delete_deployment_by_id(
                    deletion_request.identifier
                )
                
                if deletion_results.get(deletion_request.identifier, False):
                    return self.DeploymentResponse(
                        success=True,
                        message=f"Successfully deleted deployment with identifier {deletion_request.identifier}",
                        identifier=deletion_request.identifier
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to delete deployment with identifier {deletion_request.identifier}"
                    )
                    
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

        @self.app.get("/deployments")
        async def list_deployments():
            """List all current SDT deployments"""
            try:
                deployments = self.manager_core.lifecycle_manager.list_available_deployments()
                return {"deployments": deployments}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to list deployments: {str(e)}")
            
        @self.app.post("/api/SDT/create/")
        async def create_sdt(request: Request, 
                              toeid: str = Query(default="123456789", description="Target of Evaluation ID"), 
                              payload_type: str = Query(default="BOMS", description="Type of payload "),
                              hash_value: str = Query(default="123456789", description="Hash value")):
            """
            Endpoint to validate and convert a CycloneDX payload sent to SDT interface.
            
            Args:
                request (Request): The request object containing the CycloneDX payload.
                toeid (str): Target of Evaluation ID.
                payload_type (str): Type of payload (BOMS, AI, QDT, etc).
                
            Returns:
                JSONResponse: A JSON response containing the conversion status or an error message.
            """
            LOGGER.info(f"Received create request with toeid={toeid}, payload_type={payload_type}")
            try:
                # Get the adapter from the manager core
                sdt_adapter = self.manager_core.sdt_adapter
                
                # Receive the payload
                LOGGER.info("Receiving payload...")
                try:
                    payload = await request.json()
                    if not payload:
                        raise ValueError("Empty payload received")
                except Exception as e:
                    LOGGER.error(f"Failed to parse request body as JSON: {e}")
                    return JSONResponse(
                        content={"error": "Invalid JSON payload"}, 
                        status_code=400
                    )
                
                # Validate and process the payload
                LOGGER.info(f"Processing payload, validating CycloneDX...")
                conversion_time = 0
                controller_time = 0
                
                # Validate the CycloneDX payload
                if sdt_adapter.validate_cyclonedx_smart(payload, strict=False, thorough=False):
                    LOGGER.info("Validation successful, converting to Thing structure...")
                    json_payload_str = json.dumps(payload)
                    
                    # Convert CycloneDX to DT structure
                    start_time = time.time()
                    converted = sdt_adapter.from_cyclone(json_payload_str, hash_value=hash_value)
                    conversion_time = time.time() - start_time
                    LOGGER.info(f"Conversion completed in {conversion_time:.2f} seconds")
                    
                    # Send to controller
                    LOGGER.info(f"Sending to controller with toeid={toeid}, payload_type={payload_type}...")
                    start_time = time.time()
                    response = sdt_adapter.send_to_controller(converted, toeid, payload_type)
                    controller_time = time.time() - start_time
                    LOGGER.info(f"Controller request completed in {controller_time:.2f} seconds")
                    
                    # Log the response
                    if response is not None and hasattr(response, 'text'):
                        LOGGER.info(f"Response from controller: {response.text[:200]}...")
                        
                        # Check status code for success
                        if response.status_code >= 200 and response.status_code < 300:
                            return JSONResponse(content={
                                "success": True,
                                "message": "Successfully processed and sent to Ditto", 
                                "conversion_time": conversion_time,
                                "controller_time": controller_time,
                                "status_code": response.status_code
                            })
                        else:
                            return JSONResponse(content={
                                "success": False,
                                "message": f"Error from controller: {response.text}",
                                "status_code": response.status_code
                            }, status_code=response.status_code)
                    else:
                        LOGGER.error("No response received from controller")
                        return JSONResponse(content={
                            "success": False,
                            "message": "No response received from controller"
                        }, status_code=500)
                else:
                    LOGGER.error("Invalid CycloneDX payload")
                    return JSONResponse(content={
                        "success": False,
                        "message": "Invalid CycloneDX payload - validation failed"
                    }, status_code=400)
            
            except Exception as e:
                LOGGER.error(f"Error processing payload: {e}")
                import traceback
                LOGGER.error(traceback.format_exc())
                return JSONResponse(content={
                    "success": False,
                    "error": str(e)
                }, status_code=500)

        @self.app.post("/create")
        async def cyclone2dt(request: Request, 
                              toeid: str = Query(default="123456789", description="Target of Evaluation ID"), 
                              payload_type: str = Query(default="BOMS", description="Type of payload (AI or QDT)"),
                              hash_value: str = Query(default="123456789", description="Hash value")):
            """
            Legacy endpoint to validate and convert a CycloneDX payload.
            Redirects to the /api/SDT/create/ endpoint for consistency.
            
            Args:
                request (Request): The request object containing the CycloneDX payload.
                toeid (str): Target of Evaluation ID.
                payload_type (str): Type of payload (BOMS, AI, QDT, etc).
                
            Returns:
                JSONResponse: A JSON response containing the conversion status or an error message.
            """
            LOGGER.info("Received request to /create - redirecting to /api/SDT/create/")
            return await create_sdt(request, toeid, payload_type, hash_value)
    
    def start_server(self, host="0.0.0.0", port=8008):
        """Start the FastAPI server"""
        LOGGER.info(f"Starting CCM Manager API server on {host}:{port}")
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