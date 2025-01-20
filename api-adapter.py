import requests
import uvicorn
import json
import logging
import os

from adapter import *
from fastapi import Request, FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "DT Model Adapter API"}

@app.post("/api/clouditor2dt/")
async def clouditor2dt(request: Request):
    payload = await request.json()
    adapter = DTModelAdapter()
    translated = adapter.from_cloud(payload)

    ret = []
    for i in translated:
        payload = json.loads(i)
        r = adapter.send_to_controller(payload)
        logger.info(r.json())
        ret.append(payload)
    return JSONResponse(content=ret)

@app.post("/api/cbom2dt/")
async def cbom2dt(file: UploadFile = File(...)):
    """
    Endpoint to upload a CBOM (Cryptographic Bill of Materials) file and convert it using from_CCM_cbom.

    Args:
        file (UploadFile): The CBOM file to be uploaded.

    Returns:
        dict: A dictionary representing the converted CBOM.
    """
    try:
        # Read the file content
        content = await file.read()
        payload = json.loads(content)
        
        # Use the adapter to convert the CBOM
        adapter = DTModelAdapter()
        converted = adapter.from_CCM_cbom(payload)
        
        # Save the converted output to sdt_output directory
        output_dir = "/app/sdt_output" #when you are running SDT on the localhost
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "cbom_sdt_thing.json")
        logger.info("json file has been written into sdt_output directory")
        with open(output_path, "w") as f:
            json.dump(converted, f, indent=4)
        
        # Send the converted payload to the controller
        response = adapter.send_to_controller(converted)
        logger.info(response.json())
        
        return JSONResponse(content={"message": "Sent to Ditto", "response": response.json()})
    except Exception as e:
        logger.error(f"Error processing CBOM file: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    
@app.post("/api/sbom2dt/")
async def sbom2dt(file: UploadFile = File(...)):
    """
    Endpoint to upload an SBOM (Software Bill of Materials) file and convert it using from_CCM_sbom.

    Args:
        file (UploadFile): The SBOM file to be uploaded.

    Returns:
        dict: A dictionary representing the converted SBOM.
    """
    try:
        # Read the file content
        content = await file.read()
        payload = json.loads(content)
        
        # Use the adapter to convert the SBOM
        adapter = DTModelAdapter()
        converted = adapter.from_CCM_sbom(payload)
        
        # Save the converted output to sdt_output directory
        output_dir = "/app/sdt_output" #when you are running SDT on localhost
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "sbom_sdt_thing.json")
        logger.info("json file has been written into sdt_output directory")
        with open(output_path, "w") as f:
            json.dump(converted, f, indent=4)
        
        # Send the converted payload to the controller
        response = adapter.send_to_controller(converted)
        logger.info(response.json())
        
        return JSONResponse(content={"message": "Sent to Ditto", "response": response.json()})
    except Exception as e:
        logger.error(f"Error processing SBOM file: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

