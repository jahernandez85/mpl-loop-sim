# Pump

## 1\) Steady-state simulation

### Inputs

* Inlet pressure ($P\_{in}$) 1  
* Inlet enthalpy ($h\_{in}$) 2  
* Desired mass flow rate ($\\dot{m}$) or Pump speed ($\\omega$) 3, 4

### Outputs

* Outlet pressure ($P\_{out}$) 1  
* Outlet enthalpy ($h\_{out}$) 2, 5  
* Power consumption ($W\_p$) 1, 6

### Internal States

* Efficiency ($\\eta\_p$) 1, 2

### Algebraic Equations

The hydraulic power and pressure head are defined as:$$W\_p \= \\frac{\\dot{V} \\Delta P\_p}{\\eta\_p} \= \\frac{\\dot{m} (P\_{out} \- P\_{in})}{\\rho \\eta\_p}$$ 1Enthalpy rise for an isentropic process:$$h\_{out} \= h\_{in} \+ \\frac{P\_{out} \- P\_{in}}{\\rho \\eta\_p}$$ 2, 5

### Differential Equations

* None (system is equilibrated).

### Required Correlations

* Pump performance curves ($\\Delta P$ vs $\\dot{V}$ at varying $\\omega$) 7-9

### Required Properties

* Liquid density ($\\rho\_l$), Inlet enthalpy ($h\_l$) 1

### Dynamic Relevance

* Low; provides the boundary condition for the flow rate.

### Recommended Abstraction Level

* 0D / Efficiency-based Map.

## 2\) Dynamic simulation

### Inputs

* Commanded pump speed or duty cycle ($\\omega\_{cmd}$) 9  
* System back-pressure at pump outlet ($P\_{sys}$) 10

### Outputs

* Instantaneous mass flow rate ($\\dot{m}$) 10  
* Outlet pressure ($P\_{out}$)

### Internal States

* Shaft speed, fluid inertia 10

### Algebraic Equations

* Same as steady-state for instantaneous power.

### Differential Equations

The loop momentum conservation tracks the change in mass flow rate:$$\\frac{d\\dot{m}}{dt} \= \\frac{1}{I} (\\Delta P\_p \- \\Delta P\_{sys})$$ 10Where $I \= \\frac{L}{A\_c}$ is the fluid inertia of the loop 10\.

### Required Correlations

* Transient torque-speed maps.

### Required Properties

* Liquid density ($\\rho\_l$).

### Dynamic Relevance

* **High**: Sets the mechanical time constant for flow excursions like Ledinegg instability 10, 11\.

### Recommended Abstraction Level

* 0D with Inertia term.

# Evaporator

## 1\) Steady-state simulation

### Inputs

* Inlet pressure ($P\_{in}$), Inlet enthalpy ($h\_{in}$), Mass flow rate ($\\dot{m}$) 12  
* Heat load ($Q\_{in}$) 13, 14

### Outputs

* Outlet enthalpy ($h\_{out}$), Outlet quality ($x\_{out}$) 15, 16  
* Outlet pressure ($P\_{out}$) 17  
* Average wall temperature ($T\_{w,ave}$) 16

### Internal States

* Two-phase flow regime (Annular, Slug, etc.) 18, 19

### Algebraic Equations

Energy balance:$$Q\_{in} \= \\dot{m}(h\_{out} \- h\_{in})$$ 15$$x\_{out} \= \\frac{h\_{out} \- h\_{sat,l}}{h\_{fg}}$$ 16Pressure drop:$$P\_{out} \= P\_{in} \- (\\Delta P\_{fric} \+ \\Delta P\_{acc} \+ \\Delta P\_{grav})$$ 20, 21

### Differential Equations

* None.

### Required Correlations

* Heat Transfer Coefficient (HTC): Shah, Gungor-Winterton, or Kim-Mudawar 13, 22  
* Two-phase pressure drop: Muller-Steinhagen and Heck, Friedel, or Kim-Mudawar 1, 22, 23

### Required Properties

* $P\_{sat}, T\_{sat}, h\_{fg}, \\rho\_l, \\rho\_v, \\mu\_l, \\mu\_v, \\sigma$ 24, 25

### Dynamic Relevance

* Moderate (determines operational limits like CHF) 26, 27\.

### Recommended Abstraction Level

* 1D Distributed (Segmented/Nodal) 28, 29\.

## 2\) Dynamic simulation

### Inputs

* Time-varying heat flux ($q''(t)$) 30, 31  
* Inlet fluid states ($P, h, \\dot{m}$)

