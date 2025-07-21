# File: sdt_api.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional
import uvicorn
from sdt_manager import SDTManager

app = FastAPI(
    title="SDT Deployment API",
    description="API for managing SDT deployments in Kubernetes"
)

# Initialize the SDT Manager
sdt_manager = SDTManager()

class DeploymentResponse(BaseModel):
    """Response model for deployment operations"""
    success: bool
    message: str
    pod_name: Optional[str] = None
    identifier: Optional[str] = None

class DeletionRequest(BaseModel):
    """Request model for deletion operations"""
    identifier: str

@app.post("/deploy", response_model=DeploymentResponse)
async def deploy_sdt():
    """Deploy an SDT pod and service"""
    try:
        # Deploy using the manager
        sdt_manager.deploy()
        
        # Get the latest deployment info from the pod map
        pod_info = next(iter(sdt_manager.deployer.pod_map.items()), None)
        if pod_info:
            pod_name, identifier = pod_info
            return DeploymentResponse(
                success=True,
                message="SDT deployment successful",
                pod_name=pod_name,
                identifier=identifier
            )
        else:
            raise HTTPException(status_code=500, detail="Deployment failed - no pod information available")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

@app.post("/delete", response_model=DeploymentResponse)
async def delete_sdt(deletion_request: DeletionRequest):
    """Delete an SDT deployment by identifier"""
    try:
        # Verify the identifier exists in the pod map
        identifier_exists = any(
            id_val == deletion_request.identifier 
            for id_val in sdt_manager.deployer.pod_map.values()
        )
        
        if not identifier_exists:
            raise HTTPException(
                status_code=404, 
                detail=f"No deployment found with identifier {deletion_request.identifier}"
            )
        
        # Delete using the manager
        deletion_results = sdt_manager.delete_sdt_deployment_by_id(deletion_request.identifier)
        
        if deletion_results.get(deletion_request.identifier, False):
            return DeploymentResponse(
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

@app.get("/deployments")
async def list_deployments():
    """List all current SDT deployments"""
    try:
        pod_map = sdt_manager.deployer.pod_map
        deployments = [
            {
                "pod_name": pod_name,
                "identifier": identifier,
                "deployment_name": sdt_manager.cleaner.get_deployment_name_from_pod_name(pod_name)
            }
            for pod_name, identifier in pod_map.items()
        ]
        return {"deployments": deployments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list deployments: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
