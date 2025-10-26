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

import io
import json
import pandas as pd
import pvlib
import requests
import warnings

from building_stock_energy_model import constants
from calendar import isleap
from pathlib import Path
from pandas.errors import PerformanceWarning
from pyproj import Transformer

import openpyxl as op
from openpyxl.styles import Alignment, Color, Font, PatternFill


warnings.simplefilter(action='ignore', category=PerformanceWarning)


# Function: Build. Energy Sim. -> Model -> Step 01 : Load the previous result
def s01LoadPreviousResult(nutsId: str) -> tuple:
    """Model Step 01: Load the previous result.

    Args:
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
    
    Returns:
        tuple

    """

    #  Create the temporary directory
    print('Model: Step 01/>  Creating the temporary directory...')
    temporaryDirectory = Path(__file__).parent.parent / 'temporary'
    temporaryDirectory.mkdir(parents=True,
                             exist_ok=True)

    #  Load the result file of the Buildings preprocess
    print('Model: Step 01/>  Loading the result file of the Buildings preprocess...')
    csvPath = Path(__file__).parent.parent / \
        'usecases' / f'{nutsId.upper()}_preprocess.csv'
    dfPreprocess = pd.read_csv(csvPath,
                               sep=',',
                               decimal='.')

    #  Load the solar data
    print('Model: Step 01/>  Loading the solar data...')
    csvPath = Path(__file__).parent.parent / \
        'usecases' / f'{nutsId.upper()}_solar.csv'
    dfSolar = pd.read_csv(csvPath, sep=';',
                          decimal=',',
                          thousands='.')

    # Finish
    print('Model: Step 01/>  [OK]')
    return dfPreprocess, dfSolar


# Function: Build. Energy Sim. -> Model -> Step 02 -> Retrieve temperatures
def s02RetrieveTemperatures(nutsId: str,
                            year: int) -> pd.DataFrame:
    """Model Step 02: Retrieve temperatures.

    Args:
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
        year (int): The selected year.
    
    Returns:
        DataFrame

    """

    # Load the CSV from the database
    print('Model: Step 02/>  Retrieving temperatures...')
    csvPath = Path(__file__).parent.parent / 'database' / \
        '07-DemandNinja_Temperature_DB.csv'
    df = pd.read_csv(csvPath,
                     sep=';')

    # Filter for the row that contains the country code
    row = df[df['CNTR_CODE'] == nutsId[:2]]
    if row.empty:
        raise ValueError('Model: Step 02/>  ' + nutsId[:2] + ' not mapped!')

    print('Model: Step 02/>  Connecting and downloading...')
    response = requests.get(row['PopWgt'].values[0],
                            timeout=60)
    if response.status_code != 200:
        raise ValueError(
            'Model: Step 02/>  The temepratures data could not be downloaded!')

    print('Model: Step 02/>  Loading and filtering the downloaded data...')
    downloadedData = pd.read_csv(io.StringIO(
        response.text),
        comment='#',
        parse_dates=['time'],
        sep=',',
        engine='python')

    # Normalize to UTC native
    downloadedData['time'] = pd.to_datetime(downloadedData['time'],
                                            utc=True).dt.tz_convert(None)

    # Choose region column
    regionCode = nutsId[:4]
    if regionCode in downloadedData.columns:
        selectedRegion = regionCode
    elif regionCode[:3] in downloadedData.columns:
        selectedRegion = regionCode[:3]
    else:
        selectedRegion = nutsId[:2]

    # Determine the range of years available for the downloaded CSV file.
    yearsAvailable = downloadedData['time'].dt.year.unique()

    # Source year to use for calculating the target year
    srcYear = year if year <= int(
        yearsAvailable.max()) else int(yearsAvailable.max())

    # Filter hourly data from the source year
    src = downloadedData[downloadedData['time'].dt.year ==
                         srcYear][['time', selectedRegion]].copy()

    # Remove 29-Feb from the source if it exists.
    src = src.set_index('time')
    src = x03DropFeb29IfPresentForTemperaturesData(src)

    # Ensure numeric data type and clean up NaN values.
    src[selectedRegion] = pd.to_numeric(src[selectedRegion],
                                        errors='coerce')
    src = src.dropna(subset=[selectedRegion])

    # If the destination year is the same as the origin year, there is no remapping
    # If it is different, the dates are relabeled.
    if year != srcYear:
        # Remap
        new_index = x05RemapYear(src.index,
                                 year)
        src.index = new_index
        if isleap(year):
            src = x01AddFeb29IfMissingForTemperaturesData(src,
                                                          year)
    else:
        # If the target year is not a leap year, ensure that February 29th
        # does not exist (it was already removed above)
        # If it is a leap year and February 29th is missing,
        # it's possible to add it (optional)
        pass

    # Consistent time series data for the year "year" in the selected region column
    df = src.rename(columns={selectedRegion: 'HourlyTemperature'}).copy()

    # Daily calculations
    dailyMin = df.groupby([df.index.month, df.index.day])[
        'HourlyTemperature'].min()
    dailyMax = df.groupby([df.index.month, df.index.day])[
        'HourlyTemperature'].max()
    dailyAvgTemp = (dailyMin + dailyMax) / 2
    dailyAvgTemp.index = pd.date_range(start=f'{year}-01-01',
                                       end=f'{year + 1}-01-01',
                                       freq='D',
                                       inclusive='left')
    dailyAvgTemp = dailyAvgTemp.resample('h').ffill()

    # Mensual: (min+max)/2 por mes -> rellenado a horario
    monthlyMin = df.resample('ME').min()['HourlyTemperature']
    monthlyMax = df.resample('ME').max()['HourlyTemperature']
    monthlyAvgTemp = (monthlyMin + monthlyMax) / 2

    allDaysInYear = pd.date_range(start=f'{year}-01-01',
                                  end=f'{year + 1}-01-01',
                                  freq='D',
                                  inclusive='left')
    monthlyAvgTemp = monthlyAvgTemp.reindex(allDaysInYear,
                                            method='ffill').resample('h').ffill().bfill()

    # Add columns
    df.loc[:, 'DailyAvgTemp'] = dailyAvgTemp
    df.loc[:, 'MonthlyAvgTemp'] = monthlyAvgTemp

    # Fill this out in case there are any hours missing after 12/31
    lastDayFirstHour = pd.Timestamp(f'{year}-12-31 00:00:00')
    if lastDayFirstHour in dailyAvgTemp.index:
        firstHourValueDailyAvg = dailyAvgTemp.loc[lastDayFirstHour]
        firstHourValueMonthlyAvg = monthlyAvgTemp.loc[lastDayFirstHour]
        maskDaily = (df.index > lastDayFirstHour) & (df['DailyAvgTemp'].isna())
        maskMonthly = (df.index > lastDayFirstHour) & (
            df['MonthlyAvgTemp'].isna())
        df.loc[maskDaily, 'DailyAvgTemp'] = firstHourValueDailyAvg
        df.loc[maskMonthly, 'MonthlyAvgTemp'] = firstHourValueMonthlyAvg

    # Seasonal classification
    def season(temp):
        return 'W' if temp < constants.WINTER_TEMPERATURE else 'S' if temp > constants.SUMMER_TEMPERATURE else 'M'
    df['Season'] = df['MonthlyAvgTemp'].apply(season)

    # Save to the temporary directory
    print('Model: Step 02/>  Saving as CSV to a temporary directory...')
    csvPath = Path(__file__).parent.parent / \
        'temporary' / f'{nutsId[:4]}_Temperatures.csv'
    dfOut = df.copy()
    dfOut.index = dfOut.index.strftime('%m/%d/%Y %H:%M')
    dfOut.to_csv(csvPath,
                 sep=';',
                 decimal=',')

    # Finish
    print('Model: Step 02/>  [OK]')
    return dfOut


# Function: Build. Energy Sim. -> Model -> Step 03 -> Retrieve radiation values
def s03RetrieveRadiationValues(nutsId: str,
                               year: int) -> pd.DataFrame:
    """Model Step 03: Retrieve radiation values.

    Args:
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
        year (int): The selected year.
    
    Returns:
        DataFrame

    """

    # Load the CSV from the database
    print('Model: Step 03/>  Retrieving the radiation values...')
    csvPath = Path(__file__).parent.parent / 'database' / \
        '06-DemandNinja_Radiation_DB.csv'
    df = pd.read_csv(csvPath,
                     sep=';')

    # Filter for the row that contains the country code
    row = df[df['CNTR_CODE'] == nutsId[:2]]
    if row.empty:
        raise ValueError('Model: Step 03/> ' + nutsId[:2] + ' not mapped!')

    print('Model: Step 03/>  Connecting and downloading...')
    response = requests.get(row['PopWgt'].values[0])
    if response.status_code != 200:
        raise ValueError(
            'Model: Step 03/>  The radiation data could not be downloaded!')

    # Normalize the time column
    downloadedData = pd.read_csv(io.StringIO(
        response.text),
        comment='#',
        parse_dates=['time'],
        sep=',',
        engine='python')
    downloadedData['time'] = pd.to_datetime( downloadedData['time'],
                                            utc=True).dt.tz_convert(None)

    # Region column selection
    regionCode = nutsId[:4]
    if regionCode in downloadedData.columns:
        selectedRegion = regionCode
    elif regionCode[:3] in downloadedData.columns:
        selectedRegion = regionCode[:3]
    else:
        selectedRegion = nutsId[:2]

    # Detect available years range and establish the source year
    availableYears = downloadedData['time'].dt.year.unique()
    srcYear = year if year <= int(
        availableYears.max()) else int(availableYears.min())

    # Filter by source year
    src = downloadedData[downloadedData['time'].dt.year ==
                         srcYear][['time', selectedRegion]].copy()
    src = src.set_index('time')

    # Clean
    src[selectedRegion] = pd.to_numeric(src[selectedRegion],
                                        errors='coerce')
    src = src.dropna(subset=[selectedRegion])
    src = x04DropFeb29IfPresentForRadiationData(src)

    # Remap if the year is different than the source year
    if year != srcYear:
        src.index = x05RemapYear(src.index,
                                 year)
        if isleap(year):
            src = x02AddFeb29IfMissingForRadiationData(src,
                                                       year)

    # Rename the column to the original nuts code
    src = src.rename(columns={selectedRegion: nutsId})

    # Date format to export
    src.index = src.index.strftime('%m/%d/%Y %H:%M')

    # Save to the temporary directory
    print('Model: Step 03/>  Saving as CSV to the temporary directory...')
    csvPath = Path(__file__).parent.parent / \
        'temporary' / f'{selectedRegion}_Radiation.csv'
    src.to_csv(csvPath,
               sep=';',
               decimal=',')

    # Finish
    print('Model: Step 03/>  [OK]')
    return df