### Outputs

* Transient wall temperature ($T\_w(t)$) 13, 14  
* Outlet state transients.

### Internal States

* Thermal mass (capacitance) of the wall 13, 22  
* Fluid mass inventory 32

### Algebraic Equations

* Same as steady-state for local HTC and pressure drop.

### Differential Equations

Wall energy conservation:$$C\_{w} \\frac{dT\_w}{dt} \= Q\_{in} \- \\alpha A (T\_w \- T\_f)$$ 13, 14Fluid energy conservation (Enthalpy form):$$\\frac{\\partial (\\rho H)}{\\partial t} \+ \\frac{\\partial (\\rho u H)}{\\partial x} \= \\frac{Q}{V} \+ \\frac{\\partial P}{\\partial t}$$ 33, 34Conservation of mass (inventory):$$\\frac{\\partial \\rho}{\\partial t} \+ \\frac{\\partial (\\rho u)}{\\partial x} \= 0$$ 33, 34

### Required Correlations

* Same as steady-state, often using the Homogeneous Equilibrium Model (HEM) for simplicity in time-stepping 22, 35\.

### Required Properties

* Specific heat of wall material ($c\_{p,w}$), fluid densities and enthalpies.

### Dynamic Relevance

* **Critical**: Governs temperature overshoots during boiling initiation and system response to pulsed loads 36, 37\.

### Recommended Abstraction Level

* 1D Finite Volume or Moving Boundary 38, 39\.

# Condenser

## 1\) Steady-state simulation

### Inputs

* Two-phase inlet states ($P, h, \\dot{m}$) 40  
* Coolant/Sink temperature ($T\_{sink}$) and flow rate ($\\dot{m}\_{sink}$) 41, 42

### Outputs

* Outlet subcooling degree ($\\Delta T\_{sub}$) 43  
* Total heat rejected ($Q\_{out}$) 44

### Internal States

* Effective heat transfer area ($A\_{eff}$)

### Algebraic Equations

Heat rejection using effectiveness-NTU or LMTD:$$Q\_{out} \= \\epsilon C\_{min} (T\_{f,in} \- T\_{sink,in})$$ 41, 45$$h\_{out} \= h\_{in} \- \\frac{Q\_{out}}{\\dot{m}}$$

### Required Correlations

* Condensation HTC: Shah or Yan 13, 22

### Required Properties

* $\\rho, h, \\mu, k, c\_p$ for liquid and vapor 25

### Recommended Abstraction Level

* Lumped (0D) or Multi-segment.

## 2\) Dynamic simulation

### Inputs

* Sink temperature transients 18  
* Inlet mass flow and enthalpy fluctuations 32

### Outputs

* Transients in subcooled liquid temperature and system pressure.

### Internal States

* Moving boundary positions (Two-phase to Liquid interface) 9, 39

### Differential Equations

Dynamic mass and energy balance per zone (Subcooled, Two-phase, Superheated):$$\\frac{d(m\_i h\_i)}{dt} \= \\dot{m}*{in} h*{in} \- \\dot{m}*{out} h*{out} \+ \\dot{Q}\_i \+ V\_i \\frac{dP}{dt}$$ 9, 34

### Dynamic Relevance

* **High**: Condenser "flooding" or expansion affects the liquid volume returned to the accumulator/reservoir 32, 46\.

### Recommended Abstraction Level

* Moving Boundary Approach 39\.

# Pipe

## 1\) Steady-state simulation

### Inputs

* Inlet states ($P, h, \\dot{m}$)

### Outputs

* Outlet pressure ($P\_{out}$)

### Algebraic Equations

Pressure drop due to friction:$$\\Delta P\_f \= f \\frac{L}{D} \\frac{\\rho u^2}{2}$$ 47, 48

### Required Correlations

* Friction factor: Darcy-Weisbach with Colebrook or Haaland 22, 49, 50

### Recommended Abstraction Level

* 0D Resistance element.

## 2\) Dynamic simulation

### Differential Equations

Transient mass and momentum equations:$$\\frac{\\partial \\rho}{\\partial t} \+ \\frac{\\partial (\\rho u)}{\\partial x} \= 0$$ 33$$\\frac{\\partial (\\rho u)}{\\partial t} \+ \\frac{\\partial (\\rho u^2)}{\\partial x} \= \-\\frac{\\partial P}{\\partial x} \- \\tau$$ 33

### Dynamic Relevance

* **Moderate**: Governs transport delays and fluid inertia impacts on stability 51, 52\.

