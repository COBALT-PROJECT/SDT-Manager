# File: sdt_manager_core.py
import logging
import threading
import os
from sdt_lifecycle_manager import SDT_LifeCycleManager
from sdt_connector_manager import SDT_ConnectorManager
from ccm_manager_interface import CCM_Manager_Interface
from adapter import DTModelAdapter

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

class SDT_ManagerCore:
    def __init__(self):
        """Initialize the SDT Manager Core."""
        LOGGER.info("Initializing SDT Manager Core...")
        
        # Get configuration from environment variables
        sdt_interface_host = os.environ.get('SDT_INTERFACE_HOST', 'localhost')
        sdt_interface_port = os.environ.get('SDT_INTERFACE_PORT', '30008')
        api_server_host = os.environ.get('API_SERVER_HOST', '0.0.0.0')
        api_server_port = int(os.environ.get('API_SERVER_PORT', '8008'))
        
        # Initialize components
        self.lifecycle_manager = SDT_LifeCycleManager()
        LOGGER.info("SDT Lifecycle Manager has been instantiated")
        
        # Initialize SDT Connector Manager (independent IDS connector management)
        self.connector_manager = SDT_ConnectorManager()
        LOGGER.info("SDT Connector Manager has been instantiated")
        
        # Initialize adapter before CCM manager so it's available for the API
        self.sdt_adapter = DTModelAdapter()
        LOGGER.info(f"Adapter for DT Model has been instantiated with host={sdt_interface_host}, port={sdt_interface_port}")
        
        # Initialize NBI server (CCM Manager Interface)
        self.ccm_manager = CCM_Manager_Interface(self)
        LOGGER.info(f"CCM Manager API has been instantiated and will listen on {api_server_host}:{api_server_port}")

        # Store configuration
        self.config = {
            'sdt_interface_host': sdt_interface_host,
            'sdt_interface_port': sdt_interface_port,
            'api_server_host': api_server_host,
            'api_server_port': api_server_port
        }
        
        # Thread management
        self.terminate_event = threading.Event()
        self.api_thread = None
        
        LOGGER.info("SDT Manager Core has been instantiated and initialized.")
    
    def start(self):
        """Start all components of the SDT Manager"""
        LOGGER.info("Starting SDT Manager...")
        
        # Start API server
        self.api_thread = self.ccm_manager.start_server_thread(
            host=self.config['api_server_host'], 
            port=self.config['api_server_port']
        )
        LOGGER.info(f"API server thread started on {self.config['api_server_host']}:{self.config['api_server_port']}")
        
        LOGGER.info("SDT Manager started successfully")
    
    def stop(self):
        """Stop all components and threads"""
        LOGGER.info("Stopping SDT Manager...")
        
        # Signal all threads to terminate
        self.terminate_event.set()
        
        # API thread is daemon, it will terminate when main process exits
        
        LOGGER.info("SDT Manager stopped")

# Main entry point
def main():
    """Main entry point for the SDT Manager"""
    manager = SDT_ManagerCore()
    try:
        manager.start()
        # Keep main thread running
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received, shutting down...")
    finally:
        manager.stop()

if __name__ == "__main__":
    main()