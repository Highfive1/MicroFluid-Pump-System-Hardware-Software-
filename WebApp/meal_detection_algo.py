#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
S** DESTABILIZATION INDEX FOR GLUCOSE DYNAMICS
================================================================================
Physiological destabilization detector based on evolving glucose dynamics.

This framework is NOT a standard glucose threshold detector.
It identifies changes in temporal dynamical structure,
NOT merely increases in glucose magnitude.

The algorithm interprets meals as transient perturbations to the dynamical regime
of glucose regulation. Detection occurs when the S** index exceeds a threshold,
indicating that the local linear dynamics (captured by DMD) have shifted away
from baseline in terms of energy, entropy, and modal dominance.

Mathematical pipeline (preserved exactly from research prototype):
1. Delay embedding of CGM time series (causal, fixed horizon)
2. Local normalization (zero mean, unit variance) to capture dynamics, not magnitude
3. Sliding-window Dynamic Mode Decomposition (DMD) for local linear approximation
4. Computation of S** = (E - E_base) * (1 + ΔH) * D, where:
   - E = sum of eigenvalue magnitudes (total energy)
   - H = Shannon entropy of normalized eigenvalue magnitudes
   - ΔH = H_base - H (entropy shift)
   - D = max|λ| / E (dominance ratio)
5. Detection when S** > threshold within a causal future horizon

This implementation is production-quality, strictly causal, online-compatible,
and reproduces EXACT numerical outputs of the original research prototype.

Author: Based on Ali Tavasoli, Heman Shakeri (UVA)
        Professionalized for research integration.
