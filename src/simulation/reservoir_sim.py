import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import laplace
from sklearn.linear_model import LogisticRegression
import cv2
import joblib

class ReservoirNode:
    def __init__(self, id, transform_type='laplace'):
        self.id = id
        # Different transformations for different nodes
        self.transform_types = ['laplace', 'square', 'tanh', 'relu']
        self.transform_type = self.transform_types[id % len(self.transform_types)]
        self.input_buffer = []
        self.output_buffer = []
        self.state = np.zeros(100)
        self.decay_rate = 0.7 - (0.1 * (id % 3))  # More aggressive decay rates
        
    def transform(self, input_package):
        """Transform input package using specified transformation"""
        if self.transform_type == 'laplace':
            transformed = laplace(input_package)
        elif self.transform_type == 'square':
            transformed = np.square(input_package) / 127.0  # Normalize
        elif self.transform_type == 'tanh':
            transformed = np.tanh(input_package / 64.0)  # Scaled tanh
        elif self.transform_type == 'relu':
            transformed = np.maximum(0, input_package)
            
        # Add some non-linearity and scaling
        transformed = transformed * (1 + 0.1 * np.random.randn(*transformed.shape))
        
        # Update internal state with decay and feedback
        self.state = self.decay_rate * self.state + (1 - self.decay_rate) * transformed
        return self.state
        
    def process_package(self, input_package):
        """Process incoming data package and generate output"""
        self.input_buffer = input_package
        self.output_buffer = self.transform(input_package)
        return self.output_buffer

