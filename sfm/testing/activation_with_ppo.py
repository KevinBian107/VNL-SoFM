import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import torch
import gymnasium as gym
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from mvp.ppo import Args, Agent as PPOAgent, make_env

class PPOActivationVisualizer:
    def __init__(self, agent, envs, device, fig_size=(20, 5)):
        self.agent = agent
        self.envs = envs
        self.device = device
        self.fig_size = fig_size
        
        # Initialize visualization
        plt.ion()
        self.fig = plt.figure(figsize=self.fig_size)
        
        # Create subplots: env view, actor activation space, action space
        self.ax_env = self.fig.add_subplot(131)
        self.ax_actor = self.fig.add_subplot(132)
        self.ax_action = self.fig.add_subplot(133)
        
        # Initialize PCAs
        self.actor_pca = PCA(n_components=2)
        self.action_pca = PCA(n_components=2)
        
        self.current_actor_trajectory = []
        self.current_action_trajectory = []
        self.actor_trajectory_line = None
        self.action_trajectory_line = None
        
        # Get initial frame
        obs, _ = self.envs.reset()
        frame = self.envs.call('render')[0]
        self.frame_shape = frame.shape

    def get_actor_activation(self, obs):
        """Extract intermediate activation from the actor network"""
        # Get activation from second-to-last layer
        x = obs
        for i, layer in enumerate(self.agent.actor_mean):
            x = layer(x)
            if i == len(self.agent.actor_mean) - 2:  # Second-to-last layer
                return x
        return x
        
    def collect_initial_representations(self, num_episodes=5):
        """Collect initial actor and action representations"""
        actor_activations = []
        actions = []
        episode_returns = []
        episode_steps = []
        
        print("Collecting initial representations...")
        for episode in range(num_episodes):
            next_obs, _ = self.envs.reset()
            next_obs = torch.Tensor(next_obs).to(self.device)
            next_done = torch.zeros(self.envs.num_envs).to(self.device)
            episode_return = torch.zeros(self.envs.num_envs).to(self.device)
            step_count = 0
            
            while not next_done.all():
                with torch.no_grad():
                    # Get actor's hidden activation
                    actor_hidden = self.get_actor_activation(next_obs)
                    actor_activations.append(actor_hidden.cpu().numpy())
                    
                    # Get action
                    action, _, _, _ = self.agent.get_action_and_value(next_obs)
                    actions.append(action.cpu().numpy())
                    
                    # Step environment
                    next_obs, reward, terminations, truncations, _ = self.envs.step(action.cpu().numpy())
                    next_obs = torch.Tensor(next_obs).to(self.device)
                    next_done = torch.logical_or(torch.Tensor(terminations), torch.Tensor(truncations)).to(self.device)
                    episode_return += torch.Tensor(reward).to(self.device) * (~next_done)
                    step_count += 1

            print(f"Episode {episode + 1}/{num_episodes} completed with return: {episode_return.item()}")
            episode_returns.append(episode_return.item())
            episode_steps.append(step_count)
        
        return (np.vstack(actor_activations), np.vstack(actions), 
                episode_returns, episode_steps)

    def setup_visualization(self):
        """Initialize visualization with collected data"""
        (initial_actor_activations, initial_actions, 
         episode_returns, episode_steps) = self.collect_initial_representations()
        
        self.reduced_actor = self.actor_pca.fit_transform(initial_actor_activations)
        self.reduced_actions = self.action_pca.fit_transform(initial_actions)
        
        # Clear previous plots
        self.ax_env.clear()
        self.ax_actor.clear()
        self.ax_action.clear()
        
        # Plot background points for actor space
        scatter_actor = self.ax_actor.scatter(
            self.reduced_actor[:, 0], 
            self.reduced_actor[:, 1], 
            c=np.repeat(episode_returns, episode_steps), 
            cmap='viridis', 
            alpha=0.5
        )
        plt.colorbar(scatter_actor, ax=self.ax_actor, label='Episode Return')
        
        # Plot background points for action space
        scatter_action = self.ax_action.scatter(
            self.reduced_actions[:, 0], 
            self.reduced_actions[:, 1], 
            c=np.repeat(episode_returns, episode_steps), 
            cmap='viridis', 
            alpha=0.5
        )
        plt.colorbar(scatter_action, ax=self.ax_action, label='Episode Return')
        
        # Setup current points and trajectories
        self.current_actor_point = self.ax_actor.scatter(
            [], [], c='red', s=100, label='Current state'
        )
        self.current_action_point = self.ax_action.scatter(
            [], [], c='red', s=100, label='Current state'
        )
        
        self.actor_trajectory_line, = self.ax_actor.plot(
            [], [], 'r-', alpha=0.5, linewidth=1
        )
        self.action_trajectory_line, = self.ax_action.plot(
            [], [], 'r-', alpha=0.5, linewidth=1
        )
        
        # Add explained variance ratio to titles
        actor_var = self.actor_pca.explained_variance_ratio_
        action_var = self.action_pca.explained_variance_ratio_
        
        self.ax_actor.set_title(f'Actor Activation Space\nVar: {actor_var[0]:.2f}, {actor_var[1]:.2f}')
        self.ax_action.set_title(f'Action Space\nVar: {action_var[0]:.2f}, {action_var[1]:.2f}')
        self.ax_actor.legend()
        self.ax_action.legend()
        
        # Initialize environment display
        self.env_image = self.ax_env.imshow(np.zeros(self.frame_shape))
        self.ax_env.set_title('Environment')
        self.ax_env.axis('off')
        
        plt.tight_layout()
        self.fig.canvas.draw()
        print("Visualization setup completed")
    
    def update_visualization(self, obs, episode_return):
        """Update visualizations with current state"""
        try:
            # Get current representations
            with torch.no_grad():
                actor_hidden = self.get_actor_activation(torch.Tensor(obs).to(self.device))
                action, _, _, _ = self.agent.get_action_and_value(torch.Tensor(obs).to(self.device))
                
                current_actor = self.actor_pca.transform(actor_hidden.cpu().numpy())
                current_action = self.action_pca.transform(action.cpu().numpy())
            
            # Update current points
            self.current_actor_point.set_offsets(current_actor)
            self.current_action_point.set_offsets(current_action)
            
            # Update trajectories
            self.current_actor_trajectory.append(current_actor[0])
            self.current_action_trajectory.append(current_action[0])
            
            if len(self.current_actor_trajectory) > 1:
                actor_trajectory = np.array(self.current_actor_trajectory)
                action_trajectory = np.array(self.current_action_trajectory)
                self.actor_trajectory_line.set_data(
                    actor_trajectory[:, 0], actor_trajectory[:, 1]
                )
                self.action_trajectory_line.set_data(
                    action_trajectory[:, 0], action_trajectory[:, 1]
                )
            
            # Update environment rendering
            frame = self.envs.call('render')[0]
            if frame is not None:
                self.env_image.set_array(frame)
            
            # Update title with current return
            self.ax_env.set_title(f'Environment (Return: {episode_return:.2f})')
            
            # Refresh display
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
            plt.pause(0.001)
            
        except Exception as e:
            print(f"Error in update_visualization: {e}")
            import traceback
            traceback.print_exc()
    
    def run_episode(self):
        """Run episode with visualization"""
        next_obs, _ = self.envs.reset()
        next_obs = torch.Tensor(next_obs).to(self.device)
        next_done = torch.zeros(self.envs.num_envs).to(self.device)
        episode_return = torch.zeros(self.envs.num_envs).to(self.device)
        step_count = 0
        
        print("Starting new episode...")
        self.current_actor_trajectory = []
        self.current_action_trajectory = []
        
        while not next_done.all():
            self.update_visualization(next_obs, episode_return.item())
            
            with torch.no_grad():
                action, _, _, _ = self.agent.get_action_and_value(next_obs)
            
            next_obs, reward, terminations, truncations, _ = self.envs.step(action.cpu().numpy())
            next_obs = torch.Tensor(next_obs).to(self.device)
            next_done = torch.logical_or(torch.Tensor(terminations), torch.Tensor(truncations)).to(self.device)
            episode_return += torch.Tensor(reward).to(self.device) * (~next_done)
            step_count += 1
            
            if step_count % 100 == 0:
                print(f"Steps: {step_count}, Current Return: {episode_return.item():.2f}")
        
        final_return = episode_return.item()
        print(f"Episode completed - Steps: {step_count}, Return: {final_return:.2f}")
        return final_return

