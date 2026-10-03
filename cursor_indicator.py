from __future__ import annotations

import math
import platform
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import ClassVar

from PIL import Image, ImageChops, ImageDraw, ImageFont

from transcription_progress import estimated_progress

INDICATOR_SIZE = 96
INDICATOR_TARGET_FPS = 120
INDICATOR_IDLE_POLL_FPS = 30
INDICATOR_SUPERSAMPLE_SCALE = 4
TRACK_WIDTH = 1.25
INTRO_DURATION_S = 0.16
OUTRO_DURATION_S = 0.2
COLOR_RESPONSE_S = 0.025
SPEED_RESPONSE_S = 0.08
BASE_ROTATION_DEG_S = 190.0


@dataclass(frozen=True)
class IndicatorFrame:
    radius: float
    arc_start: float
    arc_extent: float
    arc_width: float
    center_dx: float = 0.0
    center_dy: float = 0.0
    marker_scale: float = 1.0
    marker_spin: float = 0.0
    extent_gain: float = 1.0
    estimated: bool = False


@dataclass(frozen=True)
class JobView:
    job_id: int
    phase: str = "transcribing"
    mode: str = "raw"
    started_at: float = 0.0
    expected_s: float = 0.0

    def progress(self, now: float) -> float | None:
        if self.phase != "transcribing":
            return None
        return estimated_progress(self.started_at, self.expected_s, now)


@dataclass(frozen=True)
class TerminalView:
    job_id: int
    outcome: str
    at: float


@dataclass(frozen=True)
class OrbitFrame:
    phase: float
    radius: float = 36.0
    extent: float = 64.0
    width: float = 1.8
    opacity: float = 0.82
    color: tuple[int, int, int, int] = (255, 165, 0, 255)
    mode: str = "raw"
    split: bool = False
    ticks: float = 0.0
    failed: bool = False
    drop: float = 0.0
    queued: int = 0


@dataclass(frozen=True)
class CursorIndicatorSnapshot:
    visible: bool
    color: tuple[int, int, int, int]
    motion_speed: float = 1.0
    label: str = ""
    mode: str = "raw"
    activity: str = "recording"
    audio_level: float = 0.0
    jobs: tuple[JobView, ...] = ()
    terminals: tuple[TerminalView, ...] = ()


@dataclass(frozen=True)
class IndicatorVisual:
    visible: bool
    frame: IndicatorFrame
    color: tuple[int, int, int, int]
    opacity: float
    label: str = ""
    mode: str = "raw"
    previous_mode: str = "raw"
    mode_mix: float = 1.0
    activity: str = "recording"
    orbits: tuple[OrbitFrame, ...] = ()


