# Reservoir Computer System

This project implements a reservoir computing system for an interactive installation. The system consists of two main components:

1. **Video Input Controller** - Processes video input to detect movement and sends data to the output controller
2. **Output Controller** - Receives movement data, processes it, and controls servos for physical output

## System Overview

The system works as follows:

1. The video input controller processes a video stream to detect movement in defined regions of interest (ROIs).
2. Movement data is collected and periodically sent to the output controller.
3. The output controller processes the movement data to control various servo mechanisms:
   - Five cube servos that rotate based on movement patterns
   - A clock servo that indicates time-of-day information

## Components

### Video Input Controller

- Processes video from a camera or video file
- Detects movement in six predefined regions of interest
- Calculates movement vectors and saves them to CSV files
- Sends movement data to the output controller
- Handles acknowledgments from the output controller

### Output Controller

- Receives movement data via WebSocket
- Controls servo motors for physical output
- Includes a time-based clock mechanism with 6 sectors (4 hours each)
- Provides testing capabilities for direct servo control
- Sends acknowledgments back to the video input controller

## Setup and Configuration

The system is configured using YAML files in the `config` directory:

- `controllers.yaml` - Main configuration file for both input and output controllers
- Other configuration files for specific components

## Usage

### Video Input Controller

To run the video input controller:

```
python -m reservoir_computer.src.networking.video_input
```

### Output Controller

To run the output controller:

```
python -m reservoir_computer.src.networking.run_output_extended
```

The output controller offers two modes:
1. **Operation Mode** - Normal operation as a WebSocket server, receiving data from the video input
2. **Test Mode** - Direct servo control for testing and calibration

### Test Mode Features

In test mode, the output controller provides a menu-driven interface:

1. **Load sample data and process** - Tests the servo movements with sample data
2. **Test clock sector movement** - Directly move the clock to a specific sector
3. **Reset all servos to center** - Return all servos to neutral positions
4. **Help - Clock sectors explanation** - Detailed help about clock sectors
5. **Exit test mode** - Exit the application

#### Clock Sectors

The clock indicates time using 6 sectors, each representing a 4-hour period:

| Sector | Time Range | Servo Angle |
|--------|------------|-------------|
| 0 | 00:00-03:59 | -150° |
| 1 | 04:00-07:59 | -90°  |
| 2 | 08:00-11:59 | -30°  |
| 3 | 12:00-15:59 | +30°  |
| 4 | 16:00-19:59 | +90°  |
| 5 | 20:00-23:59 | +150° |

## Data Storage

Movement data and processed results are stored in the `data` directory:
- `movement_vectors_YYYYMMDD.csv` - Raw movement data from video input
- `processed_movement_YYYYMMDD.csv` - Processed data from output controller

## Development and Testing

The repository includes test scripts to verify functionality:

- `tests/test_video_input.py` - Tests the video input functionality
- `tests/test_video_input_extended.py` - Extended test with acknowledgment handling

## Troubleshooting

### Common Issues

1. **Servo Communication Errors**
   - Check serial port connections and permissions
   - Verify controller configuration in `controllers.yaml`

2. **WebSocket Connection Issues**
   - Ensure IP addresses and ports are correctly configured
   - Check network connectivity between controllers

3. **Video Input Problems**
   - Verify camera connection or video file path
   - Check frame processing settings in configuration

## License

This project is proprietary and confidential. All rights reserved.
