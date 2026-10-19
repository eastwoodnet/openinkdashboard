"""
OpenInk Display Profiles (800×600 Logical Canvas · 16-Level Grayscale).
Provides device-agnostic screen specifications for E-Ink terminals.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class DeviceProfile:
    id: str
    name: str
    width: int            # Logical landscape width (800)
    height: int           # Logical landscape height (600)
    physical_width: int   # Device physical framebuffer width (600)
    physical_height: int  # Device physical framebuffer height (800)
    rotation: int         # Clockwise rotation in degrees for portrait framebuffer (90)
    dpr: float            # Device Pixel Ratio (1.0)
    color_mode: str       # 'grayscale_16'
    ppi: int              # 167
    has_grayscale: bool   # True
    has_red_channel: bool # False
    min_font_size: int    # 12


DEFAULT_PROFILE = DeviceProfile(
    id="default",
    name="OpenInk 800×600 (16-Level Grayscale)",
    width=800,
    height=600,
    physical_width=600,
    physical_height=800,
    rotation=90,
    dpr=1.0,
    color_mode="grayscale_16",
    ppi=167,
    has_grayscale=True,
    has_red_channel=False,
    min_font_size=12
)

PROFILES: Dict[str, DeviceProfile] = {
    "default": DEFAULT_PROFILE,
    "svga_800x600": DEFAULT_PROFILE,
    "n516": DEFAULT_PROFILE,
}


def get_profile(profile_id: str = "default") -> DeviceProfile:
    return PROFILES.get(profile_id, DEFAULT_PROFILE)
