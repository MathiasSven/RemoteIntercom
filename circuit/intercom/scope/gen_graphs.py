#!/usr/bin/env python3
"""Produce annotated oscilloscope plots for SPLG recordings 1–4, 6, 8 and 9.

Dependencies: numpy, pandas, matplotlib, scipy
Usage: python gen_graphs.py  (run in the directory containing the CSV files)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from scipy.ndimage import uniform_filter1d


@dataclass(frozen=True)
class Recording:
    time: np.ndarray
    voltage: np.ndarray


def load_recording(stem: str) -> Recording:
    """Accept both splg0001.csv and exports such as splg0001(1).csv."""
    matches = sorted(Path.cwd().glob(f"{stem}*.csv"))
    if not matches:
        raise FileNotFoundError(f"No CSV starting with {stem!r} in the current directory")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous {stem}: {', '.join(p.name for p in matches)}")
    data = pd.read_csv(matches[0], skiprows=14, header=None, names=["time_s", "voltage_v"])
    if data.empty or data.isna().any().any():
        raise ValueError(f"Missing or invalid samples in {matches[0]}")
    t = data.time_s.to_numpy(dtype=float)
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"Time must increase in {matches[0]}")
    return Recording(t, data.voltage_v.to_numpy(dtype=float))


def style_axis(ax: plt.Axes, ylabel: str = "Voltage (V)") -> None:
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.20, linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)


def plot_window(ax: plt.Axes, rec: Recording, start: float, stop: float, **kw) -> None:
    mask = (rec.time >= start) & (rec.time <= stop)
    ax.plot(rec.time[mask], rec.voltage[mask], linewidth=0.65, **kw)
    ax.set_xlim(start, stop)


def low_amplitude_intervals(
    rec: Recording,
    *,
    window_s: float = 0.2,
    rms_limit_v: float = 8.0,
    min_duration_s: float = 0.15,
) -> list[tuple[float, float]]:
    """Find sustained low-RMS intervals, without interpreting their physical cause."""
    dt = float(np.median(np.diff(rec.time)))
    window = max(1, int(round(window_s / dt)))
    rms = np.sqrt(np.maximum(0, uniform_filter1d(rec.voltage**2, size=window)))
    mask = rms < rms_limit_v
    boundaries = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts, ends = np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1)
    return [
        (float(rec.time[s]), float(rec.time[e - 1]))
        for s, e in zip(starts, ends)
        if (e - s) * dt >= min_duration_s
    ]


def overview(
    a: Recording,
    b: Recording,
    c: Recording,
    intervals: list[tuple[float, float]],
) -> None:
    # Separate doorbell windows make the unequal durations and scale explicit.
    windows = [(33.0, 35.0), (35.0, 36.0), (36.0, 55.0)]
    fig = plt.figure(figsize=(14, 11.2))
    gs = GridSpec(3, 3, figure=fig, height_ratios=[1, 1.25, 1.2], width_ratios=[2, 5, 5])
    ax_a = fig.add_subplot(gs[0, :])
    ax_c = fig.add_subplot(gs[1, :])
    doorbell_axes = [fig.add_subplot(gs[2, j]) for j in range(3)]

    plot_window(ax_a, a, 17.5, 18.5, color="#2563a6")
    ax_a.set_title("SPLG0001 | Door-release waveform · 1 s detail", loc="left", weight="bold")
    ax_a.set_xlabel("Time (s)")
    style_axis(ax_a)

    ax_c.plot(c.time, c.voltage, lw=0.52, color="#21806a", rasterized=True)
    ax_c.set_xlim(c.time[0], c.time[-1])
    ax_c.set_ylim(-26, 30)
    ax_c.set_title(
        r"SPLG0003 | Door release across 1 $\Omega$ shunt · full recording",
        loc="left",
        weight="bold",
    )
    ax_c.set_xlabel("Time (s)")
    style_axis(ax_c)
    for i, (start, end) in enumerate(intervals, 1):
        ax_c.axvspan(start, end, color="#f2aa4c", alpha=0.4, lw=0)
        ax_c.annotate(
            f"POI {i}\n{start:.2f}–{end:.2f} s",
            xy=((start + end) / 2, 7.0),
            xytext=((start + end) / 2 + (2 if i == 1 else -2), 24),
            ha="center",
            fontsize=9,
            weight="bold",
            color="#744513",
            arrowprops=dict(arrowstyle="->", color="#bd7428", lw=1.2),
        )

    for j, ((start, end), ax) in enumerate(zip(windows, doorbell_axes)):
        plot_window(ax, b, start, end, color="#6e56a6")
        ax.set_ylim(-28, 23)
        ax.set_xlabel("Time (s)")
        ax.grid(alpha=0.2, linewidth=0.7)
        ax.set_facecolor(["#f3f7fd", "#fff6e7", "#f4f0fa"][j])
        ax.set_title(f"{start:g}–{end:g} s  (Δt = {end - start:g} s)", fontsize=10, weight="bold")
        ax.spines[["top", "right"]].set_visible(False)
        if j:
            ax.tick_params(labelleft=False)
            ax.spines["left"].set_visible(False)
        else:
            ax.set_ylabel("Voltage (V)")
    # Reserve space for the page heading and between the three plot sections.
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.075, top=0.885, hspace=0.70, wspace=0.22)
    fig.canvas.draw()
    doorbell_top = max(ax.get_position().y1 for ax in doorbell_axes)
    fig.text(
        0.065,
        doorbell_top + 0.055,
        "SPLG0002 | Doorbell · separate time scales",
        weight="bold",
        fontsize=12,
    )
    fig.suptitle(
        "Oscilloscope recordings | annotated overview", y=0.977, fontsize=17, weight="bold"
    )
    # fig.savefig("splg_overview.png", dpi=190, bbox_inches="tight")
    fig.savefig("splg_overview.pdf", bbox_inches="tight")
    plt.close(fig)


def splg0003_detail(c: Recording, intervals: list[tuple[float, float]]) -> None:
    fig, axes = plt.subplots(len(intervals) + 1, 1, figsize=(13, 3.5 + 2.8 * len(intervals)))
    axes = np.atleast_1d(axes)
    axes[0].plot(c.time, c.voltage, color="#21806a", lw=0.55, rasterized=True)
    axes[0].set_xlim(c.time[0], c.time[-1])
    axes[0].set_title("SPLG0003 | overview and low-amplitude events", loc="left", weight="bold")
    for i, (start, end) in enumerate(intervals, 1):
        axes[0].axvspan(start, end, color="#eab45c", alpha=0.50)
        # Place the label inside the axes, away from the subplot heading.
        axes[0].text(
            (start + end) / 2,
            0.91,
            f"POI {i}",
            transform=axes[0].get_xaxis_transform(),
            ha="center",
            va="top",
            weight="bold",
            fontsize=10,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2),
        )
        ax = axes[i]
        pad = max(0.45, (end - start) * 0.65)
        plot_window(ax, c, max(0, start - pad), min(c.time[-1], end + pad), color="#21806a")
        ax.axvspan(start, end, color="#eab45c", alpha=0.4)
        ax.set_title(
            f"POI {i}: reduced amplitude · {start:.3f}–{end:.3f} s (Δt = {end - start:.3f} s)",
            loc="left",
            fontsize=11,
            weight="bold",
        )
        ax.set_xlabel("Time (s)")
        style_axis(ax)
    axes[0].set_xlabel("Time (s)")
    style_axis(axes[0])
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.085, top=0.875, hspace=0.53)
    fig.suptitle("SPLG0003 | points of interest", y=0.975, fontsize=16, weight="bold")
    # fig.savefig("splg0003_points_of_interest.png", dpi=190, bbox_inches="tight")
    fig.savefig("splg0003_points_of_interest.pdf", bbox_inches="tight")
    plt.close(fig)


def splg0004_plot(rec: Recording) -> None:
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(rec.time, rec.voltage, color="#a34b38", lw=0.55, rasterized=True)
    ax.set_xlim(rec.time[0], rec.time[-1])
    ax.set_title("SPLG0004 | Zener–PC817C node relative to terminal 4", loc="left", weight="bold")
    ax.set_xlabel("Time (s)")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("splg0004.pdf", bbox_inches="tight")
    plt.close(fig)


def splg0006_plot(rec: Recording) -> None:
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(rec.time, rec.voltage, color="#6e56a6", lw=0.55, rasterized=True)
    ax.set_xlim(rec.time[0], rec.time[-1])
    ax.set_title("SPLG0006 | Open 1N4148 output relative to terminal 4", loc="left", weight="bold")
    ax.set_xlabel("Time (s)")
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("splg0006.pdf", bbox_inches="tight")
    plt.close(fig)


def detection_plot(rec: Recording, stem: str, title: str, start: float, stop: float) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 7))
    axes[0].plot(rec.time, rec.voltage, color="#6e56a6", lw=0.55, rasterized=True)
    axes[0].set_xlim(rec.time[0], rec.time[-1])
    axes[0].axvspan(start, stop, color="#f2aa4c", alpha=0.3)
    axes[0].set_title(f"{title} | full recording", loc="left", weight="bold")
    plot_window(axes[1], rec, start, stop, color="#6e56a6")
    axes[1].set_title(f"Detail | {start:g}–{stop:g} s", loc="left", weight="bold")
    for ax in axes:
        ax.set_xlabel("Time (s)")
        style_axis(ax)
    fig.tight_layout()
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    a, b, c, d, e, f, g = (
        load_recording(stem)
        for stem in (
            "splg0001",
            "splg0002",
            "splg0003",
            "splg0004",
            "splg0006",
            "splg0008",
            "splg0009",
        )
    )
    intervals = low_amplitude_intervals(c)
    overview(a, b, c, intervals)
    splg0003_detail(c, intervals)
    splg0004_plot(d)
    splg0006_plot(e)
    detection_plot(f, "splg0008", "SPLG0008 | PC817C anode relative to terminal 4", 26.9, 28.0)
    detection_plot(
        g, "splg0009", "SPLG0009 | Voltage across PC817C collector and emitter", 28.9, 30.1
    )
    for i, (start, end) in enumerate(intervals, 1):
        print(f"SPLG0003 POI {i}: {start:.3f}–{end:.3f} s (Δt = {end - start:.3f} s)")
    # print("Saved PNG and PDF figures to the current directory.")
    print("Saved PDF figures to the current directory.")


if __name__ == "__main__":
    main()