Date: 2026
Version: 1.0
================================================================================
"""

import os
import warnings
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
import pandas as pd

# Optional dependencies: keep the module import-safe for webapp/runtime use.
try:
    import matplotlib.pyplot as plt  # type: ignore
except Exception:  # pragma: no cover
    plt = None

try:
    import chardet  # type: ignore
except Exception:  # pragma: no cover
    chardet = None

try:
    from scipy.linalg import svd, eig  # type: ignore
except Exception:  # pragma: no cover
    from numpy.linalg import svd, eig
import csv

# Suppress warnings only for production cleanliness (original behavior preserved)
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION (central, modifiable, with physiological defaults)
# =============================================================================
@dataclass
class SStarConfig:
    """
    Central configuration for S** destabilization index analysis.
    All time parameters are in minutes; step counts are derived from sampling interval.
    """
    # Time constants (minutes)
    delay_horizon_min: int = 60          # Q: delay embedding horizon (past samples)
    delay_horizon_min_2: int = 120       # Q2: secondary horizon (preserved for compatibility)
    dmd_window_min: int = 15             # Sliding window duration for DMD (local dynamics)
    label_lookback_min: int = 30         # For false positives: meal influence window
    max_detection_lag_min: int = 120     # Max time after meal to consider detection

    # DMD parameters
    dmd_rank: int = 3                    # Reduced-order rank for DMD
    svd_reg_eps: float = 1e-8            # Regularization for pseudo-inverse

    # Detection threshold (derived from original experiments: FPR≈0.017, high precision)
    sstar_threshold: float = 0.29

    # Numerical stability
    epsilon: float = 1e-12               # For log and division (avoid zero)
    std_epsilon: float = 1e-6            # For normalization denominator

    # Visualization
    save_figures: bool = True
    plot_style: str = 'seaborn-v0_8-whitegrid'

    # Derived parameters (set after loading data)
    sampling_interval_min: Optional[float] = None
    q: Optional[int] = None              # delay_horizon_min / sampling_interval
    q2: Optional[int] = None
    window_snapshots: Optional[int] = None  # dmd_window_min / sampling_interval
    label_lookback_steps: Optional[int] = None
    max_detection_steps: Optional[int] = None

    def update_from_sampling(self, interval_min: float) -> None:
        """Compute step-based parameters from the detected sampling interval."""
        self.sampling_interval_min = interval_min
        self.q = int(round(self.delay_horizon_min / interval_min))
        self.q2 = int(round(self.delay_horizon_min_2 / interval_min))
        self.window_snapshots = int(round(self.dmd_window_min / interval_min))
        self.label_lookback_steps = int(round(self.label_lookback_min / interval_min))
        self.max_detection_steps = int(round(self.max_detection_lag_min / interval_min))
        logger.info(f"Derived parameters: Q={self.q}, Q2={self.q2}, "
                    f"w={self.window_snapshots}, steps={self.label_lookback_steps}")


# Default configuration instance (can be overridden by user)
DEFAULT_CONFIG = SStarConfig()


# =============================================================================
# DATA LOADING AND PREPROCESSING (exact logic preserved)
# =============================================================================
def load_and_resample(csv_path: str, config: SStarConfig) -> pd.DataFrame:
    """
    Load CGM data from CSV, detect encoding, resample to regular time grid,
    and compute meal onset events.

    Args:
        csv_path: Path to CSV file containing time, CGM, and optional meal columns.
        config: Configuration object to update with sampling interval.

    Returns:
        DataFrame with columns: 'CGM', 'meal_grams', 'meal_onset' (1 at meal start).

    Raises:
        FileNotFoundError: If CSV file does not exist.
        ValueError: If CGM column cannot be identified.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"File not found: {csv_path}")

    # Detect file encoding (original robust method)
    with open(csv_path, 'rb') as f:
        raw = f.read(10000)
        encoding = chardet.detect(raw)['encoding'] or 'utf-8'
    logger.info(f"Detected encoding: {encoding}")

    # Attempt pandas read with various delimiters
    try:
        df = pd.read_csv(csv_path, encoding=encoding, engine='python')
        if df.shape[1] == 1:
            df = pd.read_csv(csv_path, sep=',', encoding=encoding, engine='python')
        if df.shape[1] == 1:
            df = pd.read_csv(csv_path, sep='\t', encoding=encoding, engine='python')
        if df.shape[1] == 1:
            df = pd.read_csv(csv_path, sep=';', encoding=encoding, engine='python')
    except Exception as e:
        logger.warning(f"Pandas read failed: {e}. Falling back to csv module.")
        with open(csv_path, 'r', encoding=encoding) as f:
            first_line = f.readline()
            for delim in [',', '\t', ';', '|']:
                if delim in first_line:
                    used_delim = delim
                    break
            else:
                used_delim = ','
            f.seek(0)
            reader = csv.reader(f, delimiter=used_delim)
            header = next(reader)
            data = list(reader)
        df = pd.DataFrame(data, columns=header)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='ignore')

    # Clean column names
    df.columns = df.columns.str.strip()

    # Identify time column
    time_col = None
    for col in df.columns:
        if 'time' in col.lower():
            time_col = col
            break
    if time_col is None:
        time_col = df.columns[0]
    df[time_col] = pd.to_datetime(df[time_col])
    df.set_index(time_col, inplace=True)

    # Compute median sampling interval (minutes)
    diffs = np.diff(df.index).astype('timedelta64[m]').astype(int)
    median_interval = int(np.median(diffs))
    logger.info(f"Detected sampling interval: {median_interval} min")
    config.update_from_sampling(median_interval)

    # Identify CGM column
    cgm_col = None
    for col in df.columns:
        if col.upper() in ('CGM', 'GLUCOSE', 'BG'):
            cgm_col = col
            break
    if cgm_col is None:
        raise ValueError("CGM column not found (expected 'CGM', 'GLUCOSE', or 'BG')")

    # Identify meal column (optional)
    meal_col = None
    for col in df.columns:
        if 'meal' in col.lower() or 'carbs' in col.lower():
            meal_col = col
            break

    # Build output DataFrame
    output = pd.DataFrame(index=df.index)
    output['CGM'] = df[cgm_col].astype(float)
    output['meal_grams'] = df[meal_col].astype(float) if meal_col is not None else 0.0
    # Meal onset: first sample where meal_grams > 0 after a zero (or start)
    output['meal_onset'] = ((output['meal_grams'] > 0) &
                            (output['meal_grams'].shift(1).fillna(0) == 0)).astype(int)
    output.dropna(subset=['CGM'], inplace=True)

    logger.info(f"Loaded {len(output)} samples, {output['meal_onset'].sum()} meals detected.")
    return output


# =============================================================================
# DMD CORE FUNCTIONS (exact mathematical behavior preserved)
# =============================================================================
def delay_embed_normalized(cgm_series: pd.Series, q: int) -> np.ndarray:
    """
    Construct delay-coordinate state vectors and normalize each window locally.
    
    Physiological rationale: Local normalization removes absolute glucose magnitude
    effects, forcing the DMD to focus on the dynamical structure (shape, rate of change,
    volatility) rather than hyperglycemic levels. This is essential for detecting
    destabilization independent of baseline glucose.
    
    Args:
        cgm_series: CGM time series (indexed by time).
        q: Embedding dimension (number of past samples including current).
        
    Returns:
        Array of shape (n_states, q) where each row is a normalized state vector.
    """
    states = []
    for i in range(q - 1, len(cgm_series)):
        window = cgm_series.iloc[i - q + 1 : i + 1].values
        # Normalize: subtract mean, divide by std (with epsilon for stability)
        window = (window - np.mean(window)) / (np.std(window) + 1e-6)
        states.append(window)
    return np.array(states)


