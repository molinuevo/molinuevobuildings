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

import json
import numpy as np
import pandas as pd

from pathlib import Path
from building_energy_process import executeBuildingEnergySimulationProcess


TEST_INPUT_PATH = str(Path(__file__).parent / 'input_test.json')
TEST_OUTPUT_PATH = str(Path(__file__).parent / 'output_test.csv')


# Test -> Final execution test for process
def test_finalExecutionForProcess():
    '''
    Test -> Final execution test for process, validating the output.
    Input parameters:
        None.
    '''

    exceptionsRaised = 0

    # Load the payload file
    with open(TEST_INPUT_PATH, 'r') as payloadFile:
        # Execute the process
        try:
            result = executeBuildingEnergySimulationProcess(json.load(payloadFile),
                                                            '2019-03-01T13:00:00',
                                                            '2019-03-02T13:00:00',
                                                            'Offices')
            result['Datetime'] = pd.to_datetime(result['Datetime'])

            dfResult = pd.DataFrame(result)
            with open(TEST_OUTPUT_PATH, 'r') as outputFile:
                dfTest = pd.read_csv(outputFile,
                                     header=0,
                                     encoding='ISO-8859-1',
                                     sep=',',
                                     decimal='.')
                dfTest['Datetime'] = pd.to_datetime(dfTest['Datetime'])

            # Compare both DataFrames
            scComparison = np.isclose(dfResult['Solids|Coal'],
                                      dfTest['Solids|Coal'])
            lgComparison = np.isclose(dfResult['Liquids|Gas'],
                                      dfTest['Liquids|Gas'])
            loComparison = np.isclose(dfResult['Liquids|Oil'],
                                      dfTest['Liquids|Oil'])
            ggComparison = np.isclose(result['Gases|Gas'],
                                      dfTest['Gases|Gas'])
            sbComparison = np.isclose(result['Solids|Biomass'],
                                      dfTest['Solids|Biomass'])
            eComparison = np.isclose(result['Electricity'],
                                     dfTest['Electricity'])
            heComparison = np.isclose(result['Heat'],
                                      dfTest['Heat'])
            lbComparison = np.isclose(result['Liquids|Biomass'],
                                      dfTest['Liquids|Biomass'])
            gbComparison = np.isclose(result['Gases|Biomass'],
                                      dfTest['Gases|Biomass'])
            hyComparison = np.isclose(result['Hydrogen'],
                                      dfTest['Hydrogen'])
            hsComparison = np.isclose(result['Heat|Solar'],
                                      dfTest['Heat|Solar'])
            heComparison = np.isclose(result['Heat'],
                                      dfTest['Heat'])
            total = scComparison & lgComparison & loComparison & \
                ggComparison & sbComparison & eComparison & \
                    heComparison & lbComparison & gbComparison \
                        & hyComparison & hsComparison
            if False in total:
                raise Exception()
        except:
            exceptionsRaised += 1

    assert exceptionsRaised == 0
