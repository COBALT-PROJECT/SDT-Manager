#!/usr/bin/env python3
"""
Containerized IDS Provider-Consumer Synchronization Service

This service runs in Kubernetes and synchronizes TextResources 
from Provider to Consumer with full configuration via environment variables.

Author: IDS Team
Date: July 29, 2025
"""

import requests
import json
import time
import logging
import os
import sys
from datetime import datetime
from requests.auth import HTTPBasicAuth
import urllib3
from typing import Dict, List, Set, Optional
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoint"""
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Get sync service status
            sync_service = getattr(self.server, 'sync_service', None)
            if sync_service:
                health_data = {
                    "status": "healthy" if sync_service.running else "stopped",
                    "uptime_seconds": (datetime.now() - sync_service.sync_stats["start_time"]).total_seconds(),
                    "total_synced": sync_service.sync_stats["total_synced"],
                    "errors": sync_service.sync_stats["errors"],
                    "last_sync": sync_service.sync_stats["last_sync"].isoformat() if sync_service.sync_stats["last_sync"] else None,
                    "tracked_resources": len(sync_service.known_resources)
                }
            else:
                health_data = {"status": "starting"}
            
            self.wfile.write(json.dumps(health_data).encode())
        elif self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            
            # Prometheus-style metrics
            sync_service = getattr(self.server, 'sync_service', None)
            if sync_service:
                metrics = f"""# HELP ids_sync_resources_synced_total Total number of resources synced
# TYPE ids_sync_resources_synced_total counter
ids_sync_resources_synced_total {sync_service.sync_stats["total_synced"]}

# HELP ids_sync_errors_total Total number of sync errors
# TYPE ids_sync_errors_total counter
ids_sync_errors_total {sync_service.sync_stats["errors"]}

# HELP ids_sync_resources_tracked Number of resources currently tracked
# TYPE ids_sync_resources_tracked gauge
ids_sync_resources_tracked {len(sync_service.known_resources)}

