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

import copy
import json
import re

from building_stock_energy_model import validator
from pathlib import Path


TEST_INPUT_PATH = str(Path(__file__).parent / 'input_test.json')
exceptionsRaised = 0


# Test -> Invalid payload
def test_invalidPayload():
    '''
    Test -> Invalid payload.
    Input parameters:
        None.
    '''

    # Reset the exceptions counter
    global exceptionsRaised
    exceptionsRaised = 0

    with open(TEST_INPUT_PATH, 'r') as payloadFile:
        # Load and iterate the payload
        processPayload = json.load(payloadFile)
        iteratePayload(processPayload,
                       True)

    assert exceptionsRaised > 0


# Test -> Wrong values in the payload
def test_wrongValuesPayload():
    '''
    Test -> Wrong values in the payload.
    Input parameters:
        None.
    '''

    # Reset the exceptions counter
    global exceptionsRaised
    exceptionsRaised = 0

    with open(TEST_INPUT_PATH, 'r') as payloadFile:
        # Load and iterate the payload
        processPayload = json.load(payloadFile)
        iteratePayload(processPayload,
                       False)

    assert exceptionsRaised > 0


# Test -> Valid payload
def test_validPayload():
    '''
    Test -> Valid payload.
    Input parameters:
        None.
    '''

    # Reset the exceptions counter
    global exceptionsRaised
    exceptionsRaised = 0

    # Load the payload file
    with open(TEST_INPUT_PATH, 'r') as payloadFile:
        processPayload = json.load(payloadFile)
        try:
            validator.validateProcessPayload(processPayload)
        except Exception as e:
            exceptionsRaised += 1

    assert exceptionsRaised == 0


#####################################################################
######################## Auxiliary functions ########################
#####################################################################


# Function: Iterate a payload recursively
def iteratePayload(payload: dict,
                   doRemove: bool,
                   prefix='',
                   payloadRoot=None):
    '''
    Function to iterate a payload recursively.
    Input parameters:
        payload: dict -> The current payload to iterate.
        doRemove: bool -> Indicates if a value has to be removed (True) or modified (False).
        prefix: str -> The property prefix.
        payloadRoot: dict -> The original payload.
    '''
    global exceptionsRaised

    # Assign once
    if payloadRoot is None:
        payloadRoot = payload

    if isinstance(payload, dict):
        for key, value in payload.items():
            fullKey = f"{prefix}.{key}" if prefix else key
            payloadCopy = copy.deepcopy(payloadRoot)
            if not isinstance(value, (dict, list)):
                try:
                    if doRemove:
                        deletePropertyByPath(payloadCopy,
                                             fullKey)
                    else:
                        newValue = - \
                            10000 if isinstance(value,
                                                (int, float)) else 'XXX'
                        setPropertyByPath(payloadCopy,
                                          fullKey,
                                          newValue)
                except Exception as e:
                    continue
                try:
                    validator.validateProcessPayload(payloadCopy)
                except Exception as e:
                    exceptionsRaised += 1
            iteratePayload(value,
                           doRemove,
                           prefix=fullKey,
                           payloadRoot=payloadRoot)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            iteratePayload(
                item,
                doRemove,
                prefix=f"{prefix}[{i}]",
                payloadRoot=payloadRoot)


# Function: Delete a property given its path
def deletePropertyByPath(payload: dict,
                         path: str):
    '''
    Function to delete a property given its path.
    Input parameters:
        payload: dict -> The original payload.
        path: str -> The source path.
    '''

    keys = parsePropertyFullPath(path)
    payloadCopy = payload
    for key in keys[:-1]:
        payloadCopy = payloadCopy[key]
    del payloadCopy[keys[-1]]


# Function: Change the value of a property given its path
def setPropertyByPath(payload: dict,
                      path: str,
                      value: str):
    '''
    Function to change the value of a property given its path.
    Input parameters:
        payload: dict -> The original payload.
        path: str -> The source path.
        value: str -> The new value to set.
    '''

    keys = parsePropertyFullPath(path)
    payloadCopy = payload
    for key in keys[:-1]:
        payloadCopy = payloadCopy[key]
    payloadCopy[keys[-1]] = value


# Function: Parse the full path of a property
def parsePropertyFullPath(path: str) -> list:
    '''
    Function to convert a path like 'a.b[2].c' in a path like ['a', 'b', 2, 'c'].
    Input parameters:
        path: str -> The source path.
    '''

    parts = []
    for part in path.split('.'):
        match = re.findall(r'([^\[\]]+)|\[(\d+)\]', part)
        for name, index in match:
            if name:
                parts.append(name)
            elif index:
                parts.append(int(index))
    return parts
