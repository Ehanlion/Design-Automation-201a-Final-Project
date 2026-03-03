#!/usr/bin/env python3
"""
Debug version of the thermal analysis GUI to identify issues
"""
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import datetime

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container([
    html.H1("Debug Thermal Analysis GUI"),
    
    dbc.Row([
        dbc.Col([
            html.Label("System Type:"),
            dcc.Dropdown(
                id='system-dropdown',
                options=[
                    {'label': '3D Waferscale', 'value': '3D_waferscale'},
                    {'label': '2.5D Waferscale', 'value': '2p5D_waferscale'}
                ],
                value='3D_waferscale'
            ),
            html.Br(),
            dbc.Button("Run Analysis", id="run-button", color="primary"),
            html.Br(),
            html.Div(id="output", style={'margin-top': '20px'})
        ], width=6),
        
        dbc.Col([
            html.H3("Results"),
            html.Div(id="results")
        ], width=6)
    ])
])

@app.callback(
    [Output('output', 'children'),
     Output('results', 'children')],
    [Input('run-button', 'n_clicks')],
    [State('system-dropdown', 'value')]
)
def debug_analysis(n_clicks, system_type):
    if n_clicks is None:
        return "Click 'Run Analysis' to start", "No results yet"
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log = "Analysis started at: {}\\n".format(timestamp)
        log += "System type: {}\\n".format(system_type)
        
        # Test mock results
        runtime = 12.34
        gpu_temp = 85.2
        hbm_temp = 82.1
        idle_frac = 0.15
        
        log += "Mock results generated successfully\\n"
        log += "Runtime: {:.2f}s\\n".format(runtime)
        log += "GPU Temp: {:.1f}°C\\n".format(gpu_temp)
        
        results = html.Div([
            html.P("Analysis completed!"),
            html.P("Runtime: {:.2f} seconds".format(runtime)),
            html.P("GPU Temperature: {:.1f}°C".format(gpu_temp)),
            html.P("HBM Temperature: {:.1f}°C".format(hbm_temp)),
            html.P("GPU Idle Fraction: {:.2f}".format(idle_frac))
        ])
        
        return log, results
        
    except Exception as e:
        error_msg = "Error: {}".format(str(e))
        return error_msg, "Analysis failed"

if __name__ == '__main__':
    print("Starting debug GUI on port 8053...")
    app.run(debug=True, host='0.0.0.0', port=8053)
