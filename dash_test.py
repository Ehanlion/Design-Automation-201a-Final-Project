#!/usr/bin/env python3
"""
Simple Dash test
"""
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

print("Dash version:", dash.__version__)

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Test GUI"),
    html.P("If you can see this, Dash is working!"),
    dcc.Input(id="input", value="test"),
    html.Div(id="output")
])

@app.callback(Output('output', 'children'), [Input('input', 'value')])
def update_output(value):
    return "You entered: {}".format(value)

if __name__ == '__main__':
    print("Starting test server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
