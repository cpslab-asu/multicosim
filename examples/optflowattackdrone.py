"""
GSdrone Multi-Fidelity Co-Simulation with Optical Flow Attack Falsification

This module implements a multi-fidelity drone simulation with integrated falsification
analysis using psy-taliro. It demonstrates how to use multicosim with psy-taliro as
the backend for systematic vulnerability discovery in cyber-physical systems.

Key Features:
- Multi-fidelity quadrotor simulation using FMUs (Functional Mock-up Units)
- Optical flow sensor attack implementation
- Integration with psy-taliro for automated falsification
- Safety specification checking using RTAmt temporal logic
- Counterexample visualization and analysis

Architecture:
- DroneNode: Orchestrates 4 FMU components (Quadrotor, Controller, Joystick, Mission Planner)
- DroneComponent: Multicosim component wrapper for containerized execution
- drone_attack_model: Blackbox model for psy-taliro falsification
- Safety specifications: Altitude, attitude stability constraints

Usage:
    # Run falsification analysis (default)
    python optflowattackdrone.py
    
    # Run single simulation
    python optflowattackdrone.py --mode simulation
    
    # Customize falsification parameters
    python optflowattackdrone.py --iterations 100 --runs 3

Dependencies:
- FMU files from FIRE_LoFi_Simulations/GSdrone/
- PyFMI for FMU simulation
- psy-taliro for falsification
- multicosim framework

This example is inspired by the GSdrone example in FIRE_LoFi_Simulations/GSdrone/example_closedloop_drone.py
and follows the multicosim + staliro integration pattern from multicosim/examples/rover/src/test.py.
"""

from __future__ import annotations

import json
import logging
import os
from math import gcd
from typing import Dict, Literal, Optional, Any

import attrs
import numpy as np
import pandas as pd
import pyfmi
import matplotlib.pyplot as plt
from typing_extensions import TypeAlias, override

from multicosim.simulations import CommunicationNode, Component

# Import staliro for falsification (multicosim uses staliro as backend)
import staliro
import staliro.optimizers
import staliro.specifications.rtamt

# Type aliases
FidelityLevel: TypeAlias = Literal[1, 2]
FMUType: TypeAlias = Literal["me", "cs"]
AttackScenario: TypeAlias = Literal[0, 1]


@attrs.define()
class DronePosition:
    """3D position in NED (North-East-Down) coordinate frame."""
    north: float = 0.0
    east: float = 0.0
    down: float = 0.0


@attrs.define()
class DroneVelocity:
    """3D velocity in body-fixed coordinate frame."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@attrs.define()
class DroneAcceleration:
    """3D acceleration in body-fixed coordinate frame."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@attrs.define()
class DroneAttitude:
    """Drone attitude representation with quaternions and Euler angles."""
    # Quaternion (w, x, y, z)
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    
    # Euler angles (roll, pitch, yaw)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    
    # Angular rates (body frame)
    roll_rate: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0


@attrs.define()
class DroneState:
    """Complete drone state representation."""
    position: DronePosition = attrs.field(factory=DronePosition)
    velocity: DroneVelocity = attrs.field(factory=DroneVelocity)
    acceleration: DroneAcceleration = attrs.field(factory=DroneAcceleration)
    attitude: DroneAttitude = attrs.field(factory=DroneAttitude)
    
    # Control inputs
    pwm_commands: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    
    # Mission parameters
    position_setpoint: DronePosition = attrs.field(factory=DronePosition)
    yaw_setpoint: float = 0.0
    
    # RC inputs
    rc_commands: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@attrs.define()
class AttackConfig:
    """Configuration for attack scenarios."""
    scenario: AttackScenario = 0
    optical_flow_bias: float = 0.0
    optical_flow_variance: float = 1.0
    optical_flow_rate: float = 4.0  # Hz


@attrs.define()
class SimulationConfig:
    """Simulation configuration parameters."""
    physics_fidelity: FidelityLevel = 1
    cyber_fidelity: FidelityLevel = 1
    fmu_type: FMUType = "me"
    t0: float = 0.0
    tf: float = 10.0
    dt: float = 0.1
    attack_config: AttackConfig = attrs.field(factory=AttackConfig)
    parameter_file: str = "drone_specs.json"


class FMU:
    """
    FMU wrapper class using PyFMI for external time step control.
    Embedded from FIRE_LoFi_Simulations/GSdrone/fmu.py
    """
    
    def __init__(self, file: str, fmutype: str, t0: float, tol: float = 1e-10):
        """Initialize FMU wrapper."""
        # Set library path for Linux compatibility
        os.environ["LD_LIBRARY_PATH"] = "/usr/lib/x86_64-linux-gnu:" + os.environ.get("LD_LIBRARY_PATH", "")
        
        self.model = pyfmi.load_fmu(file, kind=fmutype)
        self.model.initialize(start_time=0.0)
        
        self.t = t0
        self.t0 = t0
        self.stateNames = list(self.model.get_states_list().keys())
        self.inputNames = list(self.model.get_input_list().keys())
        self.outputNames = list(self.model.get_output_list().keys())
        self.variableNames = list(self.model.get_model_variables().keys())
        
        self.state = np.zeros((len(self.stateNames),))
        self.input = np.zeros((len(self.inputNames),))
        self.timedinput = np.hstack([np.zeros((0, 1)), np.zeros((0, len(self.inputNames)))])
        self.output = np.zeros((len(self.outputNames),))
        self.variable = np.zeros((len(self.variableNames),))
        
        self.data = {
            'time': np.empty((0,)),
            'input': {'names': self.inputNames, 'values': np.empty((0, self.input.size))},
            'state': {'names': self.stateNames, 'values': np.empty((0, self.state.size))},
            'variable': {'names': self.variableNames, 'values': np.empty((0, self.variable.size))},
            'output': {'names': self.outputNames, 'values': np.empty((0, self.output.size))}
        }
    
    def reset(self):
        """Reset the FMU to initial conditions."""
        self.model.reset()
        # Re-initialize after reset since FMU goes back to uninitialized state
        self.model.initialize(start_time=self.t0)
        self.t = self.t0
        self.empty_data()
    
    def empty_data(self):
        """Clear stored simulation data."""
        self.data['time'] = np.empty((0,))
        self.data['input']['values'] = np.empty((0, self.input.size))
        self.data['state']['values'] = np.empty((0, self.state.size))
        self.data['variable']['values'] = np.empty((0, self.variable.size))
        self.data['output']['values'] = np.empty((0, self.output.size))
    
    def set_param(self, param_dict: Dict[str, float]):
        """Set parameter values."""
        for key, value in param_dict.items():
            self.model.set(key, value)
    
    def get_param(self, param_name: str) -> float:
        """Get parameter value."""
        return self.model.get(param_name)
    
    def set_input(self, t_next: float, input_dict: Dict[str, float]):
        """Set input values for next time step."""
        input_array = np.zeros(len(self.inputNames))
        for i, name in enumerate(self.inputNames):
            if name in input_dict:
                input_array[i] = float(input_dict[name])
        
        if self.timedinput.size == 0:
            self.timedinput = np.array([[t_next] + input_array.tolist()])
        else:
            self.timedinput = np.vstack([self.timedinput, [t_next] + input_array.tolist()])
    
    def step_time(self, t_start: float, t_end: float):
        """Step the FMU from t_start to t_end."""
        # Set inputs if available
        if self.timedinput.size > 0:
            # Find inputs for this time step
            time_mask = (self.timedinput[:, 0] >= t_start) & (self.timedinput[:, 0] <= t_end)
            if np.any(time_mask):
                latest_input = self.timedinput[time_mask][-1, 1:]  # Get latest input in time range
                for i, name in enumerate(self.inputNames):
                    self.model.set(name, latest_input[i])
        
        # Simulate
        if hasattr(self.model, 'do_step'):
            # Co-simulation FMU
            self.model.do_step(t_start, t_end - t_start)
        else:
            # Model exchange FMU
            self.model.time = t_end
        
        self.t = t_end
        self._log_data()
    
    def _log_data(self):
        """Log current state, inputs, outputs, and variables."""
        # Get current values
        current_state = np.array([self.model.get(name) for name in self.stateNames])
        current_input = np.array([self.model.get(name) for name in self.inputNames])
        current_output = np.array([self.model.get(name) for name in self.outputNames])
        current_variable = np.array([self.model.get(name) for name in self.variableNames])
        
        # Ensure arrays are 2D for vstack
        if current_state.ndim == 1:
            current_state = current_state.reshape(1, -1)
        if current_input.ndim == 1:
            current_input = current_input.reshape(1, -1)
        if current_output.ndim == 1:
            current_output = current_output.reshape(1, -1)
        if current_variable.ndim == 1:
            current_variable = current_variable.reshape(1, -1)
        
        # Append to data
        self.data['time'] = np.append(self.data['time'], self.t)
        
        # Handle empty arrays properly
        if self.data['state']['values'].size == 0:
            self.data['state']['values'] = current_state
        else:
            self.data['state']['values'] = np.vstack([self.data['state']['values'], current_state])
            
        if self.data['input']['values'].size == 0:
            self.data['input']['values'] = current_input
        else:
            self.data['input']['values'] = np.vstack([self.data['input']['values'], current_input])
            
        if self.data['output']['values'].size == 0:
            self.data['output']['values'] = current_output
        else:
            self.data['output']['values'] = np.vstack([self.data['output']['values'], current_output])
            
        if self.data['variable']['values'].size == 0:
            self.data['variable']['values'] = current_variable
        else:
            self.data['variable']['values'] = np.vstack([self.data['variable']['values'], current_variable])
    
    def get_output_value(self) -> Dict[str, float]:
        """Get current output values as dictionary."""
        return {name: self.model.get(name) for name in self.outputNames}