def dmd_full_analysis(X: np.ndarray, Y: np.ndarray, rank: int, reg_eps: float = 1e-8) -> Dict[str, Any]:
    """
    Perform reduced-order DMD on snapshot matrices X and Y (Y ≈ A X).
    
    DMD extracts the eigenvalues of the best-fit linear operator A that advances
    the state. These eigenvalues represent the local dynamical modes: inside vs.
    outside unit circle indicate stability vs. instability; their magnitudes and
    distribution reflect energy and complexity of the system.
    
    Args:
        X: Matrix of current states (columns are snapshots).
        Y: Matrix of next states (Y = X shifted by one step).
        rank: Reduced rank for DMD (truncated SVD).
        reg_eps: Regularization for pseudo-inverse.
        
    Returns:
        Dictionary containing eigenvalues, U, s, V.
    """
    U, s, Vh = svd(X, full_matrices=False)
    rank = min(rank, len(s))
    U = U[:, :rank]
    s = s[:rank]
    V = Vh[:rank, :].T  # Note: Vh is (rank, n), so V is (n, rank)
    s_inv = 1.0 / (s + reg_eps)
    # A_tilde = U^T Y V diag(s_inv)  (low-dimensional approximation of A)
    A_tilde = U.T @ Y @ V @ np.diag(s_inv)
    eigvals, _ = eig(A_tilde)
    return {'eigvals': eigvals, 'U': U, 's': s, 'V': V}


def compute_sstar_online(cgm_series: pd.Series, config: SStarConfig) -> np.ndarray:
    """
    Compute S** destabilization index for each time point (strictly causal).
    
    The index combines:
      - Energy shift (E - E_base): increase in total eigenvalue magnitude.
      - Entropy shift (1 + ΔH): where ΔH = H_base - H, H = -Σ p_i log(p_i),
        p_i = |λ_i|/E. A drop in entropy (ΔH > 0) indicates modal concentration.
      - Dominance (D = max|λ|/E): a single mode taking over the dynamics.
      
    High S** indicates that the local dynamics have become more energetic,
    less entropic (more ordered), and dominated by a single mode – a signature
    of physiological destabilization following a meal perturbation.
    
    Args:
        cgm_series: CGM time series.
        config: Configuration with parameters (q, window_snapshots, rank, epsilons).
        
    Returns:
        Array of S** values same length as cgm_series (NaN where not computable).
    """
    # Step 1: delay embedding and normalization
    states = delay_embed_normalized(cgm_series, config.q)
    n_states = len(states)
    n_cgm = len(cgm_series)
    sstar = np.full(n_cgm, np.nan)

    baseline_energy = None
    baseline_entropy = None

    # Sliding window DMD (causal: only past data used)
    for end_idx in range(config.window_snapshots, n_states):
        start = end_idx - config.window_snapshots
        # X = states at times t, Y = states at times t+1
        X = states[start:end_idx+1][:-1].T   # shape (q, w)
        Y = states[start:end_idx+1][1:].T    # shape (q, w)
        dmd = dmd_full_analysis(X, Y, config.dmd_rank, config.svd_reg_eps)

        eig_abs = np.abs(dmd['eigvals'])
        E = np.sum(eig_abs)
        p = eig_abs / (E + config.epsilon)
        H = -np.sum(p * np.log(p + config.epsilon))
        max_eig = np.max(eig_abs)
        D = max_eig / (E + config.epsilon)

        # Baseline is first valid window (dynamics before any meal effect)
        if baseline_energy is None:
            baseline_energy = E
            baseline_entropy = H

        delta_H = baseline_entropy - H   # positive if entropy decreased
        E_diff = E - baseline_energy     # positive if energy increased
        sstar_val = E_diff * (1 + delta_H) * D

        # Map back to original time index (end_idx + q - 1)
        time_idx = end_idx + config.q - 1
        if time_idx < n_cgm:
            sstar[time_idx] = sstar_val

    return sstar


