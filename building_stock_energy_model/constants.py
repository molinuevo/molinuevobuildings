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


VERSION = 'v0.10.0'
WINTER_TEMPERATURE = 12
SUMMER_TEMPERATURE = 22.5
COOLING_REDUCTION_FACTOR = 0.333
SAVE_RESULT_ALLOWED = False
LEVELS = ['High', 'Medium', 'Low']
CONVERT_COORD = False

DATABASE = ['database/01-ACH.csv',
            'database/02-BaseTemperatures.csv',
            'database/03-BES_Capacity.csv',
            'database/04-BES_CAPEX.csv',
            'database/05-BES_OPEX.csv',
            'database/06-DemandNinja_Radiation_DB.csv',
            'database/07-DemandNinja_Temperature_DB.csv',
            'database/08-DHW&InternalGains.csv',
            'database/09-DwellingSizeAndShare.csv',
            'database/13-R_T_hh_eff.xlsx',
            'database/14-RES.csv',
            'database/15-RES_hh_tes.xlsx',
            'database/16-RetrofittingCost.csv',
            'database/17-RetrofittingUValues.csv',
            'database/18-Schedule.csv',
            'database/19-SER_hh_tes.xlsx',
            'database/20-SolarGainsNONOffice(Wm2).csv',
            'database/21-SolarGainsOffice(Wm2).csv',
            'database/22-UValues.csv',
            'database/23-YearPeriods.csv',
            'database/24-Sectors.csv',
            'database/25-CategorizationShare.csv',
            'database/26-Season.csv',
            'database/27-Calendar.csv']

BUILDING_USES = ['Apartment Block',
                 'Single family- Terraced houses',
                 'Hotels and Restaurants',
                 'Health',
                 'Education',
                 'Offices',
                 'Trade',
                 'Other non-residential buildings',
                 'Sport']

REGIONS = 'ES21,ES41'
REGION_LIST = [region.strip() for region in REGIONS.split(',')]
