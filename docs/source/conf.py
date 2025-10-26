# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'iDesignRES - Building Stock Energy Model'
copyright = '2025, Tecnalia'
author = 'Tecnalia'
release = '0.10.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#007acc",
        "color-brand-content": "#007acc",
    },
    "source_repository": "https://github.com/iDesignRES/Tecnalia_Building-Stock-Energy-Model",
    "source_branch": "main",
    "source_directory": "docs/",
}
html_title = "iDesignRES - Building Stock Energy Model"
html_static_path = ['_static']
