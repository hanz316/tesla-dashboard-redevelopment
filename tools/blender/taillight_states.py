#!/usr/bin/env python3
"""Taillight state semantics, as pure data.

No Blender import: the composition rules are the part that has to be provably
correct (brake must not erase an indicator, hazard must drive both sides, left
and right must be independent), so they live here where a host test can check
them without a render.

MODEL A cannot prove the real Tesla optical segmentation, so which lamp carries
which channel is a documented VISUAL_APPROXIMATION:

  outer lamp (rear_lights, FIXED_BODY)      brake / rear running light
  inner lamp (rear_lightsl/r, TRUNK_MOVING) indicator, per side
  brake lamp (light_breake, no interior)    brake, by material/emission only
"""

CHANNELS = ("BRAKE", "INDICATOR_LEFT", "INDICATOR_RIGHT", "RUNNING")

# Every state the freeze gate requires, plus the composites. A state is a set of
# logical channels; nothing else about a state is allowed to change a material.
STATES = {
    "OFF": frozenset(),
    "BRAKE": frozenset({"BRAKE"}),
    "LEFT_INDICATOR": frozenset({"INDICATOR_LEFT"}),
    "RIGHT_INDICATOR": frozenset({"INDICATOR_RIGHT"}),
    "HAZARD": frozenset({"INDICATOR_LEFT", "INDICATOR_RIGHT"}),
    "HEADLIGHT": frozenset({"RUNNING"}),
    "BRAKE_LEFT": frozenset({"BRAKE", "INDICATOR_LEFT"}),
    "BRAKE_RIGHT": frozenset({"BRAKE", "INDICATOR_RIGHT"}),
    "BRAKE_HAZARD": frozenset({"BRAKE", "INDICATOR_LEFT", "INDICATOR_RIGHT"}),
    "HEADLIGHT_LEFT": frozenset({"RUNNING", "INDICATOR_LEFT"}),
    "HEADLIGHT_RIGHT": frozenset({"RUNNING", "INDICATOR_RIGHT"}),
}

# Which lamp carries which channel. The inner lamp is the indicator because the
# outer lamp carries the brake and a single lamp object can hold only one
# material at a time - so brake and indicator cannot erase each other.
LAMP_CHANNEL = {
    "rear_lights": "BRAKE",
    "rear_lightsl": "INDICATOR_LEFT",
    "rear_lightsr": "INDICATOR_RIGHT",
    "light_breake": "BRAKE",
}

# The rear running light shares the brake lamp in this approximation, at a
# lower emission strength, exactly as a tail light is a dimmed brake light.
RUNNING_IS_BRAKE_LAMP = True


def channels_for(state):
    if state not in STATES:
        raise KeyError(f"unknown taillight state: {state}")
    return STATES[state]


def lamp_channels(state):
    """Logical channels per lamp object for a state, in one deterministic pass.

    Returns {lamp_name: frozenset(channels)} where an empty set means the lamp
    is off. A channel is only granted to the lamp that carries it, so a state
    can never light a lamp it has no channel for.
    """
    active = channels_for(state)
    out = {}
    for lamp, channel in LAMP_CHANNEL.items():
        if channel in active:
            out[lamp] = frozenset({channel})
            continue
        if (channel == "BRAKE" and RUNNING_IS_BRAKE_LAMP
                and "RUNNING" in active):
            out[lamp] = frozenset({"RUNNING"})
            continue
        out[lamp] = frozenset()
    return out


def is_lit(state, lamp):
    return bool(lamp_channels(state)[lamp])


def material_key(channels):
    """The single material key a lamp shows for a set of active channels.

    A lamp has one material at a time, so a state that asked one lamp to be
    brake AND indicator at once could only be resolved by priority - and a
    priority rule is exactly how a brake would silently erase an indicator.
    The mapping above puts them on different lamps, so this raises instead of
    choosing. The regression test asserts no state ever produces that
    combination, which is what makes "brake must not erase an indicator"
    structural rather than a matter of ordering.
    """
    if "BRAKE" in channels and ("INDICATOR_LEFT" in channels
                                or "INDICATOR_RIGHT" in channels):
        raise ValueError(
            "one lamp cannot show brake and indicator at the same time; "
            "assign them to different lamps instead of picking a priority")
    if "INDICATOR_LEFT" in channels and "INDICATOR_RIGHT" in channels:
        raise ValueError("one lamp cannot show both indicator sides")
    for key in ("BRAKE", "RUNNING", "INDICATOR_LEFT", "INDICATOR_RIGHT"):
        if key in channels:
            return key
    return "OFF"