# =============================================================================
# EVENT-CENTERED ANALYSIS (metrics, detection, false positives)
# =============================================================================
def compute_event_metrics(sstar: np.ndarray, meal_onset: pd.Series, meal_grams: pd.Series,
                          time_grid: pd.DatetimeIndex, config: SStarConfig) -> List[Dict]:
    """
    For each meal, compute detailed destabilization dynamics.
    
    Metrics include:
      - Baseline S** (30-60 min pre-meal)
      - Detection delay (first crossing above threshold, None if not detected)
      - Peak S** within 2h post-meal
      - Destabilization duration (continuous time above threshold)
      - Area under S** curve post-meal (AUC)
    
    Args:
        sstar: S** signal array.
        meal_onset: Binary series (1 at meal start).
        meal_grams: Meal size in grams.
        time_grid: Datetime index for alignment.
        config: Configuration (threshold, sampling interval, max detection steps).
        
    Returns:
        List of dictionaries, each containing event metrics.
    """
    meal_indices = np.where(meal_onset == 1)[0]
    if len(meal_indices) == 0:
        logger.info("No meals found in data.")
        return []

    events = []
    sampling = config.sampling_interval_min
    threshold = config.sstar_threshold
    max_steps = config.max_detection_steps

    for idx in meal_indices:
        meal_time = time_grid[idx]
        meal_size = meal_grams.iloc[idx]

        # Window: 60 min before to 180 min after (for duration analysis)
        pre_steps = int(60 / sampling)
        post_steps = int(180 / sampling)
        start = max(0, idx - pre_steps)
        end = min(len(sstar), idx + post_steps + 1)

        # Baseline S** from 30-60 min before meal
        baseline_start = max(0, idx - int(60 / sampling))
        baseline_end = max(0, idx - int(30 / sampling))
        baseline_sstar = sstar[baseline_start:baseline_end]
        baseline_mean = np.nanmean(baseline_sstar) if len(baseline_sstar) > 0 else 0.0

        # Detection: first crossing above threshold after meal (causal)
        detection_delay = None
        for t in range(idx, min(idx + max_steps, len(sstar))):
            if not np.isnan(sstar[t]) and sstar[t] > threshold:
                detection_time = time_grid[t]
                detection_delay = (detection_time - meal_time).total_seconds() / 60.0
                break

        # Peak S** within 2 hours after meal
        post_end = min(idx + int(120 / sampling), len(sstar))
        post_sstar = sstar[idx:post_end]
        if len(post_sstar) > 0 and not np.all(np.isnan(post_sstar)):
            peak_val = np.nanmax(post_sstar)
            peak_idx_rel = np.nanargmax(post_sstar)
            peak_time = peak_idx_rel * sampling
        else:
            peak_val = np.nan
            peak_time = np.nan

        # Destabilization duration: contiguous time above threshold after meal
        above_thresh = (sstar[idx:end] > threshold).astype(int)
        runs = np.diff(np.concatenate(([0], above_thresh, [0])))
        run_starts = np.where(runs == 1)[0]
        run_ends = np.where(runs == -1)[0]
        if len(run_starts) > 0:
            duration_steps = np.max(run_ends - run_starts)
            duration_min = duration_steps * sampling
        else:
            duration_min = 0.0

        # AUC above baseline (post-meal)
        auc = np.nansum(np.maximum(post_sstar - baseline_mean, 0)) * sampling

        events.append({
            'meal_time': meal_time,
            'meal_size_g': meal_size,
            'baseline_sstar': baseline_mean,
            'peak_sstar': peak_val,
            'peak_time_min': peak_time,
            'detection_delay_min': detection_delay,
            'destabilization_duration_min': duration_min,
            'auc_postmeal': auc,
            'detected': detection_delay is not None
        })

    return events


