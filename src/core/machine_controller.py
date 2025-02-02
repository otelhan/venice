from .states import MachineState
from .state_handlers import StateHandler

class MachineController:
    def __init__(self):
        self.current_state = None
        self.state_handler = StateHandler()
        self.movement_buffer = []  # Store received movements
        
    def handle_current_state(self):
        """Handle the current state"""
        if self.current_state == MachineState.DRIVE_WAVEMAKER:
            # Pass movement buffer to state handler
            if self.movement_buffer:
                self.state_handler.movement_buffer = self.movement_buffer
                next_state = self.state_handler.drive_wavemaker()
                if next_state:
                    self.transition_to(MachineState.IDLE)
    
    def transition_to(self, new_state: MachineState):
        """Transition to a new state"""
        if self.current_state is None:
            print(f"Initializing state to: {new_state.name}")
        else:
            print(f"Transitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state