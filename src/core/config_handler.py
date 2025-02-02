import yaml
import uuid
import os

class ConfigHandler:
    def __init__(self):
        self.config = None
        self.current_mac = self._get_mac_address()
        self.controller_name = None
        
    def _get_mac_address(self):
        """Get the MAC address of current machine"""
        return ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                        for elements in range(0,8*6,8)][::-1])
        
    def load_config(self):
        """Load configuration file"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
            
        # Find this controller in config
        for name, details in self.config['controllers'].items():
            if details['mac'].lower() == self.current_mac.lower():
                self.controller_name = name
                return True
                
        print(f"Warning: MAC address {self.current_mac} not found in config")
        return False
        
    def get_controller_name(self):
        """Get name of current controller"""
        return self.controller_name
        
    def get_controller_info(self):
        """Get full info for current controller"""
        if not self.controller_name or not self.config:
            return None
        return self.config['controllers'].get(self.controller_name) 