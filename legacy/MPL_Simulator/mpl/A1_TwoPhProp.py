# -*- coding: utf-8 -*-
"""
Created on Fri Feb  7 19:48:51 2025

@author: AndresH
"""

import pandas as pd
import numpy as np
import os

# List of fluid CSV files
fluid_files = ['R1233ZDE.csv', 'TOLUENE.csv', 'NPENTANE.csv', 'NHEXANE.csv',
            'CARBONDIOXIDE.csv',
            'NHEPTANE.csv', 'CYCLOPENTANE.csv', 'R1234ZEE.csv',
            'R245FA.csv', 'ETHANOL.csv', 'METHANOL.csv',
            'PROPANE.csv', 'ISOBUTANE.csv',
            'R152A.csv', 'R1234YF.csv', 'R22.csv',
            'R11.csv', 'R12.csv', 'AMMONIA.csv', 'WATER.csv',
            'ISOPENTANE.csv', 'R134A.csv', 'R404A.csv', 'R410A.csv', 'R507A.csv',
            'ACETONE.csv', 'NOVEC649.csv', 'R1224YDZ.csv', 'R1336MZZZ.csv']

# Dictionary to store fluid properties
fluid_properties = {}

# Load CSV files into the dictionary
for file in fluid_files:
    fluid_name = os.path.splitext(file)[0]  # Extract fluid name from filename
    df = pd.read_csv(file)  # Read CSV file

    # Store data as a dictionary {property_name: np.array(values)}
    fluid_properties[fluid_name] = {
        prop: df[prop].values for prop in df.columns
    }

def get_Temperature_sat(fluid_name: str, pressure_sat: float):
    """
    Returns the saturation temperature for a given fluid at a specified saturation pressure.
    
    Parameters:
        fluid_name (str): Name of the fluid.
        pressure_sat (float): Saturation pressure (in appropriate units).

    Returns:
        float: Interpolated saturation temperature.
    """
    if fluid_name not in fluid_properties:
        print(f"Error: Data for {fluid_name} not found.")
        return None

    properties = fluid_properties[fluid_name]
    
    if 'Pressure_sat' not in properties or 'Temperature_sat' not in properties:
        print("Error: Required properties not found in the data.")
        return None
    
    pressures = properties['Pressure_sat']
    temperatures = properties['Temperature_sat']
    
    # Sort data by pressure
    sorted_indices = np.argsort(pressures)
    pressures = pressures[sorted_indices]
    temperatures = temperatures[sorted_indices]
    
    # Interpolate using np.interp
    if pressure_sat < pressures.min() or pressure_sat > pressures.max():
        print("Error: Pressure out of range for interpolation.")
        return None
    
    return np.interp(pressure_sat, pressures, temperatures)

# Generic function to interpolate
def interpolate_property(fluid_name: str, temperature_sat: float, quality_X: float, prop_liq: str, prop_vap: str):
    """
    Generic function to interpolate a property for a given fluid at a specified saturation temperature and quality.
    
    Parameters:
        fluid_name (str): Name of the fluid.
        temperature_sat (float): Saturation temperature (in appropriate units).
        quality_X (float): Vapor quality (0 for saturated liquid, 1 for saturated vapor).
        prop_liq (str): Column name for the liquid phase property.
        prop_vap (str): Column name for the vapor phase property.

    Returns:
        float: Interpolated property value.
    """
    if fluid_name not in fluid_properties:
        print(f"Error: Data for {fluid_name} not found.")
        return None

    properties = fluid_properties[fluid_name]
    
    if 'Temperature_sat' not in properties or prop_liq not in properties or prop_vap not in properties:
        print("Error: Required properties not found in the data.")
        return None
    
    temperatures = properties['Temperature_sat']
    prop_liq_values = properties[prop_liq]
    prop_vap_values = properties[prop_vap]
    
    # Sort data by temperature
    sorted_indices = np.argsort(temperatures)
    temperatures = temperatures[sorted_indices]
    prop_liq_values = prop_liq_values[sorted_indices]
    prop_vap_values = prop_vap_values[sorted_indices]
    
    # Interpolate using np.interp
    if temperature_sat < temperatures.min() or temperature_sat > temperatures.max():
        print("Error: Temperature out of range for interpolation.")
        return None
    
    P_l = np.interp(temperature_sat, temperatures, prop_liq_values)
    P_v = np.interp(temperature_sat, temperatures, prop_vap_values)
    
    # Compute property using quality factor
    return P_l + quality_X * (P_v - P_l)

def get_Density(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'Density_liq', 'Density_vap')

def get_SpecificHeat(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'SpecificHeat_liq', 'SpecificHeat_vap')

def get_SoundVel(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'SoundVel_liq', 'SoundVel_vap')

def get_LatentHeat(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, 0, 'LatentHeat_liqvap', 'LatentHeat_liqvap')

def get_ThermalConductivity(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'ThConduc_liq', 'ThConduc_vap')

def get_ElectricalConductivity(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'EleConduc_liq', 'EleConduc_vap')

def get_RelativePermittivity(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'RelPermittivity_liq', 'RelPermittivity_vap')

def get_ViscosityDynamic(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'ViscosityDyn_liq', 'ViscosityDyn_vap')

def get_SurfaceTension(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, 0, 'Surface_tension', 'Surface_tension')

def get_Enthalpy(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'Enthalpy_liq', 'Enthalpy_vap')

def get_Entropy(fluid_name: str, temperature_sat: float, quality_X: float):
    return interpolate_property(fluid_name, temperature_sat, quality_X, 'Entropy_liq', 'Entropy_vap')

# # Example Obtaining T_sat
# fluid_name = "AMMONIA"  # Choose fluid from loaded files
# P_sat_input = 684679  # Example: Given saturation temperature
# X_input = 0  # Example: Vapor quality
# T_sat = get_Temperature_sat(fluid_name, P_sat_input)

# print(f"For {fluid_name}, P_sat = {P_sat_input} K and X = {X_input}:")
# print(f"Saturation temperature (°C) = {T_sat} °C")

# # Example Obtaining T_sat
# fluid_name = "AMMONIA"  # Choose fluid from loaded files
# T_sat_input = 286  # Example: Given saturation temperature
# X_input = 0.5  # Example: Vapor quality
# elec_cond = get_ElectricalConductivity(fluid_name, P_sat_input, X_input)

# print(f"For {fluid_name}, P_sat = {P_sat_input} K and X = {X_input}:")
# print(f"Saturation temperature (°C) = {T_sat} °C")


# # Example Obtaining T_sat
# fluid_name = "ETHANOL"  # Choose fluid from loaded files
# T_sat_input = 280  # Example: Given saturation temperature
# X_input = 0.5  # Example: Vapor quality
# elec_cond = get_LatentHeat(fluid_name, T_sat_input, X_input)

# print(f"For {fluid_name}, T_sat = {T_sat_input} K and X = {X_input}:")
# print(f"Latent heat (J/Kg) = {elec_cond} J/Kg")

# # Example Obtaining T_sat
# fluid_name = "AMMONIA"  # Choose fluid from loaded files
# T_sat_input = 286  # Example: Given saturation temperature
# X_input = 0.5  # Example: Vapor quality
# Density = get_Density(fluid_name, T_sat_input, X_input)

# print(f"For {fluid_name}, T_sat = {T_sat_input} K and X = {X_input}:")
# print(f"Density (kg/m3) = {Density} kg/m3")
