from src.simulation.reservoir_sim import ReservoirNetwork
from src.simulation.video_processor_simulator import VideoProcessorSimulator
import matplotlib.pyplot as plt
import numpy as np
import joblib  # For saving the model
import os
import cv2

def train_network():
    """Train the network using the night video"""
    network = ReservoirNetwork()
    processor = VideoProcessorSimulator()
    
    print("\nProcessing training video (Ponte delle Guglie_night.mp4)...")
    if not processor.load_video("input_videos/Ponte delle Guglie_night.mp4"):
        print("Failed to load video")
        return None
        
    print("\nSelect ROI for training...")
    if not processor.select_roi():
        print("Failed to select ROI")
        return None
        
    segments = []
    labels = []
    frame_count = 0
    segment_count = 0
    MAX_SEGMENTS = 5  # Changed from 10 to 5 segments
    
    print("\nProcessing video segments...")
    while segment_count < MAX_SEGMENTS:  # Stop after 5 segments
        print(f"\nProcessing segment {segment_count + 1} of {MAX_SEGMENTS}...")
        
        movements = processor.calculate_movement(max_frames=300, start_frame=frame_count)
        
        if movements is None:
            print(f"Reached end of video after {frame_count} frames")
            break
            
        print(f"Got {len(movements)} movement values")
        
        # Scale movements to 0-127
        movements = np.array(movements)
        scaled_movements = (movements - movements.min()) * (127.0 / (movements.max() - movements.min()))
        
        # Process through reservoir and store outputs
        print("Routing through reservoir network...")
        outputs = network.route_package(scaled_movements, update_plots=True)
        segments.append(outputs)
        labels.append(f"segment_{segment_count}")
        
        frame_count += len(movements)
        segment_count += 1
        print(f"Completed segment {segment_count} (frames {frame_count-len(movements)} to {frame_count})")
        plt.pause(0.5)  # Give time to see the plots
    
    if len(segments) >= 2:
        print(f"\nTotal segments processed: {len(segments)}")
        network.train_classifier(segments, labels)
        print("\nTraining complete!")
        
        # Save model with processor info
        models_dir = os.path.join('models')
        os.makedirs(models_dir, exist_ok=True)
        model_path = os.path.join(models_dir, 'trained_reservoir.joblib')
        network.save_model(model_path, processor)
        print(f"Model saved to '{model_path}'")
        
        # Store ROI info in network before returning
        network.roi_info = {
            'roi': processor.roi,
            'cell_size': 40,
            'selected_cells': processor.selected_cells
        }
        network.processor = processor
        
        return network
    else:
        print("Not enough segments were processed (need at least 2)")
        return None

def test_new_video(network=None):
    """Test the trained network on a new video"""
    default_roi = None
    
    if network is None:
        try:
            model_path = os.path.join('models', 'trained_reservoir.joblib')
            network = ReservoirNetwork()
            if not network.load_model(model_path):  # Use load_model method
                print("Failed to load model")
                return
            default_roi = network.roi_info  # Get ROI info from loaded model
            print(f"Using saved ROI: {default_roi is not None}")
        except Exception as e:
            print(f"Error loading model: {e}")
            return
    else:
        # If network is provided directly, try to get ROI info from it
        default_roi = getattr(network, 'roi_info', None)

    processor = VideoProcessorSimulator()
    network.processor = processor  # Store processor reference in network
    
    while True:
        print("\nAvailable test videos:")
        print("1. input_videos/Ponte delle Guglie_day.mp4")
        print("2. input_videos/Ponte delle Guglie_night.mp4")
        print("Or enter custom path")
        print("(q to quit)")
        
        choice = input("\nEnter choice (1/2/path/q): ").strip()
        
        if choice.lower() == 'q':
            break
            
        # Map choices to video paths
        video_path = {
            '1': "input_videos/Ponte delle Guglie_day.mp4",
            '2': "input_videos/Ponte delle Guglie_night.mp4"
        }.get(choice, choice)  # If not 1 or 2, use the entered path
        
        print(f"\nUsing video: {video_path}")
        
        if processor.load_video(video_path):
            print("\nSelect ROI (or press Enter to use saved ROI)...")
            cv2.namedWindow("Video", cv2.WINDOW_NORMAL)  # Initialize window before ROI selection
            if not processor.select_roi(default_roi):
                print("Failed to select ROI")
                cv2.destroyAllWindows()  # Clean up windows if ROI selection fails
                continue
            
            movements = processor.calculate_movement(max_frames=300)
            
            if movements:
                # Scale movements
                movements = np.array(movements)
                scaled_movements = (movements - movements.min()) * (127.0 / (movements.max() - movements.min()))
                
                # Test each segment
                segment_size = len(scaled_movements) // 3
                print("\nActivity Analysis:")
                
                for i in range(3):
                    start = i * segment_size
                    end = start + segment_size
                    test_segment = scaled_movements[start:end]
                    
                    # Get prediction - this will also update the plots
                    prediction, confidence = network.predict(test_segment)
                    network.update_classification_plot((prediction, confidence))
                    plt.draw()
                    plt.pause(0.1)
                    
                    print(f"\nSegment {i+1}:")
                    print(f"  - Activity Level: {prediction}")
                    print(f"  - Confidence: {confidence:.1f}%")
                    
                    # Show comparison with training data
                    print("  - Pattern Analysis:")
                    if prediction == 'low_activity':
                        print("    * Few people in frame")
                    elif prediction == 'medium_activity':
                        print("    * Normal pedestrian traffic")
                    else:
                        print("    * High pedestrian activity")
                
                print("\nPress Enter to analyze another video...")
                input()
            else:
                print("Error processing video")
        else:
            print(f"Error: Could not load video '{video_path}'")

def main():
    print("\nReservoir Computer Training/Testing")
    print("-----------------------------------")
    
    # Check if model exists
    model_path = os.path.join('models', 'trained_reservoir.joblib')
    if os.path.exists(model_path):
        print("\nExisting model found!")
        while True:
            print("\nWhat would you like to do?")
            print("1. Use existing model for testing")
            print("2. Train new model")
            print("q. Quit")
            
            choice = input("Enter choice (1/2/q): ").strip().lower()
            
            if choice == 'q':
                return
            elif choice == '1':
                test_new_video()  # Will load existing model
                break
            elif choice == '2':
                trained_network = train_network()
                if trained_network:
                    # Pass the trained network with ROI info to test
                    test_new_video(trained_network)
                else:
                    print("Error: Could not train network")
                break
            else:
                print("Invalid choice. Please try again.")
    else:
        print("\nNo existing model found. Training new model...")
        trained_network = train_network()
        if trained_network:
            test_new_video(trained_network)
        else:
            print("Error: Could not train network")

if __name__ == "__main__":
    main() 