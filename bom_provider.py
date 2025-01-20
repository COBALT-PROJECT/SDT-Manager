import requests

# Define the file paths
cbom_file_path = '/app/test_files/CCM-Output/cbom/algorithm_sbom_20241118144135.json'
sbom_file_path = '/app/test_files/CCM-Output/sbom/sbom.json'

# Define the API endpoints
cbom_api_url = 'http://127.0.0.1:8000/api/cbom2dt'
sbom_api_url = 'http://127.0.0.1:8000/api/sbom2dt'

# Function to send POST request with file
def send_post_request_with_file(url, file_path):
    with open(file_path, 'rb') as file:
        files = {'file': file}
        response = requests.post(url, files=files)
    return response

# Send the CBOM file and print the response
cbom_response = send_post_request_with_file(cbom_api_url, cbom_file_path)
print(f'CBOM API Response: {cbom_response.status_code}')
print(cbom_response.json())

# Send the SBOM file and print the response
sbom_response = send_post_request_with_file(sbom_api_url, sbom_file_path)
print(f'SBOM API Response: {sbom_response.status_code}')
print(sbom_response.json())