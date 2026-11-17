"""PanelFlow Motion Guide Model (The Choreographer) Subsystem.
Lightweight Kinematic Diffusion Transformer trained locally to guide frontier video models.
"""
from engine.motion_bank.guide.motion_dit import MotionChoreographerDiT
from engine.motion_bank.guide.generator import MotionGenerator

__all__ = ["MotionChoreographerDiT", "MotionGenerator"]