class BackgroundOrbit:
    """Independent outer orbit: terminal events, never color changes, end jobs."""

    def __init__(self):
        self.phase = -90.0
        self.last_at = None
        self.started_at = 0.0
        self.radius_from = 36.0
        self.known: dict[int, JobView] = {}
        self.exits: list[tuple[TerminalView, float, JobView]] = []
        self.was_active = False
        self.color = (255, 165, 0, 255)
        self.last_lead = None
        self.quiet_exit = None

    def update(self, snapshot, now, primary_phase):
        dt = 0.0 if self.last_at is None else min(0.1, max(0.0, now - self.last_at))
        self.last_at = now
        self.phase = (self.phase + 120 * dt) % 360
        jobs = list(snapshot.jobs)
        # The primary displays the newest pending job when the microphone is idle.
        background = jobs if snapshot.activity == "recording" and snapshot.visible else jobs[:-1]
        terminal_ids = {terminal.job_id for terminal in snapshot.terminals}
        if (
            self.was_active
            and not background
            and self.last_lead is not None
            and not terminal_ids.intersection(self.known)
        ):
            self.quiet_exit = (now, self.last_lead)
        for terminal in snapshot.terminals:
            job = self.known.pop(terminal.job_id, None)
            if (
                job is not None
                and terminal.outcome in ("success", "error")
                and now - terminal.at < 0.56
            ):
                self.exits.append((terminal, self.phase, job))
        self.exits = [entry for entry in self.exits[-4:] if now - entry[0].at < 0.56]
        if background and not self.was_active:
            self.started_at = now
            self.phase = primary_phase
            self.radius_from = 27.0
            self.quiet_exit = None
        self.was_active = bool(background)
        self.known = {job.job_id: job for job in background}
        frames = []
        if background:
            job = background[0]
            estimated = job.progress(now)
            progress = min(1.0, max(0.0, (now - self.started_at) / 0.22))
            eased = 4 * progress**3 if progress < 0.5 else 1 - (-2 * progress + 2) ** 3 / 2
            target = (220, 90, 235, 255) if job.phase == "rewriting" else (255, 165, 0, 255)
            self.color = blend_color(self.color, target, 1 - math.exp(-dt / 0.04))
            frames.append(
                OrbitFrame(
                    self.phase,
                    self.radius_from + (36 - self.radius_from) * eased,
                    64 + 286 * estimated
                    if estimated is not None
                    else 64 + 6 * math.sin(math.tau * 0.4 * now),
                    color=self.color,
                    mode=job.mode,
                    split=job.phase == "rewriting",
                    queued=max(0, len(background) - 1),
                )
            )
        self.last_lead = frames[0] if frames else None
        if self.quiet_exit is not None:
            started, last = self.quiet_exit
            fade = min(1.0, max(0.0, (now - started) / 0.16))
            if fade < 1:
                frames.append(replace(last, opacity=last.opacity * (1 - fade**2)))
            else:
                self.quiet_exit = None
        for terminal, phase, _job in self.exits:
            age = max(0.0, now - terminal.at)
            if terminal.outcome == "success":
                close = 1 - (1 - min(1.0, age / 0.18)) ** 3
                expand = 1 - (1 - min(1.0, max(0.0, (age - 0.18) / 0.24))) ** 4
                opacity = 1 - min(1.0, max(0.0, (age - 0.30) / 0.26)) ** 2
                color = blend_color((255, 165, 0, 255), (80, 220, 135, 255), age / 0.14)
                ticks = max(0.0, 1 - (age - 0.20) / 0.28) if age >= 0.20 else 0.0
                frames.append(
                    OrbitFrame(
                        phase + 120 * age,
                        36 + 4.5 * expand,
                        64 + 296 * close,
                        1.8 + 1.2 * math.sin(math.pi * min(1, max(0, (age - 0.18) / 0.24))),
                        opacity,
                        color,
                        ticks=ticks,
                    )
                )
            else:
                fracture = min(1.0, max(0.0, (age - 0.24) / 0.28))
                shake = 7 * math.exp(-12 * age) * math.sin(math.tau * 9 * age)
                frames.append(
                    OrbitFrame(
                        phase + shake,
                        opacity=1 - fracture,
                        color=(176, 128, 96, 255),
                        failed=True,
                        drop=4 * fracture**2,
                    )
                )
        return tuple(frames)


def indicator_frame(elapsed_s: float, motion_speed: float = 1.0) -> IndicatorFrame:
    pulse = math.sin(elapsed_s * math.tau * 0.8)
    return IndicatorFrame(
        radius=25.0 + pulse * 1.5,
        arc_start=(elapsed_s * 190.0 * motion_speed - 90.0) % 360.0,
        arc_extent=105.0 + math.sin(elapsed_s * math.tau * 0.55) * 14.0,
        arc_width=2.6 + (pulse + 1.0) * 0.35,
    )


