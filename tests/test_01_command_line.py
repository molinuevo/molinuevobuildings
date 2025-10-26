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

from building_stock_energy_model import validator
from pathlib import Path


TEST_INPUT_PATH = str(Path(__file__).parent / 'input_test.json')


# Test -> Missing command line parameters
def test_missingCommandLineParameters():
    '''
    Test -> Missing command line parameters.
    Input parameters:
        None.
    '''

    exceptionsRaised = 0

    # Wrong number of parameters
    try:
        parameters = [TEST_INPUT_PATH]
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The first parameter does not exist
    try:
        parameters = ['',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Apartment Block']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The second parameter does not exist
    try:
        parameters = ['building_energy_process.py',
                      '',
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Sport']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The third parameter does not exist
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '',
                      '2019-03-02T13:00:00',
                      'Trade']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The fourth parameter does not exist
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '',
                      'Education']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The fifth parameter does not exist
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      '']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The payload file, corresponding to the second parameter, does not exist
    try:
        parameters = ['building_energy_process.py',
                      'wrong_input.json',
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Sport']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The "start time" parameter has an invalid format
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01 13:00:00',
                      '2019-03-02T13:00:00',
                      'Sport']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The "end time" parameter has an invalid format
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '2019-03-02 13:00:00',
                      'Sport']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The "end time" parameter is less than the "start time" parameter
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-04-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Sport']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    # The "building use" parameter has an invalid value
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Test']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    assert exceptionsRaised > 0


# Test -> The command line parameters are OK
def test_commandLineParametersOK():
    '''
    Test -> The command line parameters are OK.
    Input parameters:
        None.
    '''

    exceptionsRaised = 0
    try:
        parameters = ['building_energy_process.py',
                      TEST_INPUT_PATH,
                      '2019-03-01T13:00:00',
                      '2019-03-02T13:00:00',
                      'Apartment Block']
        validator.validateCommandLineParameters(parameters)
    except Exception as e:
        exceptionsRaised += 1

    assert exceptionsRaised == 0
