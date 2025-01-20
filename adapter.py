import json

import requests


class DTModelAdapter():
    """
    A class implementing the adapter to translate different data models to the DT model and vice-versa.

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
        print("New DTModelAdapter instance created.")

    def send_to_controller(self, payload):
        # print(payload)
        #we send information in digital twin model to the controller to create a digital twin in ditto
        url = 'http://127.0.0.1:8005/api/create/' 
        try:
            r = requests.post(url, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
            return r

            #session = requests.Session()
            #session.auth = ("ditto", "ditto")
            #r = session.post("http://10.0.1.174:8080/api/2/things/", json=payload, headers={'Content-Type': 'application/json'})

        except Exception as e:
            print(e)
        return

    def from_clouditor(self, s):
        r = self.__from_clouditor(s)
        return r

    def to_clouditor(self, s):
        r = self.__to_clouditor(s)
        return r
    
    def from_cloud(self, s):
        r = self.__from_cloud(s)
        return r

    def __from_clouditor(self, s):
        translated=[]
        resource = "resource"
        attributes = [] #["id", "timestamp"]
        resource_attributes = ["@type", "id", "name", "creationTime", "labels", "internetAccessibleEndpoint", "raw"] #["@type", "creationTime", "internetAccessibleEndpoint", "labels", "name", "publicAccess","raw"]
        resource_excluded = []
        try:

            s_data = s
            '''
            with open(s, 'r') as json_data:
                s_data = json.loads(json_data.read())
                json_data.close()
            '''

            entry = {}
            #entry["thingId"] = "cobalt:" + s_data["id"]
            entry["policyId"] = "cobalt:policy"
            entry["definition"] = "cobalt:clouditor-resource:0.0.1"
            entry["attributes"] = {}
            for i in attributes:
                try:
                    entry["attributes"][i] = s_data[i]
                except Exception as e:
                    pass

            s_data = s_data[resource]
            for i in resource_attributes:
                try:
                    entry["attributes"][i] = s_data[i]
                except Exception as e:
                    pass

            entry["features"] = {}

            for i in s_data:
                if i not in resource_attributes:
                    if i not in resource_excluded:
                        try:
                            entry["features"][i] = {}
                            entry["features"][i]["properties"] = {}
                            if isinstance(s_data[i], dict):
                                entry["features"][i]["properties"] = {}
                                entry["features"][i]["properties"] = s_data[i]
                            else:
                                entry["features"][i]["properties"][i] = {}
                                entry["features"][i]["properties"][i] = s_data[i]
                        except Exception as e:
                            pass

            # t_json = json.dumps(entry)
            # with open('test.json', 'w', encoding='utf-8') as f:
            #    json.dump(entry,f,ensure_ascii=False, indent=4)

            # print(t_json)
            print(entry)
            translated.append(entry)
            return translated
        except Exception as e:
            print(e)

        # t_json = json.dumps(s_data["resource"])

        return None

    def __to_clouditor(self, s):
        resource = "resource"
        attributes = [] #["id", "timestamp"]
        resource_attributes = ["@type", "id", "name", "creationTime", "labels", "internetAccessibleEndpoint", "raw"] #["@type", "creationTime", "internetAccessibleEndpoint", "labels", "name", "publicAccess","raw"]
        resource_excluded = []
        try:

            s_data = s
            '''
            with open(s, 'r') as json_data:
                s_data = json.loads(json_data.read())
                json_data.close()
            '''

            entry = {}
            entry[s_data["definition"]] = []
            #entry[s_data["definition"]].append(s_data["attributes"])

            tmp = s_data["attributes"]

            tmp["properties"] = {}
            for i in s_data["features"]:
                tmp["properties"][i] = {}
                if i in s_data["features"][i]["properties"]:
                    tmp["properties"][i] = s_data["features"][i]["properties"][i]
                else:
                    tmp["properties"][i] = s_data["features"][i]["properties"]

            entry[s_data["definition"]].append(tmp)

            '''
            entry["definition"] = "cobalt:clouditor-resource:0.0.1"
            entry["attributes"] = {}
            for i in attributes:
                try:
                    entry["attributes"][i] = s_data[i]
                except Exception as e:
                    pass

            s_data = s_data[resource]
            for i in resource_attributes:
                try:
                    entry["attributes"][i] = s_data[i]
                except Exception as e:
                    pass

            entry["features"] = {}

            for i in s_data:
                if i not in resource_attributes:
                    if i not in resource_excluded:
                        try:
                            entry["features"][i] = {}
                            entry["features"][i]["properties"] = {}
                            if isinstance(s_data[i], dict):
                                entry["features"][i]["properties"] = {}
                                entry["features"][i]["properties"] = s_data[i]
                            else:
                                entry["features"][i]["properties"][i] = {}
                                entry["features"][i]["properties"][i] = s_data[i]
                        except Exception as e:
                            pass

            # t_json = json.dumps(entry)
            # with open('test.json', 'w', encoding='utf-8') as f:
            #    json.dump(entry,f,ensure_ascii=False, indent=4)
            '''
            # print(t_json)
            print(json.dumps(entry))
            #return json.dumps(entry)

        except Exception as e:
            print(e)

        # t_json = json.dumps(s_data["resource"])

        return None

    def __from_cloud(self, s):

        translated = []
        try:
            s_data = s
            for i in s_data:
                try:

                    n = -1
                    for j in s_data[i]:
                        n += 1

                        entry = {}
                        # entry["thingId"] = "cobalt:test"
                        entry["policyId"] = "cobalt:policy"
                        entry["definition"] = "cobalt:clouditor-resource:0.0.1"
                        entry["attributes"] = {}
                        entry["features"] = {}


                        #entry["features"][i]["properties"] = {}

                        for k in j:
                            if k != "properties":
                                entry["attributes"][k] = {}
                                entry["attributes"][k] = s_data[i][n][k]
                            else:
                                for l in s_data[i][n][k]:
                                    entry["features"][l] = {}
                                    entry["features"][l]["properties"] = {}
                                    if isinstance(s_data[i][n][k][l], dict):

                                        entry["features"][l]["properties"] = s_data[i][n][k][l]
                                    else:
                                        entry["features"][l]["properties"][l] = {}
                                        entry["features"][l]["properties"][l] = s_data[i][n][k][l]

                    '''
                    print(entry)
                    session = requests.Session()
                    session.auth = ("ditto", "ditto")
                    r = session.post("http://10.0.1.174:8080/api/2/things/", json=entry, headers={'Content-Type': 'application/json'})
                    print(r.json())
                    '''

                    translated.append(json.dumps(entry))

                except Exception as e:
                    print(e)

            return translated

        except Exception as e:
            print(e)

        # t_json = json.dumps(s_data["resource"])

        return None

    # def __from_cloud3(self, s):
    #     translated=[]
    #     try:
    #         s_data = s

    #         entry = {}
    #         #entry["thingId"] = "cobalt:test"
    #         entry["policyId"] = "cobalt:policy"
    #         entry["definition"] = "cobalt:clouditor-resource:0.0.1"
    #         entry["attributes"] = {}
    #         entry["features"] = {}

    #         for i in s_data:
    #             try:
    #                 #entry["attributes"][i] = {}
    #                 n = -1
    #                 for j in s_data[i]:
    #                     n += 1

    #                     entry["attributes"][i+"."+str(n)] = {}

    #                     entry["features"][i+"."+str(n)] = {}
    #                     entry["features"][i+"."+str(n)]["properties"] = {}

    #                     for k in j:
    #                         if k != "properties":
    #                             entry["attributes"][i+"."+str(n)][k] = {}
    #                             entry["attributes"][i+"."+str(n)][k] = s_data[i][n][k]
    #                         else:
    #                             entry["features"][i+"."+str(n)]["properties"] = {}
    #                             entry["features"][i+"."+str(n)]["properties"] = s_data[i][n][k]

    #             except Exception as e:
    #                 print(e)
    #         '''
    #         for i in s_data:
    #             try:
    #                 entry["features"][i] = {}
    #                 entry["features"][i]["properties"] = {}
    #                 n = -1
    #                 for j in s_data[i]:
    #                     n += 1
    #                     for k in j:

    #                         if k == "properties":
    #                             entry["features"][i]["properties"][n] = {}
    #                             entry["features"][i]["properties"][n] = s_data[i][n][k]

    #             except Exception as e:
    #                 print("Error"+str(e))
    #         '''
    #         print(entry)

    #         #session = requests.Session()
    #         #session.auth = ("ditto", "ditto")
    #         #r = session.post("http://10.0.1.174:8080/api/2/things/", json=entry, headers={'Content-Type': 'application/json'})

    #         translated.append(entry)
    #         return translated

    #     except Exception as e:
    #         print(e)

    #     # t_json = json.dumps(s_data["resource"])

    #     return None

    # def __from_cloud2(self, s):
    #     translated=[]
    #     try:
    #         s_data = s

    #         entry = {}
    #         #entry["thingId"] = "cobalt:test"
    #         entry["policyId"] = "cobalt:policy"
    #         entry["definition"] = "cobalt:clouditor-resource:0.0.1"
    #         entry["attributes"] = {}
    #         entry["features"] = {}

    #         for i in s_data:
    #             try:
    #                 entry["attributes"][i] = {}
    #                 n = -1
    #                 for j in s_data[i]:
    #                     n += 1

    #                     entry["attributes"][i][n] = {}

    #                     entry["features"][i] = {}
    #                     entry["features"][i]["properties"] = {}

    #                     for k in j:
    #                         if k != "properties":
    #                             entry["attributes"][i][n][k] = {}
    #                             entry["attributes"][i][n][k] = s_data[i][n][k]
    #                         else:
    #                             entry["features"][i]["properties"][n] = {}
    #                             entry["features"][i]["properties"][n] = s_data[i][n][k]

    #             except Exception as e:
    #                 print(e)
    #         '''
    #         for i in s_data:
    #             try:
    #                 entry["features"][i] = {}
    #                 entry["features"][i]["properties"] = {}
    #                 n = -1
    #                 for j in s_data[i]:
    #                     n += 1
    #                     for k in j:

    #                         if k == "properties":
    #                             entry["features"][i]["properties"][n] = {}
    #                             entry["features"][i]["properties"][n] = s_data[i][n][k]

    #             except Exception as e:
    #                 print("Error"+str(e))
    #         '''
    #         print(entry)

    #         #session = requests.Session()
    #         #session.auth = ("ditto", "ditto")
    #         #r = session.post("http://10.0.1.174:8080/api/2/things/", json=entry, headers={'Content-Type': 'application/json'})
    #         translated.append(entry)
    #         return translated#json.dumps(entry)

    #     except Exception as e:
    #         print(e)

    #     # t_json = json.dumps(s_data["resource"])

    #     return None

    def from_CCM_cbom(self, cbom_content):
        """
        Transforms a CBOM (Cryptographic Bill of Materials) file into a new structure with attributes and components.

        Args:
            cbom_content (dict): The parsed JSON content of the CBOM file.

        Returns:
            dict: A dictionary representing the transformed CBOM.
        """
        # Extract metadata and components
        metadata = cbom_content.get("metadata", {})
        components = cbom_content.get("components", [])

        # Create the attributes section from metadata
        attributes = {
            "bomFormat": cbom_content.get("bomFormat"),
            "specVersion": cbom_content.get("specVersion"),
            "serialNumber": cbom_content.get("serialNumber"),
            "version": cbom_content.get("version"),
            "timestamp": metadata.get("timestamp"),
            "component": metadata.get("component", {}).get("name"),
            "version": metadata.get("component", {}).get("version")
        }

        # Rename components to features
        features = {}
        for component in components:
            name = component.get("name")
            properties = component.get("cryptoProperties")
            features[name] = {
                "properties": properties
            }

        # Create the new structure
        transformed_cbom = {
            "policyId" : "cobalt:policy",
            "definition": "cobalt:clouditor-resource:0.0.1",
            "attributes": attributes,
            "features": features
        }

        return transformed_cbom

    def from_CCM_sbom(self, sbom_content):
        """
        Transforms an SBOM (Software Bill of Materials) file into a new structure with attributes and components.

        Args:
            sbom_content (dict): The parsed JSON content of the SBOM file.

        Returns:
            dict: A dictionary representing the transformed SBOM.
        """
        # Create the features section from Components, metadata and Dependencies
        features = {
            "sbom_metadata": {"properties": sbom_content.get("metadata", {})},
            "sbom_components": {"properties": {"components": sbom_content.get("components", [])}},
            "sbom_dependencies": {"properties": {"dependencies": sbom_content.get("dependencies", [])}}
        }

        # Create the attributes section
        attributes = {
            "serialNumber": sbom_content.get("serialNumber", ""),
            "version": sbom_content.get("version", ""),
            "bomFormat": sbom_content.get("bomFormat", ""),
            "specVersion": sbom_content.get("specVersion", ""),
            "schema": sbom_content.get("$schema", "")
        }
        
        # Create the new structure
        transformed_sbom = {
            "policyId" : "cobalt:policy",
            "definition" : "cobalt:clouditor-resource:0.0.1",
            "attributes": attributes,
            "features": features,
   
        }

        return transformed_sbom

