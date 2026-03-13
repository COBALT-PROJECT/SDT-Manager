# File: sdt_manager_core.py
import logging
import threading
import os
from sdt_lifecycle_manager import SDT_LifeCycleManager
from sdt_connector_manager import SDT_ConnectorManager
from watchtower_manager import WatchTower_LifeCycleManager
from sdt_manager_interface import SDT_Manager_Interface
from sdt_credential_store import SDTCredentialStore
from sdt_authentication_manager import SDTAuthenticationManager
from adapter_all import DTModelAdapter

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
        sdt_interface_port = int(os.environ.get('SDT_INTERFACE_PORT', '30008'))
        api_server_host = os.environ.get('API_SERVER_HOST', '0.0.0.0')
        api_server_port = int(os.environ.get('API_SERVER_PORT', '8008'))
        
        # Initialize SDT Lifecycle Manager
        self.lifecycle_manager = SDT_LifeCycleManager()
        LOGGER.info("SDT Lifecycle Manager has been instantiated")
        
        # Initialize Watchtower Lifecycle Manager
        self.watchtower_manager = WatchTower_LifeCycleManager()
        LOGGER.info("Watchtower Lifecycle Manager has been instantiated")
        
        # Initialize SDT Connector Manager (independent IDS connector management)
        self.connector_manager = SDT_ConnectorManager()
        LOGGER.info("SDT Connector Manager has been instantiated")
        
        # Initialize adapter before CCM manager so it's available for the API
        self.sdt_adapter = DTModelAdapter()
        LOGGER.info(f"Adapter for DT Model has been instantiated with host={sdt_interface_host}, port={sdt_interface_port}")
        
        # Initialize SQLite credential store
        db_path = os.environ.get('CREDENTIAL_DB_PATH', 'sdt_credentials.db')
        self.credential_store = SDTCredentialStore(db_path=db_path)
        LOGGER.info("SDT Credential Store has been instantiated")
        
        # Initialize Authentication Manager
        self.auth_manager = SDTAuthenticationManager(
            credential_store=self.credential_store,
            am_base_url=os.environ.get('AM_BASE_URL'),
            wallet_controller_url=os.environ.get('WALLET_CONTROLLER_URL'),
            wallet_controller_key=os.environ.get('WALLET_CONTROLLER_KEY'),
            digital_twin_api_key=os.environ.get('DIGITAL_TWIN_API_KEY'),
        )
        LOGGER.info("SDT Authentication Manager has been instantiated")
        
        # Initialize NBI server (SDT Manager Interface)
        self.sdt_manager = SDT_Manager_Interface(self)
        LOGGER.info(f"SDT Manager API has been instantiated and will listen on {api_server_host}:{api_server_port}")

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
        self.api_thread = self.sdt_manager.start_server_thread(
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