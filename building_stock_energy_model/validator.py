# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright (c) 2025 Tecnalia Research & Innovation

import math
import os

from datetime import datetime
from building_stock_energy_model import constants


#######################################################################
############################## Validator ##############################
#######################################################################


# Function: Validate the limits of a given value
def validateLimits(value: float,
                   limitDown: float,
                   limitUp: float) -> bool:
    """Function to check the limits of a given value.

    Args:
        value (float): The value of the property to be evaluated.
        limitDown (float): The lower limit.
        limitUp (float): The highest limit.
    
    Returns:
        bool

    """

    return True if limitDown <= value <= limitUp else False


# Function: Validate the command line parameters
def validateCommandLineParameters(parameters: list):
    """Funtion to validate the command line parameters.
        
    Args:
        parameters (list): The list of command line parameters. Example::

            [
                "building_energy_process.py",
                "input.json",
                "2019-03-01T13:00:00",
                "2019-03-02T13:00:00",
                "Offices"
            ]
    
    Returns:
        None
    
    """

    # Validate the parameters
    if len(parameters) != 5:
        raise Exception(
            'Validator/>  The number of input parameters is incorrect! (5)')

    # Validate if the payload file exists
    if not os.path.exists(parameters[1].strip()):
        raise Exception(
            'Validator/>  The process input data file does not exist!')

    # Validate the datetime objects
    try:
        datetime.strptime(parameters[2],
                          '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        raise Exception(
            'Validator/>  The third input parameter (start datetime) has an incorrect format (yyyy-MM-ddTHH:mm:ss)')
    try:
        datetime.strptime(parameters[3],
                          '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        raise Exception(
            'Validator/>  The fourth input parameter (end datetime) has an incorrect format (yyyy-MM-ddTHH:mm:ss)')
    if (parameters[3] <= parameters[2]):
        raise Exception(
            'Validator/>  The end time cannot be less than the start time!')

    # Validate the building use
    if not parameters[4] or not parameters[4].strip() or parameters[4].strip() not in constants.BUILDING_USES:
        raise Exception('Validator/>  The building use must be one of the following: '
                        '"Apartment Block", "Single family- Terraced houses", "Hotels and Restaurants",'
                        '"Health", "Education", "Offices", "Trade", "Other non-residential buildings", "Sport"')


# Function: Validate the integrity of the database
def validateDatabaseIntegrity():
    """Funtion to validate the integrity of the database.
        
    Args:
        None
    
    Returns:
        None
    
    """

    for filePath in constants.DATABASE:
        if not os.path.exists(filePath):
            raise Exception(
                'Validator/>  The file "' + filePath + '" does not exist in the database!')