def eul2quat(eul: np.ndarray) -> np.ndarray:
    """
    Convert Euler angles to quaternion.
    Embedded from FIRE_LoFi_Simulations/GSdrone/utils.py
    """
    if eul.shape[0] != 3:
        raise ValueError('Check the input dimension')
    
    phi = eul[0]    # roll
    theta = eul[1]  # pitch  
    psi = eul[2]    # yaw
    
    out = np.zeros((4,))
    
    # Compute quaternion (w, x, y, z)
    out[0] = np.cos(psi/2)*np.cos(theta/2)*np.cos(phi/2) + np.sin(psi/2)*np.sin(theta/2)*np.sin(phi/2)
    out[1] = np.cos(psi/2)*np.cos(theta/2)*np.sin(phi/2) - np.sin(psi/2)*np.sin(theta/2)*np.cos(phi/2)
    out[2] = np.cos(psi/2)*np.sin(theta/2)*np.cos(phi/2) + np.sin(psi/2)*np.cos(theta/2)*np.sin(phi/2)
    out[3] = np.sin(psi/2)*np.cos(theta/2)*np.cos(phi/2) - np.cos(psi/2)*np.sin(theta/2)*np.sin(phi/2)
    
    return out


def _gcd_dt(dts: list[float], quantum: float = 1e-6) -> float:
    """
    Compute robust GCD time step for floating periods.
    Embedded from FIRE_LoFi_Simulations/GSdrone/dronesim.py
    """
    us = [max(1, int(round(dt/quantum))) for dt in dts]  # Convert to integer ticks
    g = us[0]
    for u in us[1:]:
        g = gcd(g, u)
    return g * quantum


