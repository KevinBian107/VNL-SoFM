## All wrappers for env modification

import os
import torch
import gymnasium as gym
import numpy as np
import matplotlib.pyplot as plt
from torch.distributions import Normal
import torch.nn as nn
from collections import deque
import random

class FlipRewardWrapper(gym.Wrapper):
    def __init__(self,
                 env,
                 angle_index=2,
                 flip_target_angle=3.14,
                 angle_tolerance=0.2,
                 reward_scale=5.0):
        """
        angle_index: Which index in the observation array corresponds to the agent's pitch angle.
        flip_target_angle: The angle (in radians) representing a 'full flip' or desired orientation.
        angle_tolerance: How close the pitch angle must be to flip_target_angle to get the bonus.
        reward_scale: Additional reward granted if the agent’s pitch is within angle_tolerance of flip_target_angle.
        """
        super(FlipRewardWrapper, self).__init__(env)
        self.angle_index = angle_index
        self.flip_target_angle = flip_target_angle
        self.angle_tolerance = angle_tolerance
        self.reward_scale = reward_scale

    def step(self, action):
        obs, base_reward, terminated, truncated, info = self.env.step(action)

        # We assume obs[self.angle_index] is the pitch angle
        pitch_angle = obs[self.angle_index]  # You must verify that obs[2] is indeed pitch angle!

        # Check how close the pitch is to the desired flip angle
        angle_error = abs(self.flip_target_angle - pitch_angle)
        if angle_error <= self.angle_tolerance:
            base_reward += self.reward_scale

        return obs, base_reward, terminated, truncated, info

class TargetVelocityWrapper(gym.Wrapper):
    def __init__(self, env, target_velocity=2.0, tolerance=0.5):
        super(TargetVelocityWrapper, self).__init__(env)
        self.target_velocity = target_velocity
        self.tolerance = tolerance

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        velocity = obs[
            8
        ]  # Assuming velocity is part of the observation (e.g., index 8)

        # Calculate how close the velocity is to the target velocity
        velocity_error = abs(self.target_velocity - velocity)
        velocity_reward = max(
            0, 1 - (velocity_error / self.tolerance)
        )  # Higher reward for being close to target

        # Modify the reward based on velocity proximity to the target
        reward = velocity_reward

        return obs, reward, terminated, truncated, info


class JumpRewardWrapper(gym.Wrapper):
    def __init__(self, env, jump_target_height=1.0):
        super(JumpRewardWrapper, self).__init__(env)
        self.jump_target_height = jump_target_height

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        torso_height = obs[
            0
        ]  # Assuming the torso's z-coordinate is at index 0 (check observation space)

        # Reward based on how high the torso is, encouraging jumps
        height_reward = torso_height / self.jump_target_height

        reward = height_reward  # Override original reward with height-based reward

        return obs, reward, terminated, truncated, info


class DelayedRewardWrapper(gym.RewardWrapper):
    def __init__(self, env, delay_steps=10):
        super(DelayedRewardWrapper, self).__init__(env)
        self.delay_steps = delay_steps
        self.reward_buffer = deque(maxlen=delay_steps)

    def reward(self, reward):
        # Add the current reward to the buffer
        self.reward_buffer.append(reward)

        # If we haven't accumulated enough steps, return zero reward
        if len(self.reward_buffer) < self.delay_steps:
            return 0.0
        else:
            # Once enough steps have passed, release the oldest reward
            return self.reward_buffer.popleft()

class NoisyObservationWrapper(gym.ObservationWrapper):
    def __init__(self, env, noise_scale=0.05):
        super(NoisyObservationWrapper, self).__init__(env)
        self.noise_scale = noise_scale

    def observation(self, observation):
        # Add Gaussian noise to the observation
        noise = np.random.normal(0, self.noise_scale, size=observation.shape)
        return observation + noise

class PartialObservabilityWrapper(gym.ObservationWrapper):
    def __init__(self, env, observable_ratio=0.5):
        super(PartialObservabilityWrapper, self).__init__(env)
        self.observable_ratio = observable_ratio

    def observation(self, observation):
        # Mask part of the observation to simulate limited observability
        mask = np.random.rand(*observation.shape) < self.observable_ratio
        return np.where(mask, observation, 0)

class ActionMaskingWrapper(gym.Wrapper):
    def __init__(self, env, mask_prob=0.1):
        super(ActionMaskingWrapper, self).__init__(env)
        self.mask_prob = mask_prob

    def step(self, action):
        # Randomly mask actions with a given probability
        if random.random() < self.mask_prob:
            action = np.zeros_like(action)  # Masked action
        return self.env.step(action)

class NonLinearDynamicsWrapper(gym.ActionWrapper):
    def __init__(self, env, dynamic_change_threshold=100):
        super().__init__(env)
        self.dynamic_change_threshold = dynamic_change_threshold
        self.step_count = 0

    def step(self, action):
        self.step_count += 1

        # Apply non-linear dynamics after the threshold
        if self.step_count > self.dynamic_change_threshold:
            # Randomly choose to multiply or divide the action
            if random.random() > 0.5:
                action = action * random.uniform(
                    1.2, 2.0
                )  # Multiply by a random factor
            else:
                action = action / random.uniform(1.2, 2.0)  # Divide by a random factor

        return self.env.step(action)