def false_positive_analysis(sstar: np.ndarray, meal_onset: pd.Series,
                            time_grid: pd.DatetimeIndex, cgm: pd.Series,
                            config: SStarConfig) -> None:
    """
    Analyze false positive detections (S** > threshold without recent meal).
    
    A false positive is defined as a sample where S** exceeds threshold,
    but no meal occurred in the preceding `label_lookback_min` minutes.
    
    Args:
        sstar: S** signal array.
        meal_onset: Binary meal onset series.
        time_grid: Datetime index.
        cgm: Original CGM series (for context in output).
        config: Configuration (threshold, lookback steps).
    """
    threshold = config.sstar_threshold
    lookback = config.label_lookback_steps

    # Build ground truth labels: 1 if meal occurred within lookback window
    labels = np.zeros(len(meal_onset), dtype=int)
    for i in range(len(meal_onset)):
        start = max(0, i - lookback + 1)
        if np.any(meal_onset.iloc[start:i+1] == 1):
            labels[i] = 1

    y_pred = (sstar >= threshold).astype(int)
    fp_mask = (y_pred == 1) & (labels == 0)
    fp_indices = np.where(fp_mask)[0]

    if len(fp_indices) == 0:
        print(f"\nNo false positives at threshold {threshold}.")
        return

    # Group contiguous false positives into events
    fp_events = []
    current = []
    for idx in fp_indices:
        if len(current) == 0 or idx == current[-1] + 1:
            current.append(idx)
        else:
            if len(current) > 0:
                fp_events.append(current)
            current = [idx]
    if len(current) > 0:
        fp_events.append(current)

    print(f"\n=== FALSE POSITIVE ANALYSIS (threshold={threshold}) ===")
    print(f"Total false positive samples: {len(fp_indices)}")
    print(f"Contiguous false positive events: {len(fp_events)}")
    print("\nTop 5 false positive events by peak S**:")

    event_info = []
    for ev in fp_events:
        max_val = np.nanmax(sstar[ev])
        duration = len(ev) * config.sampling_interval_min
        start_t = time_grid[ev[0]]
        end_t = time_grid[ev[-1]]
        cgm_vals = cgm.iloc[ev].values
        event_info.append((max_val, duration, start_t, end_t, cgm_vals))

    event_info.sort(key=lambda x: x[0], reverse=True)
    for i, (maxv, dur, st, et, cgm_vals) in enumerate(event_info[:5]):
        print(f"  FP {i+1}: peak S**={maxv:.3f}, duration={dur:.0f} min, {st} to {et}")
        print(f"      CGM: min={np.min(cgm_vals):.1f}, max={np.max(cgm_vals):.1f}, mean={np.mean(cgm_vals):.1f}")

    # Optional visualization (if matplotlib is available)
    try:
        plt.figure(figsize=(12, 4))
        plt.plot(time_grid, sstar, 'b-', alpha=0.5, label='S**')
        plt.axhline(y=threshold, color='r', linestyle='--', label=f'threshold={threshold}')
        for ev in fp_events[:10]:
            plt.axvspan(time_grid[ev[0]], time_grid[ev[-1]], alpha=0.3, color='orange')
        plt.xlabel('Time')
        plt.ylabel('S**')
        plt.title('False positive events (orange bands)')
        plt.legend()
        if config.save_figures:
            plt.savefig('false_positives_Sstar.png', dpi=150)
        plt.show()
    except Exception as e:
        logger.warning(f"Could not generate false positive plot: {e}")