def main():
    print("Initializing environment and agent...")
    args = Args()
    device = torch.device("cuda" if torch.cuda.is_available() and args.cuda else "cpu")
    print(f"Using device: {device}")
    
    envs = gym.vector.SyncVectorEnv(
        [make_env(args.env_id, i, True, args.exp_name, args.gamma) for i in range(1)]
    )
    print(f"Environment created: {args.env_id}")
    
    agent = PPOAgent(envs).to(device)
    model_path = os.path.join(os.getcwd(), "mvp", "params", "ppo_vector_5e6.pth")
    agent.load_state_dict(torch.load(model_path, map_location=device))
    print("Model loaded successfully")
    
    visualizer = PPOActivationVisualizer(agent, envs, device)
    visualizer.setup_visualization()
    
    num_episodes = 5
    returns = []
    for episode in range(num_episodes):
        print(f"\nStarting Episode {episode + 1}/{num_episodes}")
        episode_return = visualizer.run_episode()
        returns.append(episode_return)
        print(f"Episode {episode + 1}/{num_episodes} completed, Return: {episode_return:.2f}")
    
    print("\nAll episodes completed")
    print(f"Average Return: {np.mean(returns):.2f} ± {np.std(returns):.2f}")
    plt.ioff()
    plt.show()

if __name__ == "__main__":
    main()