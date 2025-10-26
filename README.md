# iDesignRES: Building Stock Energy Model

This README provides an overview of the Model iDesignRES Building Stock Energy Model within iDesignRES.

It is handled by Tecnalia and part of WP1, Task number Task 1.4.

## Purpose of the model

The objective of the model is to simulate the energy performance of the building stock of any region in Europe (NUTS Level2) both for an initial diagnosis and to evaluate different years of the transition period considered in the scenarios proposed. The aim is to cover the building stock for different uses including the residential and tertiary sector with a high degree of disaggregation in both cases. 
Besides, the model aims to generate information that provides greater granularity to the building sector models generated in the project for higher scales such as the national scale and exploitation.

## Model design philosophy

In the case of the building sector, when developing new models and functionalities that allow ESM type models (traditionally focused on covering the European and country scales) to reach a regional resolution, it is necessary to find the balance between the agility of calculation and this greater detail of analysis. In this process, it is worth highlighting the potential associated with the use of georeferenced information to capture the specificities of each region in terms of building typologies. This allows a more detailed disaggregation of the building energy model at the country level, capturing aspects such as the number of buildings, surface area, age, or the most specific use for each building typology in the region, as well as their geographic distribution. Traditional methods used for obtaining and processing detailed georeferenced data are applied at smaller scales such as the district or urban scales since they are based on cadastral data. Moreover, they are not easily replicable and automatable for other cities and regions due to their high heterogeneity. This aspect related to the specificity to the case study and the complexity of data preprocessing is an important barrier that makes it unusual to disaggregate national models at the regional level with a high degree of disaggregation of building typologies based on bottom-up data collected. 
The developed model aims to help break this barrier by treating and preprocessing geometric and semantic information of each of the buildings (level of detail at the building portal level) in the region. It follows this bottom-up georeferenced information processing approach but starting from georeferenced data available for the whole Europe and developed ad-hoc to cover larger scales such as the regional scale. This information is then used to adapt the energy calculation of the building sector through the use of building archetypes that provide greater detail for each building use. The model performs hourly simulations for given years so that they can be used for initial diagnosis and analysis of potential future scenarios.

## Input to and output from the model

Input data:

(a) For initial diagnosis: energy demand (base year assessment):

- Data to be filled in by the user: NUTS Level 2 Code or NUTS Level 3 Code.
- Main data used by the model as input (provided by the model with the option to be modified by the user in case more accurate data are available): Meteorological data (Outdoor dry bulb temperature (hourly), Radiation, Solar gains, heating, and cooling periods); geometry, surface area, age, use of each building. Other building parameters (U-values, H/C base temperature, Window-to-wall ratio, adjacent buildings).

(b) For initial diagnosis: energy consumption calculation (base year assessment):

- Main data used by the model as input (provided by the model with the option to be modified by the user in case more accurate data are available): Shares of fuels/technologies by building type (From statistical data or model results of a higher scale, used for the adjustment), Hourly profiles (for Heating, Cooling, DHW, Occupancy, Lighting, Equipment, kitchen), Installed power (Lighting, Equipment), Equipment performance, Fuel cost, Environmental impact factors.

(c) For the scenarios:

- Main data used by the model as input (provided by the model with the option to be modified by the user in case more accurate data are available): Shares of fuels/technologies of the scenario to be simulated (if available from model results of a higher scale, used for the adjustment). Investments/measurement of amount of technology deployed in each sector/type of buildings. For example (for refurbishment total m2 refurbished or associated investment, for solar PV total MW installed or associated investment, etc.).

Output data:

- Energy results: Energy demand and energy consumption by building typology: use of buildings/age/archetype/end use of energy/fuel (On an annual basis and on an hourly basis).
- Energy generation results for building integrated solar technology.
- Costs and CO2 emissions associated.

## Implemented features

- The model allows building stock simulations for any region in Europe avoiding most of the building data collection, treatment, and preprocessing.
  
  > It should be noted that in the current implementation stage, the model is only available for the use case in the Basque Country. The other use cases for the project will also be included when appropriate.

- The model allows simulations of a given year on an hourly basis (based on the heating degree hours method) for both NUTS Level 2 and NUTS level 3 contained in the region.

