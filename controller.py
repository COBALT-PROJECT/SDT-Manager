import json
import requests
import os

#the class which defines the SDT Controller object
class Controller():
    """
    A class implementing the Controller to send the translated data from adaptor to eclipse ditto.

    ...

    Attributes
    ----------
    __source_file : String
        a String defining...

    Methods
    -------
    translate(s, t, model)
        Method to...

    """

    def __init__(self):
        #we are gonna set ip for url call to dockergateway because this is the equivalent to localhost:8080, the container docker_nginx_1 of ditto was bound to port 8080 of the ubuntu VM.
        self.ip = os.getenv("DITTO_HOST", "docker_nginx_1") #we contact the container directly by-passing the VM
        self.port = 80

    def __create_policy(self):
        try:
            f = '/app/test_files/policy.json'
            with open(f, 'r') as json_data:
                #payload = json.loads(json_data.read())
                payload = json_data.read()
                json_data.close()
                print(payload)
        except Exception as e:
            print(e)


        #return
        #ip = '10.0.1.174'
        #ip = '127.0.0.1' #when you are running the component as a software on the localhost
        #ip = "docker_policies_1" #the ditto container responsible for creating policy
        url = f"http://{self.ip}:{self.port}/api/2/policies/cobalt:policy"
        try:
            print("Send policy to Ditto!")
            session = requests.Session()
            session.auth = ("ditto", "ditto") #the default username and password to access ditto
            r = session.put(url, json=json.loads(payload), headers={'Content-Type': 'application/json'})
            print(r.json())
            return r
        except Exception as e:
            print(e)
        return None

    def create_in_ditto(self, payload):
        self.__create_policy()
        url = f"http://{self.ip}:{self.port}/api/2/things/"
        try:
            print("Send DT model to Ditto!")

            session = requests.Session()
            session.auth = ("ditto", "ditto")
            r = session.post(url, json=json.loads(payload), headers={'Content-Type': 'application/json'})
            print(r.json())
            return r

            # session = requests.Session()
            # session.auth = ("ditto", "ditto")
            # r = session.post("http://10.0.1.174:8080/api/2/things/", json=payload, headers={'Content-Type': 'application/json'})
            # thing_id = payload["thingId"]
            # r = session.put("http://10.0.1.174:8080/api/2/things/"+thing_id, json=payload, headers={'Content-Type': 'application/json'})

        except Exception as e:
            print(e)
        return None

    def update_in_ditto(self, payload):
        print(payload)
        ip = 'sdt_container'
        port = 8080 #the port on which ditto runs on.
        #url = 'http://' + ip + ':' + str(port) + 

        return 