class PenalizeLargeActionWrapper(gym.Wrapper):
    def __init__(self, env, action_penalty_coeff=0.1):
        super(PenalizeLargeActionWrapper, self).__init__(env)
        self.action_penalty_coeff = action_penalty_coeff

    def step(self, action):
        # Step the environment
        obs, reward, terminated, truncated, info = self.env.step(action)

        # Calculate the penalty for large actions
        action_penalty = self.action_penalty_coeff * np.sum(np.square(action))

        # Adjust the reward
        modified_reward = reward - action_penalty

        return obs, modified_reward, terminated, truncated, info

    def reset(self, **kwargs):
        return self.env.reset(**kwargs)

class NoFlipWrapper(gym.Wrapper):
    def __init__(self, env, flip_penalty=-10.0, max_torso_angle=1.0):
        super(NoFlipWrapper, self).__init__(env)
        self.flip_penalty = flip_penalty
        self.max_torso_angle = (
            max_torso_angle  # Maximum tilt angle (in radians) before applying a penalty
        )

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)

        # Assuming torso pitch (tilt) is at index 2 in the observation array
        torso_pitch = obs[2]

        # Check if the torso pitch exceeds the maximum allowable angle (i.e., the agent is flipping)
        if abs(torso_pitch) > self.max_torso_angle:
            reward += self.flip_penalty  # Apply a penalty for flipping
            terminated = True  # Optionally end the episode if the agent flips over

        return obs, reward, terminated, truncated, info

    def reset(self, **kwargs):
        return self.env.reset(**kwargs)

class StabilityWrapper(gym.Wrapper):
    def __init__(
        self, env, torso_height_range=(0.5, 1.5), orientation_penalty_scale=1.0
    ):
        super().__init__(env)
        self.torso_height_range = torso_height_range
        self.orientation_penalty_scale = orientation_penalty_scale

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)

        # Get torso height and orientation (z-axis rotation) from state
        # HalfCheetah state space: [x_torso, z_torso, theta_torso, ...other joints...]
        torso_height = observation[1]  # z coordinate of torso
        torso_angle = observation[2]  # rotation of torso

        # Penalize if torso height is outside desired range
        height_penalty = 0
        if (
            torso_height < self.torso_height_range[0]
            or torso_height > self.torso_height_range[1]
        ):
            height_penalty = -1.0

        # Penalize extreme rotations (being upside down)
        # torso_angle is in radians, we want to penalize rotations > 45 degrees
        orientation_penalty = -abs(torso_angle) if abs(torso_angle) > np.pi / 4 else 0
        orientation_penalty *= self.orientation_penalty_scale

        # Modify reward
        modified_reward = reward + height_penalty + orientation_penalty

        # Add early termination for extreme cases
        if abs(torso_angle) > np.pi / 2:  # terminate if rotation > 90 degrees
            terminated = True
            modified_reward -= 10  # Additional penalty for termination

        return observation, modified_reward, terminated, truncated, info


class DelayedHalfCheetahEnv(gym.Wrapper):
    def __init__(
        self,
        env,
        proprio_delay=2,  # 20ms at 100Hz
        force_delay=5,  # 50ms at 100Hz
    ):
        super().__init__(env)
        self.proprio_delay = proprio_delay
        self.force_delay = force_delay

        # Initialize buffers for different sensor types
        self.proprio_buffer = deque(maxlen=proprio_delay + 1)
        self.force_buffer = deque(maxlen=force_delay + 1)

        # Half-Cheetah observation space indices:
        # [0:8] - positions (proprioception)
        # [8:17] - velocities (proprioception)
        # [17:] - external forces/contact forces
        self.proprio_indices = list(range(0, 17))
        self.force_indices = list(range(17, self.env.observation_space.shape[0]))

    def _get_delayed_obs(self, observation):
        delayed_obs = observation.copy()

        # Get delayed proprioceptive feedback
        if len(self.proprio_buffer) == self.proprio_delay + 1:
            delayed_obs[self.proprio_indices] = self.proprio_buffer[0][
                self.proprio_indices
            ]

        # Get delayed force feedback
        if len(self.force_buffer) == self.force_delay + 1:
            delayed_obs[self.force_indices] = self.force_buffer[0][self.force_indices]

        return delayed_obs

    def reset(self, **kwargs):
        observation, info = self.env.reset(**kwargs)

        # Clear and initialize all buffers with initial observation
        self.proprio_buffer.clear()
        self.force_buffer.clear()

        for _ in range(max(self.proprio_delay, self.force_delay) + 1):
            self.proprio_buffer.append(observation)
            self.force_buffer.append(observation)

        delayed_obs = self._get_delayed_obs(observation)
        return delayed_obs, info

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)

        # Update delay buffers
        self.proprio_buffer.append(observation)
        self.force_buffer.append(observation)

        delayed_obs = self._get_delayed_obs(observation)

        return delayed_obs, reward, terminated, truncated, info

    def get_delay_info(self):
        return {
            "proprioception_delay_ms": self.proprio_delay * 10,  # Assuming 100Hz
            "force_delay_ms": self.force_delay * 10,
        }