def color_hex(color: tuple[int, int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def muted_color(color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return (*tuple(round(channel * 0.42) for channel in color[:3]), 255)


def muted_color_hex(color: tuple[int, int, int, int]) -> str:
    return color_hex(muted_color(color))


def blend_color(
    start: tuple[int, int, int, int],
    end: tuple[int, int, int, int],
    amount: float,
) -> tuple[int, int, int, int]:
    progress = min(1.0, max(0.0, amount))
    return tuple(
        round(first + (second - first) * progress) for first, second in zip(start, end, strict=True)
    )


class IndicatorAnimator:
    def __init__(self) -> None:
        self.background = BackgroundOrbit()
        self.last_at: float | None = None
        self.cycle_started_at = 0.0
        self.intro_started_at = 0.0
        self.outro_started_at = 0.0
        self.phase = -90.0
        self.current_color = (0, 0, 0, 0)
        self.current_speed = 1.0
        self.last_snapshot: CursorIndicatorSnapshot | None = None
        self.present = False
        self.target_visible = False
        self.audio_level = 0.0
        self.radius_offset = 0.0
        self.previous_mode = "raw"
        self.mode = "raw"
        self.mode_changed_at = 0.0
        self.activity = "recording"
        self.activity_started_at = 0.0
        self.geometry_scale = 0.08
        self.opacity = 0.0
        self.transition_scale = 0.08
        self.transition_opacity = 0.0
        self.fresh_intro = True
        self.impulses: list[tuple[float, float]] = []
        self.jostle_armed = True
        self.last_onset_at = -math.inf

    def update(self, snapshot: CursorIndicatorSnapshot, now: float) -> IndicatorVisual:
        orbits = self.background.update(snapshot, now, self.phase)
        visual = self._update_primary(snapshot, now)
        if snapshot.activity == "transcribing" and snapshot.jobs:
            progress = snapshot.jobs[-1].progress(now)
            if progress is not None:
                frame = visual.frame
                extent = 64 + 286 * progress
                # Grow behind the traveler, preserving its angular position.
                frame = replace(
                    frame,
                    arc_start=frame.arc_start + frame.arc_extent - extent,
                    arc_extent=extent,
                    estimated=True,
                )
                visual = replace(visual, frame=frame)
        return replace(visual, visible=visual.visible or bool(orbits), orbits=orbits)

    def _update_primary(self, snapshot: CursorIndicatorSnapshot, now: float) -> IndicatorVisual:
        previous_at = self.last_at
        self.last_at = now
        delta_s = 0.0 if previous_at is None else min(0.1, max(0.0, now - previous_at))

        if snapshot.visible:
            if not self.present:
                self.present = True
                self.phase = -90.0
                self.cycle_started_at = now
                self.intro_started_at = now
                self.current_color = snapshot.color
                self.current_speed = snapshot.motion_speed
                self.audio_level = 0.0
                self.radius_offset = 0.0
                self.mode = self.previous_mode = snapshot.mode
                self.activity = snapshot.activity
                self.activity_started_at = now
                self.geometry_scale = 0.08
                self.opacity = 0.0
                self.geometry_scale = 0.5
                self.impulses.clear()
                self.jostle_armed = True
                self.last_onset_at = -math.inf
                self.fresh_intro = True
                delta_s = 0.0
            elif not self.target_visible:
                self.fresh_intro = False
            if not self.target_visible:
                self.intro_started_at = now
                self.transition_scale = self.geometry_scale
                self.transition_opacity = self.opacity
            if snapshot.mode != self.mode:
                self.previous_mode = self.mode
                self.mode = snapshot.mode
                self.mode_changed_at = now
            if snapshot.activity != self.activity:
                self.activity = snapshot.activity
                self.activity_started_at = now
            self.target_visible = True
            self.last_snapshot = snapshot
        elif self.target_visible:
            self.target_visible = False
            self.outro_started_at = now
            self.transition_scale = self.geometry_scale
            self.transition_opacity = self.opacity

        effective_snapshot = snapshot if snapshot.visible else self.last_snapshot
        if not self.present or effective_snapshot is None:
            return self._hidden_visual()

        color_progress = 1.0 - math.exp(-delta_s / COLOR_RESPONSE_S)
        speed_progress = 1.0 - math.exp(-delta_s / SPEED_RESPONSE_S)
        self.current_color = blend_color(
            self.current_color,
            effective_snapshot.color,
            color_progress,
        )
        target_speed = effective_snapshot.motion_speed
        travel = (
            target_speed * delta_s
            + (self.current_speed - target_speed) * SPEED_RESPONSE_S * speed_progress
        )
        self.current_speed += (target_speed - self.current_speed) * speed_progress
        age = max(0.0, now - self.cycle_started_at)

        def entry_sweep(t: float) -> float:
            return 26.6 * (1.0 - (1.0 - min(1.0, max(0.0, t / 0.28))) ** 4)

        self.phase = (
            self.phase
            + BASE_ROTATION_DEG_S * travel
            + entry_sweep(age)
            - entry_sweep(
                max(0.0, (previous_at if previous_at is not None else now) - self.cycle_started_at)
            )
        ) % 360.0

        if self.target_visible:
            progress = min(1.0, max(0.0, (now - self.intro_started_at) / INTRO_DURATION_S))
            eased = 1.0 - (1.0 - progress) ** 3
            geometry_scale = self.transition_scale + (1.0 - self.transition_scale) * eased
            opacity = self.transition_opacity + (1.0 - self.transition_opacity) * eased
            if self.fresh_intro:
                if age < 0.13:
                    geometry_scale = 0.5 + 0.55 * (1.0 - (1.0 - age / 0.13) ** 3)
                else:
                    settle = min(1.0, (age - 0.13) / 0.15)
                    geometry_scale = 1.025 + 0.025 * math.cos(math.pi * settle)
                opacity = 1.0 - (1.0 - min(1.0, age / 0.08)) ** 2
        else:
            progress = min(1.0, max(0.0, (now - self.outro_started_at) / OUTRO_DURATION_S))
            if progress >= 1.0:
                self.present = False
                self.last_snapshot = None
                return self._hidden_visual()
            geometry_scale = self.transition_scale * (1.0 - progress**3)
            opacity = self.transition_opacity * (1.0 - progress)

        # Reversals begin at the last displayed envelope, including partial entry/exit.
        self.geometry_scale = geometry_scale
        self.opacity = opacity

        base_frame = indicator_frame(now - self.cycle_started_at)
        level = effective_snapshot.audio_level
        level = min(1.0, max(0.0, level)) if math.isfinite(level) else 0.0
        if effective_snapshot.activity != "recording":
            level = 0.0
        response = 0.035 if level > self.audio_level else 0.16
        previous_level = self.audio_level
        self.audio_level += (level - self.audio_level) * (1.0 - math.exp(-delta_s / response))
        if self.jostle_armed and level > 0.12 and previous_level < 0.12 <= self.audio_level:
            # Solve the exponential crossing rather than quantizing onsets to a frame.
            crossing = response * math.log((level - previous_level) / (level - 0.12))
            onset = now - delta_s + crossing
            if onset - self.last_onset_at >= 0.16:
                self.impulses.append((onset, math.radians(self.phase + 90.0)))
                self.last_onset_at = onset
            self.jostle_armed = False
        if self.audio_level < 0.06:
            self.jostle_armed = True
        self.impulses = [(t, d) for t, d in self.impulses[-3:] if now - t < 0.35]
        radial = dx = dy = 0.0
        for onset, direction in self.impulses:
            t = max(0.0, now - onset)
            impulse = 0.8 * math.exp(-20.735 * t) * math.sin(65.933 * t)
            radial += impulse
            dx += impulse * math.cos(direction)
            dy += impulse * math.sin(direction)
        jostle = math.tanh(radial)
        distance = math.hypot(dx, dy)
        offset_scale = 0.7 * math.tanh(distance) / distance if distance else 0.0
        target_offset = -2.0 if effective_snapshot.activity == "transcribing" else 0.0
        self.radius_offset += (target_offset - self.radius_offset) * speed_progress
        terminal_age = max(0.0, now - self.activity_started_at)
        flourish = (
            2.5 * math.sin(min(1.0, terminal_age / 0.35) * math.pi)
            if effective_snapshot.activity == "success"
            else 0.0
        )
        extent_gain = 1.0 - 0.65 * (1.0 - min(1.0, age / 0.22)) ** 3
        extent = (base_frame.arc_extent + 16.0 * self.audio_level) * extent_gain
        frame = IndicatorFrame(
            radius=min(
                31.0,
                (
                    25.0
                    + (base_frame.radius - 25.0) * 0.3
                    + self.audio_level * 1.6
                    + 1.1 * jostle
                    + self.radius_offset
                    + flourish
                )
                * geometry_scale,
            ),
            arc_start=(self.phase + 6.0 * jostle - extent) % 360.0,
            arc_extent=extent,
            arc_width=min(
                3.8,
                base_frame.arc_width * (0.55 + 0.45 * min(1.0, geometry_scale))
                + 0.4 * self.audio_level,
            ),
            center_dx=dx * offset_scale * geometry_scale,
            center_dy=dy * offset_scale * geometry_scale,
            marker_scale=1.0 + 0.15 * math.sin(math.pi * min(1.0, age / 0.28)),
            marker_spin=90.0 * (1.0 - min(1.0, age / 0.28)) ** 3,
            extent_gain=extent_gain,
        )
        return IndicatorVisual(
            True,
            frame,
            self.current_color,
            opacity,
            effective_snapshot.label,
            effective_snapshot.mode,
            self.previous_mode,
            min(1.0, max(0.0, (now - self.mode_changed_at) / 0.1)),
            effective_snapshot.activity,
        )

    def _hidden_visual(self) -> IndicatorVisual:
        return IndicatorVisual(
            False,
            IndicatorFrame(0.0, self.phase, 0.0, 0.0),
            self.current_color,
            0.0,
        )


@lru_cache(maxsize=4)
def indicator_label_font(scale: int):
    return ImageFont.load_default(size=11 * scale)


def draw_background_orbit(draw, orbit: OrbitFrame, center: float, scale: int):
    radius = orbit.radius * scale
    cy = center + orbit.drop * scale
    bounds = (center - radius, cy - radius, center + radius, cy + radius)
    fill = (*orbit.color[:3], round(255 * orbit.opacity))
    if not orbit.ticks and not orbit.failed:
        draw.ellipse(
            bounds,
            outline=(*orbit.color[:3], round(70 * orbit.opacity)),
            width=max(1, round(0.8 * scale)),
        )
    count = 3 if orbit.failed else 2 if orbit.split else 1
    gap = 10 if orbit.failed else 8 if orbit.split else 0
    part = (orbit.extent - gap * (count - 1)) / count
    for index in range(count):
        start = orbit.phase - orbit.extent + index * (part + gap)
        draw.arc(
            bounds,
            start=start,
            end=start + part,
            fill=fill,
            width=max(1, round(orbit.width * scale)),
        )

    def point(angle, r):
        return center + math.cos(math.radians(angle)) * r * scale, cy + math.sin(
            math.radians(angle)
        ) * r * scale

    if orbit.mode in ("tidy", "fun"):
        x, y = point(orbit.phase, orbit.radius)
        r = (2.2 if orbit.mode == "tidy" else 2.6) * scale
        points = []
        count = 4 if orbit.mode == "tidy" else 8
        for index in range(count):
            angle = math.radians(index * 360 / count - 90)
            length = r if count == 4 or index % 2 == 0 else r * 0.3
            points.append((x + math.cos(angle) * length, y + math.sin(angle) * length))
        draw.polygon(points, fill=fill)
    for index in range(min(3, orbit.queued)):
        x, y = point(orbit.phase - orbit.extent - 16 - 14 * index, orbit.radius)
        r = 1.3 * scale
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)
    if orbit.queued > 3:
        draw.arc(
            bounds,
            start=orbit.phase - orbit.extent - 60,
            end=orbit.phase - orbit.extent - 56,
            fill=fill,
            width=max(1, round(1.2 * scale)),
        )
    if orbit.ticks:
        for index in range(8):
            # Retain the completion's orientation while the active traveler continues.
            angle = index * 45
            inner = 42 - 4 * orbit.ticks
            draw.line(
                (point(angle, inner), point(angle, inner + 3 * orbit.ticks)),
                fill=fill,
                width=max(1, round(1.2 * scale)),
            )


def render_indicator_image(
    frame: IndicatorFrame,
    color: tuple[int, int, int, int],
    *,
    size: int = INDICATOR_SIZE,
    scale: int = INDICATOR_SUPERSAMPLE_SCALE,
    opacity: float = 1.0,
    label: str = "",
    mode: str = "raw",
    previous_mode: str | None = None,
    mode_mix: float = 1.0,
    activity: str = "recording",
    orbits: tuple[OrbitFrame, ...] = (),
) -> Image.Image:
    if previous_mode is not None and previous_mode != mode and mode_mix < 1.0:
        common = {
            "size": size,
            "scale": scale,
            "opacity": opacity,
            "label": label,
            "activity": activity,
            "orbits": orbits,
        }
        return Image.blend(
            render_indicator_image(frame, color, mode=previous_mode, **common),
            render_indicator_image(frame, color, mode=mode, **common),
            max(0.0, mode_mix),
        )
    render_size = size * scale
    center = render_size / 2
    cx = center + frame.center_dx * scale
    cy = center + frame.center_dy * scale
    radius = frame.radius * scale
    bounds = (
        round(cx - radius),
        round(cy - radius),
        round(cx + radius),
        round(cy + radius),
    )
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for orbit in orbits:
        draw_background_orbit(draw, orbit, center, scale)
    alpha_scale = min(1.0, max(0.0, opacity))
    track_rgb = muted_color(color)[:3]
    draw.ellipse(
        bounds,
        outline=(*track_rgb, round(178 * alpha_scale)),
        width=max(1, round(TRACK_WIDTH * scale)),
    )
    extent = (
        frame.arc_extent
        if mode == "raw" or frame.estimated
        else (42.0 if mode == "tidy" else 66.0) * frame.extent_gain
    )
    end_angle = frame.arc_start + frame.arc_extent
    draw.arc(
        bounds,
        start=end_angle - extent,
        end=end_angle,
        fill=(*color[:3], round(color[3] * alpha_scale)),
        width=max(1, round(frame.arc_width * scale)),
    )
    if mode in ("tidy", "fun"):

        def point(angle, distance):
            radians = math.radians(angle)
            return (cx + math.cos(radians) * distance, cy + math.sin(radians) * distance)

        x, y = point(end_angle, radius)
        marker = min(1.0, frame.radius / 25.0) * frame.marker_scale * scale
        fill = (*color[:3], round(255 * alpha_scale))
        if mode == "tidy":
            r = 3.2 * marker
            draw.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill)
        else:
            r = (4.0 + (frame.arc_width - 2.6) * 1.8) * marker
            points = []
            for index in range(8):
                angle = math.radians(index * 45 - 90 + frame.marker_spin)
                length = r if index % 2 == 0 else r * 0.3
                points.append((x + math.cos(angle) * length, y + math.sin(angle) * length))
            draw.polygon(points, fill=fill)
            for offset, dot in ((-22, 1.5), (-40, 0.9)):
                dx, dy = point(end_angle + offset, radius)
                dr = dot * marker
                draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=fill)
    if label:
        font = indicator_label_font(scale)
        draw.text(
            (center, render_size - 5 * scale),
            label,
            font=font,
            anchor="mb",
            fill=(255, 255, 255, round(255 * alpha_scale)),
            stroke_width=scale,
            stroke_fill=(20, 20, 20, round(230 * alpha_scale)),
        )
    if activity == "rewriting" and radius > 5 * scale:
        draw.arc(
            (
                cx - radius + 4 * scale,
                cy - radius + 4 * scale,
                cx + radius - 4 * scale,
                cy + radius - 4 * scale,
            ),
            start=end_angle + 150,
            end=end_angle + 200,
            fill=(*color[:3], round(150 * alpha_scale)),
            width=scale,
        )
    elif activity == "error":
        # A stationary central warning is distinguishable without relying on color.
        draw.line(
            (center, center - 5 * scale, center, center + scale),
            fill=(*color[:3], round(255 * alpha_scale)),
            width=2 * scale,
        )
        draw.ellipse(
            (center - scale, center + 4 * scale, center + scale, center + 6 * scale),
            fill=(*color[:3], round(255 * alpha_scale)),
        )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def premultiplied_bgra_bytes(image: Image.Image) -> bytes:
    red, green, blue, alpha = image.convert("RGBA").split()
    premultiplied = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(red, alpha),
            ImageChops.multiply(green, alpha),
            ImageChops.multiply(blue, alpha),
            alpha,
        ),
    )
    return premultiplied.tobytes("raw", "BGRA")