### Recommended Abstraction Level

* 1D Discretized nodes 29, 38\.

# Accumulator

## 1\) Steady-state simulation

### Inputs

* Target system pressure ($P\_{set}$) 53, 54

### Outputs

* Reference pressure node ($P\_{ref}$) 32, 55

### Algebraic Equations

Sets the loop pressure level:$$P\_{sys} \= P\_{acc}$$ 32

### Recommended Abstraction Level

* Fixed pressure node.

## 2\) Dynamic simulation

### Inputs

* Mass flow rate from loop expansion/contraction ($\\dot{m}\_a$) 32, 56  
* Control input (Heater power or Nitrogen pressure) 57, 58

### Outputs

* Instantaneous system pressure ($P(t)$) 46, 59

### Internal States

* Gas volume ($V\_g$), Liquid volume ($V\_l$) 60

### Algebraic Equations

Polytropic gas process:$$P\_s V\_s^n \= \\text{constant}$$ 5, 60, 61

### Differential Equations

Rate of pressure change:$$\\frac{dP\_{acc}}{dt} \= \\frac{n P\_{acc}}{V\_g} \\frac{dV\_g}{dt} \= \\frac{n P\_{acc}}{V\_g} \\frac{\\dot{m}\_a}{\\rho\_l}$$ 5, 53

### Dynamic Relevance

* **Highest**: Known as the system "brain"; regulates pressure and absorbs transients 53, 62, 63\.

### Recommended Abstraction Level

* 0D Compressible Nodal model 5, 64\.

# Splitter / Mixer

## 1\) Steady-state simulation

### Algebraic Equations

Mass and energy conservation at the junction:$$\\sum \\dot{m}*{in} \= \\sum \\dot{m}*{out}$$ 56$$\\sum (\\dot{m} h)*{in} \= \\sum (\\dot{m} h)*{out}$$

### Recommended Abstraction Level

* 0D Algebraic Node.

## 2\) Dynamic simulation

### Algebraic Equations

Same as steady-state; typically assumed to have negligible storage capacity 65\.

### Dynamic Relevance

* Low; ensures conservation convergence between branches 66\.

# Valve

## 1\) Steady-state simulation

### Algebraic Equations

Local pressure loss:$$\\Delta P\_v \= K\_L \\frac{\\rho u^2}{2}$$ 23, 65

### Required Correlations

* Loss coefficients ($K\_L$) for specific valve openings 23

## 2\) Dynamic simulation

### Inputs

* Opening percentage/Position over time.

### Dynamic Relevance

* **High** for stability; used to increase system stiffness to mitigate Pressure Drop Oscillations (PDO) 67-69.

# Reservoir

## 1\) Steady-state simulation

### Outputs

* Inlet liquid inventory 70

### Algebraic Equations

Total system mass check:$$M\_{tot} \= \\sum (\\rho V)\_{components}$$ 71

## 2\) Dynamic simulation

### Internal States

* Liquid level / Interface height 22, 72

### Differential Equations

Mass accumulation:$$\\frac{dm\_{res}}{dt} \= \\dot{m}*{in} \- \\dot{m}*{out}$$ 60, 73

### Dynamic Relevance

* **Moderate**: Ensures Net Positive Suction Head (NPSH) for the pump during transients 55, 74, 75\.

# Explanation of Simulation Differences

### 1\. Algebraic vs. Differential Nature

* **Steady-State**: Solves a system of non-linear **algebraic equations**. The objective is to find the point where pump head matches the sum of loop resistances ($\\Delta P\_p \= \\sum \\Delta P\_i$) 1, 29\.  
* **Dynamic**: Solves a system of **Ordinary Differential Equations (ODEs)** or Partial Differential Equations (PDEs). It tracks the derivative of states (e.g., $\\frac{dh}{dt}, \\frac{dP}{dt}$) to account for mass and energy storage in components 5, 33\.

### 2\. Time Constants

* **Steady-State**: Assumes all transients have decayed; time is not a variable.  
* **Dynamic**: Explicitly models hardware time constants (e.g., 3.5s for a pump, 0.1s for a power supply) and thermal inertia ($C\_{wall}$) 13, 76\.

### 3\. Loop Closure

* **Steady-State**: Often closed via an iteration loop (e.g., assuming a reservoir pressure and iterating until the pressure drop around the loop returns to zero) 2, 29\.  
* **Dynamic**: Closure is handled by the numerical integrator (e.g., RK45) as mass flows between storage components and the accumulator adjusts the system pressure node 26, 77, 78\.