# Function: Validate the process payload
def validateProcessPayload(payload: dict) -> dict:
    """Funtion to validate the process payload.

    Args:
        payload (dict): The process payload::
        
            Example: see "input.json" file in the root directory.
    
    Returns:
        dict

    """

    # Validate the property: nutsid
    if not 'nutsid' in payload or payload['nutsid'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "nutsid"')
    if payload['nutsid'].strip().upper() not in constants.REGION_LIST:
        raise Exception(
            'Validator/>  The following property has an invalid value: "nutsid"')

    # Validate the property: year
    if not 'year' in payload or payload['year'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "year"')
    if not validateLimits(int(payload['year']),
                          1900,
                          2050):
        raise Exception(
            'Validator/>  The following property has an invalid value (1900 - 2050): "year"')

    # Validate the property: scenario
    if not 'scenario' in payload or payload['scenario'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "scenario"')
    scenario = payload['scenario']

    # Validate the property: increase_residential_built_area
    if not 'increase_residential_built_area' in scenario or scenario['increase_residential_built_area'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "increase_residential_built_area"')
    if not validateLimits(scenario['increase_residential_built_area'],
                          0,
                          1):
        raise Exception(
            'Validator/>  The following property has an invalid value (0 - 1): "increase_residential_built_area"')

    # Validate the property: increase_service_built_area
    if not 'increase_service_built_area' in scenario or scenario['increase_service_built_area'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "increase_service_built_area"')
    if not validateLimits(scenario['increase_service_built_area'],
                          0,
                          1):
        raise Exception(
            'Validator/>  The following property has an invalid value (0 - 1): "increase_service_built_area"')

    # Validate the property: hdd_reduction
    if not 'hdd_reduction' in scenario or scenario['hdd_reduction'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "hdd_reduction"')
    if not validateLimits(scenario['hdd_reduction'],
                          -1,
                          1):
        raise Exception(
            'Validator/>  The following property has an invalid value (0-1 - 1): "hdd_reduction"')

    # Validate the property: cdd_reduction
    if not 'cdd_reduction' in scenario or scenario['cdd_reduction'] is None:
        raise Exception(
            'Validator/>  The following property is not present or has a null value: "cdd_reduction"')
    if not validateLimits(scenario['cdd_reduction'],
                          -1,
                          1):
        raise Exception(
            'Validator/>  The following property has an invalid value (-1 - 1): "cdd_reduction"')

    # Validate the property: active_measures
    if not 'active_measures' in scenario or scenario['active_measures'] is None or len(scenario['active_measures']) == 0:
        raise Exception(
            'Validator/>  The following property is not present, has a null value or is empty: "active_measures"')

    # Iterate through the property: active_measures
    for measure in scenario['active_measures']:
        # Validate the property: building_use
        if not 'building_use' in measure or measure['building_use'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "building_use"')
        if measure['building_use'] not in constants.BUILDING_USES:
            raise Exception('Validator/>  The property "active_measures" -> "building_use" must be one of the following: '
                            '"Apartment Block", "Single family- Terraced houses", "Hotels and Restaurants",'
                            '"Health", "Education", "Offices", "Trade", "Other non-residential buildings", "Sport"')

        # Validate the property: user_defined_data
        if not 'user_defined_data' in measure or measure['user_defined_data'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "user_defined_data"')
        if not isinstance(measure['user_defined_data'], bool):
            raise Exception(
                'Validator/>  The following property has an invalid value (true / false): "active_measures" -> "user_defined_data"')

        # Validate the property: space_heating
        if not 'space_heating' in measure or measure['space_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" (' + measure['building_use'] + ')')
        spaceHeating = measure['space_heating']

        # Validate the property: space_heating -> pct_build_equipped
        if not 'pct_build_equipped' in spaceHeating or spaceHeating['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> solids
        if not 'solids' in spaceHeating or spaceHeating['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> lpg
        if not 'lpg' in spaceHeating or spaceHeating['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> diesel_oil
        if not 'diesel_oil' in spaceHeating or spaceHeating['diesel_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "diesel_oil" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['diesel_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "diesel_oil" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> gas_heat_pumps
        if not 'gas_heat_pumps' in spaceHeating or spaceHeating['gas_heat_pumps'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "gas_heat_pumps" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['gas_heat_pumps'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "gas_heat_pumps" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> natural_gas
        if not 'natural_gas' in spaceHeating or spaceHeating['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> biomass
        if not 'biomass' in spaceHeating or spaceHeating['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> geothermal
        if not 'geothermal' in spaceHeating or spaceHeating['geothermal'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "geothermal" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['geothermal'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "geothermal" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> distributed_heat
        if not 'distributed_heat' in spaceHeating or spaceHeating['distributed_heat'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "distributed_heat" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['distributed_heat'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "distributed_heat" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> advanced_electric_heating
        if not 'advanced_electric_heating' in spaceHeating or spaceHeating['advanced_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['advanced_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> conventional_electric_heating
        if not 'conventional_electric_heating' in spaceHeating or spaceHeating['conventional_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "conventional_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['conventional_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "conventional_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> bio_oil
        if not 'bio_oil' in spaceHeating or spaceHeating['bio_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "bio_oil" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['bio_oil'],
                              0, 
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "bio_oil" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> bio_gas
        if not 'bio_gas' in spaceHeating or spaceHeating['bio_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "bio_gas" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['bio_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "bio_gas" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> hydrogen
        if not 'hydrogen' in spaceHeating or spaceHeating['hydrogen'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "hydrogen" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['hydrogen'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "hydrogen" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> electricity_in_circulation
        if not 'electricity_in_circulation' in spaceHeating or spaceHeating['electricity_in_circulation'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_heating" -> "electricity_in_circulation" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['electricity_in_circulation'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_heating" -> "electricity_in_circulation" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling
        if not 'space_cooling' in measure or measure['space_cooling'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_cooling" (' + measure['building_use'] + ')')
        spaceCooling = measure['space_cooling']

        # Validate the property: space_cooling -> pct_build_equipped
        if not 'pct_build_equipped' in spaceCooling or spaceCooling['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_cooling" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_cooling" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling -> gas_heat_pumps
        if not 'gas_heat_pumps' in spaceCooling or spaceCooling['gas_heat_pumps'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_cooling" -> "gas_heat_pumps" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['gas_heat_pumps'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_cooling" -> "gas_heat_pumps" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling -> electric_space_cooling
        if not 'electric_space_cooling' in spaceCooling or spaceCooling['electric_space_cooling'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "space_cooling" -> "electric_space_cooling" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['electric_space_cooling'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "space_cooling" -> "electric_space_cooling" (' + measure['building_use'] + ')')

        # Validate the property: water_heating
        if not 'water_heating' in measure or measure['water_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" (' + measure['building_use'] + ')')
        waterHeating = measure['water_heating']

        # Validate the property: water_heating -> pct_build_equipped
        if not 'pct_build_equipped' in waterHeating or waterHeating['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> solids
        if not 'solids' in waterHeating or waterHeating['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> lpg
        if not 'lpg' in waterHeating or waterHeating['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> diesel_oil
        if not 'diesel_oil' in waterHeating or waterHeating['diesel_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "diesel_oil" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['diesel_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "diesel_oil" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> natural_gas
        if not 'natural_gas' in waterHeating or waterHeating['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> biomass
        if not 'biomass' in waterHeating or waterHeating['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> geothermal
        if not 'geothermal' in waterHeating or waterHeating['geothermal'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "geothermal" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['geothermal'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "geothermal" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> distributed_heat
        if not 'distributed_heat' in waterHeating or waterHeating['distributed_heat'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "distributed_heat" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['distributed_heat'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "distributed_heat" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> advanced_electric_heating
        if not 'advanced_electric_heating' in waterHeating or waterHeating['advanced_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['advanced_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> bio_oil
        if not 'bio_oil' in waterHeating or waterHeating['bio_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "bio_oil" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['bio_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "bio_oil" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> bio_gas
        if not 'bio_gas' in waterHeating or waterHeating['bio_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "bio_gas" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['bio_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "bio_gas" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> hydrogen
        if not 'hydrogen' in waterHeating or waterHeating['hydrogen'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "hydrogen" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['hydrogen'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "hydrogen" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> solar
        if not 'solar' in waterHeating or waterHeating['solar'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "solar" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['solar'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "solar" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> electricity
        if not 'electricity' in waterHeating or waterHeating['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "water_heating" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "water_heating" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: cooking
        if not 'cooking' in measure or measure['cooking'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" (' + measure['building_use'] + ')')
        cooking = measure['cooking']

        # Validate the property: cooking -> pct_build_equipped
        if not 'pct_build_equipped' in cooking or cooking['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> solids
        if not 'solids' in cooking or cooking['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> lpg
        if not 'lpg' in cooking or cooking['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> natural_gas
        if not 'natural_gas' in cooking or cooking['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> biomass
        if not 'biomass' in cooking or cooking['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> electricity
        if not 'electricity' in cooking or cooking['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "cooking" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "cooking" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: lighting
        if not 'lighting' in measure or measure['lighting'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "lighting" (' + measure['building_use'] + ')')
        lighting = measure['lighting']

        # Validate the property: lighting -> pct_build_equipped
        if not 'pct_build_equipped' in lighting or lighting['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "lighting" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(lighting['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "lighting" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: lighting -> electricity
        if not 'electricity' in lighting or lighting['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "lighting" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(lighting['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "lighting" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: appliances
        if not 'appliances' in measure or measure['appliances'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "appliances" (' + measure['building_use'] + ')')
        appliances = measure['appliances']

        # Validate the property: appliances -> pct_build_equipped
        if not 'pct_build_equipped' in appliances or appliances['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "appliances" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(appliances['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "appliances" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: appliances -> electricity
        if not 'electricity' in appliances or appliances['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures" -> "appliances" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(appliances['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures" -> "appliances" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the values defined by the user (if needed)
        if bool(measure['user_defined_data']):
            # Validate the values of the property: space_heating
            if (math.floor((float(measure['space_heating']['solids']) +
                            float(measure['space_heating']['lpg']) +
                            float(measure['space_heating']['diesel_oil']) +
                            float(measure['space_heating']['gas_heat_pumps']) +
                            float(measure['space_heating']['natural_gas']) +
                            float(measure['space_heating']['biomass']) +
                            float(measure['space_heating']['geothermal']) +
                            float(measure['space_heating']['distributed_heat']) +
                            float(measure['space_heating']['advanced_electric_heating']) +
                            float(measure['space_heating']['conventional_electric_heating']) +
                            float(measure['space_heating']['bio_oil']) +
                            float(measure['space_heating']['bio_gas']) +
                            float(measure['space_heating']['hydrogen'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "space_heating" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: space_cooling
            if (math.floor((float(measure['space_cooling']['gas_heat_pumps']) +
                            float(measure['space_cooling']['electric_space_cooling'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "space_cooling" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: water_heating
            if (math.floor((float(measure['water_heating']['solids']) +
                            float(measure['water_heating']['lpg']) +
                            float(measure['water_heating']['diesel_oil']) +
                            float(measure['water_heating']['natural_gas']) +
                            float(measure['water_heating']['biomass']) +
                            float(measure['water_heating']['geothermal']) +
                            float(measure['water_heating']['distributed_heat']) +
                            float(measure['water_heating']['advanced_electric_heating']) +
                            float(measure['water_heating']['bio_oil']) +
                            float(measure['water_heating']['bio_gas']) +
                            float(measure['water_heating']['hydrogen']) +
                            float(measure['water_heating']['solar']) +
                            float(measure['water_heating']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "water_heating" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: cooking
            if (math.floor((float(measure['cooking']['solids']) +
                            float(measure['cooking']['lpg']) +
                            float(measure['cooking']['natural_gas']) +
                            float(measure['cooking']['biomass']) +
                            float(measure['cooking']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "cooking" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: lighting
            if (math.floor((float(measure['lighting']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "lighting" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: appliances
            if (math.floor((float(measure['appliances']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures" -> "appliances" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

    # Validate the property: active_measures_baseline
    if not 'active_measures_baseline' in scenario or scenario['active_measures_baseline'] is None or len(scenario['active_measures_baseline']) == 0:
        raise Exception(
            'Validator/>  The following property is not present, has a null value or is empty: "active_measures_baseline"')

    # Iterate through the property: active_measures_baseline
    for measure in scenario['active_measures_baseline']:
        # Validate the property: building_use
        if not 'building_use' in measure or measure['building_use'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline -> building_use"')
        if measure['building_use'] not in constants.BUILDING_USES:
            raise Exception('Validator/>  The property "active_measures -> active_measures_baseline" must be one of the following: '
                            '"Apartment Block", "Single family- Terraced houses", "Hotels and Restaurants",'
                            '"Health", "Education", "Offices", "Trade", "Other non-residential buildings", "Sport"')

        # Validate the property: user_defined_data
        if not 'user_defined_data' in measure or measure['user_defined_data'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline -> user_defined_data"')
        if not isinstance(measure['user_defined_data'], bool):
            raise Exception(
                'Validator/>  The following property has an invalid value (true / false): "active_measures_baseline -> user_defined_data"')

        # Validate the property: space_heating
        if not 'space_heating' in measure or measure['space_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline -> space_heating (' + measure['building_use'] + ')"')
        spaceHeating = measure['space_heating']

        # Validate the property: space_heating -> pct_build_equipped
        if not 'pct_build_equipped' in spaceHeating or spaceHeating['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> solids
        if not 'solids' in spaceHeating or spaceHeating['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> lpg
        if not 'lpg' in spaceHeating or spaceHeating['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> diesel_oil
        if not 'diesel_oil' in spaceHeating or spaceHeating['diesel_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "diesel_oil" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['diesel_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "diesel_oil" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> gas_heat_pumps
        if not 'gas_heat_pumps' in spaceHeating or spaceHeating['gas_heat_pumps'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "gas_heat_pumps" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['gas_heat_pumps'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "gas_heat_pumps" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> natural_gas
        if not 'natural_gas' in spaceHeating or spaceHeating['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> biomass
        if not 'biomass' in spaceHeating or spaceHeating['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> geothermal
        if not 'geothermal' in spaceHeating or spaceHeating['geothermal'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "geothermal" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['geothermal'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "geothermal" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> distributed_heat
        if not 'distributed_heat' in spaceHeating or spaceHeating['distributed_heat'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "distributed_heat" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['distributed_heat'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "distributed_heat" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> advanced_electric_heating
        if not 'advanced_electric_heating' in spaceHeating or spaceHeating['advanced_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['advanced_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> conventional_electric_heating
        if not 'conventional_electric_heating' in spaceHeating or spaceHeating['conventional_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "conventional_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['conventional_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "conventional_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> bio_oil
        if not 'bio_oil' in spaceHeating or spaceHeating['bio_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "bio_oil" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['bio_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "bio_oil" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> bio_gas
        if not 'bio_gas' in spaceHeating or spaceHeating['bio_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "bio_gas" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['bio_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "bio_gas" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> hydrogen
        if not 'hydrogen' in spaceHeating or spaceHeating['hydrogen'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "hydrogen" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['hydrogen'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "hydrogen" (' + measure['building_use'] + ')')

        # Validate the property: space_heating -> electricity_in_circulation
        if not 'electricity_in_circulation' in spaceHeating or spaceHeating['electricity_in_circulation'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_heating" -> "electricity_in_circulation" (' + measure['building_use'] + ')')
        if not validateLimits(spaceHeating['electricity_in_circulation'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_heating" -> "electricity_in_circulation" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling
        if not 'space_cooling' in measure or measure['space_cooling'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_cooling" (' + measure['building_use'] + ')')
        spaceCooling = measure['space_cooling']

        # Validate the property: space_cooling -> pct_build_equipped
        if not 'pct_build_equipped' in spaceCooling or spaceCooling['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_cooling" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_cooling" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling -> gas_heat_pumps
        if not 'gas_heat_pumps' in spaceCooling or spaceCooling['gas_heat_pumps'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_cooling" -> "gas_heat_pumps" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['gas_heat_pumps'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_cooling" -> "gas_heat_pumps" (' + measure['building_use'] + ')')

        # Validate the property: space_cooling -> electric_space_cooling
        if not 'electric_space_cooling' in spaceCooling or spaceCooling['electric_space_cooling'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "space_cooling" -> "electric_space_cooling" (' + measure['building_use'] + ')')
        if not validateLimits(spaceCooling['electric_space_cooling'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "space_cooling" -> "electric_space_cooling" (' + measure['building_use'] + ')')

        # Validate the property: water_heating
        if not 'water_heating' in measure or measure['water_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" (' + measure['building_use'] + ')')
        waterHeating = measure['water_heating']

        # Validate the property: water_heating -> pct_build_equipped
        if not 'pct_build_equipped' in waterHeating or waterHeating['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> solids
        if not 'solids' in waterHeating or waterHeating['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> lpg
        if not 'lpg' in waterHeating or waterHeating['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> diesel_oil
        if not 'diesel_oil' in waterHeating or waterHeating['diesel_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "diesel_oil" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['diesel_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "diesel_oil" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> natural_gas
        if not 'natural_gas' in waterHeating or waterHeating['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> biomass
        if not 'biomass' in waterHeating or waterHeating['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> geothermal
        if not 'geothermal' in waterHeating or waterHeating['geothermal'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "geothermal" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['geothermal'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "geothermal" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> distributed_heat
        if not 'distributed_heat' in waterHeating or waterHeating['distributed_heat'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "distributed_heat" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['distributed_heat'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "distributed_heat" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> advanced_electric_heating
        if not 'advanced_electric_heating' in waterHeating or waterHeating['advanced_electric_heating'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['advanced_electric_heating'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "advanced_electric_heating" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> bio_oil
        if not 'bio_oil' in waterHeating or waterHeating['bio_oil'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "bio_oil" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['bio_oil'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "bio_oil" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> bio_gas
        if not 'bio_gas' in waterHeating or waterHeating['bio_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "bio_gas" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['bio_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "bio_gas" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> hydrogen
        if not 'hydrogen' in waterHeating or waterHeating['hydrogen'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "hydrogen" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['hydrogen'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "hydrogen" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> solar
        if not 'solar' in waterHeating or waterHeating['solar'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "solar" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['solar'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "solar" (' + measure['building_use'] + ')')

        # Validate the property: water_heating -> electricity
        if not 'electricity' in waterHeating or waterHeating['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "water_heating" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(waterHeating['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "water_heating" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: cooking
        if not 'cooking' in measure or measure['cooking'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" (' + measure['building_use'] + ')')
        cooking = measure['cooking']

        # Validate the property: cooking -> pct_build_equipped
        if not 'pct_build_equipped' in cooking or cooking['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> solids
        if not 'solids' in cooking or cooking['solids'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "solids" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['solids'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "solids" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> lpg
        if not 'lpg' in cooking or cooking['lpg'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "lpg" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['lpg'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "lpg" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> natural_gas
        if not 'natural_gas' in cooking or cooking['natural_gas'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "natural_gas" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['natural_gas'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "natural_gas" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> biomass
        if not 'biomass' in cooking or cooking['biomass'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "biomass" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['biomass'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "biomass" (' + measure['building_use'] + ')')

        # Validate the property: cooking -> electricity
        if not 'electricity' in cooking or cooking['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "cooking" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(cooking['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "cooking" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: lighting
        if not 'lighting' in measure or measure['lighting'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "lighting" (' + measure['building_use'] + ')')
        lighting = measure['lighting']

        # Validate the property: lighting -> pct_build_equipped
        if not 'pct_build_equipped' in lighting or lighting['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "lighting" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(lighting['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "lighting" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: lighting -> electricity
        if not 'electricity' in lighting or lighting['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "lighting" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(lighting['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "lighting" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the property: appliances
        if not 'appliances' in measure or measure['appliances'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "appliances" (' + measure['building_use'] + ')')
        appliances = measure['appliances']

        # Validate the property: appliances -> pct_build_equipped
        if not 'pct_build_equipped' in appliances or appliances['pct_build_equipped'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "appliances" -> "pct_build_equipped" (' + measure['building_use'] + ')')
        if not validateLimits(appliances['pct_build_equipped'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "appliances" -> "pct_build_equipped" (' + measure['building_use'] + ')')

        # Validate the property: appliances -> electricity
        if not 'electricity' in appliances or appliances['electricity'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "active_measures_baseline" -> "appliances" -> "electricity" (' + measure['building_use'] + ')')
        if not validateLimits(appliances['electricity'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "active_measures_baseline" -> "appliances" -> "electricity" (' + measure['building_use'] + ')')

        # Validate the values defined by the user (if needed)
        if bool(measure['user_defined_data']):
            # Validate the values of the property: space_heating
            if (math.floor((float(measure['space_heating']['solids']) +
                            float(measure['space_heating']['lpg']) +
                            float(measure['space_heating']['diesel_oil']) +
                            float(measure['space_heating']['gas_heat_pumps']) +
                            float(measure['space_heating']['natural_gas']) +
                            float(measure['space_heating']['biomass']) +
                            float(measure['space_heating']['geothermal']) +
                            float(measure['space_heating']['distributed_heat']) +
                            float(measure['space_heating']['advanced_electric_heating']) +
                            float(measure['space_heating']['conventional_electric_heating']) +
                            float(measure['space_heating']['bio_oil']) +
                            float(measure['space_heating']['bio_gas']) +
                            float(measure['space_heating']['hydrogen'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "space_heating" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: space_cooling
            if (math.floor((float(measure['space_cooling']['gas_heat_pumps']) +
                            float(measure['space_cooling']['electric_space_cooling'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "space_cooling" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: water_heating
            if (math.floor((float(measure['water_heating']['solids']) +
                            float(measure['water_heating']['lpg']) +
                            float(measure['water_heating']['diesel_oil']) +
                            float(measure['water_heating']['natural_gas']) +
                            float(measure['water_heating']['biomass']) +
                            float(measure['water_heating']['geothermal']) +
                            float(measure['water_heating']['distributed_heat']) +
                            float(measure['water_heating']['advanced_electric_heating']) +
                            float(measure['water_heating']['bio_oil']) +
                            float(measure['water_heating']['bio_gas']) +
                            float(measure['water_heating']['hydrogen']) +
                            float(measure['water_heating']['solar']) +
                            float(measure['water_heating']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "water_heating" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: cooking
            if (math.floor((float(measure['cooking']['solids']) +
                            float(measure['cooking']['lpg']) +
                            float(measure['cooking']['natural_gas']) +
                            float(measure['cooking']['biomass']) +
                            float(measure['cooking']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "cooking" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: lighting
            if (math.floor((float(measure['lighting']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "lighting" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

            # Validate the values of the property: appliances
            if (math.floor((float(measure['appliances']['electricity'])) * 1.0e+04) / 1.0e+04) != 1:
                raise ValueError('Validator/>  "active_measures_baseline" -> "appliances" ' +
                                 '(' + measure['building_use'] + '): The value of all ' +
                                 'Energy Systems must add up to 1!')

    # Validate the property: passive_measures
    if not 'passive_measures' in scenario or scenario['passive_measures'] is None or len(scenario['passive_measures']) == 0:
        raise Exception(
            'Validator/>  The following property is not present, has a null value or is empty: "passive_measures"')

    # Iterate through the property: passive_measures
    for measure in scenario['passive_measures']:
        # Validate the property: building_use
        if not 'building_use' in measure or measure['building_use'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "building_use"')
        if measure['building_use'] not in constants.BUILDING_USES:
            raise Exception('Validator/>  The property "passive_measures" -> "building_use" must be one of the following: '
                            '"Apartment Block", "Single family- Terraced houses", "Hotels and Restaurants",'
                            '"Health", "Education", "Offices", "Trade", "Other non-residential buildings", "Sport"')

        # Validate the property: ref_level
        if not 'ref_level' in measure or measure['ref_level'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "ref_level" (' + measure['building_use'] + ')')
        if measure['ref_level'] not in constants.LEVELS:
            raise Exception(
                'Validator/>  The following property has an invalid value (High / Medium / Low): "passive_measures" -> "ref_level" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods
        if not 'percentages_by_periods' in measure or measure['percentages_by_periods'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" (' + measure['building_use'] + ')')
        percentagesByPeriods = measure['percentages_by_periods']

        # Validate the property: percentages_by_periods -> Pre-1945
        if not 'Pre-1945' in percentagesByPeriods or percentagesByPeriods['Pre-1945'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "Pre-1945" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['Pre-1945'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "Pre-1945" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> 1945-1969
        if not '1945-1969' in percentagesByPeriods or percentagesByPeriods['1945-1969'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "1945-1969" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['1945-1969'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "1945-1969" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> 1970-1979
        if not '1970-1979' in percentagesByPeriods or percentagesByPeriods['1970-1979'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "1970-1979" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['1970-1979'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "1970-1979" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> 1980-1989
        if not '1980-1989' in percentagesByPeriods or percentagesByPeriods['1980-1989'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "1980-1989" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['1980-1989'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "1980-1989" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> 1990-1999
        if not '1990-1999' in percentagesByPeriods or percentagesByPeriods['1990-1999'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "1990-1999" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['1990-1999'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "1990-1999" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> 2000-2010
        if not '2000-2010' in percentagesByPeriods or percentagesByPeriods['2000-2010'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "2000-2010" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['2000-2010'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "2000-2010" (' + measure['building_use'] + ')')

        # Validate the property: percentages_by_periods -> Post-2010
        if not 'Post-2010' in percentagesByPeriods or percentagesByPeriods['Post-2010'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "passive_measures" -> "percentages_by_periods" -> "Post-2010" (' + measure['building_use'] + ')')
        if not validateLimits(percentagesByPeriods['Post-2010'],
                              0,
                              1):
            raise Exception(
                'Validator/>  The following property has an invalid value (0 - 1): "passive_measures" -> "percentages_by_periods" -> "Post-2010" (' + measure['building_use'] + ')')

    # Validate the property: solar
    if not 'solar' in scenario or scenario['solar'] is None or len(scenario['solar']) == 0:
        raise Exception(
            'Validator/>  The following property is not present, has a null value or is empty: "solar"')
    
    # Iterate through the property: solar
    for item in scenario['solar']:
        # Validate the property: building_use
        if not 'building_use' in item or item['building_use'] is None:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "solar" -> "building_use"')
        if item['building_use'] not in constants.BUILDING_USES:
            raise Exception('Validator/>  The property "solar" -> "building_use" must be one of the following: '
                            '"Apartment Block", "Single family- Terraced houses", "Hotels and Restaurants",'
                            '"Health", "Education", "Offices", "Trade", "Other non-residential buildings", "Sport"')

        # Validate the property: area_total
        if not 'area_total' in item:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "solar" -> "area_total" (' + item['area_total'] + ')')
        
        # Validate the property: power
        if not 'power' in item:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "solar" -> "power" (' + item['power'] + ')')
        
        # Validate the property: capex
        if not 'capex' in item:
            raise Exception(
                'Validator/>  The following property is not present or has a null value: "solar" -> "arecapexa_total" (' + item['capex'] + ')')
    
    # If no exception occurred, return the modified payload
    return payload


# Function: Validate the process output
def validateProcessOutput(result: dict) -> bool:
    """Funtion to validate the process output.

    Args:
        result (dict): The process result. Example::

           {
                "Apartment Block": DataFrame,
                "Single family- Terraced houses": DataFrame,
                "Offices",: DataFrame,
                "Education": DataFrame,
                "Health": DataFrame,
                "Trade": DataFrame,
                "Hotels and Restaurants": DataFrame,
                "Other non-residential buildings": DataFrame,
                "Sport": DataFrame
            }

    Returns:
        bool

    """

    # Check negative values in numeric columns
    numericColumns = result.select_dtypes(include='number')
    return (numericColumns < 0).any().any()