- The model generates in a first instance the most relevant information required as input to the energy model in an automated way for the selected NUTS Level 2 region of Europe. Avoiding the user having to contact the different local, provincial, and regional entities in question for the request of cadaster shape files. The characterization obtained is at the portal level of each building in the region collecting the main characteristics in terms of use, sub-use, age, geometry, area and height, as well as their geographical distribution that can be used for finer analysis than NUTS Level 2.

- In a second simulation phase, the model treats the information obtained and simplifies it to the level of archetypes of representative building typologies (according to the form factor) to be simulated for the region.

- The model offers a high degree of disaggregation for both the calculation and the presentation of results based on the following structure: Use - age - archetype - final use – fuel

- The model has an internal database that provides the most relevant data to perform the simulations for any region in Europe. It also offers the possibility of substituting these values for others proposed by the modeler in case more specific information is available.

- Through new simulations of future years, the model allows to evaluate the behavior of the building stock for different scenarios that consider different degrees of deployment of certain technologies.

- Regarding the coordination with the rest of the models of higher scales that contemplate the behavior of the building sector, the developed model maintains a coherence with them using a structure of disaggregation of building typologies, final uses and fuels used, as well as allowing the use of the outputs of the simulation models at higher scales to adjust some of the parameters of the regional model.

## Core assumption

- Following the Energy Performance of Buildings Directive[1], static equations are used to determine the heating, cooling and domestic hot water (DHW) energy demand. The methodology is based on the Degree-Days method. However, to obtain a more detailed analysis, the calculation is done on an hourly basis and considers internal gains, solar gains, ventilation losses[2].
- The model does not allow optimization. It is a simulation model that allows the evaluation of prospective exploratory scenarios based on the narratives set for each proposed scenario.
- Once the information is collected for each building, the model groups areas/geometries of buildings based on a clustering of buildings according to their form factor. Three archetypes are considered for each age range of residential buildings and a single representative archetype for each sub-use of the tertiary sector (7 subcategories of tertiary buildings are considered).
- Buildings of industrial use do not fall within the scope of the model. However, their geometric characteristics and geographic distribution across the region are considered to rule out areas available for large-scale solar technology use in the solar module.
- Limitations in terms of technologies or measures considered in the generation of future scenarios: Rehabilitation measures are contemplated differentiating, facades, roofs, and windows (differentiating 3 levels; high, medium, low), replacement of heating and cooling systems, improvement of performances, installation of solar photovoltaic and thermal systems. To include measures related to district heating and cooling systems, they must be introduced as a new technology defining their share of fuel mix, performance, as well as other key parameters representative for the case study.

---

---

# Getting started

## System requirements

The recommended system requirements are as follows:

- Broadband Internet connection.

- *RAM memory*: it is recommended to have 32GB.

- *Operating system*: the models run on any operating system that supports Python and Poetry.

- *Python*: version 3.10.

- *Poetry*: version 2.1.1.

To make sure *Python 3.10* is installed.:

```
python --version
```

And to make make sure that *Poetry 2.1.1* is installed:

```
poetry --version
```

## Installation

Clone the repository in the desired directory:

```
cd directory
git clone https://github.com/iDesignRES/Tecnalia_Building-Stock-Energy-Model
```

To install the Building Stock Energy Model, enter the following command:

```
poetry install
```

## Execution

Once installed, execute the *Building Stock Energy Model* entering the command:

```
poetry run python building_energy_process.py <input_payload> <start_time> <end_time> <building_use>
```

For example 

```
poetry run python building_energy_process.py input.json 2019-01-01T00:00:00 2019-01-07T23:00:00 "Offices"
```

This command automatically runs the simulation, taking the necessary input data from the *[usecases](usecases)* folder and the *[input.json](input.json)* file.

## Testing and code coverage

The following tests have been defined for the model:

- Missing command line parameters.

- Correct command line parameters.

- Invalid payload.

- Payload with incorrect values.

- Valid payload.

- The integrity of the database.

- Correct execution test, checking the correct output.

With a resulting code coverage of 92%:

| Name                  | Stmts    | Miss    | Cover   |
| --------------------- | -------- | ------- | ------- |
| modules/_ *init _*.py | 0        | 0       | 100%    |
| modules/constants.py  | 11       | 0       | 100%    |
| modules/model.py      | 1038     | 89      | 91%     |
| modules/validator.py  | 534      | 33      | 94%     |
| **TOTAL**             | **1583** | **122** | **92%** |

## Full example

To review a complete example of the model, access [this directory](example/README.md).

## Documentation

To review the complete model documentation, access [this directory](docs/README.md).