#SDT Manager v0.0.1

The component SDT-Manager is responsible for management of the SDT lifecycle(Since the sdt is implemented as a pod in a kubernetes cluster. We focus on the pod lifecycle management)

- Primary working function is to orchestrate smooth information flow between SDT and Cobalt Orchestrator.

Current Version -> contains the files for the instantiation and deletion of pods in the kubernetes cluster that make up the SDT as whole.

containerization -> it is possible to check if the sdt component runs as an independent container in docker (before instantiating a pod)

pre-requisites
Ubuntu VM 22.04 LTS or a later LTS version
Ditto -> https://github.com/eclipse-ditto/ditto (clone the repository and make sure it works on the system using docker-compose)

SET UP ENVIRONMENT FOR KUBECTL IN PYTHON
go to bashrc file and add the line at the end -> export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

WORKING
step 1 - Copy and paste the file deploy_ditto.py into the ditto repository (located at ~/ditto)

step 2 - run the script in terminal as shown -> python3 deploy_ditto deploy-ditto (the entire kubernetes cluster with all the ditto and sdt pods are instantiated and communication)

step 3 - check if all pods of sdt are running (ditto) 
kubectl get pods -n=default (will take around 1-3 minutes)
You must see something like this
allen@sdt:~/ditto$ kubectl get pods -n=default
NAME                             READY   STATUS      RESTARTS   AGE
connectivity-67b87cddb8-9qjkl    1/1     Running     0          2m11s
ditto-logs-initiator             0/1     Completed   0          2m12s
gateway-846b97d8c8-876ks         1/1     Running     0          2m11s
mongodb-7467b5bfcf-d56kg         1/1     Running     0          2m12s
nginx-7bd66f4b5-6qvj7            1/1     Running     0          2m9s
policies-669c895f7-hjqhk         1/1     Running     0          2m11s
swagger-ui-5f4ddfb595-zq6tl      1/1     Running     0          2m10s
things-6c4d5684bb-mhfvq          1/1     Running     0          2m11s
things-search-7df4f84ff7-v628n   1/1     Running     0          2m11s

step 4 -> in a new terminal run "kubectl apply -f sdt-pod-with-ditto-k3s.yaml"

check if pod has been instantiated and added to the same namespace as the ditto pods

allen@sdt:~/ditto$ kubectl get pods
NAME                             READY   STATUS      RESTARTS   AGE
connectivity-67b87cddb8-9qjkl    1/1     Running     0          12m
ditto-logs-initiator             0/1     Completed   0          12m
gateway-846b97d8c8-876ks         1/1     Running     0          12m
mongodb-7467b5bfcf-d56kg         1/1     Running     0          12m
nginx-7bd66f4b5-6qvj7            1/1     Running     0          12m
policies-669c895f7-hjqhk         1/1     Running     0          12m
sdt-deployment-6b46d87fc-z8b9m   1/1     Running     0          6s
swagger-ui-5f4ddfb595-zq6tl      1/1     Running     0          12m
things-6c4d5684bb-mhfvq          1/1     Running     0          12m
things-search-7df4f84ff7-v628n   1/1     Running     0          12m


step 4 - verify if the pipeline of the sdt has been performed (obtaining information fromt he ToE and creating a DT in Ditto)
run -> kubectl logs <sdt deployment name>

allen@sdt:~/ditto$ kubectl logs sdt-deployment-6b46d87fc-z8b9m
Starting api-adapter...
Waiting for api-adapter to be ready...
INFO:     Started server process [7]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:51840 - "GET / HTTP/1.1" 200 OK
api-adapter is ready!
Starting api-controller...
Waiting for api-controller to be ready...
INFO:     Started server process [11]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8005 (Press CTRL+C to quit)
INFO:     127.0.0.1:55528 - "GET / HTTP/1.1" 200 OK
api-controller is ready!
Starting bom_provider...
Starting toe_provider...
{"policyId": "cobalt:policy", "definition": "cobalt:clouditor-resource:0.0.1", "attributes": {"id": "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/DemoClouditorHappy/providers/Microsoft.Sto
.
.
.
 'type': 'library', 'version': '2.32.3'}]}}, 'sbom_dependencies': {'properties': {'dependencies': [{'ref': 'requirements-L1'}, {'ref': 'requirements-L2'}, {'ref': 'requirements-L3'}, {'ref': 'requirements-L4'}, {'ref': 'requirements-L5'}, {'ref': 'requirements-L6'}]}}}}
INFO:     127.0.0.1:55566 - "POST /api/create/ HTTP/1.1" 200 OK
INFO:api-adapter:DT created
New DTModelAdapter instance created.
INFO:     127.0.0.1:51882 - "POST /api/sbom2dt/ HTTP/1.1" 200 OK
CBOM API Response: 200
{'message': 'Sent to Ditto', 'response': 'DT created'}
SBOM API Response: 200
{'message': 'Sent to Ditto', 'response': 'DT created'}

NOTE: the DT has been created in the SDT from the information received from the toe provider.

DELETION OF SDT AND DITTO PODS IN THE KUBERNETES CLUSTER
copy the file 'delete_k3s_cluster.py' and paste it into ~/ditto repository
to destroy the pods (not the kubernetes cluster), run the command -> python3  delete_k3s_cluster.py
verify the pods of sdt have been deleted
allen@sdt:~/ditto$ kubectl get pods
No resources found in default namespace.


THE NEXT STEP IS TO INCLUDE THE INSTANTIATION OF THE SDT POD ALONG WITH DITTO

copy and paste the deploy_sdt_n_ditto.py file in the ditto folder (~/ditto) and then run it in the terminal as shown below:
"python3 deploy_sdt_n_ditto.py deploy-ditto-sdt"

once script has finished executing confirm if the pods are running in the cluster running the command -> kubectl get pods -n=default (you should see the sdt pod along with other ditto pods)

allen@sdt:~/ditto$ kubectl get pods
NAME                             READY   STATUS      RESTARTS   AGE
connectivity-67b87cddb8-sdd49    1/1     Running     0          2m8s
ditto-logs-initiator             0/1     Completed   0          2m8s
gateway-846b97d8c8-sqbrv         1/1     Running     0          2m7s
mongodb-7467b5bfcf-tp4rp         1/1     Running     0          2m8s
nginx-7bd66f4b5-j7pcx            1/1     Running     0          2m6s
policies-669c895f7-z5pj7         1/1     Running     0          2m7s
sdt-deployment-6b46d87fc-lsgmn   1/1     Running     0          6s
swagger-ui-5f4ddfb595-zpfsb      1/1     Running     0          2m7s
things-6c4d5684bb-lrxbc          1/1     Running     0          2m8s
things-search-7df4f84ff7-5xwz4   1/1     Running     0          2m7s