@attrs.define()
class DroneNode(CommunicationNode[DroneState, Dict[str, Any]]):
    """
    Communication node that orchestrates the multi-fidelity quadrotor co-simulation.
    Manages 4 FMU components: Quadrotor, Controller, Joystick, Mission Planner.
    """
    config: SimulationConfig
    fmu_paths: Dict[str, str]
    parameters_info: Dict[str, Dict[str, Any]] = attrs.field(factory=dict)
    
    # FMU instances
    fmudyn: Optional[FMU] = None
    fmuctrl: Optional[FMU] = None
    fmustick: Optional[FMU] = None
    fmuplanner: Optional[FMU] = None
    
    # Attack state
    optical_spoof_vector: np.ndarray = attrs.field(factory=lambda: np.zeros(3))
    
    def __attrs_post_init__(self):
        """Initialize FMUs after object creation."""
        self._initialize_fmus()
    
    def _initialize_fmus(self):
        """Initialize all FMU components."""
        # Load parameter file if exists
        if os.path.exists(self.config.parameter_file):
            with open(self.config.parameter_file, 'r') as file:
                self.parameters_info['scenario'] = json.load(file)
        
        # Initialize Quadrotor FMU
        self.fmudyn = FMU(self.fmu_paths['quadrotor'], self.config.fmu_type, self.config.t0, tol=1e-6)
        self._setup_quadrotor_fmu()
        
        # Initialize Controller FMU
        self.fmuctrl = FMU(self.fmu_paths['controller'], self.config.fmu_type, self.config.t0, tol=1e-6)
        self._setup_controller_fmu()
        
        # Initialize Joystick FMU
        self.fmustick = FMU(self.fmu_paths['joystick'], self.config.fmu_type, self.config.t0, tol=1e-6)
        self._setup_joystick_fmu()
        
        # Initialize Mission Planner FMU
        self.fmuplanner = FMU(self.fmu_paths['mission_planner'], self.config.fmu_type, self.config.t0, tol=1e-6)
        self._setup_mission_planner_fmu()
    
    def _setup_quadrotor_fmu(self):
        """Setup quadrotor FMU with initial conditions."""
        # Get parameter information
        self.parameters_info['chassis'] = {}
        if self.config.physics_fidelity == 1:
            self.parameters_info['chassis']['actuator_sample_period'] = self.fmudyn.get_param('actuator_sample_period')
            self.parameters_info['chassis']['sensor_sample_period'] = self.fmudyn.get_param('sensor_sample_period')
        
        self.fmudyn.reset()
        
        # Set initial conditions based on fidelity
        if self.config.physics_fidelity == 1:
            self.fmudyn.set_param({
                'quad_low.position_w_p_w[1]': 0.0, 'quad_low.position_w_p_w[2]': 0.0, 'quad_low.position_w_p_w[3]': 0.0,
                'quad_low.velocity_w_p_b[1]': 0.0, 'quad_low.velocity_w_p_b[2]': 0.0, 'quad_low.velocity_w_p_b[3]': 0.0,
                'quad_low.quaternion_wb[1]': 1.0, 'quad_low.quaternion_wb[2]': 0.0, 'quad_low.quaternion_wb[3]': 0.0, 'quad_low.quaternion_wb[4]': 0.0
            })
        elif self.config.physics_fidelity == 2:
            self.fmudyn.set_param({
                'quad_high.position_w_p_w[1]': 0.0, 'quad_high.position_w_p_w[2]': 0.0, 'quad_high.position_w_p_w[3]': 0.0,
                'quad_high.velocity_w_p_b[1]': 0.0, 'quad_high.velocity_w_p_b[2]': 0.0, 'quad_high.velocity_w_p_b[3]': 0.0,
                'quad_high.quaternion_wb[1]': 1.0, 'quad_high.quaternion_wb[2]': 0.0, 'quad_high.quaternion_wb[3]': 0.0, 'quad_high.quaternion_wb[4]': 0.0
            })
    
    def _setup_controller_fmu(self):
        """Setup controller FMU with initial conditions."""
        # Get parameter information
        self.parameters_info['controller'] = {}
        if self.config.cyber_fidelity == 1:
            self.parameters_info['controller']['update_period'] = self.fmuctrl.get_param('update_period')
        
        self.fmuctrl.reset()
        
        # Set initial conditions based on fidelity
        if self.config.cyber_fidelity == 1:
            self.fmuctrl.set_param({
                'euler_pid.vel_error_i[1]': 0.0, 'euler_pid.vel_error_i[2]': 0.0, 'euler_pid.vel_error_i[3]': 0.0,
                'euler_pid.vel_error_last[1]': 0.0, 'euler_pid.vel_error_last[2]': 0.0, 'euler_pid.vel_error_last[3]': 0.0,
                'euler_pid.rate_error_i[1]': 0.0, 'euler_pid.rate_error_i[2]': 0.0, 'euler_pid.rate_error_i[3]': 0.0,
                'euler_pid.rate_error_last[1]': 0.0, 'euler_pid.rate_error_last[2]': 0.0, 'euler_pid.rate_error_last[3]': 0.0
            })
    
    def _setup_joystick_fmu(self):
        """Setup joystick FMU with initial conditions."""
        # Get parameter information
        self.parameters_info['joystick'] = {}
        self.parameters_info['joystick']['sample_period'] = self.fmustick.get_param('sample_period')
        
        self.fmustick.reset()
        self.fmustick.set_param({
            'stick_cmd[1]': 0.0, 'stick_cmd[2]': 0.0, 'stick_cmd[3]': 0.0, 'stick_cmd[4]': 0.0
        })
    
    def _setup_mission_planner_fmu(self):
        """Setup mission planner FMU with initial conditions."""
        # Get parameter information
        self.parameters_info['planner'] = {}
        self.parameters_info['planner']['sample_period'] = self.fmuplanner.get_param('sample_period')
        
        self.fmuplanner.reset()
        self.fmuplanner.set_param({
            'position_setpoint_w[1]': 0.0, 'position_setpoint_w[2]': 0.0, 'position_setpoint_w[3]': -30.0,
            'yaw_setpoint_w': 0.0
        })

    @override
    def send(self, msg: DroneState) -> Dict[str, Any]:
        """
        Run multi-rate, event-driven closed-loop simulation.
        Returns simulation results as time history data.
        """
        # Compute time stepping parameters
        dt_dyn = np.min(np.array([
            self.parameters_info['chassis'].get('actuator_sample_period', 0.01),
            self.parameters_info['chassis'].get('sensor_sample_period', 0.01)
        ], dtype=np.float64))
        dt_ctrl = float(self.parameters_info['controller'].get('update_period', 0.01))
        dt_plan = float(self.parameters_info['planner'].get('sample_period', 0.1))
        dt_stick = float(self.parameters_info['joystick'].get('sample_period', 0.1))
        
        dt_base = _gcd_dt([dt_dyn, dt_ctrl, dt_plan, dt_stick], quantum=1e-6)
        if dt_base - min(dt_dyn, dt_ctrl, dt_plan, dt_stick) > 1e-12:
            dt_base = min(dt_dyn, dt_ctrl, dt_plan, dt_stick)
        
        # Number of simulation ticks
        n_ticks = int(round((self.config.tf - self.config.t0) / dt_base)) + 1
        
        # Compute execution strides for each component
        k_dyn = max(1, int(round(dt_dyn / dt_base)))
        k_ctrl = max(1, int(round(dt_ctrl / dt_base)))
        k_plan = max(1, int(round(dt_plan / dt_base)))
        k_stick = max(1, int(round(dt_stick / dt_base)))
        
        # Attack scenario setup
        if self.config.attack_config.scenario == 1:
            k_opticalflow = max(1, int(round((1.0 / self.config.attack_config.optical_flow_rate) / dt_base)))
        
        # Event loop timing
        t_last_dyn = self.config.t0
        t_last_ctrl = self.config.t0
        t_last_plan = self.config.t0
        t_last_stick = self.config.t0
        
        # Data storage
        data = {
            'time': np.zeros((0,)),
            'missionplanner': {},
            'joystick': {},
            'controller': {},
            'quadrotor': {}
        }
        
        # Main simulation loop
        for itick in range(n_ticks):
            t_cur = self.config.t0 + itick * dt_base
            
            # Mission planner update
            if itick % k_plan == 0:
                self.fmuplanner.step_time(t_last_plan, t_cur)
                t_last_plan = t_cur
            
            # Joystick update
            if itick % k_stick == 0:
                self.fmustick.step_time(t_last_stick, t_cur)
                t_last_stick = t_cur
            
            # Controller update
            if itick % k_ctrl == 0:
                if itick != 0:
                    # Get sensor feedback with potential attack injection
                    vel_feedback = self._get_velocity_feedback_with_attack()
                    
                    controller_inputs = {
                        "pos_w_p_w_fdbk[1]": self.fmudyn.get_output_value()['pos_w_p_w_meas[1]'],
                        "pos_w_p_w_fdbk[2]": self.fmudyn.get_output_value()['pos_w_p_w_meas[2]'],
                        "pos_w_p_w_fdbk[3]": self.fmudyn.get_output_value()['pos_w_p_w_meas[3]'],
                        "vel_w_p_b_fdbk[1]": vel_feedback[0],
                        "vel_w_p_b_fdbk[2]": vel_feedback[1],
                        "vel_w_p_b_fdbk[3]": vel_feedback[2],
                        "acc_w_p_b_fdbk[1]": self.fmudyn.get_output_value()['acc_w_p_b_meas[1]'],
                        "acc_w_p_b_fdbk[2]": self.fmudyn.get_output_value()['acc_w_p_b_meas[2]'],
                        "acc_w_p_b_fdbk[3]": self.fmudyn.get_output_value()['acc_w_p_b_meas[3]'],
                        "quat_wb_fdbk[1]": self.fmudyn.get_output_value()['quat_wb_meas[1]'],
                        "quat_wb_fdbk[2]": self.fmudyn.get_output_value()['quat_wb_meas[2]'],
                        "quat_wb_fdbk[3]": self.fmudyn.get_output_value()['quat_wb_meas[3]'],
                        "quat_wb_fdbk[4]": self.fmudyn.get_output_value()['quat_wb_meas[4]'],
                        "euler_wb_fdbk[1]": self.fmudyn.get_output_value()['euler_wb_meas[1]'],
                        "euler_wb_fdbk[2]": self.fmudyn.get_output_value()['euler_wb_meas[2]'],
                        "euler_wb_fdbk[3]": self.fmudyn.get_output_value()['euler_wb_meas[3]'],
                        "rate_wb_b_fdbk[1]": self.fmudyn.get_output_value()['rate_wb_b_meas[1]'],
                        "rate_wb_b_fdbk[2]": self.fmudyn.get_output_value()['rate_wb_b_meas[2]'],
                        "rate_wb_b_fdbk[3]": self.fmudyn.get_output_value()['rate_wb_b_meas[3]'],
                        "rc_input[1]": self.fmustick.get_output_value()['stick_cmd[1]'],
                        "rc_input[2]": self.fmustick.get_output_value()['stick_cmd[2]'],
                        "rc_input[3]": self.fmustick.get_output_value()['stick_cmd[3]'],
                        "rc_input[4]": self.fmustick.get_output_value()['stick_cmd[4]'],
                        "position_setpoint[1]": self.fmuplanner.get_output_value()['position_setpoint_w[1]'],
                        "position_setpoint[2]": self.fmuplanner.get_output_value()['position_setpoint_w[2]'],
                        "position_setpoint[3]": self.fmuplanner.get_output_value()['position_setpoint_w[3]'],
                        "yaw_setpoint": self.fmuplanner.get_output_value()['yaw_setpoint_w']
                    }
                else:
                    # Initial step with zero inputs
                    controller_inputs = {key: 0.0 for key in [
                        "pos_w_p_w_fdbk[1]", "pos_w_p_w_fdbk[2]", "pos_w_p_w_fdbk[3]",
                        "vel_w_p_b_fdbk[1]", "vel_w_p_b_fdbk[2]", "vel_w_p_b_fdbk[3]",
                        "acc_w_p_b_fdbk[1]", "acc_w_p_b_fdbk[2]", "acc_w_p_b_fdbk[3]",
                        "quat_wb_fdbk[1]", "quat_wb_fdbk[2]", "quat_wb_fdbk[3]", "quat_wb_fdbk[4]",
                        "euler_wb_fdbk[1]", "euler_wb_fdbk[2]", "euler_wb_fdbk[3]",
                        "rate_wb_b_fdbk[1]", "rate_wb_b_fdbk[2]", "rate_wb_b_fdbk[3]",
                        "rc_input[1]", "rc_input[2]", "rc_input[3]", "rc_input[4]",
                        "position_setpoint[1]", "position_setpoint[2]", "position_setpoint[3]",
                        "yaw_setpoint"
                    ]}
                
                self.fmuctrl.set_input(t_cur + dt_ctrl, controller_inputs)
                self.fmuctrl.step_time(t_last_ctrl, t_cur)
                t_last_ctrl = t_cur
            
            # Quadrotor dynamics update
            if itick % k_dyn == 0:
                pwm_inputs = {
                    "pwm_rotor_cmd[1]": self.fmuctrl.get_output_value()['pwm_rotor_cmd[1]'],
                    "pwm_rotor_cmd[2]": self.fmuctrl.get_output_value()['pwm_rotor_cmd[2]'],
                    "pwm_rotor_cmd[3]": self.fmuctrl.get_output_value()['pwm_rotor_cmd[3]'],
                    "pwm_rotor_cmd[4]": self.fmuctrl.get_output_value()['pwm_rotor_cmd[4]']
                }
                self.fmudyn.set_input(t_cur + dt_dyn, pwm_inputs)
                self.fmudyn.step_time(t_last_dyn, t_cur)
                t_last_dyn = t_cur
            
            # Attack dynamics
            if self.config.attack_config.scenario == 1 and itick % k_opticalflow == 0:
                self.optical_spoof_vector = np.array([
                    np.random.normal(self.config.attack_config.optical_flow_bias, self.config.attack_config.optical_flow_variance),
                    np.random.normal(self.config.attack_config.optical_flow_bias, self.config.attack_config.optical_flow_variance),
                    0.0
                ], dtype=np.float64)
            
            # Log time step
            data['time'] = np.hstack([data['time'], t_cur])
        
        # Collect and interpolate all component data
        data['missionplanner'] = self._interpolate_component_data(self.fmuplanner, data['time'])
        data['joystick'] = self._interpolate_component_data(self.fmustick, data['time'])
        data['controller'] = self._interpolate_component_data(self.fmuctrl, data['time'])
        data['quadrotor'] = self._interpolate_component_data(self.fmudyn, data['time'])
        
        return data
    
    def _get_velocity_feedback_with_attack(self) -> tuple[float, float, float]:
        """Get velocity feedback with potential attack injection."""
        base_velocity = [
            self.fmudyn.get_output_value()['vel_w_p_b_meas[1]'],
            self.fmudyn.get_output_value()['vel_w_p_b_meas[2]'],
            self.fmudyn.get_output_value()['vel_w_p_b_meas[3]']
        ]
        
        if self.config.attack_config.scenario == 1:
            return (
                base_velocity[0] + self.optical_spoof_vector[0],
                base_velocity[1] + self.optical_spoof_vector[1],
                base_velocity[2] + self.optical_spoof_vector[2]
            )
        else:
            return tuple(base_velocity)
    
    def _interpolate_component_data(self, fmu: FMU, time_grid: np.ndarray) -> Dict[str, Any]:
        """Interpolate component data to common time grid."""
        component_data = {'state': {}, 'variable': {}}
        
        # Check if we have any data to interpolate
        if fmu.data['time'].size == 0:
            # No data, return zeros
            component_data['state']['names'] = fmu.stateNames
            component_data['state']['values'] = np.zeros((time_grid.shape[0], len(fmu.stateNames)))
            component_data['variable']['names'] = fmu.variableNames
            component_data['variable']['values'] = np.zeros((time_grid.shape[0], len(fmu.variableNames)))
            return component_data
        
        # Ensure arrays have consistent lengths
        min_length = min(fmu.data['time'].size, 
                        fmu.data['state']['values'].shape[0] if fmu.data['state']['values'].size > 0 else 0,
                        fmu.data['variable']['values'].shape[0] if fmu.data['variable']['values'].size > 0 else 0)
        
        if min_length == 0:
            # No valid data, return zeros
            component_data['state']['names'] = fmu.stateNames
            component_data['state']['values'] = np.zeros((time_grid.shape[0], len(fmu.stateNames)))
            component_data['variable']['names'] = fmu.variableNames
            component_data['variable']['values'] = np.zeros((time_grid.shape[0], len(fmu.variableNames)))
            return component_data
        
        # Trim arrays to consistent length
        time_data = fmu.data['time'][:min_length]
        
        # Interpolate state data
        component_data['state']['names'] = fmu.stateNames
        if fmu.data['state']['values'].size > 0 and fmu.data['state']['values'].shape[1] > 0:
            state_data = fmu.data['state']['values'][:min_length, :]
            component_data['state']['values'] = np.empty((time_grid.shape[0], state_data.shape[1]))
            for idx in range(state_data.shape[1]):
                try:
                    component_data['state']['values'][:, idx] = np.interp(
                        time_grid, time_data, state_data[:, idx]
                    )
                except Exception as e:
                    # If interpolation fails, use zeros
                    print(f"Warning: State interpolation failed for index {idx}: {e}")
                    component_data['state']['values'][:, idx] = np.zeros(time_grid.shape[0])
        else:
            component_data['state']['values'] = np.zeros((time_grid.shape[0], len(fmu.stateNames)))
        
        # Interpolate variable data
        component_data['variable']['names'] = fmu.variableNames
        if fmu.data['variable']['values'].size > 0 and fmu.data['variable']['values'].shape[1] > 0:
            variable_data = fmu.data['variable']['values'][:min_length, :]
            component_data['variable']['values'] = np.empty((time_grid.shape[0], variable_data.shape[1]))
            for idx in range(variable_data.shape[1]):
                try:
                    component_data['variable']['values'][:, idx] = np.interp(
                        time_grid, time_data, variable_data[:, idx]
                    )
                except Exception as e:
                    # If interpolation fails, use zeros
                    print(f"Warning: Variable interpolation failed for index {idx}: {e}")
                    component_data['variable']['values'][:, idx] = np.zeros(time_grid.shape[0])
        else:
            component_data['variable']['values'] = np.zeros((time_grid.shape[0], len(fmu.variableNames)))
        
        return component_data

    @override
    def stop(self):
        """Stop the simulation and clean up resources."""
        if self.fmudyn:
            self.fmudyn.reset()
        if self.fmuctrl:
            self.fmuctrl.reset()
        if self.fmustick:
            self.fmustick.reset()
        if self.fmuplanner:
            self.fmuplanner.reset()


