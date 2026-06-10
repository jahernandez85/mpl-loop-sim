"""
PyP2PL — Pumped Two-Phase Loop simulation library.

Install in development mode (editable install):
    pip install -e .

After this, 'from pyp2pl.components.evaporator import ...' works from any
script or Spyder console, without any sys.path tricks.
"""
from setuptools import setup, find_packages

setup(
    name='pyp2pl',
    version='0.1.0',
    description='Python library for pumped two-phase loop simulation',
    packages=find_packages(),
    python_requires='>=3.8',
    install_requires=[
        'CoolProp',
        'scipy',
        'numpy',
        'matplotlib',
        'pandas',
    ],
)
