#!/usr/bin/env python3
"""
Simplified Thermal Analysis GUI for Python 3.6.8 compatibility
"""

import os
import sys
import subprocess
import re
from datetime import datetime

# Try to import required packages
try:
    import dash
    print(f"Dash version: {dash.__version__}")
except ImportError:
    print("Error: Dash is not installed. Please install with: pip install dash")
    sys.exit(1)

try:
    from dash import dcc, html
    from dash.dependencies import Input, Output, State
except ImportError:
    print("Error: Could not import Dash components")
    sys.exit(1)

try:
    import dash_bootstrap_components as dbc
    print(f"Bootstrap components available")
except ImportError:
    print("Warning: dash-bootstrap-components not available, using basic styling")
    dbc = None

try:
    import plotly.graph_objs as go
    import pandas as pd
    print("Plotly and Pandas available")
except ImportError:
    print("Warning: Plotly or Pandas not available, limited functionality")
    go = None
    pd = None

# Initialize the Dash app
if dbc:
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
else:
    app = dash.Dash(__name__)

# Simple layout without bootstrap if not available
if dbc:
    # Bootstrap layout
    app.layout = dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H1("Thermal Analysis GUI", className="text-center mb-4"),
                html.Hr(),
            ])
        ]),
        
        dbc.Row([
            dbc.Col([
                # Configuration
                dbc.Card([
                    dbc.CardHeader("Configuration"),
                    dbc.CardBody([
                        html.Label("System Type:"),
                        dcc.Dropdown(
                            id='system-dropdown',
                            options=[
                                {'label': '2.5D Waferscale', 'value': '2p5D_waferscale'},
                                {'label': '3D Waferscale', 'value': '3D_waferscale'}
                            ],
                            value='3D_waferscale'
                        ),
                        html.Br(),
                        html.Label("ML Model:"),
                        dcc.Dropdown(
                            id='model-dropdown',
                            options=[
                                {'label': 'Llama 3.3 70B', 'value': 'llama_3_3_70b'},
                                {'label': 'Llama 3.1 405B', 'value': 'llama_3_1_405b'}
                            ],
                            value='llama_3_3_70b'
                        ),
                        html.Br(),
                        html.Button("Run Analysis", id="run-button", className="btn btn-primary"),
                        html.Br(),
                        html.Div(id="output", style={'margin-top': '20px'})
                    ])
                ])
            ], width=6),
            
            dbc.Col([
                html.H3("Results"),
                html.Div(id="results")
            ], width=6)
        ])
    ])
else:
    # Basic layout without bootstrap
    app.layout = html.Div([
        html.H1("Thermal Analysis GUI"),
        html.Hr(),
        
        html.Div([
            html.Div([
                html.H3("Configuration"),
                html.Label("System Type:"),
                dcc.Dropdown(
                    id='system-dropdown',
                    options=[
                        {'label': '2.5D Waferscale', 'value': '2p5D_waferscale'},
                        {'label': '3D Waferscale', 'value': '3D_waferscale'}
                    ],
                    value='3D_waferscale'
                ),
                html.Br(),
                html.Label("ML Model:"),
                dcc.Dropdown(
                    id='model-dropdown',
                    options=[
                        {'label': 'Llama 3.3 70B', 'value': 'llama_3_3_70b'},
                        {'label': 'Llama 3.1 405B', 'value': 'llama_3_1_405b'}
                    ],
                    value='llama_3_3_70b'
                ),
                html.Br(),
                html.Button("Run Analysis", id="run-button"),
                html.Br(),
                html.Div(id="output", style={'margin-top': '20px'})
            ], style={'width': '48%', 'display': 'inline-block', 'vertical-align': 'top'}),
            
            html.Div([
                html.H3("Results"),
                html.Div(id="results")
            ], style={'width': '48%', 'display': 'inline-block', 'vertical-align': 'top', 'margin-left': '4%'})
        ])
    ])

@app.callback(
    Output('output', 'children'),
    [Input('run-button', 'n_clicks')],
    [State('system-dropdown', 'value'),
     State('model-dropdown', 'value')]
)
def run_analysis(n_clicks, system_type, model_type):
    if n_clicks is None:
        return "Click 'Run Analysis' to start"
    
    try:
        # Change to the correct directory
        os.chdir('/app/nanocad/projects/deepflow_thermal/DeepFlow')
        
        # Simple test - just check if calibrated_iterations.py exists
        if os.path.exists('calibrated_iterations.py'):
            return html.Div([
                html.P(f"Analysis started with:"),
                html.P(f"System: {system_type}"),
                html.P(f"Model: {model_type}"),
                html.P(f"File found: calibrated_iterations.py"),
                html.P(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            ])
        else:
            return "Error: calibrated_iterations.py not found"
            
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    print("Starting simplified thermal analysis GUI...")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        app.run_server(debug=True, host='0.0.0.0', port=8050)
    except Exception as e:
        print(f"Error starting server: {e}")
        print("Try running: pip install dash dash-bootstrap-components plotly pandas")