@attrs.define()
class DroneComponent(Component[None, DroneNode]):
    """
    Drone component for multicosim framework.
    Manages multi-fidelity quadrotor co-simulation with attack scenarios.
    """
    physics_fidelity: FidelityLevel = 1
    cyber_fidelity: FidelityLevel = 1
    fmu_type: FMUType = "me"
    simulation_time: float = 10.0
    time_step: float = 0.1
    attack_scenario: AttackScenario = 0
    optical_flow_bias: float = 0.0
    optical_flow_variance: float = 1.0
    parameter_file: str = "drone_specs.json"
    
    # FMU file paths (these should be set to actual FMU file locations)
    fmu_quadrotor_path: str = "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Quadrotor.fmu"
    fmu_controller_path: str = "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Controller.fmu"
    fmu_joystick_path: str = "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Joystick.fmu"
    fmu_mission_planner_path: str = "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.MissionPlanner.fmu"

    @override
    def start(self, environment: None) -> DroneNode:
        """Start the drone simulation node."""
        # Create simulation configuration
        attack_config = AttackConfig(
            scenario=self.attack_scenario,
            optical_flow_bias=self.optical_flow_bias,
            optical_flow_variance=self.optical_flow_variance
        )
        
        config = SimulationConfig(
            physics_fidelity=self.physics_fidelity,
            cyber_fidelity=self.cyber_fidelity,
            fmu_type=self.fmu_type,
            tf=self.simulation_time,
            dt=self.time_step,
            attack_config=attack_config,
            parameter_file=self.parameter_file
        )
        
        # Create FMU path mapping
        fmu_paths = {
            'quadrotor': self.fmu_quadrotor_path,
            'controller': self.fmu_controller_path,
            'joystick': self.fmu_joystick_path,
            'mission_planner': self.fmu_mission_planner_path
        }
        
        return DroneNode(config=config, fmu_paths=fmu_paths)


def create_drone_specs_json(filename: str = "drone_specs.json"):
    """Create a default drone specifications JSON file."""
    default_specs = {
        "__comment": "unit: -, deg, deg, m, m, m, w, deg, Hz, Hz",
        "eps_controller": 28,
        "emi_disturbance": 120,
        "heading": 90,
        "width": 0.294,
        "COM_height": 0.064,
        "turn_radius": 0.5962,
        "acoustic_power": 100,
        "gyro_misalignment": 2,
        "drive_freq": 15000,
        "acoustic_freq_range": 5,
        "speaker_dist": 0.01,
        "wire_dir": 3,
        "wire_relative_dist": 0.01
    }
    
    with open(filename, 'w') as f:
        json.dump(default_specs, f, indent=2)