class ReservoirNetwork:
    def __init__(self, num_nodes=4, package_size=300):
        self.nodes = [ReservoirNode(i) for i in range(num_nodes)]
        self.package_size = package_size
        self.classifier = LogisticRegression()
        self.is_trained = False
        self.processor = None  # Add this to store the processor
        
        # Setup visualization with grid layout
        plt.ion()
        
        # Create main window for reservoirs
        self.reservoir_fig = plt.figure(figsize=(15, 10))
        self.reservoir_fig.canvas.manager.set_window_title('Reservoir Computer Analysis')
        
        # Create 2x4 grid for input/output pairs
        gs = self.reservoir_fig.add_gridspec(2, 4, hspace=0.3, wspace=0.3)
        
        # Initialize plots for each reservoir
        self.input_axes = []
        self.output_axes = []
        self.input_lines = []
        self.output_lines = []
        
        for i in range(num_nodes):
            row = i // 2
            col = (i % 2) * 2  # Multiply by 2 to leave space for output
            
            # Input plot
            ax_in = self.reservoir_fig.add_subplot(gs[row, col])
            ax_in.set_title(f'Reservoir {i} Input')
            ax_in.grid(True)
            line_in, = ax_in.plot([], [])
            self.input_axes.append(ax_in)
            self.input_lines.append(line_in)
            
            # Output plot
            ax_out = self.reservoir_fig.add_subplot(gs[row, col + 1])
            ax_out.set_title(f'Reservoir {i} Output')
            ax_out.grid(True)
            line_out, = ax_out.plot([], [])
            self.output_axes.append(ax_out)
            self.output_lines.append(line_out)
            
        # Classification window
        self.class_fig, self.class_ax = plt.subplots(figsize=(6, 4))
        self.class_fig.canvas.manager.set_window_title('Activity Classification')
        
        # Adjust activity thresholds to be more sensitive
        self.activity_thresholds = {
            'low': 5,     # Lower threshold to catch more variation
            'medium': 15,  # Adjusted medium threshold
            'high': 30    # Lower high threshold
        }
        
        # Create denser connectivity matrix (only 30% pruned)
        self.connectivity = np.random.rand(num_nodes, num_nodes)
        self.connectivity[self.connectivity < 0.3] = 0  # Less pruning
        
        # Stronger weights with both positive and negative connections
        self.weights = (np.random.rand(num_nodes, num_nodes) * 2 - 1) * 1.5
        # Ensure strong connections between adjacent nodes
        for i in range(num_nodes-1):
            self.weights[i, i+1] = 1.0
            self.weights[i+1, i] = 0.8
        
        self.weights = self.weights * self.connectivity  # Apply connectivity mask
        
        # Add readout layer visualization window
        self.readout_fig, self.readout_ax = plt.subplots(figsize=(8, 6))
        self.readout_fig.canvas.manager.set_window_title('Reservoir Readout Layer')
        self.readout_ax.set_title('Readout Layer Activity')
        self.readout_ax.set_xlabel('Time')
        self.readout_ax.set_ylabel('Node Output')
        self.readout_lines = [self.readout_ax.plot([], [], label=f'Node {i}')[0] 
                            for i in range(num_nodes)]
        self.readout_ax.legend()
        self.readout_ax.grid(True)
        
        # Add connectivity visualization window
        self.conn_fig, self.conn_ax = plt.subplots(figsize=(8, 6))
        self.conn_fig.canvas.manager.set_window_title('Reservoir Connectivity')
        
        # Visualize initial connectivity
        self.update_connectivity_plot()
        
        plt.show()
        
    def update_readout_plot(self, outputs):
        """Update readout layer visualization"""
        # Clear old data
        self.readout_ax.clear()
        
        # Plot each node's output history with different colors and lower opacity
        colors = ['red', 'blue', 'green', 'purple']  # Distinct colors for each node
        for i, node_output in enumerate(outputs):
            self.readout_ax.plot(node_output, label=f'Node {i}', 
                               color=colors[i], alpha=0.4,  # Lower opacity
                               linewidth=2)  # Thicker lines
            
        # Reset plot properties
        self.readout_ax.set_title('Readout Layer Activity')
        self.readout_ax.set_xlabel('Time')
        self.readout_ax.set_ylabel('Node Output')
        self.readout_ax.legend(loc='upper right')  # Move legend to upper right
        self.readout_ax.grid(True, alpha=0.3)  # Lighter grid
        
        self.readout_fig.canvas.draw()
        
    def route_package(self, input_package, update_plots=True):
        """Route package through reservoir network with recurrent connections"""
        # Initialize states for each node
        current_states = []
        for node in self.nodes:
            node.state = np.zeros(100)  # Reset state
            current_states.append(node.state)
            
        all_outputs = []
        node_outputs_history = [[] for _ in self.nodes]  # Track history for each node
        
        # Process input package in chunks to match state size
        chunk_size = 100
        for i in range(0, len(input_package), chunk_size):
            chunk = input_package[i:i + chunk_size]
            if len(chunk) < chunk_size:
                # Pad last chunk if needed
                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                
            # Process through reservoir with recurrent connections
            new_states = []
            
            for i, node in enumerate(self.nodes):
                # Combine input with recurrent connections
                recurrent_input = np.zeros_like(chunk)
                for j in range(len(self.nodes)):
                    if self.connectivity[i,j] > 0:
                        recurrent_input += self.weights[i,j] * current_states[j]
                
                # Combine external input with recurrent
                combined_input = chunk + recurrent_input
                output = node.process_package(combined_input)
                new_states.append(output)
                
                # Update plots if needed
                if update_plots:
                    self.input_lines[i].set_data(range(len(combined_input)), combined_input)
                    self.input_axes[i].relim()
                    self.input_axes[i].autoscale_view()
                    
                    self.output_lines[i].set_data(range(len(output)), output)
                    self.output_axes[i].relim()
                    self.output_axes[i].autoscale_view()
                
                # Store output history for this node
                node_outputs_history[i].extend(output)
            
            current_states = new_states
            all_outputs.extend(new_states)
            
            if update_plots:
                # Update existing plots
                self.reservoir_fig.canvas.draw()
                
                # Update readout layer visualization with full history
                self.update_readout_plot(node_outputs_history)
                
                plt.pause(0.01)
        
        return all_outputs
        
    def classify_activity(self, movement_values):
        """Classify activity level based on movement values"""
        avg_movement = np.mean(movement_values)
        print(f"DEBUG: Average movement value: {avg_movement:.2f}")
        
        if avg_movement < self.activity_thresholds['low']:
            activity = 'low_activity'
        elif avg_movement < self.activity_thresholds['medium']:
            activity = 'medium_activity'
        else:
            activity = 'high_activity'
            
        print(f"DEBUG: Classified as: {activity}")
        return activity
            
    def train_classifier(self, training_data, labels):
        """Train the output layer classifier with activity levels"""
        try:
            # First ensure all segments have same shape
            min_length = min(len(out) for segment in training_data for out in segment)
            print(f"Normalizing all outputs to length: {min_length}")
            
            # Extract meaningful features from each node
            all_outputs = []
            for segment in training_data:
                segment_features = []
                for node_output in segment:
                    # Extract features from each node's output
                    node_features = [
                        np.mean(node_output),  # Average activity
                        np.std(node_output),   # Variability
                        np.max(node_output),   # Peak activity
                        np.min(node_output),   # Minimum activity
                        # Add more features as needed
                    ]
                    segment_features.extend(node_features)
                all_outputs.append(segment_features)
            
            X = np.array(all_outputs)
            print(f"Training data shape: {X.shape}")
            
            # Convert numerical labels to activity levels
            activity_labels = []
            for i, segment in enumerate(training_data):
                print(f"\nSegment {i+1}:")
                activity = self.classify_activity(segment[0])
                activity_labels.append(activity)
            
            unique_activities = set(activity_labels)
            print(f"\nUnique activity levels found: {unique_activities}")
            
            # Force at least two classes if needed
            if len(unique_activities) < 2:
                print("WARNING: Only one activity level detected. Forcing class diversity...")
                # Split the segments roughly in half between low and medium activity
                mid_point = len(activity_labels) // 2
                activity_labels = ['low_activity'] * mid_point + ['medium_activity'] * (len(activity_labels) - mid_point)
            
            self.classifier.fit(X, activity_labels)
            self.is_trained = True
            print("Classifier training successful")
            
        except Exception as e:
            print(f"Error during classifier training: {e}")
            raise
        
    def predict(self, input_package):
        """Predict activity level with confidence scores"""
        if not self.is_trained:
            return None, None
            
        outputs = self.route_package(input_package)
        
        try:
            # Get expected number of features from classifier
            expected_features = self.classifier.n_features_in_
            print(f"Expected features: {expected_features}")
            
            # Combine all outputs
            all_features = []
            for out in outputs:
                # Ensure each output contributes equally to total feature count
                features_per_output = expected_features // len(outputs)
                if len(out) > features_per_output:
                    out = out[:features_per_output]
                elif len(out) < features_per_output:
                    out = np.pad(out, (0, features_per_output - len(out)))
                all_features.extend(out)
            
            # Ensure total feature count matches exactly
            if len(all_features) > expected_features:
                all_features = all_features[:expected_features]
            elif len(all_features) < expected_features:
                all_features = np.pad(all_features, (0, expected_features - len(all_features)))
                
            X = np.array(all_features).reshape(1, -1)
            print(f"Prediction input shape: {X.shape}")
            
            # Get prediction and probabilities
            prediction = self.classifier.predict(X)[0]
            probabilities = self.classifier.predict_proba(X)[0]
            
            # Get confidence score
            confidence = max(probabilities) * 100
            
            return prediction, confidence
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            print(f"Expected features: {self.classifier.n_features_in_}")
            print(f"Got features: {len(all_features)}")
            raise
        
    def update_classification_plot(self, prediction_data):
        """Update classification plot with activity level and confidence"""
        self.class_ax.clear()
        
        if prediction_data:
            prediction, confidence = prediction_data
            self.class_ax.bar(['Activity Level'], [confidence], 
                            label=f"{prediction}\n{confidence:.1f}% confident")
            self.class_ax.set_ylim(0, 100)
            self.class_ax.set_ylabel('Confidence (%)')
            
            colors = {
                'low_activity': 'blue',
                'medium_activity': 'yellow',
                'high_activity': 'red'
            }
            self.class_ax.get_children()[0].set_color(colors.get(prediction, 'gray'))
            
        self.class_ax.set_title('Activity Classification')
        self.class_ax.legend()
        self.class_fig.canvas.draw_idle()
        
    def process_video_roi(self, video_path):
        """Process video ROI and generate input package"""
        cap = cv2.VideoCapture(video_path)
        
        # Let user select ROI
        ret, frame = cap.read()
        if not ret:
            return None
            
        roi = cv2.selectROI("Select ROI", frame)
        cv2.destroyWindow("Select ROI")
        
        movement_scores = []
        prev_frame = None
        
        while len(movement_scores) < self.package_size:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Extract ROI
            x, y, w, h = roi
            roi_frame = frame[int(y):int(y+h), int(x):int(x+w)]
            gray_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
            
            if prev_frame is not None:
                # Calculate movement score
                diff = cv2.absdiff(gray_roi, prev_frame)
                score = np.sum(diff) / (diff.shape[0] * diff.shape[1])
                movement_scores.append(score)
                
            prev_frame = gray_roi.copy()
            
        cap.release()
        
        # Scale scores to 0-127
        if movement_scores:
            scores = np.array(movement_scores)
            scaled_scores = (scores - scores.min()) * (127.0 / (scores.max() - scores.min()))
            return scaled_scores
            
        return None

    def update_connectivity_plot(self):
        """Update connectivity matrix visualization"""
        self.conn_ax.clear()
        
        # Plot connectivity matrix
        im = self.conn_ax.imshow(self.connectivity * self.weights, 
                               cmap='RdBu', interpolation='nearest')
        self.conn_fig.colorbar(im, ax=self.conn_ax, label='Connection Weight')
        
        # Add weight values as text
        for i in range(self.connectivity.shape[0]):
            for j in range(self.connectivity.shape[1]):
                weight = self.connectivity[i,j] * self.weights[i,j]
                if weight != 0:
                    self.conn_ax.text(j, i, f'{weight:.2f}', 
                                    ha='center', va='center',
                                    color='white' if abs(weight) > 0.5 else 'black')
        
        self.conn_ax.set_title('Reservoir Node Connectivity')
        self.conn_ax.set_xlabel('To Node')
        self.conn_ax.set_ylabel('From Node')
        
        # Add node transformation types as tick labels
        node_labels = [f"Node {i}\n({node.transform_type})" 
                      for i, node in enumerate(self.nodes)]
        self.conn_ax.set_xticks(range(len(self.nodes)))
        self.conn_ax.set_yticks(range(len(self.nodes)))
        self.conn_ax.set_xticklabels(node_labels, rotation=45)
        self.conn_ax.set_yticklabels(node_labels)
        
        self.conn_fig.tight_layout()
        self.conn_fig.canvas.draw()

    def save_model(self, model_path, processor):
        """Save model with ROI information"""
        model_data = {
            'classifier': self.classifier,
            'activity_thresholds': self.activity_thresholds,
            'nodes': self.nodes,
            'roi_info': {
                'roi': processor.roi,
                'cell_size': 40,
                'selected_cells': processor.selected_cells
            }
        }
        joblib.dump(model_data, model_path)
        print(f"Model and ROI info saved to '{model_path}'")

    def load_model(self, model_path):
        """Load model and ROI information"""
        try:
            model_data = joblib.load(model_path)
            self.classifier = model_data['classifier']
            self.activity_thresholds = model_data['activity_thresholds']
            self.nodes = model_data['nodes']
            self.roi_info = model_data.get('roi_info', None)
            self.is_trained = True
            print(f"Model loaded with ROI info: {self.roi_info is not None}")
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False 