#this is the api to interface/talk with the SDT Controller
import requests
import uvicorn
import json
from adapter import *
from fastapi import Request, FastAPI
#TODO: GraphQL
from controller import Controller

app = FastAPI()
ctrl = Controller() #instance of SDT-Controller is created.

@app.get("/")
async def root():
    return "DT Controller API"

@app.post("/api/create/")
async def create(request: Request):
    """
    Endpoint to create a Digital Twin (DT) in Ditto.

    This endpoint receives a JSON payload from the request, processes it, 
    and sends it to the Ditto service to create a new Digital Twin.

    Args:
        request (Request): The incoming HTTP request containing the JSON payload.

    Returns:
        str: A confirmation message indicating that the Digital Twin has been created.

    Note:
        The function currently prints the payload and calls the `create_in_ditto` method 
        from the `ctrl` module to handle the creation in Ditto. The commented-out code 
        shows an alternative approach using the `requests` library to send the payload 
        to a Ditto instance running at a specified IP address.
    """
    payload = await request.json()
    payload = json.dumps(payload)
    print(payload)
    ctrl.create_in_ditto(payload)
    #session = requests.Session()
    #session.auth = ("ditto", "ditto")
    #r = session.post("http://10.0.1.174:8080/api/2/things/", json=payload, headers={'Content-Type': 'application/json'})
    # thing_id = payload["thingId"]
    #r = session.put("http://10.0.1.174:8080/api/2/things/"+thing_id, json=payload, headers={'Content-Type': 'application/json'})
    #return r
    return "DT created" #payload

#if __name__ == '__main__':
#we define the fast api server to run on port 8005
#we set host as 0.0.0.0 so it listens on port 8005 of all its interfaces, that was if ditto or client(from localhost machine) wants to communicate they can
uvicorn.run(app, port=8005, host='0.0.0.0')