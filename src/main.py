from src.core.machine_controller import MachineController
from src.core.states import MachineState

def main():
    controller = MachineController()
    
    try:
        print("\n=== Starting in COLLECT_SIGNAL state ===")
        
        while True:
            if controller.current_state == MachineState.COLLECT_SIGNAL:
                result = controller.handle_current_state()
                if result == 'd':
                    controller.transition_to(MachineState.DRIVE_WAVEMAKER)
                elif result == 'q':
                    break
                    
            elif controller.current_state == MachineState.DRIVE_WAVEMAKER:
                controller.handle_current_state()
                controller.transition_to(MachineState.COLLECT_SIGNAL)
            
    except KeyboardInterrupt:
        print("\nProgram terminated by user")

if __name__ == "__main__":
    main()