# HELP ids_sync_service_up Service status (1 = up, 0 = down)
# TYPE ids_sync_service_up gauge
ids_sync_service_up {1 if sync_service.running else 0}
"""
            else:
                metrics = "ids_sync_service_up 0\n"
            
            self.wfile.write(metrics.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP access logs
        pass

class ContainerizedIDSSyncService:
    def __init__(self):
        # Configuration from environment variables
        self.provider_url = os.getenv('PROVIDER_URL', 'https://tc-provider:8090')
        self.consumer_url = os.getenv('CONSUMER_URL', 'https://tc-consumer:8444')
        self.username = os.getenv('IDS_USERNAME', 'admin')
        self.password = os.getenv('IDS_PASSWORD', 'password')
        
        # State tracking
        self.known_resources: Set[str] = set()
        self.sync_stats = {
            "total_synced": 0,
            "last_sync": None,
            "errors": 0,
            "start_time": datetime.now()
        }
        
        # Configuration
        self.poll_interval = int(os.getenv('POLL_INTERVAL_SECONDS', '30'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.health_port = int(os.getenv('HEALTH_PORT', '8080'))
        self.running = True
        
        # Setup logging
        self.setup_logging()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Start health check server
        self.start_health_server()
    
    def setup_logging(self):
        """Setup logging configuration for containerized environment"""
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        # Create logs directory if it doesn't exist
        os.makedirs('/app/logs', exist_ok=True)
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/app/logs/ids-sync.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('ids-sync')
        
        # Log configuration
        self.logger.info(f"🐳 Containerized IDS Sync Service starting...")
        self.logger.info(f"📡 Provider URL: {self.provider_url}")
        self.logger.info(f"📥 Consumer URL: {self.consumer_url}")
        self.logger.info(f"⏱️  Poll Interval: {self.poll_interval} seconds")
        self.logger.info(f"🏥 Health Check Port: {self.health_port}")
        self.logger.info(f"📝 Log Level: {log_level}")
    
    def start_health_server(self):
        """Start HTTP health check server in background thread"""
        def run_server():
            try:
                server = HTTPServer(('0.0.0.0', self.health_port), HealthCheckHandler)
                server.sync_service = self  # Pass reference for health checks
                self.logger.info(f"🏥 Health check server started on port {self.health_port}")
                server.serve_forever()
            except Exception as e:
                self.logger.error(f"Health server error: {e}")
        
        health_thread = threading.Thread(target=run_server, daemon=True)
        health_thread.start()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"📡 Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def get_provider_catalog(self) -> Optional[Dict]:
        """Get the complete Provider catalog to discover resources"""
        try:
            self.logger.debug("🔍 Fetching Provider catalog...")
            
            response = requests.get(
                f"{self.provider_url}/api/selfDescription/",
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Accept": "application/json"},
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                catalog_data = response.json()
                self.logger.debug("✅ Provider catalog retrieved successfully")
                return catalog_data
            else:
                self.logger.error(f"❌ Failed to get Provider catalog: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"💥 Error fetching Provider catalog: {e}")
            return None
    
    def extract_resource_identifiers(self, catalog_data: Dict) -> List[str]:
        """Extract all TextResource identifiers from catalog"""
        resource_ids = []
        
        try:
            catalogs = catalog_data.get('ids:resourceCatalog', [])
            
            for catalog in catalogs:
                offered_resources = catalog.get('ids:offeredResource', [])
                
                for resource in offered_resources:
                    resource_id = resource.get('@id')
                    resource_type = resource.get('@type')
                    
                    # Only sync TextResources
                    if resource_id and resource_type == 'ids:TextResource':
                        resource_ids.append(resource_id)
            
            self.logger.debug(f"📋 Found {len(resource_ids)} TextResources in Provider catalog")
            return resource_ids
            
        except Exception as e:
            self.logger.error(f"💥 Error extracting resource IDs: {e}")
            return []
    
    def get_resource_details(self, resource_id: str) -> Optional[Dict]:
        """Get complete resource details from Provider"""
        try:
            self.logger.debug(f"📄 Fetching details for resource: {resource_id.split('/')[-1]}")
            
            response = requests.get(
                f"{self.provider_url}/api/offeredResource/",
                auth=HTTPBasicAuth(self.username, self.password),
                headers={
                    "Accept": "application/json",
                    "resource": resource_id
                },
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                resource_data = response.json()
                self.logger.debug(f"✅ Resource details retrieved: {resource_id.split('/')[-1]}")
                return resource_data
            else:
                self.logger.error(f"❌ Failed to get resource {resource_id.split('/')[-1]}: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"💥 Error fetching resource {resource_id.split('/')[-1]}: {e}")
            return None
    
    def get_consumer_catalog_header(self) -> Optional[str]:
        """Get the catalog ID needed for Consumer POST requests"""
        try:
            self.logger.debug("🔍 Getting Consumer catalog header...")
            
            response = requests.get(
                f"{self.consumer_url}/api/selfDescription/",
                auth=HTTPBasicAuth(self.username, self.password),
                headers={"Accept": "application/json"},
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                consumer_data = response.json()
                catalogs = consumer_data.get('ids:resourceCatalog', [])
                
                if catalogs:
                    catalog_id = catalogs[0].get('@id')
                    
                    if catalog_id:
                        clean_catalog_id = catalog_id.strip().strip("'\"")
                        self.logger.debug(f"✅ Consumer catalog ID: {clean_catalog_id}")
                        return clean_catalog_id
                    else:
                        self.logger.error("❌ Catalog ID is empty")
                        return None
                else:
                    self.logger.warning("⚠️  No catalog found in Consumer")
                    return None
            else:
                self.logger.error(f"❌ Failed to get Consumer catalog: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"💥 Error getting Consumer catalog: {e}")
            return None
    
    def post_resource_to_consumer(self, resource_data: Dict, catalog_header: str) -> bool:
        """Post resource to Consumer with enhanced error handling"""
        try:
            resource_id = resource_data.get('@id', 'unknown')
            resource_name = resource_id.split('/')[-1]
            self.logger.info(f"🚀 Posting resource to Consumer: {resource_name}")
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'catalog': catalog_header
            }
            
            response = requests.post(
                f"{self.consumer_url}/api/offeredResource/",
                auth=HTTPBasicAuth(self.username, self.password),
                headers=headers,
                data=json.dumps(resource_data, separators=(',', ':')),  # Compact JSON
                verify=False,
                timeout=60
            )
            
            if response.status_code == 200:
                self.logger.info(f"✅ Successfully synced resource: {resource_name}")
                self.sync_stats["total_synced"] += 1
                return True
            else:
                self.logger.error(f"❌ Failed to post resource {resource_name}: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                self.sync_stats["errors"] += 1
                return False
                
        except Exception as e:
            self.logger.error(f"💥 Exception posting resource to Consumer: {e}")
            self.sync_stats["errors"] += 1
            return False
    
    def sync_new_resources(self) -> None:
        """Main synchronization logic"""
        try:
            self.logger.info("🔄 Starting synchronization cycle...")
            
            # Step 1: Get Provider catalog
            catalog_data = self.get_provider_catalog()
            if not catalog_data:
                self.logger.error("❌ Cannot proceed without Provider catalog")
                return
            
            # Step 2: Extract resource identifiers
            current_resources = set(self.extract_resource_identifiers(catalog_data))
            
            # Step 3: Find new resources
            new_resources = current_resources - self.known_resources
            
            if new_resources:
                self.logger.info(f"🆕 Found {len(new_resources)} new resources to sync")
                
                # Step 4: Get Consumer catalog header
                catalog_header = self.get_consumer_catalog_header()
                if not catalog_header:
                    self.logger.error("❌ Cannot sync without Consumer catalog header")
                    return
                
                # Step 5: Sync each new resource
                success_count = 0
                for resource_id in new_resources:
                    resource_name = resource_id.split('/')[-1]
                    
                    # Get full resource details from Provider
                    resource_data = self.get_resource_details(resource_id)
                    if resource_data:
                        # Post to Consumer
                        success = self.post_resource_to_consumer(resource_data, catalog_header)
                        if success:
                            self.known_resources.add(resource_id)
                            success_count += 1
                        
                        # Small delay between requests
                        time.sleep(1)
                    else:
                        self.logger.error(f"❌ Failed to get details for {resource_name}")
                
                self.logger.info(f"📊 Sync batch complete: {success_count}/{len(new_resources)} successful")
            else:
                self.logger.info("✅ No new resources found")
            
            # Update stats
            self.sync_stats["last_sync"] = datetime.now()
            self.known_resources.update(current_resources)
            
            success_rate = (self.sync_stats["total_synced"] / max(self.sync_stats["total_synced"] + self.sync_stats["errors"], 1)) * 100
            self.logger.info(f"📊 Sync complete. Resources: {len(self.known_resources)}, Success Rate: {success_rate:.1f}%")
            
        except Exception as e:
            self.logger.error(f"💥 Error during synchronization: {e}")
            self.sync_stats["errors"] += 1
    
    def run(self) -> None:
        """Main service loop"""
        self.logger.info("🚀 IDS Provider-Consumer Sync Service (Containerized) starting...")
        self.logger.info(f"🐳 Running in Kubernetes pod")
        
        try:
            # Initial sync
            self.sync_new_resources()
            
            # Main loop
            while self.running:
                try:
                    self.logger.debug(f"⏳ Waiting {self.poll_interval} seconds until next sync...")
                    time.sleep(self.poll_interval)
                    
                    if self.running:
                        self.sync_new_resources()
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"💥 Error in main loop: {e}")
                    time.sleep(5)  # Brief pause before retrying
        
        except KeyboardInterrupt:
            pass
        
        finally:
            self.logger.info("🛑 IDS Sync Service stopped")
            uptime = datetime.now() - self.sync_stats["start_time"]
            success_rate = (self.sync_stats["total_synced"] / max(self.sync_stats["total_synced"] + self.sync_stats["errors"], 1)) * 100
            
            self.logger.info(f"📊 Final Stats:")
            self.logger.info(f"   ⏰ Uptime: {uptime}")
            self.logger.info(f"   📈 Success Rate: {success_rate:.1f}%")
            self.logger.info(f"   ✅ Total Synced: {self.sync_stats['total_synced']}")
            self.logger.info(f"   ❌ Errors: {self.sync_stats['errors']}")
            self.logger.info(f"   📋 Resources Tracked: {len(self.known_resources)}")

def main():
    """Entry point for containerized service"""
    service = ContainerizedIDSSyncService()
    try:
        service.run()
    except Exception as e:
        service.logger.error(f"💥 Service error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()