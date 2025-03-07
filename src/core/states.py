from enum import Enum, auto

class MachineState(Enum):
    IDLE = auto()
    DRIVE_WAVEMAKER = auto()
    COLLECT_SIGNAL = auto()
    PROCESS_DATA = auto()  # Defined but not used
    SEND_DATA = auto()
    RECEIVE_DATA = auto()
    STATE_3 = auto()  # placeholder
    STATE_4 = auto()  # placeholder