# Function: Build. Energy Sim. -> Model -> Step 04 -> Load the database
def s04LoadDatabase(nutsId: str,
                    hddReduction: float,
                    cddReduction: float)-> tuple:
    """Model Step 04: Load the database.

    Args:
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
        hddReduction (float): Reduction in heating degree days
            for future scenario.
        cddReduction (float): Reduction in cooling degree days
            for future scenarios.
    
    Returns:
        tuple

    """

    print('Model: Step 04/>  Loading the database...')
    filePath = Path(__file__).parent.parent / \
        'database' / '08-DHW&InternalGains.csv'
    dfDHW = pd.read_csv(filePath,
                        sep=';',
                        decimal=',',
                        thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / '23-YearPeriods.csv'
    dfYears = pd.read_csv(filePath,
                          sep=';')
    filePath = Path(__file__).parent.parent / 'database' / '24-Sectors.csv'
    dfSectors = pd.read_csv(filePath,
                            sep=';')
    filePath = Path(__file__).parent.parent / 'database' / '26-Season.csv'
    dfSeasons = pd.read_csv(filePath, sep=';',
                            decimal=',',
                            thousands='.')
    filePath = Path(__file__).parent.parent / 'temporary' / \
        f'{nutsId[:4]}_Temperatures.csv'
    dfTemperatures = pd.read_csv(filePath,
                                 sep=';',
                                 decimal=',',
                                 thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / '18-Schedule.csv'
    dfSchedule = pd.read_csv(filePath,
                             sep=';',
                             decimal=',',
                             thousands='.')
    filePath = Path(__file__).parent.parent / \
        'database' / '15-RES_hh_tes.xlsx'
    dfResHHTes = pd.read_excel(filePath)
    filePath = Path(__file__).parent.parent / \
        'database' / '19-SER_hh_tes.xlsx'
    dfSerHHTes = pd.read_excel(filePath)
    filePath = Path(__file__).parent.parent / 'database' / '22-UValues.csv'
    dfUvalues = pd.read_csv(filePath,
                            sep=';',
                            decimal=',',
                            thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / \
        '17-RetrofittingUValues.csv'
    dfRetroUvalues = pd.read_csv(filePath,
                                 sep=';',
                                 decimal=',',
                                 thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / '01-ACH.csv'
    dfACH = pd.read_csv(filePath,
                        sep=';',
                        decimal=',',
                        thousands='.')
    filePath = Path(__file__).parent.parent / \
        'database' / '02-BaseTemperatures.csv'
    dfBaseTemperatures = pd.read_csv(filePath,
                                     sep=';',
                                     decimal=',',
                                     thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / '27-Calendar.csv'
    dfCalendar = pd.read_csv(filePath,
                             sep=';',
                             decimal=',',
                             thousands='.')
    filePath = Path(__file__).parent.parent / 'database' / '04-BES_CAPEX.csv'
    dfBesCapex = pd.read_csv(filePath,
                             sep=';',
                             decimal=',',
                             thousands='.',
                             encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / '05-BES_OPEX.csv'
    dfBesOpex = pd.read_csv(filePath,
                            sep=';',
                            decimal=',',
                            thousands='.',
                            encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / '14-RES.csv'
    dfRes = pd.read_csv(filePath,
                        sep=';',
                        decimal=',',
                        thousands='.',
                        encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / \
        'database' / '03-BES_Capacity.csv'
    dfBesCapacity = pd.read_csv(filePath,
                                sep=';',
                                decimal=',',
                                thousands='.',
                                encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / \
        'database' / '16-RetrofittingCost.csv'
    dfRetroCost = pd.read_csv(filePath,
                              sep=';',
                              decimal=',',
                              thousands='.',
                              encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / \
        '21-SolarGainsOffice(Wm2).csv'
    dfSolarOffice = pd.read_csv(filePath, sep=';',
                                decimal=',',
                                thousands='.',
                                encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / \
        '20-SolarGainsNONOffice(Wm2).csv'
    dfSolarNoffice = pd.read_csv(filePath,
                                 sep=';',
                                 decimal=',',
                                 thousands='.',
                                 encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / \
        '09-DwellingSizeAndShare.csv'
    dfDwellings = pd.read_csv(filePath,
                              sep=';',
                              decimal=',',
                              thousands='.',
                              encoding='ISO-8859-1')
    filePath = Path(__file__).parent.parent / 'database' / '13-R_T_hh_eff.xlsx'
    dfRTHHEff = pd.read_excel(filePath)
    filePath = Path(__file__).parent.parent / 'database' / '28-Solar_parameter_buildings.json'
    with open(filePath, 'r', encoding='utf-8') as jsonFile:
        dictBuildings = json.load(jsonFile)

    # Build the HDH dataframe
    dfHDH = dfCalendar[['Datetime']].copy()
    dfHDH['HDH'] = None
    dfHDH['CDH'] = None
    for index, row in dfTemperatures.iterrows():
        values = [0, 0]
        if float(dfBaseTemperatures.at[0, 'Base Temperature']) - row.iloc[1] < 0:
            values[0] = 0
        elif row.iloc[2] < float(dfBaseTemperatures.at[0, 'ThresholdTemperture']):
            values[0] = float(
                dfBaseTemperatures.at[0, 'Base Temperature']) - row.iloc[1]
        else:
            values[0] = 0

        if row.iloc[1] - float(dfBaseTemperatures.at[1, 'Base Temperature']) < 0:
            values[1] = 0
        elif row.iloc[2] > float(dfBaseTemperatures.at[1, 'ThresholdTemperture']):
            values[1] = row.iloc[1] - \
                float(dfBaseTemperatures.at[1, 'Base Temperature'])
        else:
            values[1] = 0

        dfHDH.at[index, 'HDH'] = values[0] * (1 - hddReduction)
        dfHDH.at[index, 'CDH'] = values[1] * (1 - cddReduction)

    # Append the HDH dataframe to the Schedule dataframe
    dfHDHExtended = pd.DataFrame()
    ln = len(dfSchedule.groupby('Use'))
    for i in range(ln):
        dfHDHExtended = pd.concat([dfHDHExtended, dfHDH],
                                  ignore_index=True)
    dfSchedule[['HDH', 'CDH']] = dfHDHExtended[['HDH', 'CDH']]

    # Add to the Temperatures dataframe the Heating and Cooling factors
    dfTemperatures = dfTemperatures.merge(dfSeasons[['Season', 'Heating']],
                                          on='Season',
                                          how='left')
    dfTemperatures = dfTemperatures.merge(dfSeasons[['Season', 'Cooling']],
                                          on='Season',
                                          how='left')

    # Finish
    print('Model: Step 04/>  [OK]')
    return dfDHW, dfYears, dfSectors, dfSeasons, dfTemperatures, dfSchedule, dfResHHTes, \
        dfSerHHTes, dfUvalues, dfRetroUvalues, dfACH, dfBaseTemperatures, dfCalendar, \
        dfBesCapex, dfBesOpex, dfRes, dfBesCapacity, dfRetroCost, dfSolarOffice, \
        dfSolarNoffice, dfDwellings, dfRTHHEff, dictBuildings


# Function: Build. Energy Sim. -> Model -> Step 05 -> Retrieve solar data
def s05RetrieveSolarData(nutsId: str,
                         year: int,
                         listInputJsonSolar: list,
                         dictDBBuildings: dict):
    """Model Step 05: Retrieve radiation values.

    Args:
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
        year (int): The selected year.
        listInputJsonSolar(list): Data from the input.json file. Example::

            [
                {'building_use': 'Apartment Block', 'area_total': None, 'power': 195.826, 'capex': None},
                {'building_use': 'Single family- Terraced houses', ...},
                {'building_use': 'Offices', ...},
                {'building_use': 'Education', ...},
                {'building_use': 'Health', ...},
                {'building_use': 'Trade', ...},
                {'building_use': 'Hotels and Restaurants', ...},
                {'building_use': 'Other non-residential buildings', ...},
                {'building_use': 'Sport', ...}
            ]
        
        dictDBBuildings (dict): Data from the database file. Example::

            {
                'System': {'system_cost': 0.5, 'opex_pv': 15000, 'min_ghi_pv': 1000, 'land_use_pv': 100},
                'Apartment Block': {'tilt': 30, 'azimuth': 180, 'loss': 14, 'efficiency': 18,
                    'tracking_porcentage': 0, 'use_factor': 100, 'distribution': [0.6, 0.2, 0.2]},
                'Single family- Terraced houses': {...},
                'Hotels and Restaurants': {...},
                'Health': {...},
                'Education': {...},
                'Offices': {...},
                'Sport': {.},
                'Trade': {.},
                'Other non-residential buildings': {...},
            }
    
    Returns:
        DataFrame

    """


    # Load the necessary information
    print('Model: Step 05/>  Loading the solar data...')
    filePath = Path(__file__).parent.parent / 'usecases' / \
        (nutsId + '_solar.csv')
    dfSolar = pd.read_csv(filePath,
                          sep=',',
                          decimal='.',
                          encoding='ISO-8859-1')
    
    # Obtain the "System" configuration, and read the properties
    dictSystem = dictDBBuildings['System']
    systemCost = x06EstablishValue(dictSystem,
                                   'system_cost',
                                   0.2,
                                   1,
                                   0.5)
    opexPV = x06EstablishValue(dictSystem,
                               'opex_pv',
                               0,
                               3.0e+04,
                               1.5e+03)
    minGHIPV = x06EstablishValue(dictSystem,
                                 'min_ghi_pv',
                                 500,
                                 2.0e+03,
                                 1.0e+03)
    landUsePV = x06EstablishValue(dictSystem,
                                  'land_use_pv',
                                  50,
                                  200,
                                  100)

    # Create dataframes for later, and the output dictionary
    prodAgreggated = pd.DataFrame()
    nuts2Distrib = pd.DataFrame()
    output = []
    
    # Separate by archetypes
    for archetype in constants.BUILDING_USES:
        dfSolarArch = dfSolar[dfSolar['Building_Use'] == archetype]
        for element in listInputJsonSolar:
            if element['building_use'] == archetype:
                # Merge with de information loaded from the database
                dictArchetype = element
                dictArchetype.update(dictDBBuildings[archetype])
                break
        
        dictScada = dfSolarArch.sort_values(by='Median_Radiation',
                                            ascending=False)
        
        areaAvailable = x06EstablishValue(dictArchetype,
                                          'area_total',
                                          0,
                                          10**10,
                                          0) if 'area_total' in dictArchetype else None
        power = x06EstablishValue(dictArchetype,
                                  'power',
                                  0,
                                  10**10,
                                  0) if 'power' in dictArchetype else None
        capex = x06EstablishValue(dictArchetype,
                                  'capex',
                                  0,
                                  10**10,
                                  0) if 'capex' in dictArchetype else None
        if areaAvailable is None and power is None and capex is None:
            areaAvailable = 0
            power = None
            capex = None
        
        loss = x06EstablishValue(dictArchetype,
                                 'loss',
                                 0,
                                 20,
                                 14)
        tracking = x06EstablishValue(dictArchetype,
                                     'tracking_porcentage',
                                     0,
                                     2,
                                     0)
        tilt = x06EstablishValue(dictArchetype,
                                 'tilt',
                                 0,
                                 90,
                                 30)
        azimuth = x06EstablishValue(dictArchetype,
                                    'azimuth',
                                    0,
                                    180,
                                    180)
        if 'distribution' in dictArchetype:
            distributionResidential = dictArchetype['distribution']
            if distributionResidential:
                distribAzimuth = [180, 90, 270]
                porcent = distributionResidential
                if len(porcent) != len(distribAzimuth) or sum(porcent) != 1:
                    porcent = [0.6, 0.2, 0.2]
            else:
                distribAzimuth = [azimuth]
                porcent = [1]
        else:
            distribAzimuth = [180, 90, 270]
            porcent = [0.6, 0.2, 0.2]

        # Obtain the available area
        listParameters = [areaAvailable, power, capex]
        print('Model: Step 05/>  Obtaining the available area for "' + archetype + '"...')
        areaAvailable, power, capex = x07GetAvailableArea(parameters=listParameters,
                                                          cost=systemCost,
                                                          landUse=landUsePV)
        if areaAvailable > 0:
            # Obtain the regions
            rows, name_nuts2 = x08GetRegions(dictScada=dictScada,
                                             area=areaAvailable,
                                             minGhi=minGHIPV)

            # Obtain the PV production
            print('Model: Step 05/>  Obtaining the PV production for "' + archetype + '"...')
            productionTracking = x09GetPVProduction(rows=rows,
                                                    landUse=landUsePV,
                                                    tilt=tilt,
                                                    distribAzimuth=distribAzimuth,
                                                    tracking=1,
                                                    loss=loss,
                                                    porcent=porcent,
                                                    year=year)
            productionFixed = x09GetPVProduction(rows=rows,
                                                 landUse=landUsePV,
                                                 tilt=tilt,
                                                 distribAzimuth=distribAzimuth,
                                                 tracking=0,
                                                 loss=loss,
                                                 porcent=porcent,
                                                 year=year)
            production = list(
                map(sum, zip(map(lambda x: x * tracking, productionTracking),
                             map(lambda x: x * (1 - tracking), productionFixed))))
            prodAgreggated[archetype] = pd.DataFrame(production).sum(axis=0)
            nuts2, potDistrib, areasDistrib = x10GetDistribution(rows=rows,
                                                                 label='production')

    # Save results in temporary directory
    prodAgreggated.index=pd.to_datetime(prodAgreggated.index).round('h').strftime('%d/%m/%Y %H:%M')
    csvPath = Path(__file__).parent.parent / \
        'temporary' / f'{nutsId.upper()}_solar_results.csv'
    prodAgreggated.to_csv(csvPath,
                          sep=';',
                          decimal=',')

    # Finish
    print('Model: Step 05/>  [OK]')
    return prodAgreggated


# Function: Build. Energy Sim. -> Model -> Step 06 -> Add columns to the main DataFrame
def s06AddColumnsToMainDataFrame(dfCSV: pd.DataFrame) -> pd.DataFrame:
    """Model Step 06: Add columns to the main dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
    
    Returns:
        DataFrame

    """

    print('Model: Step 06/>  Adding new columns to the input dataframe...')
    dfCSV = pd.concat([dfCSV,
                       pd.DataFrame(columns=['Opaque fachade area',
                                             'Window Area', 'Period', 'Net heated floor area', 'Heated Volume', 'Wall to floor ratio', 'Sector',
                                             'Ref Level', 'Ref%', 'Solar thermal', 'Roof [W/m2K]', 'Wall [W/m2K]', 'Window [W/m2K]',
                                             'Equipment internal gains [W/m2]', 'Occupancy internal gains [W/m2]', 'Lighting power [W/m2]',
                                             'DHW demand [KW/m2·year]', 'Cooking [KW/m2·year]', 'Air renovation losses',
                                             'Space heating', 'SH. Solids', 'SH. LPG', 'SH. Diesel oil', 'SH. Gas heat pumps', 'SH. Natural gas', 'SH. Biomass',
                                             'SH. Geothermal', 'SH. Distributed heat', 'SH. Advanced electric heating', 'SH. Conventional electric heating',
                                             'SH. BioOil', 'SH. BioGas', 'SH. Hydrogen', 'SH. Solar', 'SH. Electricity in circulation',
                                             'SH. Electric space cooling', 'SH. Electricity',
                                             'Space cooling', 'SC. Solids', 'SC. LPG', 'SC. Diesel oil', 'SC. Gas heat pumps', 'SC. Natural gas', 'SC. Biomass',
                                             'SC. Geothermal', 'SC. Distributed heat', 'SC. Advanced electric heating', 'SC. Conventional electric heating',
                                             'SC. BioOil', 'SC. BioGas', 'SC. Hydrogen', 'SC. Solar', 'SC. Electricity in circulation',
                                             'SC. Electric space cooling', 'SC. Electricity',
                                             'Water heating', 'WH. Solids', 'WH. LPG', 'WH. Diesel oil', 'WH. Gas heat pumps', 'WH. Natural gas', 'WH. Biomass',
                                             'WH. Geothermal', 'WH. Distributed heat', 'WH. Advanced electric heating', 'WH. Conventional electric heating',
                                             'WH. BioOil', 'WH. BioGas', 'WH. Hydrogen', 'WH. Solar', 'WH. Electricity in circulation',
                                             'WH. Electric space cooling', 'WH. Electricity',
                                             'Cooking', 'C. Solids', 'C. LPG', 'C. Diesel oil', 'C. Gas heat pumps', 'C. Natural gas', 'C. Biomass',
                                             'C. Geothermal', 'C. Distributed heat', 'C. Advanced electric heating', 'C. Conventional electric heating',
                                             'C. BioOil', 'C. BioGas', 'C. Hydrogen', 'C. Solar', 'C. Electricity in circulation',
                                             'C. Electric space cooling', 'C. Electricity',
                                             'Lighting', 'L. Solids', 'L. LPG', 'L. Diesel oil', 'L. Gas heat pumps', 'L. Natural gas', 'L. Biomass',
                                             'L. Geothermal', 'L. Distributed heat', 'L. Advanced electric heating', 'L. Conventional electric heating',
                                             'L. BioOil', 'L. BioGas', 'L. Hydrogen', 'L. Solar', 'L. Electricity in circulation',
                                             'L. Electric space cooling', 'L. Electricity',
                                             'Appliances', 'A. Solids', 'A. LPG', 'A. Diesel oil', 'A. Gas heat pumps', 'A. Natural gas', 'A. Biomass',
                                             'A. Geothermal', 'A. Distributed heat', 'A. Advanced electric heating', 'A. Conventional electric heating',
                                             'A. BioOil', 'A. BioGas', 'A. Hydrogen', 'A. Solar', 'A. Electricity in circulation',
                                             'A. Electric space cooling', 'A. Electricity',
                                             'Space heating base', 'SH. Solids base', 'SH. LPG base', 'SH. Diesel oil base', 'SH. Gas heat pumps base',
                                             'SH. Natural gas base', 'SH. Biomass base', 'SH. Geothermal base', 'SH. Distributed heat base',
                                             'SH. Advanced electric heating base', 'SH. Conventional electric heating base', 'SH. BioOil base', 'SH. BioGas base',
                                             'SH. Hydrogen base', 'SH. Solar base', 'SH. Electricity in circulation base', 'SH. Electric space cooling base',
                                             'SH. Electricity base',
                                             'Space cooling base', 'SC. Solids base', 'SC. LPG base', 'SC. Diesel oil base', 'SC. Gas heat pumps base',
                                             'SC. Natural gas base', 'SC. Biomass base', 'SC. Geothermal base', 'SC. Distributed heat base',
                                             'SC. Advanced electric heating base', 'SC. Conventional electric heating base', 'SC. BioOil base', 'SC. BioGas base',
                                             'SC. Hydrogen base', 'SC. Solar base', 'SC. Electricity in circulation base', 'SC. Electric space cooling base',
                                             'SC. Electricity base',
                                             'Water heating base', 'WH. Solids base', 'WH. LPG base', 'WH. Diesel oil base', 'WH. Gas heat pumps base',
                                             'WH. Natural gas base', 'WH. Biomass base', 'WH. Geothermal base', 'WH. Distributed heat base',
                                             'WH. Advanced electric heating base', 'WH. Conventional electric heating base', 'WH. BioOil base', 'WH. BioGas base',
                                             'WH. Hydrogen base', 'WH. Solar base', 'WH. Electricity in circulation base', 'WH. Electric space cooling base',
                                             'WH. Electricity base',
                                             'Cooking base', 'C. Solids base', 'C. LPG base', 'C. Diesel oil base', 'C. Gas heat pumps base', 'C. Natural gas base',
                                             'C. Biomass base', 'C. Geothermal base', 'C. Distributed heat base', 'C. Advanced electric heating base',
                                             'C. Conventional electric heating base', 'C. BioOil base', 'C. BioGas base', 'C. Hydrogen base', 'C. Solar base',
                                             'C. Electricity in circulation base', 'C. Electric space cooling base', 'C. Electricity base',
                                             'Lighting base', 'L. Solids base', 'L. LPG base', 'L. Diesel oil base', 'L. Gas heat pumps base', 'L. Natural gas base',
                                             'L. Biomass base', 'L. Geothermal base', 'L. Distributed heat base', 'L. Advanced electric heating base',
                                             'L. Conventional electric heating base', 'L. BioOil base', 'L. BioGas base', 'L. Hydrogen base', 'L. Solar base',
                                             'L. Electricity in circulation base', 'L. Electric space cooling base', 'L. Electricity base',
                                             'Appliances base', 'A. Solids base', 'A. LPG base', 'A. Diesel oil base', 'A. Gas heat pumps base', 'A. Natural gas base',
                                             'A. Biomass base', 'A. Geothermal base', 'A. Distributed heat base', 'A. Advanced electric heating base',
                                             'A. Conventional electric heating base', 'A. BioOil base', 'A. BioGas base', 'A. Hydrogen base', 'A. Solar base',
                                             'A. Electricity in circulation base', 'A. Electric space cooling base', 'A. Electricity base',
                                             'SH. Cost Solids', 'SH. Cost LPG', 'SH. Cost Diesel oil', 'SH. Cost Gas heat pumps', 'SH. Cost Natural gas',
                                             'SH. Cost Biomass', 'SH. Cost Geothermal', 'SH. Cost Distributed heat', 'SH. Cost Advanced electric heating',
                                             'SH. Cost Conventional electric heating', 'SH. Cost BioOil', 'SH. Cost BioGas', 'SH. Cost Hydrogen', 'SH. Cost Solar',
                                             'SH. Cost Electric space cooling', 'SH. Cost Electricity',
                                             'SC. Cost Solids', 'SC. Cost LPG', 'SC. Cost Diesel oil', 'SC. Cost Gas heat pumps', 'SC. Cost Natural gas',
                                             'SC. Cost Biomass', 'SC. Cost Geothermal', 'SC. Cost Distributed heat', 'SC. Cost Advanced electric heating',
                                             'SC. Cost Conventional electric heating', 'SC. Cost BioOil', 'SC. Cost BioGas', 'SC. Cost Hydrogen', 'SC. Cost Solar',
                                             'SC. Cost Electric space cooling', 'SC. Cost Electricity',
                                             'WH. Cost Solids', 'WH. Cost LPG', 'WH. Cost Diesel oil', 'WH. Cost Gas heat pumps', 'WH. Cost Natural gas',
                                             'WH. Cost Biomass', 'WH. Cost Geothermal', 'WH. Cost Distributed heat', 'WH. Cost Advanced electric heating',
                                             'WH. Cost Conventional electric heating', 'WH. Cost BioOil', 'WH. Cost BioGas', 'WH. Cost Hydrogen', 'WH. Cost Solar',
                                             'WH. Cost Electric space cooling', 'WH. Cost Electricity',
                                             'Eff. SH', 'Eff. SH. Solids', 'Eff. SH. LPG', 'Eff. SH. Diesel oil', 'Eff. SH. Gas heat pumps', 'Eff. SH. Natural gas',
                                             'Eff. SH. Biomass', 'Eff. SH. Geothermal', 'Eff. SH. Distributed heat', 'Eff. SH. Advanced electric heating',
                                             'Eff. SH. Conventional electric heating', 'Eff. SH. BioOil', 'Eff. SH. BioGas', 'Eff. SH. Hydrogen', 'Eff. EIC',
                                             'Eff. SC', 'Eff. SC. Gas heat pumps', 'Eff. SC. Electric space cooling',
                                             'Eff. WH', 'Eff. WH. Solids', 'Eff. WH. LPG', 'Eff. WH. Diesel oil', 'Eff. WH. Natural gas', 'Eff. WH. Biomass',
                                             'Eff. WH. Geothermal', 'Eff. WH. Distributed heat', 'Eff. WH. Advanced electric heating', 'Eff. WH. Electricity',
                                             'Eff. WH. BioOil', 'Eff. WH. BioGas', 'Eff. WH. Hydrogen', 'Eff. WH. Solar',
                                             'Eff. C', 'Eff. C. Solids', 'Eff. C. LPG', 'Eff. C. Natural gas', 'Eff. C. Biomass', 'Eff. C. Electricity',
                                             'Eff. L', 'Eff. L. Electricity',
                                             'Eff. A', 'Eff. A. Electricity',
                                             'CAPEX SH. Solids', 'CAPEX SH. LPG', 'CAPEX SH. Diesel oil', 'CAPEX SH. Gas heat pumps', 'CAPEX SH. Natural gas',
                                             'CAPEX SH. Biomass', 'CAPEX SH. Geothermal', 'CAPEX SH. Distributed heat', 'CAPEX SH. Advanced electric heating',
                                             'CAPEX SH. Conventional electric heating', 'CAPEX SH. BioOil', 'CAPEX SH. BioGas', 'CAPEX SH. Hydrogen',
                                             'CAPEX SH. Electric space cooling', 'CAPEX SH. Electricity', 'CAPEX SH. Solar',
                                             'CAPEX SC. Solids', 'CAPEX SC. LPG', 'CAPEX SC. Diesel oil', 'CAPEX SC. Gas heat pumps', 'CAPEX SC. Natural gas',
                                             'CAPEX SC. Biomass', 'CAPEX SC. Geothermal', 'CAPEX SC. Distributed heat', 'CAPEX SC. Advanced electric heating',
                                             'CAPEX SC. Conventional electric heating', 'CAPEX SC. BioOil', 'CAPEX SC. BioGas', 'CAPEX SC. Hydrogen',
                                             'CAPEX SC. Electric space cooling', 'CAPEX SC. Electricity', 'CAPEX SC. Solar',
                                             'CAPEX WH. Solids', 'CAPEX WH. LPG', 'CAPEX WH. Diesel oil', 'CAPEX WH. Gas heat pumps', 'CAPEX WH. Natural gas',
                                             'CAPEX WH. Biomass', 'CAPEX WH. Geothermal', 'CAPEX WH. Distributed heat', 'CAPEX WH. Advanced electric heating',
                                             'CAPEX WH. Conventional electric heating', 'CAPEX WH. BioOil', 'CAPEX WH. BioGas', 'CAPEX WH. Hydrogen',
                                             'CAPEX WH. Electric space cooling', 'CAPEX WH. Electricity', 'CAPEX WH. Solar',
                                             'CAPEX C. Solids', 'CAPEX C. LPG', 'CAPEX C. Diesel oil', 'CAPEX C. Gas heat pumps', 'CAPEX C. Natural gas',
                                             'CAPEX C. Biomass', 'CAPEX C. Geothermal', 'CAPEX C. Distributed heat', 'CAPEX C. Advanced electric heating',
                                             'CAPEX C. Conventional electric heating', 'CAPEX C. BioOil', 'CAPEX C. BioGas', 'CAPEX C. Hydrogen',
                                             'CAPEX C. Electric space cooling', 'CAPEX C. Electricity', 'CAPEX C. Solar',
                                             'CAPEX L. Solids', 'CAPEX L. LPG', 'CAPEX L. Diesel oil', 'CAPEX L. Gas heat pumps', 'CAPEX L. Natural gas',
                                             'CAPEX L. Biomass', 'CAPEX L. Geothermal', 'CAPEX L. Distributed heat', 'CAPEX L. Advanced electric heating',
                                             'CAPEX L. Conventional electric heating', 'CAPEX L. BioOil', 'CAPEX L. BioGas', 'CAPEX L. Hydrogen',
                                             'CAPEX L. Electric space cooling', 'CAPEX L. Electricity', 'CAPEX L. Solar',
                                             'CAPEX A. Solids', 'CAPEX A. LPG', 'CAPEX A. Diesel oil', 'CAPEX A. Gas heat pumps', 'CAPEX A. Natural gas',
                                             'CAPEX A. Biomass', 'CAPEX A. Geothermal', 'CAPEX A. Distributed heat', 'CAPEX A. Advanced electric heating',
                                             'CAPEX A. Conventional electric heating', 'CAPEX A. BioOil', 'CAPEX A. BioGas', 'CAPEX A. Hydrogen',
                                             'CAPEX A. Electric space cooling', 'CAPEX A. Electricity', 'CAPEX A. Solar',
                                             'OPEX Fixed cost Solids|Coal', 'OPEX Fixed cost Liquids|Gas', 'OPEX Fixed cost Liquids|Oil', 'OPEX Fixed cost Gases|Gas',
                                             'OPEX Fixed cost Solids|Biomass', 'OPEX Fixed cost Electricity', 'OPEX Fixed cost Heat', 'OPEX Fixed cost Liquids|Biomass',
                                             'OPEX Fixed cost Gases|Biomass', 'OPEX Fixed cost Hydrogen', 'OPEX Fixed cost Heat|Solar',
                                             'OPEX Variable cost Solids|Coal', 'OPEX Variable cost Liquids|Gas', 'OPEX Variable cost Liquids|Oil',
                                             'OPEX Variable cost Gases|Gas', 'OPEX Variable cost Solids|Biomass', 'OPEX Variable cost Electricity',
                                             'OPEX Variable cost Heat', 'OPEX Variable cost Liquids|Biomass', 'OPEX Variable cost Gases|Biomass',
                                             'OPEX Variable cost Hydrogen', 'OPEX Variable cost Heat|Solar',
                                             'OPEX Emissions Solids|Coal', 'OPEX Emissions Liquids|Gas', 'OPEX Emissions Liquids|Oil', 'OPEX Emissions Gases|Gas',
                                             'OPEX Emissions Solids|Biomass', 'OPEX Emissions Electricity', 'OPEX Emissions Heat', 'OPEX Emissions Liquids|Biomass',
                                             'OPEX Emissions Gases|Biomass', 'OPEX Emissions Hydrogen', 'OPEX Emissions Heat|Solar',
                                             'RFC Cost Low Wall', 'RFC Cost Medium Wall', 'RFC Cost High Wall',
                                             'RFC Cost Low Roof', 'RFC Cost Medium Roof', 'RFC Cost High Roof',
                                             'RFC Cost Low Window', 'RFC Cost Medium Window', 'RFC Cost High Window',
                                             'RES ST. Cost', 'RES ST. Impact', 'RES ST. Lifetime', 'RES ST. Efficiency', 'RES ST. N0', 'RES ST. K1',
                                             'RES ST. K2', 'RES ST. NS',
                                             'RES SP. Cost', 'RES SP. Impact', 'RES SP. Lifetime', 'RES SP. Efficiency', 'RES SP. N0', 'RES SP. K1',
                                             'RES SP. K2', 'RES SP. NS',
                                             'Central HP (SH)', 'Central Boiler (SH)', 'Individual Boiler (24KW) (SH)', 'Individual HP 8KW (SH)', 'HP (SC)',
                                             'Central HP (WH)', 'Central Boiler (WH)', 'Individual Boiler (24KW) (WH)', 'Individual HP 8KW (WH)',
                                             'Share Individual', 'Avg. Dwelling Size', 'AVG SFH Size', 'Occ. Dwellings',
                                             'EP. Solids (SH)', 'EP. LPG (SH)', 'EP. Diesel oil (SH)', 'EP. Gas heat pumps (SH)', 'EP. Natural gas (SH)',
                                             'EP. Biomass (SH)', 'EP. Geothermal (SH)', 'EP. Distributed heat (SH)', 'EP. Advanced electric heating (SH)',
                                             'EP. Conventional electric heating (SH)', 'EP. BioOil (SH)', 'EP. BioGas (SH)', 'EP. Hydrogen (SH)',
                                             'EP. Solar (SH)', 'EP. Electric space cooling (SH)', 'EP. Electricity (SH)',
                                             'EP. Solids (SC)', 'EP. LPG (SC)', 'EP. Diesel oil (SC)', 'EP. Gas heat pumps (SC)', 'EP. Natural gas (SC)',
                                             'EP. Biomass (SC)', 'EP. Geothermal (SC)', 'EP. Distributed heat (SC)', 'EP. Advanced electric heating (SC)',
                                             'EP. Conventional electric heating (SC)', 'EP. BioOil (SC)', 'EP. BioGas (SH)', 'EP. Hydrogen (SC)',
                                             'EP. Solar (SC)', 'EP. Electric space cooling (SC)', 'EP. Electricity (SC)',
                                             'EP. Solids (WH)', 'EP. LPG (WH)', 'EP. Diesel oil (WH)', 'EP. Gas heat pumps (WH)', 'EP. Natural gas (WH)',
                                             'EP. Biomass (WH)', 'EP. Geothermal (WH)', 'EP. Distributed heat (WH)', 'EP. Advanced electric heating (WH)',
                                             'EP. Conventional electric heating (WH)', 'EP. BioOil (WH)', 'EP. BioGas (WH)', 'EP. Hydrogen (WH)',
                                             'EP. Solar (WH)', 'EP. Electric space cooling (WH)', 'EP. Electricity (WHSH)'])],
                      axis=1)

    # Finish
    print('Model: Step 06/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 07 -> Add the input data to the main DataFrame
def s07AddInputDataToMainDataframe(dfCSV: pd.DataFrame,
                                   dfDHW: pd.DataFrame,
                                   dfYears: pd.DataFrame,
                                   dfSectors: pd.DataFrame,
                                   dfDwellings: pd.DataFrame,
                                   nutsId: str,
                                   increaseResidentialBuiltArea: float,
                                   increaseServiceBuiltArea: float) -> pd.DataFrame:
    """Model Step 07: Add the input data to the main DataFrame.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfDHW: (DataFrame): The DataFrame corresponding to DHW.
        dfYears (DataFrame): The DataFrame corresponding to Years.
        dfSectors (DataFrame): The DataFrame corresponding to Sectors.
        dfDwellings (DataFrame): The DataFrame corresponding to Dwellings.
        nutsId (str): Identifier of NUTS2 region for which the analysis
            will be carried out.
        increaseResidentialBuiltArea (float): Reduction in heating degree
            days for future scenario.
        increaseServiceBuiltArea (float): Reduction in cooling degree days
            for future scenarios.
    
    Returns:
        DataFrame

    """

    print('Model: Step 07/>  Updating the dataframe information...')
    for index, row in dfCSV.iterrows():
        value = float(dfDHW[dfDHW['BuildingUse'] == row['Use']]['WWR'].iloc[0])
        dfCSV.at[index, 'Window Area'] = float(
            row['Total External Facade area']) * value
        dfCSV.at[index, 'Opaque fachade area'] = float(
            row['Total External Facade area']) - (float(row['Total External Facade area']) * value)
        dfCSV.at[index, 'Period'] = dfYears[dfYears['Year']
                                            == row['Age']]['Period'].iloc[0]
        value = float(dfDHW[dfDHW['BuildingUse'] ==
                      row['Use']]['GtH ratio'].iloc[0])
        dfCSV.at[index, 'Net heated floor area'] = float(
            row['Gross floor area']) / value
        dfCSV.at[index, 'Heated Volume'] = ((float(
            row['Gross floor area']) / value) / float(row['Number of floors'])) * float(row['Height'])
        dfCSV.at[index, 'Wall to floor ratio'] = float(
            row['Total External Facade area']) / float(row['Gross floor area'])
        value = dfSectors[dfSectors['Use'] == row['Use']]['Sector'].iloc[0]
        dfCSV.at[index, 'Sector'] = value

    if increaseResidentialBuiltArea > 0 or increaseServiceBuiltArea > 0:
        gfaResTotal, gfaSrvTotal, gfaRes2020, gfaSrv2020 = 0, 0, 0, 0
        for index, row in dfCSV.iterrows():
            if row['Sector'] == 'Residential':
                gfaResTotal += float(row['Gross floor area'])
                if row['Period'] == 'Post-2010':
                    gfaRes2020 += float(row['Gross floor area'])
            elif row['Sector'] == 'Service':
                gfaSrvTotal += float(row['Gross floor area'])
                if row['Period'] == 'Post-2010':
                    gfaSrv2020 += float(row['Gross floor area'])

        for index, row in dfCSV.iterrows():
            if row['Period'] == 'Post-2010':
                if increaseResidentialBuiltArea > 0 and row['Sector'] == 'Residential':
                    gfa = row['Gross floor area'] / gfaRes2020 * \
                        gfaResTotal * increaseResidentialBuiltArea
                    dfCSV.at[index, 'Gross floor area'] += gfa
                    dfCSV.at[index,
                             'Footprint Area'] += (gfa / row['Number of floors'])
                    dfCSV.at[index,
                             'Volume'] += ((gfa / row['Number of floors']) * row['Height'])
                    dfCSV.at[index, 'Total External Facade area'] += (
                        gfa * row['Wall to floor ratio'])
                    value = (gfa * row['Wall to floor ratio']) * float(
                        dfDHW[dfDHW['BuildingUse'] == row['Use']]['WWR'].iloc[0])
                    dfCSV.at[index, 'Window Area'] += value
                    dfCSV.at[index, 'Opaque fachade area'] += (
                        (gfa * row['Wall to floor ratio']) - value)
                    value = gfa / \
                        float(dfDHW[dfDHW['BuildingUse'] ==
                              row['Use']]['GtH ratio'].iloc[0])
                    dfCSV.at[index, 'Net heated floor area'] += value
                    dfCSV.at[index, 'Heated Volume'] += (
                        (value / row['Number of floors']) * row['Height'])
                if increaseServiceBuiltArea > 0 and row['Sector'] == 'Service':
                    gfa = row['Gross floor area'] / gfaSrv2020 * \
                        gfaSrvTotal * increaseServiceBuiltArea
                    dfCSV.at[index, 'Gross floor area'] += gfa
                    dfCSV.at[index,
                             'Footprint Area'] += (gfa / row['Number of floors'])
                    dfCSV.at[index,
                             'Volume'] += ((gfa / row['Number of floors']) * row['Height'])
                    dfCSV.at[index, 'Total External Facade area'] += (
                        gfa * row['Wall to floor ratio'])
                    value = (gfa * row['Wall to floor ratio']) * float(
                        dfDHW[dfDHW['BuildingUse'] == row['Use']]['WWR'].iloc[0])
                    dfCSV.at[index, 'Window Area'] += value
                    dfCSV.at[index, 'Opaque fachade area'] += (
                        (gfa * row['Wall to floor ratio']) - value)
                    value = gfa / \
                        float(dfDHW[dfDHW['BuildingUse'] ==
                              row['Use']]['GtH ratio'].iloc[0])
                    dfCSV.at[index, 'Net heated floor area'] += value
                    dfCSV.at[index, 'Heated Volume'] += (
                        (value / row['Number of floors']) * row['Height'])

    dfCSV['Share Individual'] = dfDwellings[dfDwellings['CountryID']
                                            == nutsId[:2].upper()].values[0][1]
    dfCSV['Avg. Dwelling Size'] = dfDwellings[dfDwellings['CountryID']
                                              == nutsId[:2].upper()].values[0][2]
    dfCSV['AVG SFH Size'] = dfDwellings[dfDwellings['CountryID']
                                        == nutsId[:2].upper()].values[0][3]
    dfCSV['Occ. Dwellings'] = dfDwellings[dfDwellings['CountryID']
                                          == nutsId[:2].upper()].values[0][4]

    # Finish
    print('Model: Step 07/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 08 -> Add the active measures
def s08AddActiveMeasures(dfCSV: pd.DataFrame,
                         dfReshhtes: pd.DataFrame,
                         dfSerhhtes: pd.DataFrame,
                         dfRThheff: pd.DataFrame,
                         nutsId: str,
                         activeMeasures: list,
                         activeMeasuresBaseline: list,
                         archetypes: list) -> pd.DataFrame:
    """Model Step 08: Add the active measures.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfReshhtes (DataFrame): The DataFrame corresponding to Residential.
        dfSerhhtes (DataFrame): The DataFrame corresponding to Service.
        dfRThheff (DataFrame): The DataFrame corresponding to RT.
        nutsId: str -> Identifier of NUTS2 region for which the
            analysis will be carried out.
        activeMeasures (list): The list of active measures::
            
            Example: see "input.json" file in the root directory.
        
        activeMeasuresBaseline (list): The list of active measures corresponding to the baseline::

            Example: see "input.json" file in the root directory.
        
        archetypes (list): The list of building uses. Example::

            "[
                "Apartment Block",
                "Single family- Terraced houses",
                "Hotels and Restaurants",
                "Health",
                "Education",
                "Offices",
                "Trade",
                "Other non-residential buildings",
                "Sport"
            ]"
    
    Returns:
        DataFrame

    """
            

    dfReshhtes = dfReshhtes[['Energy service_Fuel',
                             'Energy service', nutsId[:2].upper()]]
    dfSerhhtes = dfSerhhtes[['Energy service_Fuel',
                             'Energy service', nutsId[:2].upper()]]
    dfRThheff = dfRThheff[['Energy service_Fuel',
                           'Energy service', nutsId[:2].upper()]]

    print('Model: Step 08/>  Writing the Active measures...')
    for measure in activeMeasures:
        if measure['user_defined_data']:
            # Space heating
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Space heating', 'SH. Solids', 'SH. LPG', 'SH. Diesel oil', 'SH. Gas heat pumps', 'SH. Natural gas', 'SH. Biomass',
                'SH. Geothermal', 'SH. Distributed heat', 'SH. Advanced electric heating', 'SH. Conventional electric heating',
                'SH. BioOil', 'SH. BioGas', 'SH. Hydrogen', 'SH. Solar', 'SH. Electricity in circulation',
                'SH. Electric space cooling', 'SH. Electricity'
            ]] = [
                measure['space_heating']['pct_build_equipped'], measure['space_heating']['solids'], measure['space_heating']['lpg'],
                measure['space_heating']['diesel_oil'], measure['space_heating']['gas_heat_pumps'],
                measure['space_heating']['natural_gas'], measure['space_heating']['biomass'],
                measure['space_heating']['geothermal'], measure['space_heating']['distributed_heat'],
                measure['space_heating']['advanced_electric_heating'], measure['space_heating']['conventional_electric_heating'],
                measure['space_heating']['bio_oil'], measure['space_heating']['bio_gas'],
                measure['space_heating']['hydrogen'], 0.0, measure['space_heating']['electricity_in_circulation'], 0.0, 0.0
            ]
            # Space cooling
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Space cooling', 'SC. Solids', 'SC. LPG', 'SC. Diesel oil', 'SC. Gas heat pumps', 'SC. Natural gas', 'SC. Biomass',
                'SC. Geothermal', 'SC. Distributed heat', 'SC. Advanced electric heating', 'SC. Conventional electric heating',
                'SC. BioOil', 'SC. BioGas', 'SC. Hydrogen', 'SC. Solar', 'SC. Electricity in circulation',
                'SC. Electric space cooling', 'SC. Electricity'
            ]] = [
                measure['space_cooling']['pct_build_equipped'], 0.0, 0.0, 0.0, measure['space_cooling']['gas_heat_pumps'],
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, measure[
                    'space_cooling']['electric_space_cooling'], 0.0
            ]
            # Water heating
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Water heating', 'WH. Solids', 'WH. LPG', 'WH. Diesel oil', 'WH. Gas heat pumps', 'WH. Natural gas', 'WH. Biomass',
                'WH. Geothermal', 'WH. Distributed heat', 'WH. Advanced electric heating', 'WH. Conventional electric heating',
                'WH. BioOil', 'WH. BioGas', 'WH. Hydrogen', 'WH. Solar', 'WH. Electricity in circulation',
                'WH. Electric space cooling', 'WH. Electricity'
            ]] = [
                measure['water_heating']['pct_build_equipped'], measure['water_heating']['solids'], measure['water_heating']['lpg'],
                measure['water_heating']['diesel_oil'], 0.0, measure['water_heating']['natural_gas'],
                measure['water_heating']['biomass'], measure['water_heating']['geothermal'], measure['water_heating']['distributed_heat'],
                measure['water_heating']['advanced_electric_heating'], 0.0, measure['water_heating']['bio_oil'],
                measure['water_heating']['bio_gas'], measure['water_heating']['hydrogen'], measure['water_heating']['solar'], 0.0, 0.0,
                measure['water_heating']['electricity']
            ]
            # Cooking
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Cooking', 'C. Solids', 'C. LPG', 'C. Diesel oil', 'C. Gas heat pumps', 'C. Natural gas', 'C. Biomass',
                'C. Geothermal', 'C. Distributed heat', 'C. Advanced electric heating', 'C. Conventional electric heating',
                'C. BioOil', 'C. BioGas', 'C. Hydrogen', 'C. Solar', 'C. Electricity in circulation',
                'C. Electric space cooling', 'C. Electricity'
            ]] = [
                measure['cooking']['pct_build_equipped'], measure['cooking']['solids'], measure['cooking']['lpg'], 0.0, 0.0,
                measure['cooking']['natural_gas'], measure['cooking']['biomass'],
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, measure['cooking']['electricity']
            ]
            # Lighting
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Lighting', 'L. Solids', 'L. LPG', 'L. Diesel oil', 'L. Gas heat pumps', 'L. Natural gas', 'L. Biomass',
                'L. Geothermal', 'L. Distributed heat', 'L. Advanced electric heating', 'L. Conventional electric heating',
                'L. BioOil', 'L. BioGas', 'L. Hydrogen', 'L. Solar', 'L. Electricity in circulation',
                'L. Electric space cooling', 'L. Electricity'
            ]] = [
                measure['lighting']['pct_build_equipped'], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                measure['lighting']['electricity']
            ]
            # Appliances
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Appliances', 'A. Solids', 'A. LPG', 'A. Diesel oil', 'A. Gas heat pumps', 'A. Natural gas', 'A. Biomass',
                'A. Geothermal', 'A. Distributed heat', 'A. Advanced electric heating', 'A. Conventional electric heating',
                'A. BioOil', 'A. BioGas', 'A. Hydrogen', 'A. Solar', 'A. Electricity in circulation',
                'A. Electric space cooling', 'A. Electricity'
            ]] = [
                measure['appliances']['pct_build_equipped'], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                measure['appliances']['electricity']
            ]
        else:
            dfCSV = dfCSV.assign(
                # Space heating (for Residential and Service sectors)
                space_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Space heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Space heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Space heating']), axis=1),
                sh_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Solids']), axis=1),
                sh_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. LPG']), axis=1),
                sh_diesel_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Diesel oil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Diesel oil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Diesel oil']), axis=1),
                sh_gas_heat_pumps=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Gas heat pumps'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Gas heat pumps'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Gas heat pumps']), axis=1),
                sh_natural_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Natural gas']), axis=1),
                sh_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Biomass']), axis=1),
                sh_geothermal=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Geothermal'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Geothermal'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Geothermal']), axis=1),
                sh_distributed_heat=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Distributed heat'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Distributed heat'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Distributed heat']), axis=1),
                sh_advanced_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Advanced electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Advanced electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Advanced electric heating']), axis=1),
                sh_conventional_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Conventional electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Conventional electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Conventional electric heating']), axis=1),
                sh_bio_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_BioOil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_BioOil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. BioOil']), axis=1),
                sh_bio_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_BioGas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_BioGas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. BioGas']), axis=1),
                sh_hydrogen=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Hydrogen'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Hydrogen'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Hydrogen']), axis=1),
                sh_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Solar']), axis=1),
                sh_electricity_in_circulation=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Electricity in circulation'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Electricity in circulation'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electricity in circulation']), axis=1),
                sh_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electric space cooling']), axis=1),
                sh_electricity=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electricity']), axis=1),
                # Space cooling (for Residential and Service sectors)
                space_cooling=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Space cooling'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Space cooling'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Space cooling']), axis=1),
                sc_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Solids']), axis=1),
                sc_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. LPG']), axis=1),
                sc_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Diesel oil']), axis=1),
                sc_gas_heat_pumps=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space cooling_Gas heat pumps'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space cooling_Gas heat pumps'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Gas heat pumps']), axis=1),
                sc_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Natural gas']), axis=1),
                sc_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Biomass']), axis=1),
                sc_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Geothermal']), axis=1),
                sc_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Distributed heat']), axis=1),
                sc_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Advanced electric heating']), axis=1),
                sc_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Conventional electric heating']), axis=1),
                sc_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. BioOil']), axis=1),
                sc_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. BioGas']), axis=1),
                sc_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Hydrogen']), axis=1),
                sc_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Solar']), axis=1),
                sc_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electricity in circulation']), axis=1),
                sc_electric_space_cooling=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space cooling_Electric space cooling'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space cooling_Electric space cooling'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electric space cooling']), axis=1),
                sc_electricity=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electricity']), axis=1),
                # Water heating (for Residential and Service sectors)
                water_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Water heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Water heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Water heating']), axis=1),
                wh_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Solids']), axis=1),
                wh_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Water heating_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. LPG']), axis=1),
                wh_diesel_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Diesel oil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Diesel oil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Diesel oil']), axis=1),
                wh_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Gas heat pumps']), axis=1),
                wh_natural_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Natural gas']), axis=1),
                wh_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Biomass']), axis=1),
                wh_geothermal=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Geothermal'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Geothermal'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Geothermal']), axis=1),
                wh_distributed_heat=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Distributed heat'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Distributed heat'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Distributed heat']), axis=1),
                wh_advanced_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Water heating_Advanced electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Advanced electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Advanced electric heating']), axis=1),
                wh_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Conventional electric heating']), axis=1),
                wh_bio_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_BioOil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_BioOil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. BioOil']), axis=1),
                wh_bio_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_BioGas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_BioGas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. BioGas']), axis=1),
                wh_hydrogen=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Hydrogen'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Hydrogen'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Hydrogen']), axis=1),
                wh_solar=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Solar'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Solar'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Solar']), axis=1),
                wh_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electric space cooling']), axis=1),
                wh_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electric space cooling']), axis=1),
                wh_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electricity']), axis=1),
                # Cooking (for Residential and Service sectors)
                cooking=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Cooking'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Cooking'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Cooking']), axis=1),
                c_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Solids']), axis=1),
                c_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. LPG']), axis=1),
                c_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Diesel oil']), axis=1),
                c_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Gas heat pumps']), axis=1),
                c_natural_gass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Natural gas']), axis=1),
                c_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Biomass']), axis=1),
                c_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Geothermal']), axis=1),
                c_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Distributed heat']), axis=1),
                c_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Advanced electric heating']), axis=1),
                c_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Conventional electric heating']), axis=1),
                c_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. BioOil']), axis=1),
                c_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. BioGas']), axis=1),
                c_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Hydrogen']), axis=1),
                c_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Solar']), axis=1),
                c_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electricity in circulation']), axis=1),
                c_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electric space cooling']), axis=1),
                c_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electricity']), axis=1),
                # Lighting (for Residential and Service sectors)
                lighting=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Lighting'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Lighting'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Lighting']), axis=1),
                l_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Solids']), axis=1),
                l_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. LPG']), axis=1),
                l_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Diesel oil']), axis=1),
                l_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Gas heat pumps']), axis=1),
                l_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Natural gas']), axis=1),
                l_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Biomass']), axis=1),
                l_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Geothermal']), axis=1),
                l_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Distributed heat']), axis=1),
                l_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Advanced electric heating']), axis=1),
                l_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Conventional electric heating']), axis=1),
                l_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. BioOil']), axis=1),
                l_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. BioGas']), axis=1),
                l_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Hydrogen']), axis=1),
                l_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Solar']), axis=1),
                l_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity in circulation']), axis=1),
                l_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electric space cooling']), axis=1),
                l_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Lighting_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Lighting_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity']), axis=1),
                # Appliances (for Residential and Service sectors)
                appliances=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Appliances'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Appliances'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Appliances']), axis=1),
                a_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Solids']), axis=1),
                a_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. LPG']), axis=1),
                a_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['a. Diesel oil']), axis=1),
                a_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Gas heat pumps']), axis=1),
                a_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Natural gas']), axis=1),
                a_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Biomass']), axis=1),
                a_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Geothermal']), axis=1),
                a_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Distributed heat']), axis=1),
                a_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Advanced electric heating']), axis=1),
                a_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Conventional electric heating']), axis=1),
                a_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. BioOil']), axis=1),
                a_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. BioGas']), axis=1),
                a_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Hydrogen']), axis=1),
                a_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Solar']), axis=1),
                a_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Electricity in circulation']), axis=1),
                a_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Electric space cooling']), axis=1),
                a_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Lighting_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Lighting_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity']), axis=1)
            )

    print('Model: Step 08/>  Writing the Active measures (baseline)...')
    for measure in activeMeasuresBaseline:
        if measure['user_defined_data']:
            # Space heating
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Space heating base', 'SH. Solids base', 'SH. LPG base', 'SH. Diesel oil base', 'SH. Gas heat pumps base',
                'SH. Natural gas base', 'SH. Biomass base', 'SH. Geothermal base', 'SH. Distributed heat base',
                'SH. Advanced electric heating base', 'SH. Conventional electric heating base', 'SH. BioOil base', 'SH. BioGas base',
                'SH. Hydrogen base', 'SH. Solar base', 'SH. Electricity in circulation base', 'SH. Electric space cooling base',
                'SH. Electricity base'
            ]] = [
                measure['space_heating']['pct_build_equipped'], measure['space_heating']['solids'], measure['space_heating']['lpg'],
                measure['space_heating']['diesel_oil'], measure['space_heating']['gas_heat_pumps'],
                measure['space_heating']['natural_gas'], measure['space_heating']['biomass'],
                measure['space_heating']['geothermal'], measure['space_heating']['distributed_heat'],
                measure['space_heating']['advanced_electric_heating'], measure['space_heating']['conventional_electric_heating'],
                measure['space_heating']['bio_oil'], measure['space_heating']['bio_gas'],
                measure['space_heating']['hydrogen'], 0.0, measure['space_heating']['electricity_in_circulation'], 0.0, 0.0
            ]
            # Space cooling
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Space cooling base', 'SC. Solids base', 'SC. LPG base', 'SC. Diesel oil base', 'SC. Gas heat pumps base',
                'SC. Natural gas base', 'SC. Biomass base', 'SC. Geothermal base', 'SC. Distributed heat base',
                'SC. Advanced electric heating base', 'SC. Conventional electric heating base', 'SC. BioOil base', 'SC. BioGas base',
                'SC. Hydrogen base', 'SC. Solar base', 'SC. Electricity in circulation base', 'SC. Electric space cooling base',
                'SC. Electricity base'
            ]] = [
                measure['space_cooling']['pct_build_equipped'], 0.0, 0.0, 0.0, measure['space_cooling']['gas_heat_pumps'],
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, measure[
                    'space_cooling']['electric_space_cooling'], 0.0
            ]
            # Water heating
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Water heating base', 'WH. Solids base', 'WH. LPG base', 'WH. Diesel oil base', 'WH. Gas heat pumps base',
                'WH. Natural gas base', 'WH. Biomass base', 'WH. Geothermal base', 'WH. Distributed heat base',
                'WH. Advanced electric heating base', 'WH. Conventional electric heating base', 'WH. BioOil base', 'WH. BioGas base',
                'WH. Hydrogen base', 'WH. Solar base', 'WH. Electricity in circulation base', 'WH. Electric space cooling base',
                'WH. Electricity base'
            ]] = [
                measure['water_heating']['pct_build_equipped'], measure['water_heating']['solids'], measure['water_heating']['lpg'],
                measure['water_heating']['diesel_oil'], 0.0, measure['water_heating']['natural_gas'],
                measure['water_heating']['biomass'], measure['water_heating']['geothermal'], measure['water_heating']['distributed_heat'],
                measure['water_heating']['advanced_electric_heating'], 0.0, measure['water_heating']['bio_oil'],
                measure['water_heating']['bio_gas'], measure['water_heating']['hydrogen'], measure['water_heating']['solar'], 0.0, 0.0,
                measure['water_heating']['electricity']
            ]
            # Cooking
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Cooking base', 'C. Solids base', 'C. LPG base', 'C. Diesel oil base', 'C. Gas heat pumps base', 'C. Natural gas base',
                'C. Biomass base', 'C. Geothermal base', 'C. Distributed heat base', 'C. Advanced electric heating base',
                'C. Conventional electric heating base', 'C. BioOil base', 'C. BioGas base', 'C. Hydrogen base', 'C. Solar base',
                'C. Electricity in circulation base', 'C. Electric space cooling base', 'C. Electricity base'
            ]] = [
                measure['cooking']['pct_build_equipped'], measure['cooking']['solids'], measure['cooking']['lpg'], 0.0, 0.0,
                measure['cooking']['natural_gas'], measure['cooking']['biomass'],
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, measure['cooking']['electricity']
            ]
            # Lighting
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Lighting base', 'L. Solids base', 'L. LPG base', 'L. Diesel oil base', 'L. Gas heat pumps base', 'L. Natural gas base',
                'L. Biomass base', 'L. Geothermal base', 'L. Distributed heat base', 'L. Advanced electric heating base',
                'L. Conventional electric heating base', 'L. BioOil base', 'L. BioGas base', 'L. Hydrogen base', 'L. Solar base',
                'L. Electricity in circulation base', 'L. Electric space cooling base', 'L. Electricity base'
            ]] = [
                measure['lighting']['pct_build_equipped'], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                measure['lighting']['electricity']
            ]
            # Appliances
            dfCSV.loc[dfCSV['Use'] == measure['building_use'], [
                'Appliances base', 'A. Solids base', 'A. LPG base', 'A. Diesel oil base', 'A. Gas heat pumps base', 'A. Natural gas base',
                'A. Biomass base', 'A. Geothermal base', 'A. Distributed heat base', 'A. Advanced electric heating base',
                'A. Conventional electric heating base', 'A. BioOil base', 'A. BioGas base', 'A. Hydrogen base', 'A. Solar base',
                'A. Electricity in circulation base', 'A. Electric space cooling base', 'A. Electricity base'
            ]] = [
                measure['appliances']['pct_build_equipped'], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                measure['appliances']['electricity']
            ]
        else:
            dfCSV = dfCSV.assign(
                # Space heating (for Residential and Service sectors)
                space_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Space heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Space heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Space heating base']), axis=1),
                sh_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Solids base base']), axis=1),
                sh_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. LPG base']), axis=1),
                sh_diesel_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Diesel oil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Diesel oil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Diesel oil base']), axis=1),
                sh_gas_heat_pumps=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Gas heat pumps'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Gas heat pumps'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Gas heat pumps base']), axis=1),
                sh_natural_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Natural gas base']), axis=1),
                sh_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Biomass base']), axis=1),
                sh_geothermal=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Geothermal'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Geothermal'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Geothermal base']), axis=1),
                sh_distributed_heat=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Distributed heat'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Distributed heat'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Distributed heat base']), axis=1),
                sh_advanced_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Advanced electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Advanced electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Advanced electric heating base']), axis=1),
                sh_conventional_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Space heating_Conventional electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Conventional electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Conventional electric heating base']), axis=1),
                sh_bio_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_BioOil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_BioOil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. BioOil base']), axis=1),
                sh_bio_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_BioGas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_BioGas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. BioGas base']), axis=1),
                sh_hydrogen=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space heating_Hydrogen'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space heating_Hydrogen'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Hydrogen base']), axis=1),
                sh_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Solar base']), axis=1),
                sh_electricity_in_circulation=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Electricity in circulation'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Electricity in circulation'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electricity in circulation base']), axis=1),
                sh_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electric space cooling base']), axis=1),
                sh_electricity=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SH. Electricity base']), axis=1),
                # Space cooling (for Residential and Service sectors)
                space_cooling=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Space cooling'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Space cooling'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Space cooling base']), axis=1),
                sc_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Solids base']), axis=1),
                sc_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. LPG base']), axis=1),
                sc_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Diesel oil base']), axis=1),
                sc_gas_heat_pumps=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space cooling_Gas heat pumps'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space cooling_Gas heat pumps'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Gas heat pumps base']), axis=1),
                sc_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Natural gas base']), axis=1),
                sc_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Biomass base']), axis=1),
                sc_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Geothermal base']), axis=1),
                sc_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Distributed heat base']), axis=1),
                sc_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Advanced electric heating base']), axis=1),
                sc_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Conventional electric heating base']), axis=1),
                sc_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. BioOil base']), axis=1),
                sc_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. BioGas base']), axis=1),
                sc_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Hydrogen base']), axis=1),
                sc_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Solar base']), axis=1),
                sc_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electricity in circulation base']), axis=1),
                sc_electric_space_cooling=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Space cooling_Electric space cooling'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Space cooling_Electric space cooling'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electric space cooling base']), axis=1),
                sc_electricity=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['SC. Electricity base']), axis=1),
                # Water heating (for Residential and Service sectors)
                water_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Water heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Water heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Water heating base']), axis=1),
                wh_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Solids base']), axis=1),
                wh_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Water heating_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. LPG base']), axis=1),
                wh_diesel_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Diesel oil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Diesel oil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Diesel oil base']), axis=1),
                wh_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Gas heat pumps base']), axis=1),
                wh_natural_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Natural gas base']), axis=1),
                wh_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Biomass base']), axis=1),
                wh_geothermal=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Geothermal'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Geothermal'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Geothermal base']), axis=1),
                wh_distributed_heat=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Distributed heat'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Distributed heat'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Distributed heat base']), axis=1),
                wh_advanced_electric_heating=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel'] ==
                                           'Water heating_Advanced electric heating'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Advanced electric heating'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Advanced electric heating base']), axis=1),
                wh_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Conventional electric heating base']), axis=1),
                wh_bio_oil=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_BioOil'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_BioOil'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. BioOil base']), axis=1),
                wh_bio_gas=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_BioGas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_BioGas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. BioGas base']), axis=1),
                wh_hydrogen=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Hydrogen'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Hydrogen'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Hydrogen base']), axis=1),
                wh_solar=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Solar'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Solar'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Solar base']), axis=1),
                wh_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electric space cooling base']), axis=1),
                wh_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electric space cooling base']), axis=1),
                wh_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Water heating_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Water heating_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['WH. Electricity base']), axis=1),
                # Cooking (for Residential and Service sectors)
                cooking=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Cooking'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Cooking'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Cooking base']), axis=1),
                c_solids=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Solids'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Solids'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Solids base']), axis=1),
                c_lpg=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Liquified petroleum gas (LPG)'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Liquified petroleum gas (LPG)'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. LPG base']), axis=1),
                c_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Diesel oil base']), axis=1),
                c_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Gas heat pumps base']), axis=1),
                c_natural_gass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Natural gas'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Natural gas'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Natural gas base']), axis=1),
                c_biomass=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Biomass'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Biomass'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Biomass base']), axis=1),
                c_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Geothermal base']), axis=1),
                c_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Distributed heat base']), axis=1),
                c_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Advanced electric heating base']), axis=1),
                c_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Conventional electric heating base']), axis=1),
                c_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. BioOil base']), axis=1),
                c_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. BioGas base']), axis=1),
                c_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Hydrogen base']), axis=1),
                c_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Solar base']), axis=1),
                c_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electricity in circulation base']), axis=1),
                c_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electric space cooling base']), axis=1),
                c_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Cooking_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Cooking_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['C. Electricity base']), axis=1),
                # Lighting (for Residential and Service sectors)
                lighting=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Lighting'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Lighting'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Lighting base']), axis=1),
                l_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Solids base']), axis=1),
                l_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. LPG base']), axis=1),
                l_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Diesel oil base']), axis=1),
                l_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Gas heat pumps base']), axis=1),
                l_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Natural gas base']), axis=1),
                l_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Biomass base']), axis=1),
                l_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Geothermal base']), axis=1),
                l_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Distributed heat base']), axis=1),
                l_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Advanced electric heating base']), axis=1),
                l_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Conventional electric heating base']), axis=1),
                l_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. BioOil base']), axis=1),
                l_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. BioGas base']), axis=1),
                l_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Hydrogen base']), axis=1),
                l_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Solar base']), axis=1),
                l_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity in circulation base']), axis=1),
                l_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electric space cooling base']), axis=1),
                l_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Lighting_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Lighting_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity base']), axis=1),
                # Appliances (for Residential and Service sectors)
                appliances=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == '_Appliances'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == '_Appliances'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['Appliances base']), axis=1),
                a_solids=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Solids base']), axis=1),
                a_lpg=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. LPG base']), axis=1),
                a_diesel_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['a. Diesel oil base']), axis=1),
                a_gas_heat_pumps=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Gas heat pumps base']), axis=1),
                a_natural_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Natural gas base']), axis=1),
                a_biomass=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Biomass base']), axis=1),
                a_geothermal=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Geothermal base']), axis=1),
                a_distributed_heat=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Distributed heat base']), axis=1),
                a_advanced_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Advanced electric heating base']), axis=1),
                a_conventional_electric_heating=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Conventional electric heating base']), axis=1),
                a_bio_oil=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. BioOil base']), axis=1),
                a_bio_gas=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. BioGas base']), axis=1),
                a_hydrogen=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Hydrogen base']), axis=1),
                a_solar=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Solar base']), axis=1),
                a_electricity_in_circulation=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Electricity in circulation base']), axis=1),
                a_electric_space_cooling=dfCSV.apply(
                    lambda row: 0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (0.0 if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['A. Electric space cooling base']), axis=1),
                a_electricity=dfCSV.apply(
                    lambda row: dfReshhtes[dfReshhtes['Energy service_Fuel']
                                           == 'Lighting_Electricity'].values[0][2]
                    if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Residential')
                    else (dfSerhhtes[dfSerhhtes['Energy service_Fuel'] == 'Lighting_Electricity'].values[0][2]
                          if (row['Use'] == measure['building_use']) and (row['Sector'] == 'Service')
                          else row['L. Electricity base']), axis=1)
            )

    # Energy services (dfRThheff)
    for arch in archetypes:
        # Space heating
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH'] = dfRThheff[dfRThheff['Energy service_Fuel']
                                                               == '_Space heating'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Solids'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Space heating_Solids'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. LPG'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Liquified petroleum gas (LPG)'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Diesel oil'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Diesel oil'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Gas heat pumps'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Gas heat pumps'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Natural gas'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Natural gas'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Biomass'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Space heating_Biomass'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Geothermal'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Geothermal'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Distributed heat'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Distributed heat'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Advanced electric heating'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Advanced electric heating'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Conventional electric heating'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space heating_Conventional electric heating'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. BioOil'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Space heating_BioOil'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. BioGas'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Space heating_BioGas'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SH. Hydrogen'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Space heating_Hydrogen'].values[0][2]
        # Electricity in circulation
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. EIC'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      '_Electricity in circulation'].values[0][2]
        # Space cooling
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SC'] = dfRThheff[dfRThheff['Energy service_Fuel']
                                                               == '_Space cooling'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SC. Gas heat pumps'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space cooling_Gas heat pumps'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. SC. Electric space cooling'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Space cooling_Electric space cooling'].values[0][2]
        # Water heating
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH'] = dfRThheff[dfRThheff['Energy service_Fuel']
                                                               == '_Water heating'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Solids'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_Solids'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. LPG'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Liquified petroleum gas (LPG)'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Diesel oil'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Diesel oil'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Natural gas'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Natural gas'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Biomass'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_Biomass'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Geothermal'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Geothermal'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Distributed heat'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Distributed heat'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Advanced electric heating'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Advanced electric heating'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Electricity'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Water heating_Electricity'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. BioOil'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_BioOil'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. BioGas'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_BioGas'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Hydrogen'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_Hydrogen'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. WH. Solar'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Water heating_Solar'].values[0][2]
        # Cooking
        dfCSV.loc[dfCSV['Use'] == arch,
                  'Eff. C'] = dfRThheff[dfRThheff['Energy service_Fuel'] == '_Cooking'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. C. Solids'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Cooking_Solids'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. C. LPG'] =\
            dfRThheff[dfRThheff['Energy service_Fuel'] ==
                      'Cooking_Liquified petroleum gas (LPG)'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. C. Natural gas'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Cooking_Natural gas'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. C. Biomass'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Cooking_Biomass'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. C. Electricity'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Cooking_Electricity'].values[0][2]
        # Lighting
        dfCSV.loc[dfCSV['Use'] == arch,
                  'Eff. L'] = dfRThheff[dfRThheff['Energy service_Fuel'] == '_Lighting'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. L. Electricity'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Lighting_Electricity'].values[0][2]
        # Appliances
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. A'] = dfRThheff[dfRThheff['Energy service_Fuel']
                                                              == '_Appliances'].values[0][2]
        dfCSV.loc[dfCSV['Use'] == arch, 'Eff. A. Electricity'] =\
            dfRThheff[dfRThheff['Energy service_Fuel']
                      == 'Appliances_Electricity'].values[0][2]

    # Finish
    print('Model: Step 08/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 09 -> Add the passive measures
def s09AddPassiveMeasures(dfCSV: pd.DataFrame,
                          passiveMeasures: pd.DataFrame) -> pd.DataFrame:
    """Model Step 09: Add the passive measures.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        passiveMeasures (list): The list of passive measures::

            Example: see "input.json" file in the root directory.
    
    Returns:
        DataFrame

    """

    print('Model: Step 09/>  Writing the Passive measures...')
    for measure in passiveMeasures:
        dfCSV.loc[dfCSV['Use'] == measure['building_use'],
                  'Ref Level'] = measure['ref_level']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == 'Pre-1945'), 'Ref%'] =\
            measure['percentages_by_periods']['Pre-1945']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == '1945-1969'), 'Ref%'] =\
            measure['percentages_by_periods']['1945-1969']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == '1970-1979'), 'Ref%'] =\
            measure['percentages_by_periods']['1970-1979']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == '1980-1989'), 'Ref%'] =\
            measure['percentages_by_periods']['1980-1989']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == '1990-1999'), 'Ref%'] =\
            measure['percentages_by_periods']['1990-1999']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == '2000-2010'), 'Ref%'] =\
            measure['percentages_by_periods']['2000-2010']
        dfCSV.loc[(dfCSV['Use'] == measure['building_use']) & (dfCSV['Period'] == 'Post-2010'), 'Ref%'] =\
            measure['percentages_by_periods']['Post-2010']

    # Finish
    print('Model: Step 09/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 10 -> Write the U-Values and the Internal Gains
def s10WriteUValuesAndInternalGains(dfCSV: pd.DataFrame,
                                    dfDHW: pd.DataFrame,
                                    dfUValues: pd.DataFrame,
                                    dfRUValues: pd.DataFrame,
                                    dfACH: pd.DataFrame,
                                    nutsId: str) -> pd.DataFrame:
    """Model Step 10: Write the U-Values and the Internal Gains.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfDHW (DataFrame): The DataFrame corresponding to DHW.
        dfUValues (DataFrame): The DataFrame corresponding to U-Values.
        dfRUValues (DataFrame): The DataFrame corresponding to Retroffitting U-Values.
        dfACH (DataFrame): The DataFrame corresponding to ACH.
        nutsId (str) :Identifier of NUTS2 region for which the
            analysis will be carried out.
    
    Returns:
        DataFrame

    """

    print('Model: Step 10/>  Writing the U-Values and the Internal Gains...')
    country = nutsId[:2].upper()
    for index, row in dfCSV.iterrows():
        # U-Values
        sector, period = row['Sector'], row['Period']
        dfRUV = dfRUValues[dfRUValues['Level'] == dfCSV.at[index, 'Ref Level']]
        dfRUV = dfRUV.reset_index(drop=True)
        dfq = dfUValues.query(
            'Country_ID == @country and Sector == @sector and Period == @period')
        dfCSV.at[index, 'Roof [W/m2K]'] = (1 / (1 / float(dfq['Roof'].iloc[0]) + dfRUV.iloc[0, 1]))\
            * dfCSV.at[index, 'Ref%'] + (float(dfq['Roof'].iloc[0]) * (1 - dfCSV.at[index, 'Ref%']))
        dfCSV.at[index, 'Wall [W/m2K]'] = (1 / (1 / float(dfq['Wall'].iloc[0]) + dfRUV.iloc[0, 2]))\
            * dfCSV.at[index, 'Ref%'] + (float(dfq['Wall'].iloc[0]) * (1 - dfCSV.at[index, 'Ref%']))
        dfCSV.at[index, 'Window [W/m2K]'] = dfRUV.iloc[0, 3] * dfCSV.at[index, 'Ref%'] +\
            float(dfq['Window'].iloc[0]) * (1 - dfCSV.at[index, 'Ref%'])

        # Internal Gains
        df = dfDHW[dfDHW['BuildingUse'] == row['Use']]
        df = df.reset_index(drop=True)
        dfCSV.at[index, 'Equipment internal gains [W/m2]'] = df.at[0,
                                                                   'Equipment internal gains [W/m2]']
        dfCSV.at[index, 'Occupancy internal gains [W/m2]'] = df.at[0,
                                                                   'Occupancy internal gains [W/m2]']
        dfCSV.at[index, 'Lighting power [W/m2]'] = df.at[0,
                                                         'Lighting power [W/m2]']
        dfCSV.at[index, 'DHW demand [KW/m2·year]'] = df.at[0,
                                                           'Anual DHW demand (KWh/m2)']
        dfCSV.at[index, 'Cooking [KW/m2·year]'] = df.at[0,
                                                        'Cooking [KWh/m2·year]']
        ach = dfACH[dfACH['Country_ID'] == country][row['Period']].iloc[0]
        dfCSV.at[index, 'Air renovation losses'] = ach * \
            (1 - dfCSV.at[index, 'Ref%']) + \
            min(0.6, 1 + 1.2) * dfCSV.at[index, 'Ref%']

    # Common factors
    dfCSV['D-Factor'] = dfCSV['Footprint Area'] * dfCSV['Roof [W/m2K]'] +\
        dfCSV['Opaque fachade area'] * dfCSV['Wall [W/m2K]'] +\
        dfCSV['Window Area'] * dfCSV['Window [W/m2K]']
    dfCSV['IG-Li-Factor'] = dfCSV['Lighting power [W/m2]'] * \
        dfCSV['Net heated floor area']
    dfCSV['IG-Eq-Factor'] = dfCSV['Equipment internal gains [W/m2]'] * \
        dfCSV['Net heated floor area']
    dfCSV['IG-Oc-Factor'] = dfCSV['Occupancy internal gains [W/m2]'] * \
        dfCSV['Net heated floor area']
    dfCSV['ARL-Factor'] = 0.33 * \
        dfCSV['Air renovation losses'] * dfCSV['Heated Volume']

    # Finish
    print('Model: Step 10/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 11 -> Add the CAPEX dataframe
def s11AddCapexDataFrame(dfCSV: pd.DataFrame,
                         dfBesCapex: pd.DataFrame) -> pd.DataFrame:
    """Model Step 11: Add the CAPEX dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfBesCapex (DataFrame): The DataFrame corresponding to Capex.
    
    Returns:
        DataFrame

    """

    print('Model: Step 11/>  Adding the CAPEX dataframe...')

    # Space heating
    dfCSV = dfCSV.assign(
        **{
            'CAPEX SH. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Solids', 'Space Heating'].iloc[0],
            'CAPEX SH. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                            'Liquified petroleum gas (LPG)', 'Space Heating'].iloc[0],
            'CAPEX SH. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Diesel oil', 'Space Heating'].iloc[0],
            'CAPEX SH. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                       'Gas heat pumps', 'Space Heating'].iloc[0],
            'CAPEX SH. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Natural gas', 'Space Heating'].iloc[0],
            'CAPEX SH. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Biomass', 'Space Heating'].iloc[0],
            'CAPEX SH. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Geothermal', 'Space Heating'].iloc[0],
            'CAPEX SH. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                         'Distributed heat', 'Space Heating'].iloc[0],
            'CAPEX SH. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                  'Advanced electric heating', 'Space Heating'].iloc[0],
            'CAPEX SH. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                      'Conventional electric heating', 'Space Heating'].iloc[0],
            'CAPEX SH. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioOil', 'Space Heating'].iloc[0],
            'CAPEX SH. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioGas', 'Space Heating'].iloc[0],
            'CAPEX SH. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                 'Hydrogen', 'Space Heating'].iloc[0],
            'CAPEX SH. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                               'Electric space cooling', 'Space Heating'].iloc[0],
            'CAPEX SH. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Electricity', 'Space Heating'].iloc[0],
            'CAPEX SH. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solar', 'Space Heating'].iloc[0]
        }
    )

    # Space cooling
    dfCSV = dfCSV.assign(
        **{
            'CAPEX SC. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Solids', 'Space Cooling'].iloc[0],
            'CAPEX SC. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                            'Liquified petroleum gas (LPG)', 'Space Cooling'].iloc[0],
            'CAPEX SC. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Diesel oil', 'Space Cooling'].iloc[0],
            'CAPEX SC. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                       'Gas heat pumps', 'Space Cooling'].iloc[0],
            'CAPEX SC. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Natural gas', 'Space Cooling'].iloc[0],
            'CAPEX SC. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Biomass', 'Space Cooling'].iloc[0],
            'CAPEX SC. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Geothermal', 'Space Cooling'].iloc[0],
            'CAPEX SC. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                         'Distributed heat', 'Space Cooling'].iloc[0],
            'CAPEX SC. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                  'Advanced electric heating', 'Space Cooling'].iloc[0],
            'CAPEX SC. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                      'Conventional electric heating', 'Space Cooling'].iloc[0],
            'CAPEX SC. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioOil', 'Space Cooling'].iloc[0],
            'CAPEX SC. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioGas', 'Space Cooling'].iloc[0],
            'CAPEX SC. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                 'Hydrogen', 'Space Cooling'].iloc[0],
            'CAPEX SC. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                               'Electric space cooling', 'Space Cooling'].iloc[0],
            'CAPEX SC. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Electricity', 'Space Cooling'].iloc[0],
            'CAPEX SC. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solar', 'Space Cooling'].iloc[0]
        }
    )

    # Water heating
    dfCSV = dfCSV.assign(
        **{
            'CAPEX WH. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Solids', 'Water Heating'].iloc[0],
            'CAPEX WH. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                            'Liquified petroleum gas (LPG)', 'Water Heating'].iloc[0],
            'CAPEX WH. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Diesel oil', 'Water Heating'].iloc[0],
            'CAPEX WH. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                       'Gas heat pumps', 'Water Heating'].iloc[0],
            'CAPEX WH. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Natural gas', 'Water Heating'].iloc[0],
            'CAPEX WH. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Biomass', 'Water Heating'].iloc[0],
            'CAPEX WH. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Geothermal', 'Water Heating'].iloc[0],
            'CAPEX WH. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                         'Distributed heat', 'Water Heating'].iloc[0],
            'CAPEX WH. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                  'Advanced electric heating', 'Water Heating'].iloc[0],
            'CAPEX WH. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                      'Conventional electric heating', 'Water Heating'].iloc[0],
            'CAPEX WH. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioOil', 'Water Heating'].iloc[0],
            'CAPEX WH. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'BioGas', 'Water Heating'].iloc[0],
            'CAPEX WH. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                 'Hydrogen', 'Water Heating'].iloc[0],
            'CAPEX WH. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                               'Electric space cooling', 'Water Heating'].iloc[0],
            'CAPEX WH. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                    'Electricity', 'Water Heating'].iloc[0],
            'CAPEX WH. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solar', 'Water Heating'].iloc[0]
        }
    )

    # Cooking
    dfCSV = dfCSV.assign(
        **{
            'CAPEX C. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solids', 'Cooking'].iloc[0],
            'CAPEX C. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                           'Liquified petroleum gas (LPG)', 'Cooking'].iloc[0],
            'CAPEX C. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Diesel oil', 'Cooking'].iloc[0],
            'CAPEX C. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                      'Gas heat pumps', 'Cooking'].iloc[0],
            'CAPEX C. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Natural gas', 'Cooking'].iloc[0],
            'CAPEX C. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Biomass', 'Cooking'].iloc[0],
            'CAPEX C. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Geothermal', 'Cooking'].iloc[0],
            'CAPEX C. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                        'Distributed heat', 'Cooking'].iloc[0],
            'CAPEX C. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                 'Advanced electric heating', 'Cooking'].iloc[0],
            'CAPEX C. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                     'Conventional electric heating', 'Cooking'].iloc[0],
            'CAPEX C. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioOil', 'Cooking'].iloc[0],
            'CAPEX C. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioGas', 'Cooking'].iloc[0],
            'CAPEX C. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Hydrogen', 'Cooking'].iloc[0],
            'CAPEX C. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                              'Electric space cooling', 'Cooking'].iloc[0],
            'CAPEX C. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Electricity', 'Cooking'].iloc[0],
            'CAPEX C. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                             'Solar', 'Cooking'].iloc[0]
        }
    )

    # Lighting
    dfCSV = dfCSV.assign(
        **{
            'CAPEX L. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solids', 'Lighting'].iloc[0],
            'CAPEX L. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                           'Liquified petroleum gas (LPG)', 'Lighting'].iloc[0],
            'CAPEX L. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Diesel oil', 'Lighting'].iloc[0],
            'CAPEX L. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                      'Gas heat pumps', 'Lighting'].iloc[0],
            'CAPEX L. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Natural gas', 'Lighting'].iloc[0],
            'CAPEX L. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Biomass', 'Lighting'].iloc[0],
            'CAPEX L. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Geothermal', 'Lighting'].iloc[0],
            'CAPEX L. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                        'Distributed heat', 'Lighting'].iloc[0],
            'CAPEX L. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                 'Advanced electric heating', 'Lighting'].iloc[0],
            'CAPEX L. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                     'Conventional electric heating', 'Lighting'].iloc[0],
            'CAPEX L. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioOil', 'Lighting'].iloc[0],
            'CAPEX L. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioGas', 'Lighting'].iloc[0],
            'CAPEX L. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Hydrogen', 'Lighting'].iloc[0],
            'CAPEX L. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                              'Electric space cooling', 'Lighting'].iloc[0],
            'CAPEX L. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Electricity', 'Lighting'].iloc[0],
            'CAPEX L. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                             'Solar', 'Lighting'].iloc[0]
        }
    )

    # Appliances
    dfCSV = dfCSV.assign(
        **{
            'CAPEX A. Solids': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'Solids', 'Appliances'].iloc[0],
            'CAPEX A. LPG': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                           'Liquified petroleum gas (LPG)', 'Appliances'].iloc[0],
            'CAPEX A. Diesel oil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Diesel oil', 'Appliances'].iloc[0],
            'CAPEX A. Gas heat pumps': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                      'Gas heat pumps', 'Appliances'].iloc[0],
            'CAPEX A. Natural gas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Natural gas', 'Appliances'].iloc[0],
            'CAPEX A. Biomass': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                               'Biomass', 'Appliances'].iloc[0],
            'CAPEX A. Geothermal': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                  'Geothermal', 'Appliances'].iloc[0],
            'CAPEX A. Distributed heat': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                        'Distributed heat', 'Appliances'].iloc[0],
            'CAPEX A. Advanced electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                 'Advanced electric heating', 'Appliances'].iloc[0],
            'CAPEX A. Conventional electric heating': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                                     'Conventional electric heating', 'Appliances'].iloc[0],
            'CAPEX A. BioOil': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioOil', 'Appliances'].iloc[0],
            'CAPEX A. BioGas': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                              'BioGas', 'Appliances'].iloc[0],
            'CAPEX A. Hydrogen': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                'Hydrogen', 'Appliances'].iloc[0],
            'CAPEX A. Electric space cooling': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                              'Electric space cooling', 'Appliances'].iloc[0],
            'CAPEX A. Electricity': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                                   'Electricity', 'Appliances'].iloc[0],
            'CAPEX A. Solar': dfBesCapex.loc[dfBesCapex['Building Energy System CAPEX E/KW'] ==
                                             'Solar', 'Appliances'].iloc[0]
        }
    )

    # Finish
    print('Model: Step 11/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 12 -> Add the OPEX dataframe
def s12AddOpexDataFrame(dfCSV: pd.DataFrame,
                        dfBesOpex: pd.DataFrame) -> pd.DataFrame:
    """Model Step 12: Add the OPEX dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfBesOpex (DataFrame): The DataFrame corresponding to Opex.
    
    Returns:
        DataFrame

    """

    print('Model: Step 12/>  Adding the OPEX dataframe...')

    # Fixed cost
    dfCSV = dfCSV.assign(
        **{
            'OPEX Fixed cost Solids|Coal': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                         'Solids|Coal', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Liquids|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                         'Liquids|Gas', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Liquids|Oil': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                         'Liquids|Oil', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Gases|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                       'Gases|Gas', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Solids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Solids|Biomass', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Electricity': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                         'Electricity', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Heat': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                  'Heat', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Liquids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                             'Liquids|Biomass', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Gases|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                           'Gases|Biomass', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Hydrogen': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                      'Hydrogen', 'Fixed cost E/KW'].iloc[0],
            'OPEX Fixed cost Heat|Solar': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                        'Heat|Solar', 'Fixed cost E/KW'].iloc[0]
        }
    )

    # Variable cost
    dfCSV = dfCSV.assign(
        **{
            'OPEX Variable cost Solids|Coal': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Solids|Coal', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Liquids|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Liquids|Gas', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Liquids|Oil': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Liquids|Oil', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Gases|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                          'Gases|Gas', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Solids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                               'Solids|Biomass', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Electricity': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Electricity', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Heat': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                     'Heat', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Liquids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                                'Liquids|Biomass', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Gases|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                              'Gases|Biomass', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Hydrogen': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                         'Hydrogen', 'Variable cost E/KWh'].iloc[0],
            'OPEX Variable cost Heat|Solar': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                           'Heat|Solar', 'Variable cost E/KWh'].iloc[0]
        }
    )

    # Emissions
    dfCSV = dfCSV.assign(
        **{
            'OPEX Emissions Solids|Coal': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                        'Solids|Coal', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Liquids|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                        'Liquids|Gas', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Liquids|Oil': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                        'Liquids|Oil', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Gases|Gas': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                      'Gases|Gas', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Solids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                           'Solids|Biomass', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Electricity': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                        'Electricity', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Heat': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                 'Heat', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Liquids|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                            'Liquids|Biomass', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Gases|Biomass': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                          'Gases|Biomass', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Hydrogen': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                     'Hydrogen', 'Emisions kgCO2/KWh'].iloc[0],
            'OPEX Emissions Heat|Solar': dfBesOpex.loc[dfBesOpex['Building Energy System OPEX'] ==
                                                       'Heat|Solar', 'Emisions kgCO2/KWh'].iloc[0]
        }
    )

    # Finish
    print('Model: Step 12/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 13 -> Add the Retrofitting Cost dataframe
def s13AddRetrofittingCostDataFrame(dfCSV: pd.DataFrame,
                                    dfRetroCost: pd.DataFrame) -> pd.DataFrame:
    """Model Step 13: Add the Retrofitting Cost dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfRetroCost (DataFrame): The DataFrame corresponding to Retrofitting Cost.
    
    Returns:
        DataFrame

    """

    print('Model: Step 13/>  Adding the Retrofitting Cost dataframe...')
    dfCSV = dfCSV.assign(
        **{
            'RFC Cost Low Wall': dfRetroCost.loc[dfRetroCost['Level'] == 'Low', 'Wall'].iloc[0],
            'RFC Cost Medium Wall': dfRetroCost.loc[dfRetroCost['Level'] == 'Medium', 'Wall'].iloc[0],
            'RFC Cost High Wall': dfRetroCost.loc[dfRetroCost['Level'] == 'High', 'Wall'].iloc[0],
            'RFC Cost Low Roof': dfRetroCost.loc[dfRetroCost['Level'] == 'Low', 'Roof'].iloc[0],
            'RFC Cost Medium Roof': dfRetroCost.loc[dfRetroCost['Level'] == 'Medium', 'Roof'].iloc[0],
            'RFC Cost High Roof': dfRetroCost.loc[dfRetroCost['Level'] == 'High', 'Roof'].iloc[0],
            'RFC Cost Low Window': dfRetroCost.loc[dfRetroCost['Level'] == 'Low', 'Window'].iloc[0],
            'RFC Cost Medium Window': dfRetroCost.loc[dfRetroCost['Level'] == 'Medium', 'Window'].iloc[0],
            'RFC Cost High Window': dfRetroCost.loc[dfRetroCost['Level'] == 'High', 'Window'].iloc[0]
        }
    )

    # Finish
    print('Model: Step 13/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 14 -> Add the Renewable Energy Systems dataframe
def s14AddRenewableEnergySystemsDataFrame(dfCSV: pd.DataFrame,
                                          dfRes: pd.DataFrame) -> pd.DataFrame:
    """Model Step 14: Add the Renewable Energy Systems dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfRes (DataFrame): The DataFrame corresponding to Renewable Energy Systems.
    
    Returns:
        DataFrame

    """

    print('Model: Step 14/>  Adding the Renewable Energy Systems (RES) dataframe...')
    dfCSV = dfCSV.assign(
        **{
            'RES ST. Cost': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'Cost (E/m2)'].iloc[0],
            'RES ST. Impact': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'Impact (kgCO2/m2)'].iloc[0],
            'RES ST. Lifetime': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'Lifetime (years)'].iloc[0],
            'RES ST. Efficiency': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'Efficiency'].iloc[0],
            'RES ST. N0': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'n0'].iloc[0],
            'RES ST. K1': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'k1'].iloc[0],
            'RES ST. K2': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'k2'].iloc[0],
            'RES ST. NS': dfRes.loc[dfRes['RES'] == 'Solar Thermal', 'ns'].iloc[0],
            'RES SP. Cost': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'Cost (E/m2)'].iloc[0],
            'RES SP. Impact': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'Impact (kgCO2/m2)'].iloc[0],
            'RES SP. Lifetime': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'Lifetime (years)'].iloc[0],
            'RES SP. Efficiency': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'Efficiency'].iloc[0],
            'RES SP. N0': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'n0'].iloc[0],
            'RES SP. K1': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'k1'].iloc[0],
            'RES SP. K2': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'k2'].iloc[0],
            'RES SP. NS': dfRes.loc[dfRes['RES'] == 'Solar Photovoltaic', 'ns'].iloc[0]
        }
    )

    # Finish
    print('Model: Step 14/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 15 -> Add the Capacity dataframe
def s15AddCapacityDataFrame(dfCSV: pd.DataFrame,
                            dfCapacity: pd.DataFrame,
                            archetypes: list) -> pd.DataFrame:
    """Model Step 15: Add the Capacity dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfCapacity (DataFrame): The DataFrame corresponding to Capacity.
        archetypes (list): The list of building uses. Example::

            "[
                "Apartment Block",
                "Single family- Terraced houses",
                "Hotels and Restaurants",
                "Health",
                "Education",
                "Offices",
                "Trade",
                "Other non-residential buildings",
                "Sport"
            ]"
    
    Returns:
        DataFrame

    """

    print('Model: Step 15/>  Adding the Capacity dataframe...')
    for arch in archetypes:
        dfCSV.loc[dfCSV['Use'] == arch, 'Central HP (SH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Space heating')
                                                                            & (dfCapacity['Capacity KW/m2'] == 'Central HP'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Central Boiler (SH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Space heating')
                                                                                & (dfCapacity['Capacity KW/m2'] == 'Central Boiler'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Individual Boiler (24KW) (SH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Space heating')
                                                                                          & (dfCapacity['Capacity KW/m2'] == 'Individual Boiler (24KW)'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Individual HP 8KW (SH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Space heating')
                                                                                   & (dfCapacity['Capacity KW/m2'] == 'Individual HP 8KW'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'HP (SC)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Space cooling')
                                                                    & (dfCapacity['Capacity KW/m2'] == 'HP'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Central HP (WH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Water heating')
                                                                            & (dfCapacity['Capacity KW/m2'] == 'Central HP'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Central Boiler (WH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Water heating')
                                                                                & (dfCapacity['Capacity KW/m2'] == 'Central Boiler'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Individual Boiler (24KW) (WH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Water heating')
                                                                                          & (dfCapacity['Capacity KW/m2'] == 'Individual Boiler (24KW)'), arch].iloc[0]
        dfCSV.loc[dfCSV['Use'] == arch, 'Individual HP 8KW (WH)'] = dfCapacity.loc[(dfCapacity['Energy Service'] == 'Water heating')
                                                                                   & (dfCapacity['Capacity KW/m2'] == 'Individual HP 8KW'), arch].iloc[0]

    # Finish
    print('Model: Step 15/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 16 -> Add the Equivalent Power dataframe
def s16AddEquivalentPowerDataFrame(dfCSV: pd.DataFrame) -> pd.DataFrame:
    """Model Step 16: Add the Equivalent Power dataframe.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
    
    Returns:
        DataFrame

    """

    print('Model: Step 16/>  Adding the Equivalent Power dataframe...')

    centralHPColumns = ['EP. Gas heat pumps', 'EP. Advanced electric heating']
    centralBoilerColumns = ['EP. LPG', 'EP. Diesel oil', 'EP. Natural gas',
                            'EP. Biomass', 'EP. Geothermal', 'EP. Distributed heat',
                            'EP. Conventional electric heating', 'EP. BioOil', 'EP. BioGas', 'EP. Hydrogen',
                            'EP. Solar', 'EP. Electric space cooling', 'EP. Electricity']
    for index, row in dfCSV.iterrows():
        centralHP = [
            row['Central HP (SH)'], row['HP (SC)'], row['Central Boiler (WH)']]
        centralBoiler = [
            row['Central Boiler (SH)'], row['HP (SC)'], row['Central Boiler (WH)']]
        if row['Use'] == 'Apartment Block':
            centralHP[0] = centralHP[0] * (1 - row['Share Individual']) + \
                row['Individual HP 8KW (SH)'] * row['Share Individual']
            centralHP[2] = centralHP[2] * (1 - row['Share Individual']) + \
                row['Individual Boiler (24KW) (WH)'] * row['Share Individual']
            centralBoiler[0] = centralBoiler[0] * (1 - row['Share Individual']) + \
                row['Individual Boiler (24KW) (SH)'] * row['Share Individual']
            centralBoiler[2] = centralBoiler[2] * (
                1 - row['Share Individual']) + row['Central Boiler (WH)'] * row['Share Individual']

        # Space heating
        dfCSV.at[index, 'EP. Solids (SH)'] = round(centralBoiler[0] / 1.0e+06, 6)
        for col in centralHPColumns:
            dfCSV.at[index, col + ' (SH)'] = round(centralHP[0], 6)
        for col in centralBoilerColumns:
            dfCSV.at[index, col + ' (SH)'] = round(centralBoiler[0], 6)

        # Space cooling
        dfCSV.at[index, 'EP. Solids (SC)'] = round(centralHP[1], 6)
        for col in centralHPColumns:
            dfCSV.at[index, col + ' (SC)'] = round(centralHP[1], 6)
        for col in centralBoilerColumns:
            dfCSV.at[index, col + ' (SC)'] = round(centralHP[1], 6)

        # Water heating
        dfCSV.at[index, 'EP. Solids (WH)'] = round(centralHP[2], 6)
        for col in centralHPColumns:
            dfCSV.at[index, col + ' (WH)'] = round(centralHP[2], 6)
        for col in centralBoilerColumns:
            dfCSV.at[index, col + ' (WH)'] = round(centralHP[2], 6)

    # Finish
    print('Model: Step 16/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 17 -> Calculate the costs
def s17CalculateCosts(dfCSV: pd.DataFrame) -> pd.DataFrame:
    """Model Step 17: Calculate the costs.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
    
    Returns:
        DataFrame

    """

    print('Model: Step 17/>  Calculating the costs...')
    dfDwellings = dfCSV[['Sector', 'Occ. Dwellings']]
    dfDwellings.loc[dfDwellings['Sector'] !=
                    'Residential', 'Occ. Dwellings'] = 1
    for index, row in dfCSV.iterrows():
        # Space heating
        val = row['CAPEX SH. Solids'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Solids (SH)'] * (
                row['SH. Solids'] - row['SH. Solids base']) /  1.0e+06
        dfCSV.at[index, 'SH. Cost Solids'] = 0 if val < 0 else val
        val = row['CAPEX SH. LPG'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * \
            row['EP. LPG (SH)'] * (row['SH. LPG'] -
                                   row['SH. LPG base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost LPG'] = 0 if val < 0 else val
        val = row['CAPEX SH. Diesel oil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Diesel oil (SH)'] * (
                row['SH. Diesel oil'] - row['SH. Diesel oil base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Diesel oil'] = 0 if val < 0 else val
        val = row['CAPEX SH. Gas heat pumps'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Gas heat pumps (SH)'] * (
                row['SH. Gas heat pumps'] - row['SH. Gas heat pumps base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Gas heat pumps'] = 0 if val < 0 else val
        val = row['CAPEX SH. Natural gas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Natural gas (SH)'] * (
                row['SH. Natural gas'] - row['SH. Natural gas base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Natural gas'] = 0 if val < 0 else val
        val = row['CAPEX SH. Biomass'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Biomass (SH)'] * (
                row['SH. Biomass'] - row['SH. Biomass base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Biomass'] = 0 if val < 0 else val
        val = row['CAPEX SH. Geothermal'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Geothermal (SH)'] * (
                row['SH. Geothermal'] - row['SH. Geothermal base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Geothermal'] = 0 if val < 0 else val
        val = row['CAPEX SH. Distributed heat'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Distributed heat (SH)'] * (
                row['SH. Distributed heat'] - row['SH. Distributed heat base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Distributed heat'] = 0 if val < 0 else val
        val = row['CAPEX SH. Advanced electric heating'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Advanced electric heating (SH)'] *\
            (row['SH. Advanced electric heating'] -
             row['SH. Advanced electric heating base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Advanced electric heating'] = 0 if val < 0 else val
        val = row['CAPEX SH. Conventional electric heating'] * row['Net heated floor area'] *\
            dfDwellings.at[index, 'Occ. Dwellings'] * row['Space heating'] * row['EP. Conventional electric heating (SH)'] *\
            (row['SH. Conventional electric heating'] -
             row['SH. Conventional electric heating base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Conventional electric heating'] = 0 if val < 0 else val
        val = row['CAPEX SH. BioOil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. BioOil (SH)'] * (
                row['SH. BioOil'] - row['SH. BioOil base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost BioOil'] = 0 if val < 0 else val
        val = row['CAPEX SH. BioGas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. BioGas (SH)'] * (
                row['SH. BioGas'] - row['SH. BioGas base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost BioGas'] = 0 if val < 0 else val
        val = row['CAPEX SH. Hydrogen'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Hydrogen (SH)'] * (
                row['SH. Hydrogen'] - row['SH. Hydrogen base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Hydrogen'] = 0 if val < 0 else val
        val = row['CAPEX SH. Solar'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Solar (SH)'] * (
                row['SH. Solar'] - row['SH. Solar base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Solar'] = 0 if val < 0 else val
        val = row['CAPEX SH. Electric space cooling'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Electric space cooling (SH)'] *\
            (row['SH. Electric space cooling'] -
             row['SH. Electric space cooling base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Electric space cooling'] = 0 if val < 0 else val
        val = row['CAPEX SH. Electricity'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space heating'] * row['EP. Electricity (SH)'] * (
                row['SH. Electricity'] - row['SH. Electricity base']) / 1.0e+06
        dfCSV.at[index, 'SH. Cost Electricity'] = 0 if val < 0 else val

        # Space cooling
        val = row['CAPEX SC. Solids'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Solids (SC)'] * (
                row['SC. Solids'] - row['SC. Solids base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Solids'] = 0 if val < 0 else val
        val = row['CAPEX SC. LPG'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * \
            row['EP. LPG (SC)'] * (row['SC. LPG'] -
                                   row['SC. LPG base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost LPG'] = 0 if val < 0 else val
        val = row['CAPEX SC. Diesel oil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Diesel oil (SC)'] * (
                row['SC. Diesel oil'] - row['SC. Diesel oil base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Diesel oil'] = 0 if val < 0 else val
        val = row['CAPEX SC. Gas heat pumps'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Gas heat pumps (SC)'] * (
                row['SC. Gas heat pumps'] - row['SC. Gas heat pumps base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Gas heat pumps'] = 0 if val < 0 else val
        val = row['CAPEX SC. Natural gas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Natural gas (SC)'] * (
                row['SC. Natural gas'] - row['SC. Natural gas base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Natural gas'] = 0 if val < 0 else val
        val = row['CAPEX SC. Biomass'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Biomass (SC)'] * (
                row['SC. Biomass'] - row['SC. Biomass base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Biomass'] = 0 if val < 0 else val
        val = row['CAPEX SC. Geothermal'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Geothermal (SC)'] * (
                row['SC. Geothermal'] - row['SC. Geothermal base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Geothermal'] = 0 if val < 0 else val
        val = row['CAPEX SC. Distributed heat'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Distributed heat (SC)'] * (
                row['SC. Distributed heat'] - row['SC. Distributed heat base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Distributed heat'] = 0 if val < 0 else val
        val = row['CAPEX SC. Advanced electric heating'] * row['Net heated floor area'] *\
            dfDwellings.at[index, 'Occ. Dwellings'] * row['Space cooling'] * row['EP. Advanced electric heating (SC)'] *\
            (row['SC. Advanced electric heating'] -
             row['SC. Advanced electric heating base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Advanced electric heating'] = 0 if val < 0 else val
        val = row['CAPEX SC. Conventional electric heating'] * row['Net heated floor area'] *\
            dfDwellings.at[index, 'Occ. Dwellings'] * row['Space cooling'] * row['EP. Conventional electric heating (SC)'] *\
            (row['SC. Conventional electric heating'] -
             row['SC. Conventional electric heating base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Conventional electric heating'] = 0 if val < 0 else val
        val = row['CAPEX SC. BioOil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. BioOil (SC)'] * (
                row['SC. BioOil'] - row['SC. BioOil base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost BioOil'] = 0 if val < 0 else val
        val = row['CAPEX SC. BioGas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. BioGas (SC)'] * (
                row['SC. BioGas'] - row['SC. BioGas base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost BioGas'] = 0 if val < 0 else val
        val = row['CAPEX SC. Hydrogen'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Hydrogen (SC)'] * (
                row['SC. Hydrogen'] - row['SC. Hydrogen base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Hydrogen'] = 0 if val < 0 else val
        val = row['CAPEX SC. Solar'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Solar (SC)'] * (
                row['SC. Solar'] - row['SC. Solar base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Solar'] = 0 if val < 0 else val
        val = row['CAPEX SC. Electric space cooling'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Electric space cooling (SC)'] *\
            (row['SC. Electric space cooling'] -
             row['SC. Electric space cooling base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Electric space cooling'] = 0 if val < 0 else val
        val = row['CAPEX SC. Electricity'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Space cooling'] * row['EP. Electricity (SC)'] * (
                row['SC. Electricity'] - row['SC. Electricity base']) / 1.0e+06
        dfCSV.at[index, 'SC. Cost Electricity'] = 0 if val < 0 else val

        # Water heating
        val = row['CAPEX WH. Solids'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Solids (WH)'] * (
                row['WH. Solids'] - row['WH. Solids base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Solids'] = 0 if val < 0 else val
        val = row['CAPEX WH. LPG'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * \
            row['EP. LPG (WH)'] * (row['WH. LPG'] -
                                   row['WH. LPG base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost LPG'] = 0 if val < 0 else val
        val = row['CAPEX WH. Diesel oil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Diesel oil (WH)'] * (
                row['WH. Diesel oil'] - row['WH. Diesel oil base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Diesel oil'] = 0 if val < 0 else val
        val = row['CAPEX WH. Gas heat pumps'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Gas heat pumps (WH)'] * (
                row['WH. Gas heat pumps'] - row['WH. Gas heat pumps base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Gas heat pumps'] = 0 if val < 0 else val
        val = row['CAPEX WH. Natural gas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Natural gas (WH)'] * (
                row['WH. Natural gas'] - row['WH. Natural gas base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Natural gas'] = 0 if val < 0 else val
        val = row['CAPEX WH. Biomass'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Biomass (WH)'] * (
                row['WH. Biomass'] - row['WH. Biomass base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Biomass'] = 0 if val < 0 else val
        val = row['CAPEX WH. Geothermal'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Geothermal (WH)'] * (
                row['WH. Geothermal'] - row['WH. Geothermal base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Geothermal'] = 0 if val < 0 else val
        val = row['CAPEX WH. Distributed heat'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Distributed heat (WH)'] * (
                row['WH. Distributed heat'] - row['WH. Distributed heat base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Distributed heat'] = 0 if val < 0 else val
        val = row['CAPEX WH. Advanced electric heating'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Advanced electric heating (WH)'] *\
            (row['WH. Advanced electric heating'] -
             row['WH. Advanced electric heating base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Advanced electric heating'] = 0 if val < 0 else val
        val = row['CAPEX WH. Conventional electric heating'] * row['Net heated floor area'] *\
            dfDwellings.at[index, 'Occ. Dwellings'] * row['Water heating'] * row['EP. Conventional electric heating (WH)'] *\
            (row['WH. Conventional electric heating'] -
             row['WH. Conventional electric heating base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Conventional electric heating'] = 0 if val < 0 else val
        val = row['CAPEX WH. BioOil'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. BioOil (WH)'] * (
                row['WH. BioOil'] - row['WH. BioOil base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost BioOil'] = 0 if val < 0 else val
        val = row['CAPEX WH. BioGas'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. BioGas (WH)'] * (
                row['WH. BioGas'] - row['WH. BioGas base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost BioGas'] = 0 if val < 0 else val
        val = row['CAPEX WH. Hydrogen'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Hydrogen (WH)'] * (
                row['WH. Hydrogen'] - row['WH. Hydrogen base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Hydrogen'] = 0 if val < 0 else val
        val = row['CAPEX WH. Solar'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Solar (WH)'] * (
                row['WH. Solar'] - row['WH. Solar base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Solar'] = 0 if val < 0 else val
        val = row['CAPEX WH. Electric space cooling'] * row['Net heated floor area'] *\
            dfDwellings.at[index, 'Occ. Dwellings'] * row['Water heating'] * row['EP. Electric space cooling (WH)'] *\
            (row['WH. Electric space cooling'] -
             row['WH. Electric space cooling base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Electric space cooling'] = 0 if val < 0 else val
        val = row['CAPEX WH. Electricity'] * row['Net heated floor area'] * dfDwellings.at[index, 'Occ. Dwellings'] *\
            row['Water heating'] * row['EP. Electricity (WH)'] * (
                row['WH. Electricity'] - row['WH. Electricity base']) / 1.0e+06
        dfCSV.at[index, 'WH. Cost Electricity'] = 0 if val < 0 else val

    # Finish
    print('Model: Step 17/>  [OK]')
    return dfCSV


# Function: Build. Energy Sim. -> Model -> Step 18 -> Calculate the General Schedule for each archetype
def s18CalculateGeneralSchedule(dfCSV: pd.DataFrame,
                                dfSched: pd.DataFrame,
                                dfTemperatures: pd.DataFrame,
                                dfBaseTemperatures: pd.DataFrame,
                                dfSolarOffice: pd.DataFrame,
                                dfSolarNOffice: pd.DataFrame,
                                nutsId: str) -> dict:
    """Model Step 18: Calculate the General Schedule for each archetype.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfSched (DataFrame): The DataFrame corresponding to Schedule.
        dfTemperatures (DataFrame): The DataFrame corresponding
            to Temperatures.
        dfBaseTemperatures (DataFrame): The DataFrame corresponding
            to Base Temperatures.
        dfSolarOffice (DataFrame): The DataFrame corresponding to Solar Office data.
        dfSolarNOffice (DataFrame): The DataFrame corresponding to Solar Non-Office data.
        nutsId (str): Identifier of NUTS2 region for which the
            analysis will be carried out.
    
    Returns:
        dict

    """

    # Divide the Schedule dataframe by column value
    print('Model: Step 18/>  Dividing the Schedule dataframe by archetypes...')
    dfSchedGroups = dfSched.groupby('Use')

    # Archetype: Apartment block
    dfGenSchedApartmentBlock = dfSchedGroups.get_group('Apartment block')
    dfGenSchedApartmentBlock = dfGenSchedApartmentBlock.reset_index(drop=True)
    dfGenSchedApartmentBlock['Heating'] = dfGenSchedApartmentBlock['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedApartmentBlock['Cooling'] = dfGenSchedApartmentBlock['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedApartmentBlock['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                          'Base Temperature']
    dfGenSchedApartmentBlock['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                          'Base Temperature']
    dfGenSchedApartmentBlock['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedApartmentBlock['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Single family- Terraced houses
    dfGenSchedSingleFamily = dfSchedGroups.get_group(
        'Single family- Terraced houses')
    dfGenSchedSingleFamily = dfGenSchedSingleFamily.reset_index(drop=True)
    dfGenSchedSingleFamily['Heating'] = dfGenSchedSingleFamily['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedSingleFamily['Cooling'] = dfGenSchedSingleFamily['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedSingleFamily['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                        'Base Temperature']
    dfGenSchedSingleFamily['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                        'Base Temperature']
    dfGenSchedSingleFamily['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedSingleFamily['Solar'] = dfSolarNOffice[nutsId[:2].upper()]
    dfGenSchedSingleFamily = dfGenSchedSingleFamily.drop('Use', axis=1)

    # Archetype: Hotels and Restaurants
    dfGenSchedHotels = dfSchedGroups.get_group('Hotels and Restaurants')
    dfGenSchedHotels = dfGenSchedHotels.reset_index(drop=True)
    dfGenSchedHotels['Heating'] = dfGenSchedHotels['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedHotels['Cooling'] = dfGenSchedHotels['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedHotels['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                  'Base Temperature']
    dfGenSchedHotels['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                  'Base Temperature']
    dfGenSchedHotels['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedHotels['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Health
    dfGenSchedHealth = dfSchedGroups.get_group('Health')
    dfGenSchedHealth = dfGenSchedHealth.reset_index(drop=True)
    dfGenSchedHealth['Heating'] = dfGenSchedHealth['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedHealth['Cooling'] = dfGenSchedHealth['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedHealth['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                  'Base Temperature']
    dfGenSchedHealth['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                  'Base Temperature']
    dfGenSchedHealth['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedHealth['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Education
    dfGenSchedEducation = dfSchedGroups.get_group('Education')
    dfGenSchedEducation = dfGenSchedEducation.reset_index(drop=True)
    dfGenSchedEducation['Heating'] = dfGenSchedEducation['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedEducation['Cooling'] = dfGenSchedEducation['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedEducation['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                     'Base Temperature']
    dfGenSchedEducation['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                     'Base Temperature']
    dfGenSchedEducation['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedEducation['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Offices
    dfGenSchedOffices = dfSchedGroups.get_group('Offices')
    dfGenSchedOffices = dfGenSchedOffices.reset_index(drop=True)
    dfGenSchedOffices['Heating'] = dfGenSchedOffices['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedOffices['Cooling'] = dfGenSchedOffices['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedOffices['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                   'Base Temperature']
    dfGenSchedOffices['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                   'Base Temperature']
    dfGenSchedOffices['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedOffices['Solar'] = dfSolarOffice[nutsId[:2].upper()]

    # Archetype: Trade
    dfGenSchedTrade = dfSchedGroups.get_group('Trade')
    dfGenSchedTrade = dfGenSchedTrade.reset_index(drop=True)
    dfGenSchedTrade['Heating'] = dfGenSchedTrade['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedTrade['Cooling'] = dfGenSchedTrade['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedTrade['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                 'Base Temperature']
    dfGenSchedTrade['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                 'Base Temperature']
    dfGenSchedTrade['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedTrade['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Other non-residential buildings
    dfGenSchedOther = dfSchedGroups.get_group(
        'Other non-residential buildings')
    dfGenSchedOther = dfGenSchedOther.reset_index(drop=True)
    dfGenSchedOther['Heating'] = dfGenSchedOther['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedOther['Cooling'] = dfGenSchedOther['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedOther['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                 'Base Temperature']
    dfGenSchedOther['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                 'Base Temperature']
    dfGenSchedOther['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedOther['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    # Archetype: Sport
    dfGenSchedSport = dfSchedGroups.get_group('Sport')
    dfGenSchedSport = dfGenSchedSport.reset_index(drop=True)
    dfGenSchedSport['Heating'] = dfGenSchedSport['Heating'] * \
        dfTemperatures['Heating']
    dfGenSchedSport['Cooling'] = dfGenSchedSport['Cooling'] * \
        dfTemperatures['Cooling']
    dfGenSchedSport['Base Heating Temp'] = dfBaseTemperatures.at[0,
                                                                 'Base Temperature']
    dfGenSchedSport['Base Cooling Temp'] = dfBaseTemperatures.at[1,
                                                                 'Base Temperature']
    dfGenSchedSport['Hourly Temp'] = dfTemperatures['HourlyTemperature']
    dfGenSchedSport['Solar'] = dfSolarNOffice[nutsId[:2].upper()]

    print('Model: Step 18/>  Building the final schedule...')
    dictSchedule = {}
    for index, row in dfCSV.iterrows():
        schedule = None
        if row['Use'] == 'Apartment Block':
            schedule = dfGenSchedApartmentBlock
        elif row['Use'] == 'Single family- Terraced houses':
            schedule = dfGenSchedSingleFamily
        elif row['Use'] == 'Hotels and Restaurants':
            schedule = dfGenSchedHotels
        elif row['Use'] == 'Health':
            schedule = dfGenSchedHealth
        elif row['Use'] == 'Education':
            schedule = dfGenSchedEducation
        elif row['Use'] == 'Offices':
            schedule = dfGenSchedOffices
        elif row['Use'] == 'Trade':
            schedule = dfGenSchedTrade
        elif row['Use'] == 'Other non-residential buildings':
            schedule = dfGenSchedOther
        elif row['Use'] == 'Sport':
            schedule = dfGenSchedSport
        dictSchedule[row['Building ID']] = {
            'use': row['Use'],
            'schedule': schedule
        }

    # Finish
    print('Model: Step 18/>  [OK]')
    return dictSchedule


# Function: Build. Energy Sim. -> Model -> Step 19 -> Calculate the Scenario
def s19CalculateScenario(dfCSV: pd.DataFrame,
                         dictSchedule: dict) -> dict:
    """Model Step 19: Calculate the Scenario.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dictSchedule (dict): The dictionary corresponding to the Schedule. Example::

            {
                "use": "Apartment Block" "schedule": DataFrame,
                "use": "Single family- Terraced houses" "schedule" DataFrame,
                "use": "Offices", "schedule" DataFrame,
                "use": "Education" "schedule": DataFrame,
                "use": "Health", "schedule": DataFrame,
                "use": "Trade", "schedule" DataFrame,
                "use": "Hotels and Restaurants", "schedule" DataFrame,
                "use": "Other non-residential buildings" "schedule" DataFrame,
                "use": "Sport", "schedule": DataFrame
            }
    
    Returns:
        dict

    """

    print('Model: Step 19/>  Calculating the Scenario...')
    for key, dictValue in dictSchedule.items():
        # Concatenate the necessary columns and extract the CSV row to do the calculations
        dictSchedule[key]['schedule'] = pd.concat([dictSchedule[key]['schedule'],
                                                   pd.DataFrame(columns=['D-Heating', 'D-Cooling',
                                                                         'IG-Lighting', 'IG-Equipment', 'IG-Occupancy', 'IG-Solar',
                                                                         'ARL-Heating Ventilation', 'ARL-Cooling Ventilation',
                                                                         'DG-Space Heating', 'DG-Space Cooling', 'DG-Water heating', 'DG-Lighting', 'DG-Appliances', 'DG-Cooking',
                                                                         'FC-Space heating (Solids)-Solids|Coal', 'FC-Space heating (LPG)-Liquids|Gas',
                                                                         'FC-Space heating (Diesel oil)-Liquids|Oil', 'FC-Space heating (Gas heat pumps)-Gases|Gas',
                                                                         'FC-Space heating (Natural gas)-Gases|Gas', 'FC-Space heating (Biomass)-Solids|Biomass',
                                                                         'FC-Space heating (Geothermal)-Electricity', 'FC-Space heating (Distributed heat)-Heat',
                                                                         'FC-Space heating (Advanced electric heating)-Electricity',
                                                                         'FC-Space heating (Conventional electric heating)-Electricity',
                                                                         'FC-Space heating (BioOil)-Liquids|Biomass', 'FC-Space heating (BioGas)-Gases|Biomass',
                                                                         'FC-Space heating (Hydrogen)-Hydrogen', 'FC-Space cooling (Gas heat pumps)-Gases|Gas',
                                                                         'FC-Space cooling (Electric space cooling)-Electricity', 'FC-Water heating (Solids)-Solids|Coal',
                                                                         'FC-Water heating (LPG)-Liquids|Gas', 'FC-Water heating (Diesel oil)-Liquids|Oil',
                                                                         'FC-Water heating (Natural gas)-Gases|Gas', 'FC-Water heating (Biomass)-Solids|Biomass',
                                                                         'FC-Water heating (Geothermal)-Electricity', 'FC-Water heating (Distributed heat)-Heat',
                                                                         'FC-Water heating (Advanced electric heating)-Electricity', 'FC-Water heating (Electricity)-Electricity',
                                                                         'FC-Water heating (Solar)-Heat|Solar', 'FC-Water heating (BioOil)-Liquids|Biomass',
                                                                         'FC-Water heating (BioGas)-Gases|Biomass', 'FC-Water heating (Hydrogen)-Hydrogen',
                                                                         'FC-Cooking (Solids)-Solids|Coal', 'FC-Cooking (LPG)-Liquids|Gas',
                                                                         'FC-Cooking (Natural gas)-Gases|Gas', 'FC-Cooking (Biomass)-Solids|Biomass',
                                                                         'FC-Cooking (Electricity)-Electricity', 'FC-Lighting (Electricity)-Electricity',
                                                                         'FC-Appliances (Electricity)-Electricity'])], axis=1)
        csv = dfCSV[dfCSV['Building ID'] == key]
        dwellingsValue = csv['Occ. Dwellings'].iloc[0] if csv['Sector'].iloc[0] == 'Residential' else 1

        # Demand [KWh] -> 'D-' prefix
        dictSchedule[key]['schedule']['D-Heating'] = csv['D-Factor'].iloc[0] * \
            dictValue['schedule']['HDH'] / 1.0e+03
        dictSchedule[key]['schedule']['D-Cooling'] = csv['D-Factor'].iloc[0] * \
            dictValue['schedule']['CDH'] / 1.0e+03

        # Internal gains [KWh] -> 'IG-' prefix
        dictSchedule[key]['schedule']['IG-Lighting'] = csv['IG-Li-Factor'].iloc[0] * \
            dictValue['schedule']['Lighting'] / 1.0e+03
        dictSchedule[key]['schedule']['IG-Equipment'] = csv['IG-Eq-Factor'].iloc[0] * \
            dictValue['schedule']['Equipment'] / 1.0e+03
        dictSchedule[key]['schedule']['IG-Occupancy'] = csv['IG-Oc-Factor'].iloc[0] * \
            dictValue['schedule']['Occupancy'] / 1.0e+03
        dictSchedule[key]['schedule']['IG-Solar'] = csv['Window Area'].iloc[0] * \
            dictValue['schedule']['Solar'] / 1.0e+03

        # Air Renovation Losses -> 'ARL-' prefix
        dictSchedule[key]['schedule']['ARL-Heating Ventilation'] =\
            csv['ARL-Factor'].iloc[0] * (dictValue['schedule']['Base Heating Temp'] -
                                         dictValue['schedule']['Hourly Temp']) / 1.0e+03
        dictSchedule[key]['schedule']['ARL-Cooling Ventilation'] =\
            csv['ARL-Factor'].iloc[0] * (dictValue['schedule']['Hourly Temp'] -
                                         dictValue['schedule']['Base Cooling Temp']) / 1.0e+03

        # Demand considering Gains -> 'DG-' prefix
        dictSchedule[key]['schedule']['DG-Space Heating'] = (((dictSchedule[key]['schedule']['D-Heating'] +
                                                               dictSchedule[key]['schedule']['ARL-Heating Ventilation'] - dictSchedule[key]['schedule']['IG-Lighting'] -
                                                               dictSchedule[key]['schedule']['IG-Equipment'] - dictSchedule[key]['schedule']['IG-Occupancy'] -
                                                               dictSchedule[key]['schedule']['IG-Solar']) * dictSchedule[key]['schedule']['Heating']) *
                                                             csv['Space heating'].iloc[0]) * dwellingsValue
        dictSchedule[key]['schedule']['DG-Space Heating'] =\
            dictSchedule[key]['schedule']['DG-Space Heating'].apply(
                lambda x: 0 if x < 0 else x)
        dictSchedule[key]['schedule']['DG-Space Cooling'] = ((((dictSchedule[key]['schedule']['D-Cooling'] +
                                                                dictSchedule[key]['schedule']['ARL-Cooling Ventilation'] + dictSchedule[key]['schedule']['IG-Lighting'] +
                                                                dictSchedule[key]['schedule']['IG-Equipment'] + dictSchedule[key]['schedule']['IG-Occupancy'] +
                                                                dictSchedule[key]['schedule']['IG-Solar']) * dictSchedule[key]['schedule']['Cooling']) *
                                                              constants.COOLING_REDUCTION_FACTOR) *
                                                             csv['Space cooling'].iloc[0]) * dwellingsValue
        dictSchedule[key]['schedule']['DG-Space Cooling'] =\
            dictSchedule[key]['schedule']['DG-Space Cooling'].apply(
                lambda x: 0 if x < 0 else x)
        dictSchedule[key]['schedule']['DG-Water heating'] = (dictSchedule[key]['schedule']['DHW'] *
                                                             csv['Net heated floor area'].iloc[0] * csv['DHW demand [KW/m2·year]'].iloc[0] /
                                                             dictSchedule[key]['schedule']['DHW'].sum()) * csv['Water heating'].iloc[0] * dwellingsValue
        dictSchedule[key]['schedule']['DG-Water heating'] =\
            dictSchedule[key]['schedule']['DG-Water heating'].apply(
                lambda x: 0 if x < 0 else x)
        dictSchedule[key]['schedule']['DG-Lighting'] = dictSchedule[key]['schedule']['IG-Lighting'] *\
            csv['Lighting'].iloc[0] * dwellingsValue
        dictSchedule[key]['schedule']['DG-Lighting'] =\
            dictSchedule[key]['schedule']['DG-Lighting'].apply(
                lambda x: 0 if x < 0 else x)
        dictSchedule[key]['schedule']['DG-Appliances'] = dictSchedule[key]['schedule']['IG-Equipment'] *\
            csv['Appliances'].iloc[0] * dwellingsValue
        dictSchedule[key]['schedule']['DG-Appliances'] =\
            dictSchedule[key]['schedule']['DG-Appliances'].apply(
                lambda x: 0 if x < 0 else x)
        dictSchedule[key]['schedule']['DG-Cooking'] = (dictSchedule[key]['schedule']['Cooking'] *
                                                       csv['Net heated floor area'].iloc[0] * csv['Cooking [KW/m2·year]'].iloc[0] / dictSchedule[key]['schedule']['Cooking'].sum()) *\
            csv['Cooking'].iloc[0] * dwellingsValue
        dictSchedule[key]['schedule']['DG-Cooking'] =\
            dictSchedule[key]['schedule']['DG-Cooking'].apply(
                lambda x: 0 if x < 0 else x)

        # Final consumption -> 'FC-' prefix
        dictSchedule[key]['schedule']['FC-Space heating (Solids)-Solids|Coal'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Solids']).iloc[0] / csv['Eff. SH. Solids'].iloc[0]\
            if csv['Eff. SH. Solids'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Solids)-Solids|Coal'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Solids)-Solids|Coal'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (LPG)-Liquids|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. LPG']).iloc[0] / csv['Eff. SH. LPG'].iloc[0]\
            if csv['Eff. SH. LPG'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (LPG)-Liquids|Gas'] =\
            dictSchedule[key]['schedule']['FC-Space heating (LPG)-Liquids|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Diesel oil']).iloc[0] / csv['Eff. SH. Diesel oil'].iloc[0]\
            if csv['Eff. SH. Diesel oil'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Gas heat pumps'].iloc[0]) / csv['Eff. SH. Gas heat pumps'].iloc[0]\
            if csv['Eff. SH. Gas heat pumps'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Natural gas)-Gases|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Natural gas'].iloc[0]) / csv['Eff. SH. Natural gas'].iloc[0]\
            if csv['Eff. SH. Natural gas'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Natural gas)-Gases|Gas'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Natural gas)-Gases|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Biomass)-Solids|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Biomass'].iloc[0]) / csv['Eff. SH. Biomass'].iloc[0]\
            if csv['Eff. SH. Biomass'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Biomass)-Solids|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Biomass)-Solids|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Geothermal)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Geothermal'].iloc[0]) / csv['Eff. SH. Geothermal'].iloc[0]\
            if csv['Eff. SH. Geothermal'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Geothermal)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Geothermal)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Distributed heat)-Heat'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Distributed heat'].iloc[0]) /\
            csv['Eff. SH. Distributed heat'].iloc[0]\
            if csv['Eff. SH. Distributed heat'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Distributed heat)-Heat'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Distributed heat)-Heat'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Advanced electric heating)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Advanced electric heating'].iloc[0]) /\
            csv['Eff. SH. Advanced electric heating'].iloc[0]\
            if csv['Eff. SH. Advanced electric heating'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Advanced electric heating)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Advanced electric heating)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Conventional electric heating)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Conventional electric heating'].iloc[0]) /\
            csv['Eff. SH. Conventional electric heating'].iloc[0]\
            if csv['Eff. SH. Conventional electric heating'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Conventional electric heating)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Conventional electric heating)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (BioOil)-Liquids|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. BioOil'].iloc[0]) / csv['Eff. SH. BioOil'].iloc[0]\
            if csv['Eff. SH. BioOil'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (BioOil)-Liquids|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Space heating (BioOil)-Liquids|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (BioGas)-Gases|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. BioGas'].iloc[0]) / csv['Eff. SH. BioGas'].iloc[0]\
            if csv['Eff. SH. BioGas'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (BioGas)-Gases|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Space heating (BioGas)-Gases|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space heating (Hydrogen)-Hydrogen'] =\
            (dictSchedule[key]['schedule']['DG-Space Heating'] * csv['SH. Hydrogen'].iloc[0]) / csv['Eff. SH. Hydrogen'].iloc[0]\
            if csv['Eff. SH. Hydrogen'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space heating (Hydrogen)-Hydrogen'] =\
            dictSchedule[key]['schedule']['FC-Space heating (Hydrogen)-Hydrogen'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Space Cooling'] * csv['SC. Gas heat pumps'].iloc[0]) /\
            csv['Eff. SC. Gas heat pumps'].iloc[0]\
            if csv['Eff. SC. Gas heat pumps'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas'] =\
            dictSchedule[key]['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Space cooling (Electric space cooling)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Space Cooling'] * csv['SC. Electric space cooling'].iloc[0]) /\
            csv['Eff. SC. Electric space cooling'].iloc[0]\
            if csv['Eff. SC. Electric space cooling'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Space cooling (Electric space cooling)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Space cooling (Electric space cooling)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Solids)-Solids|Coal'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Solids'].iloc[0]) / csv['Eff. WH. Solids'].iloc[0]\
            if csv['Eff. WH. Solids'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Solids)-Solids|Coal'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Solids)-Solids|Coal'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (LPG)-Liquids|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. LPG'].iloc[0]) / csv['Eff. WH. LPG'].iloc[0]\
            if csv['Eff. WH. LPG'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (LPG)-Liquids|Gas'] =\
            dictSchedule[key]['schedule']['FC-Water heating (LPG)-Liquids|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Diesel oil'].iloc[0]) / csv['Eff. WH. Diesel oil'].iloc[0]\
            if csv['Eff. WH. Diesel oil'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Natural gas)-Gases|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Natural gas'].iloc[0]) / csv['Eff. WH. Natural gas'].iloc[0]\
            if csv['Eff. WH. Natural gas'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Natural gas)-Gases|Gas'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Natural gas)-Gases|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Biomass)-Solids|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Biomass'].iloc[0]) / csv['Eff. WH. Biomass'].iloc[0]\
            if csv['Eff. WH. Biomass'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Biomass)-Solids|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Biomass)-Solids|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Geothermal)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Geothermal'].iloc[0]) / csv['Eff. WH. Geothermal'].iloc[0]\
            if csv['Eff. WH. Geothermal'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Geothermal)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Geothermal)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Distributed heat)-Heat'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Distributed heat'].iloc[0]) /\
            csv['Eff. WH. Distributed heat'].iloc[0]\
            if csv['Eff. WH. Distributed heat'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Distributed heat)-Heat'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Distributed heat)-Heat'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Advanced electric heating)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Advanced electric heating'].iloc[0]) /\
            csv['Eff. WH. Advanced electric heating'].iloc[0]\
            if csv['Eff. WH. Advanced electric heating'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Advanced electric heating)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Advanced electric heating)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Electricity)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Electricity'].iloc[0]) / csv['Eff. WH. Electricity'].iloc[0]\
            if csv['Eff. WH. Electricity'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Electricity)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Electricity)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Solar)-Heat|Solar'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Solar'].iloc[0]) / csv['Eff. WH. Solar'].iloc[0]\
            if csv['Eff. WH. Solar'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Solar)-Heat|Solar'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Solar)-Heat|Solar'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (BioOil)-Liquids|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. BioOil'].iloc[0]) / csv['Eff. WH. BioOil'].iloc[0]\
            if csv['Eff. WH. BioOil'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (BioOil)-Liquids|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Water heating (BioOil)-Liquids|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (BioGas)-Gases|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. BioGas'].iloc[0]) / csv['Eff. WH. BioGas'].iloc[0]\
            if csv['Eff. WH. BioGas'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (BioGas)-Gases|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Water heating (BioGas)-Gases|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Water heating (Hydrogen)-Hydrogen'] =\
            (dictSchedule[key]['schedule']['DG-Water heating'] * csv['WH. Hydrogen'].iloc[0]) / csv['Eff. WH. Hydrogen'].iloc[0]\
            if csv['Eff. WH. Hydrogen'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Water heating (Hydrogen)-Hydrogen'] =\
            dictSchedule[key]['schedule']['FC-Water heating (Hydrogen)-Hydrogen'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Cooking (Solids)-Solids|Coal'] =\
            (dictSchedule[key]['schedule']['DG-Cooking'] * csv['C. Solids'].iloc[0]) / csv['Eff. C. Solids'].iloc[0]\
            if csv['Eff. C. Solids'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Cooking (Solids)-Solids|Coal'] =\
            dictSchedule[key]['schedule']['FC-Cooking (Solids)-Solids|Coal'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Cooking (LPG)-Liquids|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Cooking'] * csv['C. LPG'].iloc[0]) / csv['Eff. C. LPG'].iloc[0]\
            if csv['Eff. C. LPG'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Cooking (LPG)-Liquids|Gas'] =\
            dictSchedule[key]['schedule']['FC-Cooking (LPG)-Liquids|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Cooking (Natural gas)-Gases|Gas'] =\
            (dictSchedule[key]['schedule']['DG-Cooking'] * csv['C. Natural gas'].iloc[0]) / csv['Eff. C. Natural gas'].iloc[0]\
            if csv['Eff. C. Natural gas'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Cooking (Natural gas)-Gases|Gas'] =\
            dictSchedule[key]['schedule']['FC-Cooking (Natural gas)-Gases|Gas'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Cooking (Biomass)-Solids|Biomass'] =\
            (dictSchedule[key]['schedule']['DG-Cooking'] * csv['C. Biomass'].iloc[0]) / csv['Eff. C. Biomass'].iloc[0]\
            if csv['Eff. C. Biomass'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Cooking (Biomass)-Solids|Biomass'] =\
            dictSchedule[key]['schedule']['FC-Cooking (Biomass)-Solids|Biomass'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Cooking (Electricity)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Cooking'] * csv['C. Electricity'].iloc[0]) / csv['Eff. C. Electricity'].iloc[0]\
            if csv['Eff. C. Electricity'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Cooking (Electricity)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Cooking (Electricity)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Lighting (Electricity)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Lighting'] * csv['L. Electricity'].iloc[0]) / csv['Eff. L. Electricity'].iloc[0]\
            if csv['Eff. L. Electricity'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Lighting (Electricity)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Lighting (Electricity)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)
        dictSchedule[key]['schedule']['FC-Appliances (Electricity)-Electricity'] =\
            (dictSchedule[key]['schedule']['DG-Appliances'] * csv['A. Electricity'].iloc[0]) / csv['Eff. A. Electricity'].iloc[0]\
            if csv['Eff. A. Electricity'].iloc[0] != 0 else 0
        dictSchedule[key]['schedule']['FC-Appliances (Electricity)-Electricity'] =\
            dictSchedule[key]['schedule']['FC-Appliances (Electricity)-Electricity'].apply(
                lambda x: 0 if (x < 0 or pd.isna(x)) else x)

    # Finish
    print('Model: Step 19/>  [OK]')
    return dictSchedule


# Function: Build. Energy Sim. -> Model -> Step 20 -> Calculate the Anual Results
def s20CalculateAnualResults(dfCSV: pd.DataFrame,
                             dictSchedule: dict) -> pd.DataFrame:
    """Model Step 20: Calculate the Anual Results.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dictSchedule (dict): The dictionary corresponding to the Schedule. Example::

            {
                "use": "Apartment Block" "schedule": DataFrame,
                "use": "Single family- Terraced houses" "schedule" DataFrame,
                "use": "Offices", "schedule" DataFrame,
                "use": "Education" "schedule": DataFrame,
                "use": "Health", "schedule": DataFrame,
                "use": "Trade", "schedule" DataFrame,
                "use": "Hotels and Restaurants", "schedule" DataFrame,
                "use": "Other non-residential buildings" "schedule" DataFrame,
                "use": "Sport", "schedule": DataFrame
            }
    
    Returns:
        DataFrame

    """

    # Create the Anual Results dataframe
    print('Model: Step 20/>  Building the Anual Results dataframe...')
    dfAnualResults = dfCSV[['Building ID', 'Use', 'Age', 'Period', 'Sector',
                            'Ref%', 'Ref Level', 'Footprint Area', 'Opaque fachade area', 'Window Area',
                            'RFC Cost Low Wall', 'RFC Cost Medium Wall', 'RFC Cost High Wall',
                            'RFC Cost Low Roof', 'RFC Cost Medium Roof', 'RFC Cost High Roof',
                            'RFC Cost Low Window', 'RFC Cost Medium Window', 'RFC Cost High Window',
                            'SH. Cost Solids', 'SH. Cost LPG', 'SH. Cost Diesel oil', 'SH. Cost Gas heat pumps', 'SH. Cost Natural gas',
                            'SH. Cost Biomass', 'SH. Cost Geothermal', 'SH. Cost Distributed heat', 'SH. Cost Advanced electric heating',
                            'SH. Cost Conventional electric heating', 'SH. Cost BioOil', 'SH. Cost BioGas', 'SH. Cost Hydrogen', 'SH. Cost Solar',
                            'SH. Cost Electric space cooling', 'SH. Cost Electricity',
                            'SC. Cost Solids', 'SC. Cost LPG', 'SC. Cost Diesel oil', 'SC. Cost Gas heat pumps', 'SC. Cost Natural gas',
                            'SC. Cost Biomass', 'SC. Cost Geothermal', 'SC. Cost Distributed heat', 'SC. Cost Advanced electric heating',
                            'SC. Cost Conventional electric heating', 'SC. Cost BioOil', 'SC. Cost BioGas', 'SC. Cost Hydrogen', 'SC. Cost Solar',
                            'SC. Cost Electric space cooling', 'SC. Cost Electricity',
                            'WH. Cost Solids', 'WH. Cost LPG', 'WH. Cost Diesel oil', 'WH. Cost Gas heat pumps', 'WH. Cost Natural gas',
                            'WH. Cost Biomass', 'WH. Cost Geothermal', 'WH. Cost Distributed heat', 'WH. Cost Advanced electric heating',
                            'WH. Cost Conventional electric heating', 'WH. Cost BioOil', 'WH. Cost BioGas', 'WH. Cost Hydrogen', 'WH. Cost Solar',
                            'WH. Cost Electric space cooling', 'WH. Cost Electricity']]
    dfAnualResults = pd.concat([dfAnualResults, pd.DataFrame(columns=['Heating demand [KWh]',
                                                                      'Cooling demand [KWh]', 'DHW demand [KWh]', 'Cooking demand [KWh]', 'Lighting demand [KWh]',
                                                                      'Equipment demand [KWh]', 'Heating consumption [KWh]', 'Cooling consumption [KWh]',
                                                                      'DHW consumption [KWh]', 'Cooking consumption [KWh]', 'Lighting consumption [KWh]',
                                                                      'Equipment consumption [KWh]', 'CAPEX Passive measures [M€]', 'CAPEX Active measures [M€]'])], axis=1)

    for index, row in dfAnualResults.iterrows():
        dfAnualResults.at[index, 'Heating demand [KWh]'] = dictSchedule[row['Building ID']
                                                                        ]['schedule']['DG-Space Heating'].sum()
        dfAnualResults.at[index, 'Cooling demand [KWh]'] = dictSchedule[row['Building ID']
                                                                        ]['schedule']['DG-Space Cooling'].sum()
        dfAnualResults.at[index, 'DHW demand [KWh]'] = dictSchedule[row['Building ID']
                                                                    ]['schedule']['DG-Water heating'].sum()
        dfAnualResults.at[index, 'Cooking demand [KWh]'] = dictSchedule[row['Building ID']
                                                                        ]['schedule']['DG-Cooking'].sum()
        dfAnualResults.at[index, 'Lighting demand [KWh]'] = dictSchedule[row['Building ID']
                                                                         ]['schedule']['DG-Lighting'].sum()
        dfAnualResults.at[index, 'Equipment demand [KWh]'] = dictSchedule[row['Building ID']
                                                                          ]['schedule']['DG-Appliances'].sum()
        dfAnualResults.at[index, 'Heating consumption [KWh]'] =\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Solids)-Solids|Coal'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (LPG)-Liquids|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Natural gas)-Gases|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Biomass)-Solids|Biomass'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Geothermal)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Distributed heat)-Heat'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Advanced electric heating)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (Conventional electric heating)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (BioOil)-Liquids|Biomass'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Space heating (BioGas)-Gases|Biomass'].sum() +\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Space heating (Hydrogen)-Hydrogen'].sum()
        dfAnualResults.at[index, 'Cooling consumption [KWh]'] =\
            dictSchedule[row['Building ID']]['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas'].sum() +\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Space cooling (Electric space cooling)-Electricity'].sum()
        dfAnualResults.at[index, 'DHW consumption [KWh]'] =\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Solids)-Solids|Coal'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (LPG)-Liquids|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Natural gas)-Gases|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Biomass)-Solids|Biomass'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Geothermal)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Distributed heat)-Heat'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Advanced electric heating)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Electricity)-Electricity'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (Solar)-Heat|Solar'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (BioOil)-Liquids|Biomass'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Water heating (BioGas)-Gases|Biomass'].sum() +\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Water heating (Hydrogen)-Hydrogen'].sum()
        dfAnualResults.at[index, 'Cooking consumption [KWh]'] =\
            dictSchedule[row['Building ID']]['schedule']['FC-Cooking (Solids)-Solids|Coal'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Cooking (LPG)-Liquids|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Cooking (Natural gas)-Gases|Gas'].sum() +\
            dictSchedule[row['Building ID']]['schedule']['FC-Cooking (Biomass)-Solids|Biomass'].sum() +\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Cooking (Electricity)-Electricity'].sum()
        dfAnualResults.at[index, 'Lighting consumption [KWh]'] =\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Lighting (Electricity)-Electricity'].sum()
        dfAnualResults.at[index, 'Equipment consumption [KWh]'] =\
            dictSchedule[row['Building ID']
                         ]['schedule']['FC-Appliances (Electricity)-Electricity'].sum()
        dfAnualResults.at[index, 'CAPEX Passive measures [M€]'] = row['Ref%'] * (row['Footprint Area'] *
                                                                                 row['RFC Cost ' + (row['Ref Level']) + ' Roof'] + row['Opaque fachade area'] *
                                                                                 row['RFC Cost ' + (row['Ref Level']) + ' Wall'] + row['Window Area'] *
                                                                                 row['RFC Cost ' + (row['Ref Level']) + ' Window']) / 1000000
        dfAnualResults.at[index, 'CAPEX Active measures [M€]'] = row['SH. Cost Solids'] + row['SH. Cost LPG'] + row['SH. Cost Diesel oil'] +\
            row['SH. Cost Gas heat pumps'] + row['SH. Cost Natural gas'] + row['SH. Cost Biomass'] + row['SH. Cost Geothermal'] +\
            row['SH. Cost Distributed heat'] + row['SH. Cost Advanced electric heating'] + row['SH. Cost Conventional electric heating'] +\
            row['SH. Cost BioOil'] + row['SH. Cost BioGas'] + row['SH. Cost Hydrogen'] + row['SH. Cost Solar'] +\
            row['SH. Cost Electric space cooling'] + row['SH. Cost Electricity'] + row['SC. Cost Solids'] + row['SC. Cost LPG'] +\
            row['SC. Cost Diesel oil'] + row['SC. Cost Gas heat pumps'] + row['SC. Cost Natural gas'] + row['SC. Cost Biomass'] +\
            row['SC. Cost Geothermal'] + row['SC. Cost Distributed heat'] + row['SC. Cost Advanced electric heating'] +\
            row['SC. Cost Conventional electric heating'] + row['SC. Cost BioOil'] + row['SC. Cost BioGas'] + row['SC. Cost Hydrogen'] +\
            row['SC. Cost Solar'] + row['SC. Cost Electric space cooling'] + row['SC. Cost Electricity'] + row['WH. Cost Solids'] +\
            row['WH. Cost LPG'] + row['WH. Cost Diesel oil'] + row['WH. Cost Gas heat pumps'] + row['WH. Cost Natural gas'] +\
            row['WH. Cost Biomass'] + row['WH. Cost Geothermal'] + row['WH. Cost Distributed heat'] +\
            row['WH. Cost Advanced electric heating'] + row['WH. Cost Conventional electric heating'] + row['WH. Cost BioOil'] +\
            row['WH. Cost BioGas'] + row['WH. Cost Hydrogen'] + row['WH. Cost Solar'] + row['WH. Cost Electric space cooling'] +\
            row['WH. Cost Electricity']

    # Remove extra columns
    print('Model: Step 20/>  Cleaning the Anual Results dataframe')
    dfAnualResults = dfAnualResults.drop(columns=['Ref%', 'Ref Level', 'Footprint Area',
                                                  'Opaque fachade area', 'Window Area', 'RFC Cost Low Wall', 'RFC Cost Medium Wall', 'RFC Cost High Wall', 'RFC Cost Low Roof',
                                                  'RFC Cost Medium Roof', 'RFC Cost High Roof', 'RFC Cost Low Window', 'RFC Cost Medium Window', 'RFC Cost High Window',
                                                  'SH. Cost Solids', 'SH. Cost LPG', 'SH. Cost Diesel oil', 'SH. Cost Gas heat pumps', 'SH. Cost Natural gas', 'SH. Cost Biomass',
                                                  'SH. Cost Geothermal', 'SH. Cost Distributed heat', 'SH. Cost Advanced electric heating', 'SH. Cost Conventional electric heating',
                                                  'SH. Cost BioOil', 'SH. Cost BioGas', 'SH. Cost Hydrogen', 'SH. Cost Solar', 'SH. Cost Electric space cooling',
                                                  'SH. Cost Electricity', 'SC. Cost Solids', 'SC. Cost LPG', 'SC. Cost Diesel oil', 'SC. Cost Gas heat pumps', 'SC. Cost Natural gas',
                                                  'SC. Cost Biomass', 'SC. Cost Geothermal', 'SC. Cost Distributed heat', 'SC. Cost Advanced electric heating',
                                                  'SC. Cost Conventional electric heating', 'SC. Cost BioOil', 'SC. Cost BioGas', 'SC. Cost Hydrogen', 'SC. Cost Solar',
                                                  'SC. Cost Electric space cooling', 'SC. Cost Electricity', 'WH. Cost Solids', 'WH. Cost LPG', 'WH. Cost Diesel oil',
                                                  'WH. Cost Gas heat pumps', 'WH. Cost Natural gas', 'WH. Cost Biomass', 'WH. Cost Geothermal', 'WH. Cost Distributed heat',
                                                  'WH. Cost Advanced electric heating', 'WH. Cost Conventional electric heating', 'WH. Cost BioOil', 'WH. Cost BioGas',
                                                  'WH. Cost Hydrogen', 'WH. Cost Solar', 'WH. Cost Electric space cooling', 'WH. Cost Electricity'])

    # Save to Excel (if allowed)
    if constants.SAVE_RESULT_ALLOWED:
        with pd.ExcelWriter('temporary/result.xlsx') as writer:
            dfAnualResults.to_excel(
                writer, sheet_name='Anual Results', index=False)

    # Finish
    print('Model: Step 20/>  [OK]')
    return dfAnualResults


# Function: Build. Energy Sim. -> Model -> Step 21 -> Calculate the Consolidate
def s21CalculateConsolidate(dictSchedule: dict,
                            archetype: str) -> pd.DataFrame:
    """Model Step 21: Calculate the Consolidate.

    Args:
        dictSchedule (dict): The dictionary corresponding to the Schedule. Example::

            {
                "use": "Apartment Block" "schedule": DataFrame,
                "use": "Single family- Terraced houses" "schedule" DataFrame,
                "use": "Offices", "schedule" DataFrame,
                "use": "Education" "schedule": DataFrame,
                "use": "Health", "schedule": DataFrame,
                "use": "Trade", "schedule" DataFrame,
                "use": "Hotels and Restaurants", "schedule" DataFrame,
                "use": "Other non-residential buildings" "schedule" DataFrame,
                "use": "Sport", "schedule": DataFrame
            }
        
        archetype (str): The name of the archetype (building use).
    
    Returns:
        DataFrame

    """

    # Create the Consolidated dataframe
    print('Model: Step 21/>  Building the Consolidated (' +
          archetype + ') dataframe...')
    dfConsolidated = pd.DataFrame(0.0, columns=['Solids|Coal (Space Heating)', 'Liquids|Gas (Space Heating)',
                                                'Liquids|Oil (Space Heating)', 'Gases|Gas (Space Heating)', 'Solids|Biomass (Space Heating)',
                                                'Electricity (Space Heating)', 'Heat (Space Heating)', 'Liquids|Biomass (Space Heating)',
                                                'Gases|Biomass (Space Heating)', 'Hydrogen (Space Heating)', 'Heat|Solar (Space Heating)',
                                                'Solids|Coal (Space Cooling)', 'Liquids|Gas (Space Cooling)', 'Liquids|Oil (Space Cooling)', 'Gases|Gas (Space Cooling)',
                                                'Solids|Biomass (Space Cooling)', 'Electricity (Space Cooling)', 'Heat (Space Cooling)', 'Liquids|Biomass (Space Cooling)',
                                                'Gases|Biomass (Space Cooling)', 'Hydrogen (Space Cooling)', 'Heat|Solar (Space Cooling)',
                                                'Solids|Coal (Water Heating)', 'Liquids|Gas (Water Heating)', 'Liquids|Oil (Water Heating)', 'Gases|Gas (Water Heating)',
                                                'Solids|Biomass (Water Heating)', 'Electricity (Water Heating)', 'Heat (Water Heating)', 'Liquids|Biomass (Water Heating)',
                                                'Gases|Biomass (Water Heating)', 'Hydrogen (Water Heating)', 'Heat|Solar (Water Heating)',
                                                'Solids|Coal (Lighting)', 'Liquids|Gas (Lighting)', 'Liquids|Oil (Lighting)', 'Gases|Gas (Lighting)',
                                                'Solids|Biomass (Lighting)', 'Electricity (Lighting)', 'Heat (Lighting)', 'Liquids|Biomass (Lighting)',
                                                'Gases|Biomass (Lighting)', 'Hydrogen (Lighting)', 'Heat|Solar (Lighting)',
                                                'Solids|Coal (Appliances)', 'Liquids|Gas (Appliances)', 'Liquids|Oil (Appliances)', 'Gases|Gas (Appliances)',
                                                'Solids|Biomass (Appliances)', 'Electricity (Appliances)', 'Heat (Appliances)', 'Liquids|Biomass (Appliances)',
                                                'Gases|Biomass (Appliances)', 'Hydrogen (Appliances)', 'Heat|Solar (Appliances)',
                                                'Solids|Coal (Cooking)', 'Liquids|Gas (Cooking)', 'Liquids|Oil (Cooking)', 'Gases|Gas (Cooking)',
                                                'Solids|Biomass (Cooking)', 'Electricity (Cooking)', 'Heat (Cooking)', 'Liquids|Biomass (Cooking)',
                                                'Gases|Biomass (Cooking)', 'Hydrogen (Cooking)', 'Heat|Solar (Cooking)'], index=range(8760))

    for key, dictValue in dictSchedule.items():
        if dictValue['use'] == archetype:
            if not 'Datetime' in dfConsolidated:
                dfConsolidated.insert(
                    0, 'Datetime', dictValue['schedule']['Datetime'])
                dfConsolidated.insert(0, 'Building Type', dictValue['use'])
                dfConsolidated.iloc[:, 2:] = 0.0

            # Space heating
            dfConsolidated['Solids|Coal (Space Heating)'] += dictValue['schedule']['FC-Space heating (Solids)-Solids|Coal']
            dfConsolidated['Liquids|Gas (Space Heating)'] += dictValue['schedule']['FC-Space heating (LPG)-Liquids|Gas']
            dfConsolidated['Liquids|Oil (Space Heating)'] += dictValue['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil']
            dfConsolidated['Gases|Gas (Space Heating)'] += dictValue['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'] +\
                dictValue['schedule']['FC-Space heating (Natural gas)-Gases|Gas']
            dfConsolidated['Solids|Biomass (Space Heating)'] += dictValue['schedule']['FC-Space heating (Biomass)-Solids|Biomass']
            dfConsolidated['Electricity (Space Heating)'] += dictValue['schedule']['FC-Space heating (Geothermal)-Electricity'] +\
                dictValue['schedule']['FC-Space heating (Advanced electric heating)-Electricity'] +\
                dictValue['schedule']['FC-Space heating (Conventional electric heating)-Electricity']
            dfConsolidated['Heat (Space Heating)'] += dictValue['schedule']['FC-Space heating (Distributed heat)-Heat']
            dfConsolidated['Liquids|Biomass (Space Heating)'] += dictValue['schedule']['FC-Space heating (BioOil)-Liquids|Biomass']
            dfConsolidated['Gases|Biomass (Space Heating)'] += dictValue['schedule']['FC-Space heating (BioGas)-Gases|Biomass']
            dfConsolidated['Hydrogen (Space Heating)'] += dictValue['schedule']['FC-Space heating (Hydrogen)-Hydrogen']

            # Space cooling
            dfConsolidated['Gases|Gas (Space Cooling)'] += dictValue['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas']
            dfConsolidated['Electricity (Space Cooling)'] += dictValue['schedule']['FC-Space cooling (Electric space cooling)-Electricity']

            # Water heating
            dfConsolidated['Solids|Coal (Water Heating)'] += dictValue['schedule']['FC-Water heating (Solids)-Solids|Coal']
            dfConsolidated['Liquids|Gas (Water Heating)'] += dictValue['schedule']['FC-Water heating (LPG)-Liquids|Gas']
            dfConsolidated['Liquids|Oil (Water Heating)'] += dictValue['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil']
            dfConsolidated['Gases|Gas (Water Heating)'] += dictValue['schedule']['FC-Water heating (Natural gas)-Gases|Gas']
            dfConsolidated['Solids|Biomass (Water Heating)'] += dictValue['schedule']['FC-Water heating (Biomass)-Solids|Biomass']
            dfConsolidated['Electricity (Water Heating)'] += dictValue['schedule']['FC-Water heating (Geothermal)-Electricity'] +\
                dictValue['schedule']['FC-Water heating (Advanced electric heating)-Electricity'] +\
                dictValue['schedule']['FC-Water heating (Electricity)-Electricity']
            dfConsolidated['Heat (Water Heating)'] += dictValue['schedule']['FC-Water heating (Distributed heat)-Heat']
            dfConsolidated['Heat|Solar (Water Heating)'] += dictValue['schedule']['FC-Water heating (Solar)-Heat|Solar']
            dfConsolidated['Liquids|Biomass (Water Heating)'] += dictValue['schedule']['FC-Water heating (BioOil)-Liquids|Biomass']
            dfConsolidated['Gases|Biomass (Water Heating)'] += dictValue['schedule']['FC-Water heating (BioGas)-Gases|Biomass']
            dfConsolidated['Hydrogen (Water Heating)'] += dictValue['schedule']['FC-Water heating (Hydrogen)-Hydrogen']

            # Lighting and Appliances
            dfConsolidated['Electricity (Lighting)'] += dictValue['schedule']['FC-Lighting (Electricity)-Electricity']
            dfConsolidated['Electricity (Appliances)'] += dictValue['schedule']['FC-Appliances (Electricity)-Electricity']

            # Cooking
            dfConsolidated['Solids|Coal (Cooking)'] += dictValue['schedule']['FC-Cooking (Solids)-Solids|Coal']
            dfConsolidated['Liquids|Gas (Cooking)'] += dictValue['schedule']['FC-Cooking (LPG)-Liquids|Gas']
            dfConsolidated['Gases|Gas (Cooking)'] += dictValue['schedule']['FC-Cooking (Natural gas)-Gases|Gas']
            dfConsolidated['Solids|Biomass (Cooking)'] += dictValue['schedule']['FC-Cooking (Biomass)-Solids|Biomass']
            dfConsolidated['Electricity (Cooking)'] += dictValue['schedule']['FC-Cooking (Electricity)-Electricity']

    # Save to Excel (if allowed)
    if constants.SAVE_RESULT_ALLOWED:
        with pd.ExcelWriter('temporary/result.xlsx', mode='a') as writer:
            dfConsolidated.to_excel(writer,
                                    sheet_name='Consolidated (' + archetype[:4] + '.)',
                                    index=False)

    # Finish
    print('Model: Step 21/>  [OK]')
    return dfConsolidated


# Function: Build. Energy Sim. -> Model -> Step 22 -> Calculate the Hourly Results
def s22CalculateHourlyResults(dfCSV: pd.DataFrame,
                              dfSolar: pd.DataFrame,
                              dictSchedule: dict,
                              archetype: str) -> pd.DataFrame:
    """Model Step 22: Calculate the Hourly Results.

    Args:
        dfCSV (DataFrame): The built input data DataFrame.
        dfSolar (DataFrame): The solar data DataFrame.
        dictSchedule (dict): The dictionary corresponding to the Schedule. Example::

            {
                "use": "Apartment Block" "schedule": DataFrame,
                "use": "Single family- Terraced houses" "schedule" DataFrame,
                "use": "Offices", "schedule" DataFrame,
                "use": "Education" "schedule": DataFrame,
                "use": "Health", "schedule": DataFrame,
                "use": "Trade", "schedule" DataFrame,
                "use": "Hotels and Restaurants", "schedule" DataFrame,
                "use": "Other non-residential buildings" "schedule" DataFrame,
                "use": "Sport", "schedule": DataFrame
            }
        
        archetype (str): The name of the archetype (building use).
    
    Returns:
        DataFrame

    """

    # Create the Hourly Results dataframe
    print('Model: Step 22/>  Building the Hourly Results (' +
          archetype + ') dataframe...')
    dfHourlyResults = pd.DataFrame(0.0, columns=['Solids|Coal', 'Liquids|Gas', 'Liquids|Oil',
                                                 'Gases|Gas', 'Solids|Biomass', 'Electricity', 'Heat', 'Liquids|Biomass', 'Gases|Biomass', 'Hydrogen',
                                                 'Heat|Solar', 'Variable cost [€/KWh]', 'Emissions [kgCO2/KWh]'], index=range(8760))

    for key, dictValue in dictSchedule.items():
        if dictValue['use'] == archetype:
            if not 'Datetime' in dfHourlyResults:
                dfHourlyResults.insert(0,
                                       'Datetime',
                                       dictValue['schedule']['Datetime'])
                dfHourlyResults.insert(0,
                                       'Building Type',
                                       dictValue['use'])
                dfHourlyResults.iloc[:, 2:] = 0.0

            # Solids|Coal
            solidsCoal = dictValue['schedule']['FC-Space heating (Solids)-Solids|Coal'] +\
                dictValue['schedule']['FC-Water heating (Solids)-Solids|Coal'] +\
                dictValue['schedule']['FC-Cooking (Solids)-Solids|Coal']
            dfHourlyResults['Solids|Coal'] += solidsCoal

            # Liquids|Gas
            liquidsGas = dictValue['schedule']['FC-Space heating (LPG)-Liquids|Gas'] +\
                dictValue['schedule']['FC-Water heating (LPG)-Liquids|Gas'] +\
                dictValue['schedule']['FC-Cooking (LPG)-Liquids|Gas']
            dfHourlyResults['Liquids|Gas'] += liquidsGas

            # Liquids|Oil
            liquidsOil = dictValue['schedule']['FC-Space heating (Diesel oil)-Liquids|Oil'] +\
                dictValue['schedule']['FC-Water heating (Diesel oil)-Liquids|Oil']
            dfHourlyResults['Liquids|Oil'] += liquidsOil

            # Gases|Gas
            gasesGas = dictValue['schedule']['FC-Space heating (Gas heat pumps)-Gases|Gas'] +\
                dictValue['schedule']['FC-Space heating (Natural gas)-Gases|Gas'] +\
                dictValue['schedule']['FC-Space cooling (Gas heat pumps)-Gases|Gas'] +\
                dictValue['schedule']['FC-Water heating (Natural gas)-Gases|Gas'] +\
                dictValue['schedule']['FC-Cooking (Natural gas)-Gases|Gas']
            dfHourlyResults['Gases|Gas'] += gasesGas

            # Solids|Biomass
            solidsBiomass = dictValue['schedule']['FC-Space heating (Biomass)-Solids|Biomass'] +\
                dictValue['schedule']['FC-Water heating (Biomass)-Solids|Biomass'] +\
                dictValue['schedule']['FC-Cooking (Biomass)-Solids|Biomass']
            dfHourlyResults['Solids|Biomass'] += solidsBiomass

            # Electricity: substract the value of the solar energy
            electricity = dictValue['schedule']['FC-Space heating (Geothermal)-Electricity'] +\
                dictValue['schedule']['FC-Space heating (Advanced electric heating)-Electricity'] +\
                dictValue['schedule']['FC-Space heating (Conventional electric heating)-Electricity'] +\
                dictValue['schedule']['FC-Space cooling (Electric space cooling)-Electricity'] +\
                dictValue['schedule']['FC-Water heating (Geothermal)-Electricity'] +\
                dictValue['schedule']['FC-Water heating (Advanced electric heating)-Electricity'] +\
                dictValue['schedule']['FC-Water heating (Electricity)-Electricity'] +\
                dictValue['schedule']['FC-Lighting (Electricity)-Electricity'] +\
                dictValue['schedule']['FC-Appliances (Electricity)-Electricity'] +\
                dictValue['schedule']['FC-Cooking (Electricity)-Electricity']
            dfHourlyResults['Electricity'] += (electricity.values - ((dfSolar[archetype].values) / 1.0e+03))

            # Heat
            heat = dictValue['schedule']['FC-Space heating (Distributed heat)-Heat'] +\
                dictValue['schedule']['FC-Water heating (Distributed heat)-Heat']
            dfHourlyResults['Heat'] += heat

            # Liquids|Biomass
            liquidsBiomass = dictValue['schedule']['FC-Space heating (BioOil)-Liquids|Biomass'] +\
                dictValue['schedule']['FC-Water heating (BioOil)-Liquids|Biomass']
            dfHourlyResults['Liquids|Biomass'] += liquidsBiomass

            # Gases|Biomass
            gasesBiomass = dictValue['schedule']['FC-Space heating (BioGas)-Gases|Biomass'] +\
                dictValue['schedule']['FC-Water heating (BioGas)-Gases|Biomass']
            dfHourlyResults['Gases|Biomass'] += gasesBiomass

            # Hydrogen
            hydrogen = dictValue['schedule']['FC-Space heating (Hydrogen)-Hydrogen'] +\
                dictValue['schedule']['FC-Water heating (Hydrogen)-Hydrogen']
            dfHourlyResults['Hydrogen'] += hydrogen

            # Heat|Solar
            heatSolar = dictValue['schedule']['FC-Water heating (Solar)-Heat|Solar']
            dfHourlyResults['Heat|Solar'] += heatSolar

            # Obtain the coefficients from CSV data, and adjust the shape to the schedule shape
            csv = dfCSV[dfCSV['Use'] == archetype]
            csv = csv.loc[csv.index.repeat(
                len(dictValue['schedule']) - len(csv))].reset_index(drop=True)

            # Variable cost [€/KWh]
            dfHourlyResults['Variable cost [€/KWh]'] += (solidsCoal * csv['OPEX Variable cost Solids|Coal']) +\
                (liquidsGas * csv['OPEX Variable cost Liquids|Gas']) + (liquidsOil * csv['OPEX Variable cost Liquids|Oil']) +\
                (gasesGas * csv['OPEX Variable cost Gases|Gas']) + (solidsBiomass * csv['OPEX Variable cost Solids|Biomass']) +\
                (electricity * csv['OPEX Variable cost Electricity']) + (heat * csv['OPEX Variable cost Heat']) +\
                (liquidsBiomass * csv['OPEX Variable cost Liquids|Biomass']) + (gasesBiomass * csv['OPEX Variable cost Gases|Biomass']) +\
                (hydrogen * csv['OPEX Variable cost Hydrogen']) + \
                (heatSolar * csv['OPEX Variable cost Heat|Solar'])

            # Emissions [kgCO2/KWh]
            dfHourlyResults['Emissions [kgCO2/KWh]'] += (solidsCoal * csv['OPEX Emissions Solids|Coal']) +\
                (liquidsGas * csv['OPEX Emissions Liquids|Gas']) + (liquidsOil * csv['OPEX Emissions Liquids|Oil']) +\
                (gasesGas * csv['OPEX Emissions Gases|Gas']) + (solidsBiomass * csv['OPEX Emissions Solids|Biomass']) +\
                (electricity * csv['OPEX Emissions Electricity']) + (heat * csv['OPEX Emissions Heat']) +\
                (liquidsBiomass * csv['OPEX Emissions Liquids|Biomass']) + (gasesBiomass * csv['OPEX Emissions Gases|Biomass']) +\
                (hydrogen * csv['OPEX Emissions Hydrogen']) + \
                (heatSolar * csv['OPEX Emissions Heat|Solar'])

    # Save to Excel (if allowed)
    if constants.SAVE_RESULT_ALLOWED:
        with pd.ExcelWriter('temporary/result.xlsx', mode='a') as writer:
            dfHourlyResults.to_excel(writer,
                                     sheet_name='Hourly Results (' + archetype[:4] + '.)',
                                     index=False)

    # Finish
    print('Model: Step 22/>  [OK]')
    return dfHourlyResults


#####################################################################
######################## Auxiliary functions ########################
#####################################################################


# Auxiliary function 01: Add Feb. 29 if missing (for temperatures data)
def x01AddFeb29IfMissingForTemperaturesData(df: pd.DataFrame,
                                            targetYear: int) -> pd.DataFrame:
    """Auxiliary function 01: If the destination year is a leap year
        and the original year was not, replace 28-Feb with 29-Feb.

    Args:
        df (DataFrame): The source DataFrame.
        targetYear (int): The target year.
    
    Returns:
        DataFrame
    """

    if not isleap(targetYear):
        return df
    if ((df.index.month == 2) & (df.index.day == 29)).any():
        return df

    feb28Start = pd.Timestamp(f"{targetYear}-02-28 00:00:00")
    feb28End = pd.Timestamp(f"{targetYear}-02-28 23:00:00")
    feb29Start = pd.Timestamp(f"{targetYear}-02-29 00:00:00")
    feb29End = pd.Timestamp(f"{targetYear}-02-29 23:00:00")

    feb28Hours = pd.date_range(feb28Start,
                               feb28End,
                               freq="H")
    if not set(feb28Hours).issubset(set(df.index)):
        return df

    feb28 = df.loc[feb28Hours].copy()
    feb28.index = pd.date_range(feb29Start,
                                feb29End,
                                freq="H")
    out = pd.concat([df, feb28]).sort_index()
    return out


# Auxiliary function 02: Add Feb. 29 if missing (for radiation data)
def x02AddFeb29IfMissingForRadiationData(df: pd.DataFrame,
                                         targetYear: int) -> pd.DataFrame:
    """Auxiliary function 02: If the destination year is a leap year
        and the original year was not, replace 28-Feb with 29-Feb.

    Args:
        df (DataFrame): The source DataFrame.
        targetYear (int): The target year.
    
    Returns:
        DataFrame
    """

    if not isleap(targetYear):
        return df
    if ((df.index.month == 2) & (df.index.day == 29)).any():
        return df
    feb28Hours = pd.date_range(f"{targetYear}-02-28 00:00:00",
                               f"{targetYear}-02-28 23:00:00",
                               freq="h")
    if not set(feb28Hours).issubset(set(df.index)):
        return df
    feb28 = df.loc[feb28Hours].copy()
    feb28.index = pd.date_range(f"{targetYear}-02-29 00:00:00",
                                f"{targetYear}-02-29 23:00:00",
                                freq="h")
    return pd.concat([df, feb28]).sort_index()


# Auxiliary function 03: Drop Feb. 29 if present (for temperatures data)
def x03DropFeb29IfPresentForTemperaturesData(df: pd.DataFrame) -> pd.DataFrame:
    """Auxiliary function 03: Delete the rows for February 29 (if they exist).

    Args:
        df (DataFrame): The source DataFrame.
    
    Returns:
        DataFrame
    """

    mask = (df.index.month == 2) & (df.index.day == 29)
    if mask.any():
        return df.loc[~mask]
    return df


# Auxiliary function 04: Drop Feb. 29 if present (for radiation data)
def x04DropFeb29IfPresentForRadiationData(df: pd.DataFrame) -> pd.DataFrame:
    """Auxiliary function 04: Delete the rows for February 29 (if they exist).

    Args:
        df (DataFrame): The source DataFrame.
    
    Returns:
        DataFrame
    """

    return df.loc[~((df.index.month == 2) & (df.index.day == 29))]


# Auxiliary function 05: Remap year
def x05RemapYear(tsIndex: pd.DatetimeIndex,
                 targetYear: int) -> pd.DatetimeIndex:
    """Auxiliary function 05: Change the year of a DatetimeIndex while keeping
        the month/day/hour/minute/second values.

    Args:
        tsIndex (DatetimeIndex): The source DatetimeIndex.
        targetYear (int): The target year.
    
    Returns:
        DatetimeIndex
    """

    return tsIndex.map(lambda t: pd.Timestamp(year=targetYear,
                                              month=t.month,
                                              day=t.day,
                                              hour=t.hour,
                                              minute=t.minute,
                                              second=t.second))


# Auxiliary function 06: Establish value between limits
def x06EstablishValue(dict: dict,
                      name: str,
                      limitDown: float,
                      limitUp: float,
                      defaultValue: float) -> float:
    """Auxiliary function 06: Establish value between limits.

    Args:
        dict (dict): The source dictionary.
        name (str): The source property.
        limitDown (float): The lower limit of the value.
        limitUp (float): The upper limit of the value.
        defaultValue (float): The default value.
    
    Returns:
        float
    """

    if name in dict:
        value = dict[name]
        if value is not None:
            if limitDown <= value <= limitUp:
                return value
            else:
                return defaultValue
        else:
            return value
    else:
        return defaultValue


# Auxiliary function 07: Obtain the available area
def x07GetAvailableArea(parameters: list,
                        cost: float,
                        landUse: float) -> tuple:
    """Auxiliary function 07: Obtain the available area.

    Args:
        parameters (list): The list of parameters.
        cost (float): The value of the cost.
        landUse (float): The value of the land use.
    
    Returns:
        tuple
    """

    index = next((i for i, value in enumerate(parameters) if value is not None), -1)
    if index == 2:
        capex = parameters[index]
        power = parameters[index] / (cost * 1.0e+06)            # in MW
        areaAvailable = power * 1.0e+06 / landUse               # in m2
    elif index == 1:
        areaAvailable = parameters[index] * 1.0e+06 / landUse   # in m2
        power = parameters[index]
        capex = power * cost * 1.0e+06
    else:
        areaAvailable = parameters[0]                           # in m2
        power = (areaAvailable * landUse) / 1.0e+06             # in MW
        capex = power * cost * 1.0e+06

    return areaAvailable, power, capex


# Auxiliary function 08: Obtain the regions
def x08GetRegions(dictScada: dict,
                  area: float,
                  minGhi: float) -> tuple:
    """Auxiliary function 08: Obtain the regions.

    Args:
        dictScada (DataFrame): The scada dataframe.
        area (float): The value of the area.
        minGhi (float): The value of the min GHI.
    
    Returns:
        tuple
    """

    currentSum = 0
    nameNuts2 = None
    rows = []
    for index, row in dictScada.iterrows():
        if nameNuts2 is None:
            nameNuts2 = row['Region'][:-1]
        if row['Area_m2'] > 0:
            if currentSum + row['Area_m2'] > area and row['Threshold'] >= minGhi:
                row['Area_m2'] = area - currentSum
                currentSum += row['Area_m2']
                rows.append(row)
                break
            currentSum += row['Area_m2']
            rows.append(row)

    return rows, nameNuts2


# Auxiliary function 09: Obtain the PV production
def x09GetPVProduction(rows: list,
                       landUse: float,
                       tilt: float,
                       distribAzimuth: float,
                       tracking: float,
                       loss: float,
                       porcent: float,
                       year: int) -> list:
    """Auxiliary function 09: Obtain the PV production.

    Args:
        rows (list): The list of rows.
        landUse (float): The value of the land use.
        tilt (float): The value of the tilt.
        distribAzimuth (float): The value of the distribAzimuth.
        tracking (float): The value of the tracking.
        loss (float): The value of the loss.
        porcent (float): The value of the porcent.
        year (int): The year.
    
    Returns:
        list
    """

    production = []
    for region in rows:
        lon, lat = region['Median_Radiation_X'], region['Median_Radiation_Y']

        # Convert coordinates from EPSG:3035 to EPSG:4326
        if constants.CONVERT_COORD or lat > 180: 
            lon, lat = x11GetCoordinates(region)

        pot_MW = (region['Area_m2'] * landUse) / 1.0e+06
        region['power_installed(kW)'] = pot_MW
        factor = 1

        if pot_MW * 1.0e+03 > 1.0e+08:
            pot_MW = pot_MW / 1.0e+03
            factor = 1.0e+03

        prod = []
        for i in range(len(porcent)):
            df, params, meta = pvlib.iotools.get_pvgis_hourly(latitude=lat,
                                                              longitude=lon,
                                                              start=year,
                                                              end=year,
                                                              raddatabase='PVGIS-SARAH2',
                                                              surface_tilt=tilt,
                                                              surface_azimuth=distribAzimuth[i],
                                                              pvcalculation=True,
                                                              peakpower=pot_MW * 1000 * porcent[i],
                                                              trackingtype=tracking,
                                                              loss=loss,
                                                              components=False,
                                                              url='https://re.jrc.ec.europa.eu/api/v5_2/')
            prod.append(df['P'])

        region['production'] = (pd.DataFrame(prod).sum(axis=0)) * factor / 1.0e+06  # to MW
        production.append((pd.DataFrame(prod).sum(axis=0) * factor / 1.0e+06))  # to MW

    return production


# Auxiliary function 10: Obtain the distribution
def x10GetDistribution(rows: list,
                       label: str) -> tuple:
    """Auxiliary function 10: Obtain the distribution.

    Args:
        rows (list): The list of rows.
        label (str): The label.
    
    Returns:
        tuple
    """

    res = []
    for i in rows:
        if i['Region'] not in res:
            res.append(i['Region'])

    df = pd.DataFrame(rows)
    sumNuts = []
    sumAreas = []
    sumPots = []
    for i in res:
        nuts = df.loc[i == df['Region']][label]
        df_nuts = pd.DataFrame(nuts.tolist())
        sumNuts.append(df_nuts.sum())
        areasNuts3 = df.loc[i == df['Region']]['Area_m2']
        potNuts3 = df.loc[i == df['Region']]['power_installed(kW)']
        sumAreas.append(pd.DataFrame(areasNuts3.tolist()).sum())
        sumPots.append(pd.DataFrame(potNuts3.tolist()).sum())

    areas = dict(zip(res, [x[0] for x in sumAreas]))
    pots = dict(zip(res, [x[0] for x in sumPots]))

    nuts2 = pd.DataFrame(sumNuts, index=res).transpose()
    nuts2 = nuts2.dropna(axis=1)
    nuts2.index = pd.to_datetime(nuts2.index).round('h').strftime('%m/%d/%Y %H:%M')

    return nuts2, pots, areas


# Auxiliary function 11: Obtain the coordinates
def x11GetCoordinates(sourceDF: pd.DataFrame) -> tuple:
    """Auxiliary function 11: Obtain the coordinates.

    Args:
        sourceDF (DataFrame): The source DataFrame.
    
    Returns:
        tuple
    """
    
    transformer = Transformer.from_crs("EPSG:3035", "EPSG:4326",
                                       always_xy=True)
    xy = transformer.transform(sourceDF['Median_Radiation_X'],
                               sourceDF['Median_Radiation_Y'])
    return xy[0], xy[1]


# Auxiliary function 12: Calculate the OPEX
def x12CalculateOPEX(pot: dict,
                     opexPV: float) -> tuple:
    """Auxiliary function 12: Calculate the OPEX.

    Args:
        pot (dict): The pot dictionary.
        opexPV (float): The OPEX for PV.
    
    Returns:
        tuple
    """

    sumPV = 0
    for key, value in pot.items():
        sumPV += value
    return sumPV * opexPV