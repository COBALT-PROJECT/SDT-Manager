import requests
import json

# Define the file path
file_path = 'sdt_output/cbom_format.json'

# Define the API endpoint
api_url = 'http://127.0.0.1:8005/api/create/'

# Function to read JSON file
def read_json_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Function to send POST request with JSON data
def send_post_request(url, data):
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, json=data)
    return response

# Read the JSON file and send the request
data = read_json_file(file_path)
response = send_post_request(api_url, data)

# Print the response
print(f'API Response: {response.status_code}')
print(response.json())