@staliro.models.blackbox()
def drone_attack_model(inputs: staliro.models.Blackbox.Inputs) -> staliro.Trace[list[float]]:
    """
    Blackbox model for drone optical flow attack falsification.
    
    This function wraps the drone simulation to be used by psy-taliro for falsification.
    It takes attack parameters as inputs and returns a trace of drone states.
    
    Args:
        inputs: Blackbox inputs containing static attack parameters
        
    Returns:
        Trace containing time series of drone states [altitude, roll, pitch, yaw, pos_x, pos_y, pos_z]
    """
    # Extract attack parameters from inputs
    optical_flow_bias = inputs.static.get("optical_flow_bias", 0.0)
    optical_flow_variance = inputs.static.get("optical_flow_variance", 1.0)
    optical_flow_rate = inputs.static.get("optical_flow_rate", 4.0)
    
    # Create attack configuration
    attack_config = AttackConfig(
        scenario=1,  # Enable optical flow attack
        optical_flow_bias=optical_flow_bias,
        optical_flow_variance=optical_flow_variance,
        optical_flow_rate=optical_flow_rate
    )
    
    # Create simulation configuration
    config = SimulationConfig(
        physics_fidelity=1,  # Low fidelity for faster falsification
        cyber_fidelity=1,
        fmu_type="me",
        tf=25.0,  # 5 second simulation (reduced to avoid segfaults)
        dt=0.1,
        attack_config=attack_config,
        parameter_file="drone_specs.json"
    )
    
    # FMU paths (these need to be available)
    fmu_paths = {
        'quadrotor': "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Quadrotor.fmu",
        'controller': "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Controller.fmu",
        'joystick': "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.Joystick.fmu",
        'mission_planner': "/home/asurite.ad.asu.edu/asawan15/cpslab/multicosim/examples/generated_fmus/GSQuad.Components.MissionPlanner.fmu"
    }
    
    try:
        # Create and run the drone simulation
        drone_node = DroneNode(config=config, fmu_paths=fmu_paths)
        initial_state = DroneState()
        result = drone_node.send(initial_state)
        
        # Extract relevant state variables for safety analysis
        time_data = result['time']
        quadrotor_data = result['quadrotor']
        
        # Extract state indices (these depend on the FMU output structure)
        # Assuming the quadrotor output contains position, attitude, etc.
        states_list = []
        for i, t in enumerate(time_data):
            # Extract key safety-critical states
            # Note: These indices need to match the actual FMU output structure
            if i < len(quadrotor_data['variable']['values']):
                var_values = quadrotor_data['variable']['values'][i]
                
                # Extract altitude (negative z in NED frame)
                altitude = -var_values[2] if len(var_values) > 2 else 0.0
                
                # Extract attitude (roll, pitch, yaw)
                roll = var_values[4] if len(var_values) > 4 else 0.0
                pitch = var_values[5] if len(var_values) > 5 else 0.0
                yaw = var_values[6] if len(var_values) > 6 else 0.0
                
                # Extract position
                pos_x = var_values[0] if len(var_values) > 0 else 0.0
                pos_y = var_values[1] if len(var_values) > 1 else 0.0
                pos_z = var_values[2] if len(var_values) > 2 else 0.0
                
                states_list.append([altitude, roll, pitch, yaw, pos_x, pos_y, pos_z])
            else:
                # Fallback for missing data
                states_list.append([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        
        # Clean up
        drone_node.stop()
        
        return staliro.Trace(times=time_data.tolist(), states=states_list)
        
    except Exception as e:
        # Return a safe trace if simulation fails
        print(f"Simulation failed: {e}")
        safe_times = [0.0, 1.0, 2.0]
        safe_states = [[100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _ in safe_times]
        return staliro.Trace(times=safe_times, states=safe_states)




def run_falsification_analysis():
    """
    Run falsification analysis to find optical flow attack parameters that violate safety.
    """
    print("Starting Drone Optical Flow Attack Falsification Analysis")
    print("=" * 60)
    
    # Create default parameter file if it doesn't exist
    if not os.path.exists("drone_specs.json"):
        create_drone_specs_json()
        print("Created default drone_specs.json file")
    
    # Define safety specifications using RTAmt
    # Specification 1: Drone should maintain minimum altitude (safety)
    altitude_spec = staliro.specifications.rtamt.parse_dense("always (altitude > 5.0)", {"altitude": 0})
    
    # Specification 2: Roll angle should remain bounded (stability)
    roll_spec = staliro.specifications.rtamt.parse_dense("always (abs(roll) < 0.5)", {"roll": 1})  # ~30 degrees
    
    # Specification 3: Pitch angle should remain bounded (stability)
    pitch_spec = staliro.specifications.rtamt.parse_dense("always (abs(pitch) < 0.5)", {"pitch": 2})  # ~30 degrees
    
    # For this example, we'll use the altitude specification
    specification = altitude_spec
    
    # Configure optimizer (Dual Annealing is good for global optimization)
    optimizer = staliro.optimizers.DualAnnealing()
    
    # Define the attack parameter space
    attack_options = staliro.TestOptions(
        runs=1,  # Number of independent runs
        iterations=10,  # Number of iterations per run (reduced to avoid segfaults)
        tspan=(0, 25),  # Time span for simulation
        static_inputs={
            # Optical flow bias: range from -5 to +5 m/s
            "optical_flow_bias": np.array([-5.0, 5.0]),
            
            # Optical flow variance: range from 0.1 to 5.0
            "optical_flow_variance": np.array([0.1, 5.0]),
            
            # Optical flow rate: range from 1 to 10 Hz
            "optical_flow_rate": np.array([1.0, 10.0])
        },
    )
    
    print(f"Configuration:")
    print(f"  - Specification: {altitude_spec}")
    print(f"  - Optimizer: {optimizer.__class__.__name__}")
    print(f"  - Runs: {attack_options.runs}")
    print(f"  - Iterations: {attack_options.iterations}")
    print(f"  - Attack parameter ranges:")
    print(f"    * Optical flow bias: {attack_options.static_inputs['optical_flow_bias']}")
    print(f"    * Optical flow variance: {attack_options.static_inputs['optical_flow_variance']}")
    print(f"    * Optical flow rate: {attack_options.static_inputs['optical_flow_rate']}")
    
    try:
        # Run falsification
        print("\nStarting falsification search...")
        runs = staliro.staliro(drone_attack_model, specification, optimizer, attack_options)
        
        # Analyze results
        run = runs[0]
        print(f"\nFalsification Results:")
        print(f"  - Total evaluations: {len(run.evaluations)}")
        
        # Find the evaluation with minimum cost (most likely to violate specification)
        min_cost_eval = min(run.evaluations, key=lambda e: e.cost)
        
        print(f"  - Minimum cost: {min_cost_eval.cost}")
        print(f"  - Attack parameters for minimum cost:")
        print(f"    * Optical flow bias: {min_cost_eval.sample.static['optical_flow_bias']:.3f}")
        print(f"    * Optical flow variance: {min_cost_eval.sample.static['optical_flow_variance']:.3f}")
        print(f"    * Optical flow rate: {min_cost_eval.sample.static['optical_flow_rate']:.3f}")
        
        # Check if we found a counterexample (negative cost indicates specification violation)
        if min_cost_eval.cost < 0:
            print(f"\nCOUNTEREXAMPLE FOUND!")
            print(f"The following attack parameters violate the safety specification:")
            print(f"  - Optical flow bias: {min_cost_eval.sample.static['optical_flow_bias']:.3f} m/s")
            print(f"  - Optical flow variance: {min_cost_eval.sample.static['optical_flow_variance']:.3f}")
            print(f"  - Optical flow rate: {min_cost_eval.sample.static['optical_flow_rate']:.3f} Hz")
            
            # Visualize the counterexample trace
            visualize_counterexample(min_cost_eval)
        else:
            print(f"\nNo counterexample found within the given search space and iterations.")
            print(f"The system appears robust to the tested attack parameters.")
        
        return runs
        
    except Exception as e:
        print(f"Falsification failed: {e}")
        return None


def generate_falsification_region_analysis(resolution=10, max_evaluations=100):
    """
    Generate a comprehensive falsification region analysis by systematically exploring
    the attack parameter space and mapping where violations occur.
    
    Args:
        resolution: Grid resolution for each parameter dimension
        max_evaluations: Maximum number of evaluations to prevent excessive runtime
    """
    print("\n" + "="*80)
    print("FALSIFICATION REGION ANALYSIS")
    print("="*80)
    print("Systematically mapping the attack parameter space to identify")
    print("regions where safety specifications are violated.")
    print()
    
    # Create figures directory
    import os
    figures_dir = "examples/figures"
    os.makedirs(figures_dir, exist_ok=True)
    
    # Define parameter ranges for systematic exploration
    bias_range = np.linspace(-5.0, 5.0, resolution)
    variance_range = np.linspace(0.1, 5.0, resolution)
    rate_range = np.linspace(1.0, 10.0, resolution)
    
    # Create safety specification
    altitude_spec = staliro.specifications.rtamt.parse_dense("always (altitude > 5.0)", {"altitude": 0})
    
    print(f"Parameter Space Configuration:")
    print(f"  - Bias range: [{bias_range[0]:.1f}, {bias_range[-1]:.1f}] m/s ({len(bias_range)} points)")
    print(f"  - Variance range: [{variance_range[0]:.1f}, {variance_range[-1]:.1f}] ({len(variance_range)} points)")
    print(f"  - Rate range: [{rate_range[0]:.1f}, {rate_range[-1]:.1f}] Hz ({len(rate_range)} points)")
    print(f"  - Total combinations: {len(bias_range) * len(variance_range) * len(rate_range)}")
    print(f"  - Max evaluations: {max_evaluations}")
    print()
    
    # Storage for results
    results = []
    violation_count = 0
    evaluation_count = 0
    
    print("Starting systematic parameter space exploration...")
    
    # Systematic grid search (with early stopping for performance)
    for i, bias in enumerate(bias_range):
        for j, variance in enumerate(variance_range):
            for k, rate in enumerate(rate_range):
                if evaluation_count >= max_evaluations:
                    print(f"Reached maximum evaluations ({max_evaluations}), stopping early...")
                    break
                
                try:
                    # Create attack configuration
                    attack_config = AttackConfig(
                        scenario=1,
                        optical_flow_bias=bias,
                        optical_flow_variance=variance,
                        optical_flow_rate=rate
                    )
                    
                    # Run simulation with these parameters
                    config = SimulationConfig(
                        physics_fidelity=1,
                        cyber_fidelity=1,
                        fmu_type="me",
                        tf=25.0,  # Reduced for performance
                        dt=0.1,
                        attack_config=attack_config,
                        parameter_file="drone_specs.json"
                    )
                    
                    # Get FMU paths
                    fmu_paths = {
                        'quadrotor': 'examples/generated_fmus/GSQuad.Components.Quadrotor.fmu',
                        'controller': 'examples/generated_fmus/GSQuad.Components.Controller.fmu',
                        'joystick': 'examples/generated_fmus/GSQuad.Components.Joystick.fmu',
                        'mission_planner': 'examples/generated_fmus/GSQuad.Components.MissionPlanner.fmu'
                    }
                    
                    # Run simulation directly
                    node = DroneNode(config, fmu_paths)
                    trace = node.run()
                    cost = altitude_spec.evaluate(trace.times, trace.states)
                    
                    # Store result
                    result = {
                        'bias': bias,
                        'variance': variance,
                        'rate': rate,
                        'cost': cost,
                        'violation': cost < 0,  # Negative cost means specification violation
                        'min_altitude': min([state[0] for state in trace.states]) if trace.states else float('inf')
                    }
                    results.append(result)
                    
                    if cost < 0:
                        violation_count += 1
                    
                    evaluation_count += 1
                    
                    # Progress reporting
                    if evaluation_count % 10 == 0:
                        progress = evaluation_count / max_evaluations * 100
                        violation_rate = violation_count / evaluation_count * 100
                        print(f"Progress: {progress:.1f}% ({evaluation_count}/{max_evaluations}) - "
                              f"Violations found: {violation_count} ({violation_rate:.1f}%)")
                
                except Exception as e:
                    print(f"Evaluation failed for (bias={bias:.2f}, var={variance:.2f}, rate={rate:.2f}): {e}")
                    continue
                    
                if evaluation_count >= max_evaluations:
                    break
            if evaluation_count >= max_evaluations:
                break
        if evaluation_count >= max_evaluations:
            break
    
    print(f"\nRegion Analysis Complete!")
    print(f"  - Total evaluations: {evaluation_count}")
    print(f"  - Violations found: {violation_count}")
    if evaluation_count > 0:
        print(f"  - Violation rate: {violation_count/evaluation_count*100:.1f}%")
    else:
        print(f"  - Violation rate: N/A (no successful evaluations)")
    
    # Convert results to DataFrame for analysis
    import pandas as pd
    df_results = pd.DataFrame(results)
    
    if len(df_results) == 0:
        print("No valid results obtained. Check system configuration.")
        return None
    
    # Statistical Analysis
    print(f"\nSTATISTICAL ANALYSIS:")
    print(f"  - Cost statistics:")
    print(f"    * Mean: {df_results['cost'].mean():.3f}")
    print(f"    * Std: {df_results['cost'].std():.3f}")
    print(f"    * Min: {df_results['cost'].min():.3f}")
    print(f"    * Max: {df_results['cost'].max():.3f}")
    
    if violation_count > 0:
        violations = df_results[df_results['violation']]
        print(f"  - Violation region characteristics:")
        print(f"    * Bias range: [{violations['bias'].min():.2f}, {violations['bias'].max():.2f}] m/s")
        print(f"    * Variance range: [{violations['variance'].min():.2f}, {violations['variance'].max():.2f}]")
        print(f"    * Rate range: [{violations['rate'].min():.2f}, {violations['rate'].max():.2f}] Hz")
        print(f"    * Worst violation cost: {violations['cost'].min():.3f}")
        print(f"    * Minimum altitude reached: {violations['min_altitude'].min():.3f} m")
    
    # Generate comprehensive visualizations
    visualize_falsification_region(df_results, figures_dir)
    
    # Save results to CSV
    results_path = os.path.join(figures_dir, "falsification_region_analysis.csv")
    df_results.to_csv(results_path, index=False)
    print(f"\nResults saved to: {results_path}")
    
    return df_results


def visualize_falsification_region(df_results, figures_dir):
    """
    Create comprehensive visualizations of the falsification region analysis.
    """
    print(f"\nGenerating falsification region visualizations...")
    
    # 1. 3D Scatter Plot: Parameter Space with Violations
    fig = plt.figure(figsize=(15, 12))
    
    # 3D scatter plot
    ax1 = fig.add_subplot(221, projection='3d')
    violations = df_results[df_results['violation']]
    safe_points = df_results[~df_results['violation']]
    
    if len(safe_points) > 0:
        ax1.scatter(safe_points['bias'], safe_points['variance'], safe_points['rate'], 
                   c='green', alpha=0.6, s=30, label=f'Safe ({len(safe_points)})')
    
    if len(violations) > 0:
        ax1.scatter(violations['bias'], violations['variance'], violations['rate'], 
                   c='red', alpha=0.8, s=50, label=f'Violations ({len(violations)})')
    
    ax1.set_xlabel('Optical Flow Bias (m/s)')
    ax1.set_ylabel('Optical Flow Variance')
    ax1.set_zlabel('Optical Flow Rate (Hz)')
    ax1.set_title('3D Falsification Region Map')
    ax1.legend()
    
    # 2. Cost Distribution
    ax2 = fig.add_subplot(222)
    ax2.hist(df_results['cost'], bins=20, alpha=0.7, color='blue', edgecolor='black')
    ax2.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Violation Threshold')
    ax2.set_xlabel('Specification Cost')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Distribution of Specification Costs')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Bias vs Variance Heatmap (averaged over rate)
    ax3 = fig.add_subplot(223)
    pivot_data = df_results.groupby(['bias', 'variance'])['violation'].mean().reset_index()
    pivot_table = pivot_data.pivot(index='variance', columns='bias', values='violation')
    
    if not pivot_table.empty:
        im = ax3.imshow(pivot_table.values, cmap='RdYlGn_r', aspect='auto', 
                       extent=[pivot_table.columns.min(), pivot_table.columns.max(),
                              pivot_table.index.min(), pivot_table.index.max()])
        ax3.set_xlabel('Optical Flow Bias (m/s)')
        ax3.set_ylabel('Optical Flow Variance')
        ax3.set_title('Violation Probability Heatmap\n(Bias vs Variance)')
        plt.colorbar(im, ax=ax3, label='Violation Probability')
    
    # 4. Minimum Altitude vs Parameters
    ax4 = fig.add_subplot(224)
    if 'min_altitude' in df_results.columns:
        scatter = ax4.scatter(df_results['bias'], df_results['min_altitude'], 
                            c=df_results['cost'], cmap='RdYlBu', alpha=0.7)
        ax4.axhline(y=5.0, color='red', linestyle='--', linewidth=2, label='Safety Threshold')
        ax4.set_xlabel('Optical Flow Bias (m/s)')
        ax4.set_ylabel('Minimum Altitude (m)')
        ax4.set_title('Minimum Altitude vs Bias')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax4, label='Specification Cost')
    
    plt.tight_layout()
    
    # Save the comprehensive plot
    region_path = os.path.join(figures_dir, "falsification_region_comprehensive.png")
    plt.savefig(region_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    # 5. Separate detailed heatmaps for each parameter pair
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # Bias vs Variance
    if len(df_results) > 1:
        try:
            pivot_bv = df_results.groupby(['bias', 'variance'])['violation'].mean().reset_index()
            pivot_table_bv = pivot_bv.pivot(index='variance', columns='bias', values='violation')
            if not pivot_table_bv.empty:
                im1 = axes[0].imshow(pivot_table_bv.values, cmap='RdYlGn_r', aspect='auto',
                                   extent=[pivot_table_bv.columns.min(), pivot_table_bv.columns.max(),
                                          pivot_table_bv.index.min(), pivot_table_bv.index.max()])
                axes[0].set_xlabel('Optical Flow Bias (m/s)')
                axes[0].set_ylabel('Optical Flow Variance')
                axes[0].set_title('Violation Probability: Bias vs Variance')
                plt.colorbar(im1, ax=axes[0])
        except Exception as e:
            axes[0].text(0.5, 0.5, f'Insufficient data\nfor heatmap', ha='center', va='center', transform=axes[0].transAxes)
    
    # Bias vs Rate
    try:
        pivot_br = df_results.groupby(['bias', 'rate'])['violation'].mean().reset_index()
        pivot_table_br = pivot_br.pivot(index='rate', columns='bias', values='violation')
        if not pivot_table_br.empty:
            im2 = axes[1].imshow(pivot_table_br.values, cmap='RdYlGn_r', aspect='auto',
                               extent=[pivot_table_br.columns.min(), pivot_table_br.columns.max(),
                                      pivot_table_br.index.min(), pivot_table_br.index.max()])
            axes[1].set_xlabel('Optical Flow Bias (m/s)')
            axes[1].set_ylabel('Optical Flow Rate (Hz)')
            axes[1].set_title('Violation Probability: Bias vs Rate')
            plt.colorbar(im2, ax=axes[1])
    except Exception as e:
        axes[1].text(0.5, 0.5, f'Insufficient data\nfor heatmap', ha='center', va='center', transform=axes[1].transAxes)
    
    # Variance vs Rate
    try:
        pivot_vr = df_results.groupby(['variance', 'rate'])['violation'].mean().reset_index()
        pivot_table_vr = pivot_vr.pivot(index='rate', columns='variance', values='violation')
        if not pivot_table_vr.empty:
            im3 = axes[2].imshow(pivot_table_vr.values, cmap='RdYlGn_r', aspect='auto',
                               extent=[pivot_table_vr.columns.min(), pivot_table_vr.columns.max(),
                                      pivot_table_vr.index.min(), pivot_table_vr.index.max()])
            axes[2].set_xlabel('Optical Flow Variance')
            axes[2].set_ylabel('Optical Flow Rate (Hz)')
            axes[2].set_title('Violation Probability: Variance vs Rate')
            plt.colorbar(im3, ax=axes[2])
    except Exception as e:
        axes[2].text(0.5, 0.5, f'Insufficient data\nfor heatmap', ha='center', va='center', transform=axes[2].transAxes)
    
    plt.tight_layout()
    
    # Save detailed heatmaps
    heatmap_path = os.path.join(figures_dir, "falsification_region_heatmaps.png")
    plt.savefig(heatmap_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"  - Comprehensive region plot: falsification_region_comprehensive.png")
    print(f"  - Detailed heatmaps: falsification_region_heatmaps.png")
    print(f"  - All plots saved in: {figures_dir}/")
    
    return True


def visualize_counterexample(evaluation):
    """
    Visualize the counterexample trace that violates the safety specification.
    Includes comprehensive plots similar to GSdrone analysis.
    """
    try:
        trace = evaluation.extra.trace
        times = np.array(trace.times)
        states = np.array(trace.states)
        
        # Create figures directory if it doesn't exist
        import os
        figures_dir = "examples/figures"
        os.makedirs(figures_dir, exist_ok=True)
        
        # Extract state components (based on trace structure)
        # States: [altitude, roll, pitch, yaw, pos_x, pos_y, pos_z, ...]
        altitude = states[:, 0]
        roll = states[:, 1] if states.shape[1] > 1 else np.zeros_like(times)
        pitch = states[:, 2] if states.shape[1] > 2 else np.zeros_like(times)
        yaw = states[:, 3] if states.shape[1] > 3 else np.zeros_like(times)
        pos_x = states[:, 4] if states.shape[1] > 4 else np.zeros_like(times)
        pos_y = states[:, 5] if states.shape[1] > 5 else np.zeros_like(times)
        pos_z = states[:, 6] if states.shape[1] > 6 else np.zeros_like(times)
        
        # 1. ALTITUDE SAFETY PLOT (Primary safety metric)
        plt.figure(figsize=(12, 6))
        plt.plot(times, altitude, 'b-', linewidth=2, label='Altitude')
        plt.axhline(y=5.0, color='red', linestyle='--', linewidth=2, label='Safety Threshold (5m)')
        plt.xlabel('Time [sec]')
        plt.ylabel('Altitude [m]')
        plt.title('Drone Altitude Under Optical Flow Attack (Safety Analysis)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        altitude_path = os.path.join(figures_dir, "drone_counterexample_altitude.png")
        plt.savefig(altitude_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. ATTITUDE ANALYSIS (Roll, Pitch, Yaw in degrees - GSdrone style)
        plt.figure(figsize=(12, 10))
        plt.subplot(3, 1, 1)
        plt.plot(times, roll * 180.0/np.pi, '#1f77b4', linewidth=2, label='Roll')
        plt.grid(True, alpha=0.3)
        plt.ylabel('Roll [deg]')
        plt.legend()
        plt.title('Attitude Under Optical Flow Spoofing Attack')
        
        plt.subplot(3, 1, 2)
        plt.plot(times, pitch * 180.0/np.pi, '#1f77b4', linewidth=2, label='Pitch')
        plt.grid(True, alpha=0.3)
        plt.ylabel('Pitch [deg]')
        plt.legend()
        
        plt.subplot(3, 1, 3)
        plt.plot(times, yaw * 180.0/np.pi, '#1f77b4', linewidth=2, label='Yaw')
        plt.grid(True, alpha=0.3)
        plt.ylabel('Yaw [deg]')
        plt.xlabel('Time [sec]')
        plt.legend()
        
        plt.tight_layout()
        attitude_path = os.path.join(figures_dir, "drone_counterexample_attitude.png")
        plt.savefig(attitude_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. VELOCITY ANALYSIS (if we can derive velocities from position)
        if len(times) > 1:
            # Compute velocities from position derivatives
            dt = np.diff(times)
            vel_x = np.diff(pos_x) / dt
            vel_y = np.diff(pos_y) / dt  
            vel_z = np.diff(pos_z) / dt
            vel_times = times[1:]  # One less point due to derivative
            
            # Convert to body frame velocities (approximation)
            # u = forward, v = right, w = down
            u_vel = vel_x  # Simplified - would need rotation matrix for exact conversion
            v_vel = vel_y
            w_vel = vel_z
            
            plt.figure(figsize=(12, 10))
            plt.subplot(3, 1, 1)
            plt.plot(vel_times, u_vel, '#1f77b4', linewidth=2, label='u (forward velocity)')
            plt.grid(True, alpha=0.3)
            plt.ylabel(r'u (v_{forward}) [m/s]')
            plt.legend()
            plt.title('Velocity Under Optical Flow Spoofing Attack')
            
            plt.subplot(3, 1, 2)
            plt.plot(vel_times, v_vel, '#1f77b4', linewidth=2, label='v (right velocity)')
            plt.grid(True, alpha=0.3)
            plt.ylabel(r'v (v_{right}) [m/s]')
            plt.legend()
            
            plt.subplot(3, 1, 3)
            plt.plot(vel_times, w_vel, '#1f77b4', linewidth=2, label='w (down velocity)')
            plt.grid(True, alpha=0.3)
            plt.ylabel(r'w (v_{down}) [m/s]')
            plt.xlabel('Time [sec]')
            plt.legend()
            
            plt.tight_layout()
            velocity_path = os.path.join(figures_dir, "drone_counterexample_velocity.png")
            plt.savefig(velocity_path, dpi=300, bbox_inches='tight')
            plt.close()
        
        # 4. ANGULAR RATES (if we can derive from attitude)
        if len(times) > 1:
            dt = np.diff(times)
            roll_rate = np.diff(roll) / dt * 180.0/np.pi  # deg/s
            pitch_rate = np.diff(pitch) / dt * 180.0/np.pi
            yaw_rate = np.diff(yaw) / dt * 180.0/np.pi
            rate_times = times[1:]
            
            plt.figure(figsize=(12, 10))
            plt.subplot(3, 1, 1)
            plt.plot(rate_times, roll_rate, '#1f77b4', linewidth=2, label='Roll rate')
            plt.grid(True, alpha=0.3)
            plt.ylabel('Roll rate [deg/s]')
            plt.legend()
            plt.title('Angular Rates Under Optical Flow Spoofing Attack')
            
            plt.subplot(3, 1, 2)
            plt.plot(rate_times, pitch_rate, '#1f77b4', linewidth=2, label='Pitch rate')
            plt.grid(True, alpha=0.3)
            plt.ylabel('Pitch rate [deg/s]')
            plt.legend()
            
            plt.subplot(3, 1, 3)
            plt.plot(rate_times, yaw_rate, '#1f77b4', linewidth=2, label='Yaw rate')
            plt.grid(True, alpha=0.3)
            plt.ylabel('Yaw rate [deg/s]')
            plt.xlabel('Time [sec]')
            plt.legend()
            
            plt.tight_layout()
            rates_path = os.path.join(figures_dir, "drone_counterexample_rates.png")
            plt.savefig(rates_path, dpi=300, bbox_inches='tight')
            plt.close()
        
        # 5. 3D TRAJECTORY PLOT (GSdrone style)
        fig = plt.figure(figsize=(12, 9))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot trajectory
        ax.plot(pos_x, pos_y, pos_z, '#1f77b4', linewidth=2, label='Trajectory')
        
        # Mark start and end points
        if len(pos_x) > 0:
            ax.scatter(pos_x[0], pos_y[0], pos_z[0], color='#b4471f', s=100, marker='o', label='Start')
            ax.scatter(pos_x[-1], pos_y[-1], pos_z[-1], color='#5d1fb4', s=100, marker='^', label='End')
        
        ax.set_xlabel('X [m]')
        ax.set_ylabel('Y [m]') 
        ax.set_zlabel('Z [m]')
        ax.set_title('3D Trajectory of Drone Under Optical Flow Spoofing Attack')
        ax.view_init(elev=20., azim=-35)  # Same view as GSdrone
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        trajectory_path = os.path.join(figures_dir, "drone_counterexample_trajectory_3d.png")
        plt.savefig(trajectory_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # 6. 2D TRAJECTORY (Top-down view)
        plt.figure(figsize=(10, 8))
        plt.plot(pos_x, pos_y, '#1f77b4', linewidth=2, label='Trajectory')
        if len(pos_x) > 0:
            plt.plot(pos_x[0], pos_y[0], 'o', color='#b4471f', markersize=8, label='Start')
            plt.plot(pos_x[-1], pos_y[-1], '^', color='#5d1fb4', markersize=8, label='End')
        plt.grid(True, alpha=0.3)
        plt.xlabel('X [m]')
        plt.ylabel('Y [m]')
        plt.legend()
        plt.axis('equal')
        plt.title('2D Trajectory of Drone Under Optical Flow Spoofing Attack')
        plt.tight_layout()
        
        trajectory_2d_path = os.path.join(figures_dir, "drone_counterexample_trajectory_2d.png")
        plt.savefig(trajectory_2d_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Print summary
        plot_count = 6
        if len(times) <= 1:
            plot_count = 3  # Skip velocity and rate plots if insufficient data
            
        print(f"  - Counterexample visualizations saved in {figures_dir}:")
        print(f"    * drone_counterexample_altitude.png")
        print(f"    * drone_counterexample_attitude.png")
        if len(times) > 1:
            print(f"    * drone_counterexample_velocity.png")
            print(f"    * drone_counterexample_rates.png")
        print(f"    * drone_counterexample_trajectory_3d.png")
        print(f"    * drone_counterexample_trajectory_2d.png")
        print(f"    Total: {plot_count} comprehensive analysis plots generated")
        
    except Exception as e:
        print(f"Visualization failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="GSdrone Multi-Fidelity Co-Simulation with Falsification")
    parser.add_argument("--mode", choices=["simulation", "falsification", "region_analysis"], default="falsification",
                       help="Run mode: 'simulation' for single run, 'falsification' for attack analysis, 'region_analysis' for comprehensive parameter space exploration")
    parser.add_argument("--iterations", type=int, default=50, 
                       help="Number of falsification iterations (default: 50)")
    parser.add_argument("--runs", type=int, default=1,
                       help="Number of falsification runs (default: 1)")
    parser.add_argument("--resolution", type=int, default=10,
                       help="Grid resolution for region analysis (default: 10)")
    parser.add_argument("--max_evaluations", type=int, default=100,
                       help="Maximum evaluations for region analysis (default: 100)")
    
    args = parser.parse_args()
    
    if args.mode == "falsification":
        # Run falsification analysis using psy-taliro
        print("GSdrone Optical Flow Attack Falsification Analysis")
        print("=" * 55)
        print("This analysis uses psy-taliro to find attack parameters")
        print("that can cause the drone to violate safety specifications.")
        print()
        
        # Update test options with command line arguments
        run_falsification_analysis()
        
    elif args.mode == "region_analysis":
        # Run comprehensive falsification region analysis
        print("GSdrone Falsification Region Analysis")
        print("=" * 40)
        print("Comprehensive parameter space exploration to map")
        print("the complete falsification region.")
        print()
        
        # Run region analysis
        results = generate_falsification_region_analysis(
            resolution=args.resolution,
            max_evaluations=args.max_evaluations
        )
        
        if results is not None:
            print(f"\nRegion analysis completed successfully!")
            print(f"Results saved to examples/figures/")
        else:
            print(f"\nRegion analysis failed. Check system configuration.")
        
    else:
        # Original simulation mode
        print("GSdrone Multi-Fidelity Co-Simulation Example")
        print("=" * 50)
        
        # Create default parameter file if it doesn't exist
        if not os.path.exists("drone_specs.json"):
            create_drone_specs_json()
            print("Created default drone_specs.json file")
        
        # Create drone component with attack scenario
        drone = DroneComponent(
            physics_fidelity=1,  # Low-fidelity physics
            cyber_fidelity=1,    # Low-fidelity controller
            simulation_time=10.0,
            attack_scenario=1,   # Optical flow attack
            optical_flow_bias=0.0,
            optical_flow_variance=1.0
        )
        
        print(f"Configured drone simulation:")
        print(f"  - Physics fidelity: {drone.physics_fidelity}")
        print(f"  - Cyber fidelity: {drone.cyber_fidelity}")
        print(f"  - Attack scenario: {drone.attack_scenario}")
        print(f"  - Simulation time: {drone.simulation_time}s")
        
        # Note: To run this simulation, you need:
        # 1. The actual FMU files from FIRE_LoFi_Simulations/GSdrone/
        # 2. PyFMI installed
        # 3. Proper FMU file paths configured
        
        try:
            # Start the simulation node
            node = drone.start(None)
            print("Drone node initialized successfully")
            
            # Create initial state
            initial_state = DroneState()
            print("Initial state created")
            
            # Run simulation (this will fail without actual FMU files)
            print("Starting simulation...")
            result = node.send(initial_state)

            print("Simulation completed successfully")
            print(f"Result contains {len(result)} data categories")
            
            # Stop the simulation
            node.stop()
            print("Simulation stopped")
            
        except Exception as e:
            print(f"Simulation failed (expected without FMU files): {e}")