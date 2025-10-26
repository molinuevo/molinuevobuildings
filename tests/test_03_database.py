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

import os

from building_stock_energy_model import constants


# Test -> Consolidated database
def test_consolidatedDatabase():
    '''
    Test -> The database is consolidated.
    Input parameters:
        None.
    '''

    # Reset the exceptions counter
    global exceptionsRaised
    exceptionsRaised = 0

    # Validate the database
    for filePath in constants.DATABASE:
        if not os.path.exists(filePath):
            exceptionsRaised += 1

    assert exceptionsRaised == 0