class CursorActivityIndicator:
    def __init__(
        self,
        snapshot_provider: Callable[[], CursorIndicatorSnapshot],
        log: Callable[..., None],
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.log = log
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.hwnd = 0

    def start(self) -> bool:
        if platform.system() != "Windows":
            return False
        if self.thread is not None and self.thread.is_alive():
            return True
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="cursor-activity-indicator",
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()
        hwnd = self.hwnd
        if hwnd:
            import ctypes

            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        worker = self.thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        self.thread = None

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._run_windows_message_loop()
            except Exception as exc:  # overlay failures must not interrupt recording
                self.log("[Cursor indicator] Overlay failed:", exc, traceback.format_exc())
            finally:
                self.hwnd = 0
            if self.stop_event.wait(5.0):
                break
            self.log("[Cursor indicator] Recreating overlay after window shutdown.")

    def _run_windows_message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        class WndClass(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class BitmapInfoHeader(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class RgbQuad(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("rgbBlue", wintypes.BYTE),
                ("rgbGreen", wintypes.BYTE),
                ("rgbRed", wintypes.BYTE),
                ("rgbReserved", wintypes.BYTE),
            ]

        class BitmapInfo(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("bmiHeader", BitmapInfoHeader),
                ("bmiColors", RgbQuad * 1),
            ]

        class BlendFunction(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("BlendOp", wintypes.BYTE),
                ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE),
                ("AlphaFormat", wintypes.BYTE),
            ]

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND,
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE),
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            wintypes.COLORREF,
            ctypes.POINTER(BlendFunction),
            wintypes.DWORD,
        ]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BitmapInfo),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL

        def wndproc(hwnd, message, wparam, lparam):
            if message == 0x0010:  # WM_CLOSE
                user32.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._wndproc = wndproc_type(wndproc)
        instance = kernel32.GetModuleHandleW(None)
        class_name = f"PushToTalkCursorIndicator_{id(self)}"
        window_class = WndClass(
            0,
            self._wndproc,
            0,
            0,
            instance,
            None,
            None,
            None,
            None,
            class_name,
        )
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError()

        extended_style = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000 | 0x00000008
        hwnd = user32.CreateWindowExW(
            extended_style,
            class_name,
            "",
            0x80000000,  # WS_POPUP
            0,
            0,
            INDICATOR_SIZE,
            INDICATOR_SIZE,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        self.hwnd = hwnd

        memory_dc = gdi32.CreateCompatibleDC(None)
        if not memory_dc:
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        bitmap_info = BitmapInfo(
            BitmapInfoHeader(
                ctypes.sizeof(BitmapInfoHeader),
                INDICATOR_SIZE,
                -INDICATOR_SIZE,
                1,
                32,
                0,
                INDICATOR_SIZE * INDICATOR_SIZE * 4,
                0,
                0,
                0,
                0,
            ),
            (RgbQuad * 1)(),
        )
        pixel_buffer = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            memory_dc,
            ctypes.byref(bitmap_info),
            0,
            ctypes.byref(pixel_buffer),
            None,
            0,
        )
        if not bitmap or not pixel_buffer.value:
            gdi32.DeleteDC(memory_dc)
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
            raise ctypes.WinError()
        previous_bitmap = gdi32.SelectObject(memory_dc, bitmap)

        animator = IndicatorAnimator()
        shown = False
        source_point = wintypes.POINT(0, 0)
        window_size = wintypes.SIZE(INDICATOR_SIZE, INDICATOR_SIZE)
        blend = BlendFunction(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA

        def update_frame() -> bool:
            nonlocal shown
            snapshot = self.snapshot_provider()
            visual = animator.update(snapshot, time.monotonic())
            if not visual.visible:
                if shown:
                    user32.ShowWindow(hwnd, 0)  # SW_HIDE
                    shown = False
                return False
            image = render_indicator_image(
                visual.frame,
                visual.color,
                opacity=visual.opacity,
                label=visual.label,
                mode=visual.mode,
                previous_mode=visual.previous_mode,
                mode_mix=visual.mode_mix,
                activity=visual.activity,
                orbits=visual.orbits,
            )
            pixels = premultiplied_bgra_bytes(image)
            ctypes.memmove(pixel_buffer, pixels, len(pixels))
            cursor = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            offset = INDICATOR_SIZE // 2
            destination = wintypes.POINT(cursor.x - offset, cursor.y - offset)
            if not user32.UpdateLayeredWindow(
                hwnd,
                None,
                ctypes.byref(destination),
                ctypes.byref(window_size),
                memory_dc,
                ctypes.byref(source_point),
                0,
                ctypes.byref(blend),
                0x00000002,  # ULW_ALPHA
            ):
                raise ctypes.WinError()
            if not shown or not user32.IsWindowVisible(hwnd):
                # Recover when the desktop hides or changes the order of tool windows.
                user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0053)
                shown = True
            return True

        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
        winmm.timeBeginPeriod.restype = wintypes.UINT
        winmm.timeEndPeriod.argtypes = [wintypes.UINT]
        winmm.timeEndPeriod.restype = wintypes.UINT
        high_resolution_timer = False
        self.log("[Cursor indicator] Alpha overlay ready.")
        try:
            message = wintypes.MSG()
            next_frame_at = time.perf_counter()
            running = True
            while running:
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0x0001):  # PM_REMOVE
                    if message.message == 0x0012:  # WM_QUIT
                        running = False
                        break
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
                if not running:
                    break
                if self.stop_event.is_set():
                    user32.DestroyWindow(hwnd)
                    continue
                active = update_frame()
                if active and not high_resolution_timer:
                    high_resolution_timer = winmm.timeBeginPeriod(1) == 0
                elif not active and high_resolution_timer:
                    winmm.timeEndPeriod(1)
                    high_resolution_timer = False
                frame_interval_s = 1.0 / (
                    INDICATOR_TARGET_FPS if active else INDICATOR_IDLE_POLL_FPS
                )
                next_frame_at += frame_interval_s
                sleep_s = next_frame_at - time.perf_counter()
                if sleep_s > 0:
                    time.sleep(sleep_s)
                else:
                    next_frame_at = time.perf_counter()
        finally:
            if high_resolution_timer:
                winmm.timeEndPeriod(1)
            gdi32.SelectObject(memory_dc, previous_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            if user32.IsWindow(hwnd):
                user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
