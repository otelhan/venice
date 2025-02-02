import yaml
import uuid
import os
import time

class ConfigHandler:
    def __init__(self):
        self.config = None
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                      'config', 'controllers.yaml')
        self.current_mac = self._get_mac_address()
        self.controller_name = None
        
    def _get_mac_address(self):
        """Get the MAC address of current machine"""
        try:
            # Method 1: Using ip command
            import subprocess
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'link/ether' in line:
                    mac = line.split()[1].strip()
                    print(f"Found MAC address: {mac}")  # Debug print
                    return mac.lower()
                
        except Exception as e:
            print(f"Error getting MAC via ip command: {e}")
            
            # Fallback to uuid method
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0,8*6,8)][::-1])
            print(f"Fallback MAC address: {mac}")  # Debug print
            return mac.lower()
        
    def load_config(self):
        """Load configuration file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
                print("Loaded config:", self.config)  # Debug print
            
            print(f"Current MAC: {self.current_mac}")  # Debug print
            
            # Find this controller in config
            for name, details in self.config['controllers'].items():
                config_mac = details['mac'].lower()
                print(f"Checking against {name}: {config_mac}")  # Debug print
                if config_mac == self.current_mac.lower():
                    self.controller_name = name
                    return True
                
            print(f"Warning: MAC address {self.current_mac} not found in config")
            print("Available MACs in config:", [details['mac'].lower() 
                  for details in self.config['controllers'].values()])
            return False
            
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
        
    def get_controller_name(self):
        """Get name of current controller"""
        return self.controller_name
        
    def get_controller_info(self):
        """Get full info for current controller"""
        if not self.controller_name or not self.config:
            return None
        return self.config['controllers'].get(self.controller_name)
        
    def update_controller_ip(self, controller_name, ip):
        """Update IP address for a controller"""
        if not self.config or 'controllers' not in self.config:
            return False
            
        if controller_name in self.config['controllers']:
            self.config['controllers'][controller_name]['ip'] = ip
            self.config['controllers'][controller_name]['last_seen'] = time.time()
            self._save_config()
            return True
        return False
        
    def get_controller_ip(self, controller_name):
        """Get IP address for a controller"""
        if not self.config or 'controllers' not in self.config:
            return None
            
        controller = self.config['controllers'].get(controller_name)
        if controller:
            return controller.get('ip')
        return None
        
    def update_ip(self, name, ip):
        """Update IP and last_seen time for a controller"""
        if not self.config or name not in self.config['controllers']:
            return False
        
        self.config['controllers'][name]['ip'] = ip
        self.config['controllers'][name]['last_seen'] = time.time()
        return self._save_config()
        
    def _save_config(self):
        """Save current config to file"""
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False 