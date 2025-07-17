# File: sdt_connector_manager.py
import logging
from typing import Dict, Optional, List, Tuple
from ids_connector import IDS_Connector

LOGGER = logging.getLogger(__name__)

class SDT_ConnectorManager:
    """Manages the complete lifecycle of IDS Connectors independently"""
    
    def __init__(self):
        """Initialize SDT Connector Manager"""
        self.ids_connector = IDS_Connector()
        LOGGER.info("SDT Connector Manager initialized")
    
    def deploy_connector(self, connector_type: str = "consumer") -> Tuple[Optional[str], Optional[str]]:
        """
        Deploy an IDS connector.
        
        Args:
            connector_type (str): Type of connector to deploy (default: "consumer")
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (deployment_name, connector_id) or (None, None) if failed
        """
        LOGGER.info(f"Deploying {connector_type} connector via SDT Connector Manager")
        
        try:
            deployment_name, connector_id = self.ids_connector.deploy(connector_type)
            
            if deployment_name and connector_id:
                LOGGER.info(f"Successfully deployed {connector_type} connector: {deployment_name} with ID: {connector_id}")
                return deployment_name, connector_id
            else:
                LOGGER.error(f"Failed to deploy {connector_type} connector")
                return None, None
                
        except Exception as e:
            LOGGER.error(f"Error deploying {connector_type} connector: {str(e)}")
            return None, None
    
    def delete_connector(self, connector_id: str, cleanup_resources: bool = True) -> Dict[str, bool]:
        """
        Delete an IDS connector by its identifier.
        
        Args:
            connector_id (str): The connector identifier to delete
            cleanup_resources (bool): Whether to cleanup associated resources
            
        Returns:
            Dict[str, bool]: Results of deletion operations
        """
        LOGGER.info(f"Deleting connector {connector_id} via SDT Connector Manager")
        
        try:
            deletion_results = self.ids_connector.delete_connector_by_id(connector_id, cleanup_resources)
            
            if deletion_results.get(connector_id, False):
                LOGGER.info(f"Successfully deleted connector {connector_id}")
            else:
                LOGGER.error(f"Failed to delete connector {connector_id}")
                
            return deletion_results
            
        except Exception as e:
            LOGGER.error(f"Error deleting connector {connector_id}: {str(e)}")
            return {connector_id: False}
    
    def list_connectors(self) -> List[Dict]:
        """
        List all available IDS connectors.
        
        Returns:
            List[Dict]: List of connector information dictionaries
        """
        LOGGER.info("Listing all connectors via SDT Connector Manager")
        
        try:
            connectors = self.ids_connector.list_available_connectors()
            LOGGER.info(f"Found {len(connectors)} connectors")
            return connectors
            
        except Exception as e:
            LOGGER.error(f"Error listing connectors: {str(e)}")
            return []
    
    def get_connector_status(self, connector_id: str) -> Optional[Dict]:
        """
        Get detailed status of a specific connector.
        
        Args:
            connector_id (str): The connector identifier
            
        Returns:
            Optional[Dict]: Connector status information or None if not found
        """
        LOGGER.info(f"Getting status for connector {connector_id}")
        
        try:
            status = self.ids_connector.get_connector_status(connector_id)
            
            if status:
                LOGGER.info(f"Retrieved status for connector {connector_id}")
            else:
                LOGGER.warning(f"Connector {connector_id} not found")
                
            return status
            
        except Exception as e:
            LOGGER.error(f"Error getting connector status for {connector_id}: {str(e)}")
            return None
    
    def check_connector_exists(self, connector_id: str) -> bool:
        """
        Check if a connector with the given ID exists.
        
        Args:
            connector_id (str): The connector identifier to check
            
        Returns:
            bool: True if connector exists, False otherwise
        """
        try:
            return any(
                connector_id == cid 
                for cid in self.ids_connector.deployment_map.values()
            )
        except Exception as e:
            LOGGER.error(f"Error checking connector existence for {connector_id}: {str(e)}")
            return False
    
    def get_deployment_map(self) -> Dict[str, str]:
        """
        Get the current deployment map.
        
        Returns:
            Dict[str, str]: Current deployment map (deployment_name -> connector_id)
        """
        try:
            return self.ids_connector.deployment_map.copy()
        except Exception as e:
            LOGGER.error(f"Error getting deployment map: {str(e)}")
            return {}
    
    def check_connector_ready(self, connector_id: str) -> bool:
        """
        Check if a specific connector is ready.
        
        Args:
            connector_id (str): The connector identifier
            
        Returns:
            bool: True if connector is ready, False otherwise
        """
        try:
            status = self.get_connector_status(connector_id)
            if status:
                return status.get("is_ready", False)
            return False
        except Exception as e:
            LOGGER.error(f"Error checking connector readiness for {connector_id}: {str(e)}")
            return False
    
    def get_connector_logs(self, connector_id: str, lines: int = 100) -> Optional[str]:
        """
        Get logs for a specific connector.
        
        Args:
            connector_id (str): The connector identifier
            lines (int): Number of log lines to retrieve
            
        Returns:
            Optional[str]: Connector logs or None if not found
        """
        try:
            # Find deployment with matching ID
            deployment_name = None
            for dep_name, cid in self.ids_connector.deployment_map.items():
                if cid == connector_id:
                    deployment_name = dep_name
                    break
            
            if not deployment_name:
                LOGGER.warning(f"No deployment found for connector {connector_id}")
                return None
            
            # Get logs using kubectl
            cmd = f"kubectl logs deployment/{deployment_name} --tail={lines}"
            logs = self.ids_connector.run_command(cmd)
            
            if logs:
                LOGGER.info(f"Retrieved {lines} lines of logs for connector {connector_id}")
                return logs
            else:
                LOGGER.warning(f"No logs available for connector {connector_id}")
                return None
                
        except Exception as e:
            LOGGER.error(f"Error getting logs for connector {connector_id}: {str(e)}")
            return None
    
    def restart_connector(self, connector_id: str) -> bool:
        """
        Restart a specific connector deployment.
        
        Args:
            connector_id (str): The connector identifier
            
        Returns:
            bool: True if restart was successful, False otherwise
        """
        try:
            # Find deployment with matching ID
            deployment_name = None
            for dep_name, cid in self.ids_connector.deployment_map.items():
                if cid == connector_id:
                    deployment_name = dep_name
                    break
            
            if not deployment_name:
                LOGGER.warning(f"No deployment found for connector {connector_id}")
                return False
            
            # Restart deployment using kubectl rollout restart
            cmd = f"kubectl rollout restart deployment/{deployment_name}"
            result = self.ids_connector.run_command(cmd)
            
            if result:
                LOGGER.info(f"Successfully restarted connector {connector_id}")
                return True
            else:
                LOGGER.error(f"Failed to restart connector {connector_id}")
                return False
                
        except Exception as e:
            LOGGER.error(f"Error restarting connector {connector_id}: {str(e)}")
            return False
    
    def scale_connector(self, connector_id: str, replicas: int) -> bool:
        """
        Scale a specific connector deployment.
        
        Args:
            connector_id (str): The connector identifier
            replicas (int): Number of replicas to scale to
            
        Returns:
            bool: True if scaling was successful, False otherwise
        """
        try:
            # Find deployment with matching ID
            deployment_name = None
            for dep_name, cid in self.ids_connector.deployment_map.items():
                if cid == connector_id:
                    deployment_name = dep_name
                    break
            
            if not deployment_name:
                LOGGER.warning(f"No deployment found for connector {connector_id}")
                return False
            
            # Scale deployment using kubectl scale
            cmd = f"kubectl scale deployment/{deployment_name} --replicas={replicas}"
            result = self.ids_connector.run_command(cmd)
            
            if result:
                LOGGER.info(f"Successfully scaled connector {connector_id} to {replicas} replicas")
                return True
            else:
                LOGGER.error(f"Failed to scale connector {connector_id}")
                return False
                
        except Exception as e:
            LOGGER.error(f"Error scaling connector {connector_id}: {str(e)}")
            return False
    
    def get_connector_events(self, connector_id: str) -> Optional[str]:
        """
        Get Kubernetes events for a specific connector.
        
        Args:
            connector_id (str): The connector identifier
            
        Returns:
            Optional[str]: Connector events or None if not found
        """
        try:
            # Find deployment with matching ID
            deployment_name = None
            for dep_name, cid in self.ids_connector.deployment_map.items():
                if cid == connector_id:
                    deployment_name = dep_name
                    break
            
            if not deployment_name:
                LOGGER.warning(f"No deployment found for connector {connector_id}")
                return None
            
            # Get events using kubectl get events
            cmd = f"kubectl get events --field-selector involvedObject.name={deployment_name} --sort-by='.lastTimestamp'"
            events = self.ids_connector.run_command(cmd)
            
            if events:
                LOGGER.info(f"Retrieved events for connector {connector_id}")
                return events
            else:
                LOGGER.warning(f"No events found for connector {connector_id}")
                return None
                
        except Exception as e:
            LOGGER.error(f"Error getting events for connector {connector_id}: {str(e)}")
            return None