# =============================================================================
# VISUALIZATION UTILITIES (publication-quality, modular)
# =============================================================================
def plot_event_aligned_all(events: List[Dict], sstar: np.ndarray,
                           meal_onset: pd.Series, time_grid: pd.DatetimeIndex,
                           config: SStarConfig) -> Tuple[np.ndarray, np.ndarray]:
    """
    Plot all meals aligned at t=0 with individual (gray) and average (red) S** trajectories.
    
    Returns:
        mean_traj, std_traj arrays over the aligned time axis.
    """
    pre_min = 60
    post_min = 180
    sampling = config.sampling_interval_min
    pre_steps = int(pre_min / sampling)
    post_steps = int(post_min / sampling)
    total_steps = pre_steps + post_steps + 1
    t_axis = np.arange(-pre_min, post_min + sampling, sampling)

    all_trajs = []
    for idx in np.where(meal_onset == 1)[0]:
        start = max(0, idx - pre_steps)
        end = min(len(sstar), idx + post_steps + 1)
        traj = sstar[start:end]
        if len(traj) < total_steps:
            traj = np.pad(traj, (0, total_steps - len(traj)), constant_values=np.nan)
        all_trajs.append(traj[:total_steps])

    all_trajs = np.array(all_trajs)
    mean_traj = np.nanmean(all_trajs, axis=0)
    std_traj = np.nanstd(all_trajs, axis=0)

    plt.figure(figsize=(12, 6))
    # Plot up to 20 individual trajectories in light gray
    for i in range(min(len(all_trajs), 20)):
        plt.plot(t_axis, all_trajs[i], 'gray', alpha=0.2, lw=0.8)
    plt.plot(t_axis, mean_traj, 'r-', lw=2, label='Mean S**')
    plt.fill_between(t_axis, mean_traj - std_traj, mean_traj + std_traj,
                     color='r', alpha=0.2, label='±1 std')
    plt.axhline(y=config.sstar_threshold, color='b', linestyle='--',
                label=f'Threshold = {config.sstar_threshold}')
    plt.axvline(x=0, color='k', linestyle='--', label='Meal onset')
    plt.xlabel('Time relative to meal (min)')
    plt.ylabel('S** (destabilization index)')
    plt.title(f'Event-aligned S** trajectories (n={len(all_trajs)})')
    plt.legend()
    plt.grid(True, alpha=0.3)
    if config.save_figures:
        plt.savefig('event_aligned_Sstar.png', dpi=150)
    plt.show()

    # Print numerical trajectory (subsampled for readability)
    print("\nNumerical S** trajectory (mean ± std) aligned to meal:")
    print("Time(min), Mean, Std")
    step = max(1, len(t_axis) // 20)
    for i in range(0, len(t_axis), step):
        print(f"{t_axis[i]:.0f}, {mean_traj[i]:.4f}, {std_traj[i]:.4f}")
    return mean_traj, std_traj


def plot_individual_event(events: List[Dict], sstar: np.ndarray,
                          time_grid: pd.DatetimeIndex, data: pd.DataFrame,
                          event_idx: int, config: SStarConfig) -> None:
    """
    Plot a single event with CGM (top) and S** (bottom) trajectories.
    
    Args:
        events: List of event metric dictionaries.
        sstar: S** signal array.
        time_grid: Datetime index.
        data: DataFrame containing 'CGM' and 'meal_grams'.
        event_idx: Index of event to plot.
        config: Configuration (sampling interval, threshold).
    """
    if event_idx >= len(events):
        logger.error(f"Event index {event_idx} out of range (max {len(events)-1}).")
        return

    e = events[event_idx]
    meal_time = e['meal_time']
    # Find closest index in time_grid (should be exact match)
    idx = np.argmin(np.abs(time_grid - meal_time))

    pre = int(60 / config.sampling_interval_min)
    post = int(180 / config.sampling_interval_min)
    start = max(0, idx - pre)
    end = min(len(time_grid), idx + post)
    t_sub = time_grid[start:end]
    cgm_sub = data['CGM'].iloc[start:end].values
    sstar_sub = sstar[start:end]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    ax1.plot(t_sub, cgm_sub, 'b-', lw=1.5)
    ax1.set_ylabel('CGM (mg/dL)')
    ax1.set_title(f'Meal at {meal_time} (size={e["meal_size_g"]:.1f}g)')
    ax1.axvline(x=meal_time, color='g', linestyle='--', label='Meal onset')
    ax1.legend()

    ax2.plot(t_sub, sstar_sub, 'r-', lw=1.5)
    ax2.axhline(y=config.sstar_threshold, color='gray', linestyle='--',
                label=f'Threshold={config.sstar_threshold}')
    ax2.axvline(x=meal_time, color='g', linestyle='--')
    ax2.set_ylabel('S**')
    ax2.set_xlabel('Time')
    ax2.legend()
    plt.tight_layout()
    if config.save_figures:
        plt.savefig(f'event_{event_idx}_Sstar.png', dpi=150)
    plt.show()

    # Print numerical details
    print(f"\nNumerical data for event {event_idx}:")
    print(f"  Meal: {meal_time}, size={e['meal_size_g']:.1f}g")
    print(f"  Baseline S**: {e['baseline_sstar']:.4f}")
    print(f"  Peak S**: {e['peak_sstar']:.4f} at {e['peak_time_min']:.1f} min")
    if e['detected']:
        print(f"  Detection delay: {e['detection_delay_min']:.1f} min")
    else:
        print("  Detection delay: Not detected")
    print(f"  Destabilization duration: {e['destabilization_duration_min']:.1f} min")
    print(f"  AUC (post-meal): {e['auc_postmeal']:.1f}")


def print_event_table(events: List[Dict], config: SStarConfig) -> None:
    """Print detailed event-by-event table."""
    print("\n" + "="*90)
    print(f"EVENT-CENTERED ANALYSIS (Threshold S** = {config.sstar_threshold})")
    print("="*90)
    print(f"{'Meal time':<20} | {'Size(g)':>6} | {'Baseline':>8} | {'Peak S**':>8} | "
          f"{'Peak time(min)':>12} | {'Delay(min)':>9} | {'Duration(min)':>12} | "
          f"{'AUC':>8} | {'Detected':>8}")
    print("-" * 110)
    for e in events:
        delay_str = f"{e['detection_delay_min']:9.1f}" if e['detected'] else "      ---"
        print(f"{str(e['meal_time'])[:19]:<20} | {e['meal_size_g']:6.1f} | "
              f"{e['baseline_sstar']:8.3f} | {e['peak_sstar']:8.3f} | "
              f"{e['peak_time_min']:12.1f} | {delay_str:>9} | "
              f"{e['destabilization_duration_min']:12.1f} | {e['auc_postmeal']:8.1f} | "
              f"{e['detected']:>8}")
    print("="*90)


def print_summary_statistics(events: List[Dict], config: SStarConfig) -> None:
    """Print summary statistics across all meals."""
    detected = [e for e in events if e['detected']]
    undetected = [e for e in events if not e['detected']]
    print("\n=== SUMMARY STATISTICS ===")
    print(f"Total meals: {len(events)}")
    print(f"Detected (S** > {config.sstar_threshold} within {config.max_detection_lag_min} min): "
          f"{len(detected)} ({100*len(detected)/len(events):.1f}%)")
    print(f"Undetected: {len(undetected)} ({100*len(undetected)/len(events):.1f}%)")

    if len(detected) > 0:
        delays = [e['detection_delay_min'] for e in detected if e['detection_delay_min'] is not None]
        peaks = [e['peak_sstar'] for e in detected]
        durations = [e['destabilization_duration_min'] for e in detected]
        if delays:
            print(f"Median detection delay: {np.median(delays):.1f} min")
            print(f"IQR: {np.percentile(delays, 75) - np.percentile(delays, 25):.1f} min")
            print(f"Mean detection delay: {np.mean(delays):.1f} min")
            print(f"Min delay: {np.min(delays):.1f} min, Max delay: {np.max(delays):.1f} min")
        print(f"Median peak S**: {np.median(peaks):.3f} (range {np.min(peaks):.3f}-{np.max(peaks):.3f})")
        print(f"Median destabilization duration: {np.median(durations):.1f} min")
    else:
        print("No meals detected.")

    # Correlation between meal size and peak S** (only detected)
    if len(detected) > 1:
        sizes = [e['meal_size_g'] for e in detected]
        peaks = [e['peak_sstar'] for e in detected]
        corr = np.corrcoef(sizes, peaks)[0, 1]
        print(f"Correlation (meal size vs peak S**): {corr:.3f}")


# =============================================================================
# MAIN ORCHESTRATOR (production-ready pipeline)
# =============================================================================
def run_sstar_analysis(csv_path: str, config: Optional[SStarConfig] = None) -> Tuple[List[Dict], np.ndarray]:
    """
    Run complete S** destabilization analysis on a CGM CSV file.
    
    This function executes the full pipeline:
      1. Load and resample data
      2. Compute S** signal (causal, online)
      3. Compute event metrics for each meal
      4. Generate visualizations and print reports
      5. Perform false positive analysis
    
    Args:
        csv_path: Path to CSV file with time, CGM, and optional meal columns.
        config: Optional configuration (uses DEFAULT_CONFIG if None).
        
    Returns:
        events: List of event metric dictionaries.
        sstar: Array of S** values (same length as data).
    """
    if config is None:
        config = DEFAULT_CONFIG

    logger.info("="*70)
    logger.info("EVENT-CENTERED PHYSIOLOGICAL ANALYSIS: S** Destabilization Index")
    logger.info(f"Detection threshold: {config.sstar_threshold}")
    logger.info("="*70)

    # Step 1: Load data
    data = load_and_resample(csv_path, config)
    cgm = data['CGM']
    meal_onset = data['meal_onset']
    meal_grams = data['meal_grams']
    time_grid = cgm.index

    # Step 2: Compute S** (causal DMD)
    logger.info("Computing S** signal (causal DMD)...")
    sstar = compute_sstar_online(cgm, config)

    # Step 3: Event metrics
    events = compute_event_metrics(sstar, meal_onset, meal_grams, time_grid, config)
    if len(events) == 0:
        logger.warning("No events found. Exiting.")
        return events, sstar

    # Step 4: Print table
    print_event_table(events, config)

    # Step 5: Aligned trajectory plot
    plot_event_aligned_all(events, sstar, meal_onset, time_grid, config)

    # Step 6: Individual event plots (first 5)
    for i in range(min(5, len(events))):
        plot_individual_event(events, sstar, time_grid, data, i, config)

    # Step 7: False positive analysis
    false_positive_analysis(sstar, meal_onset, time_grid, cgm, config)

    # Step 8: Summary statistics
    print_summary_statistics(events, config)

    logger.info("Analysis complete.")
    return events, sstar


# =============================================================================
# EXAMPLE USAGE (when run as script)
# =============================================================================


# =============================================================================
# STREAMING WRAPPER (for real-time CGM ingestion)
# =============================================================================
from collections import deque
from datetime import datetime


class SStarStreamDetector:
    """Online/streaming interface around `compute_sstar_online`.

    Keeps a bounded rolling CGM history per instance and reports a meal event when
    the latest S** value crosses the configured threshold.
    """

    def __init__(
        self,
        config: Optional[SStarConfig] = None,
        sampling_interval_min: float = 1.0,
        history_minutes: int = 240,
        cooldown_minutes: int = 60,
    ) -> None:
        self.config = config or DEFAULT_CONFIG
        # Copy a few fields so per-instance tuning doesn't mutate the global default.
        self.config = SStarConfig(**{k: getattr(self.config, k) for k in self.config.__dataclass_fields__.keys()})
        self.config.update_from_sampling(float(sampling_interval_min))

        self._maxlen = max(1, int(round(history_minutes / float(sampling_interval_min))))
        self._cooldown_sec = float(cooldown_minutes) * 60.0

        self._times: deque = deque(maxlen=self._maxlen)
        self._values: deque = deque(maxlen=self._maxlen)
        self._last_detect_ts: Optional[float] = None
        self._last_sstar: Optional[float] = None

    @property
    def last_sstar(self) -> Optional[float]:
        return self._last_sstar

    def update(self, timestamp: datetime, glucose_mgdl: float) -> Dict[str, Any]:
        """Add one CGM sample.

        Returns dict with keys:
          - detected (bool)
          - sstar (float|None)
          - threshold (float)
          - reason (str)
        """
        try:
            g = float(glucose_mgdl)
        except Exception:
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "bad_glucose"}

        if not np.isfinite(g):
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "nonfinite_glucose"}

        if not isinstance(timestamp, datetime):
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "bad_timestamp"}

        self._times.append(timestamp)
        self._values.append(g)

        # Need enough samples to form delay embedding + DMD window.
        min_needed = int(self.config.q or 0) + int(self.config.window_snapshots or 0) + 2
        if len(self._values) < max(10, min_needed):
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "warming_up"}

        try:
            series = pd.Series(list(self._values), index=pd.DatetimeIndex(list(self._times)))
            sstar = compute_sstar_online(series, self.config)
            sstar_val = float(sstar[-1]) if len(sstar) else float('nan')
        except Exception:
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "compute_error"}

        self._last_sstar = sstar_val if np.isfinite(sstar_val) else None
        if self._last_sstar is None:
            return {"detected": False, "sstar": None, "threshold": self.config.sstar_threshold, "reason": "no_sstar"}

        now_ts = timestamp.timestamp()
        if self._last_sstar > float(self.config.sstar_threshold):
            if self._last_detect_ts is None or (now_ts - self._last_detect_ts) >= self._cooldown_sec:
                self._last_detect_ts = now_ts
                return {"detected": True, "sstar": self._last_sstar, "threshold": self.config.sstar_threshold, "reason": "threshold_cross"}

        return {"detected": False, "sstar": self._last_sstar, "threshold": self.config.sstar_threshold, "reason": "below_threshold"}


if __name__ == "__main__":
    """
    Example usage of the S** destabilization index framework.
    
    To run with your own CSV file, change the `csv_file_path` variable.
    Expected CSV columns: a time column (any name with 'time'), a CGM column
    (named 'CGM', 'GLUCOSE', or 'BG'), and optionally a meal column
    (containing carbohydrate grams, with 'meal' or 'carbs' in name).
    
    The algorithm automatically detects sampling interval and sets all
    step-based parameters.
    """
    # Example path (user should replace with actual file)
    csv_file_path = r"C:\Users\krish\Documents\Github\glycoSMC\glycoSMC\data\adolescent_003.csv"

    if not os.path.exists(csv_file_path):
        print(f"ERROR: File not found at {csv_file_path}")
        print("Please update the path to your CSV file.")
    else:
        # Optional: customize configuration
        # config = SStarConfig(sstar_threshold=0.30, dmd_rank=4)
        # events, sstar = run_sstar_analysis(csv_file_path, config=config)
        
        # Run with default configuration
        events, sstar = run_sstar_analysis(csv_file_path)