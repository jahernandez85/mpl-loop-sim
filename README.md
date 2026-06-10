# MPL Loop Simulation Library

A modular scientific framework for the simulation, analysis and surrogate-model generation of mechanically pumped two-phase loops (MPLs).

The objective of this project is to provide a reusable and extensible platform capable of modelling vapor-compression and mechanically pumped thermal systems using physics-based thermo-hydraulic models.

The framework is designed to support both research and engineering applications, ranging from single evaporator loops to complex architectures with multiple parallel evaporators, condensers, accumulators and control devices.

## Main Goals

* Build a reusable component-based simulation library.
* Support steady-state thermo-hydraulic analysis.
* Enable future dynamic and control-oriented models.
* Generate high-fidelity datasets for surrogate-model development.
* Allow rapid reconfiguration of loop topologies.
* Provide a transparent and physically consistent modelling framework.

## Target Systems

Examples of systems that can be represented include:

* Mechanically Pumped Loops (MPL)
* Pumped Two-Phase Loops (P2PL)
* Electronics cooling loops
* Space thermal-control systems
* Heat-pump and refrigeration subsystems
* Experimental two-phase test benches

## Core Modelling Philosophy

The library follows a component-oriented approach.

Physical systems are constructed by connecting reusable components through fluid ports.

Typical components include:

* Pump
* Pipe
* Evaporator
* Condenser
* Accumulator
* Valve
* Splitter
* Mixer
* Reservoir

The thermodynamic state is represented internally using pressure and enthalpy (P-h), while additional properties are obtained through CoolProp or REFPROP.

## Planned Capabilities

### Phase 1

* Fluid properties framework
* Steady-state solver
* Pipe models
* Microchannel evaporator models
* Plate condenser models
* Accumulator models
* Parallel branch support

### Phase 2

* Dynamic simulation framework
* Moving-boundary models
* Control-oriented reduced-order models
* MPC-compatible state-space generation

### Phase 3

* Automated Design of Experiments (DOE)
* Surrogate-model generation
* Machine-learning-assisted closure models
* Hybrid physics-informed modelling

## Validation Strategy

The framework will be continuously validated against:

* Published literature
* Experimental test benches
* Reference datasets
* Existing simulation tools

## Project Status

Current stage:

Architecture definition and literature consolidation.

The project is currently focused on extracting modelling requirements from the scientific literature and defining a robust software architecture before implementation.

## Long-Term Vision

Develop an open, modular and scientifically rigorous simulation environment for next-generation two-phase thermal management systems.

## Documentation Structure

The project documentation is organized as follows:

```text
docs/
├── literature/
├── architecture/
├── validation/
├── roadmap/
└── decisions/
└── meeting_notes/

Developed at Université de Liège - Andrés Hernández June 2026