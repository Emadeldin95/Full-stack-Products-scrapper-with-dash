import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import flask
import json
from threading import Thread, Event

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Global variables
scraping_thread = None
stop_event = Event()
scraped_data = []
total_products_scraped = 0  

BASE_URL = "https://makerselectronics.com/products"

# Function to scrape product data
def scrape_product_data():
    global scraped_data, total_products_scraped
    page = 1

    while True:
        if stop_event.is_set():
            break  

        url = f"{BASE_URL}/page/{page}" if page > 1 else BASE_URL
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        product_wrappers = soup.find_all('div', class_='product-wrapper')
        if not product_wrappers:
            break  

        for product_div in product_wrappers:
            if stop_event.is_set():
                break  

            try:
                product_data_span = product_div.find('span', class_='gtm4wp_productdata')
                product_data = json.loads(product_data_span['data-gtm4wp_product_data'])

                name = product_data.get('item_name', 'N/A')
                price = f"{product_data.get('price', 'N/A')} EGP"
                product_url = product_data.get('productlink', '#')

                image_tag = product_div.find('img', class_='attachment-shop_catalog')
                image_url = image_tag['data-src'] if 'data-src' in image_tag.attrs else image_tag['src']

                scraped_data.append({
                    'Name': name,
                    'Price': price,
                    'Product URL': f'[{name}]({product_url})',  
                    'Image': f'<img src="{image_url}" width="50">'  
                })
                total_products_scraped += 1  

            except Exception as e:
                print(f"Error processing product: {e}")

        next_button = soup.find('a', class_='next page-numbers')
        if next_button and not stop_event.is_set():
            page += 1
        else:
            break  

    df = pd.DataFrame(scraped_data)
    os.makedirs('data', exist_ok=True)
    df.to_excel('data/products_data.xlsx', index=False)


# App layout
app.layout = dbc.Container([
    dbc.NavbarSimple(
        brand="MAKERS Electronics Product Dashboard",
        color="primary",
        dark=True,
        className="mb-4"
    ),

    # Table Container
    html.Div([
        dash_table.DataTable(
            id='product-table',
            columns=[
                {'name': 'Name', 'id': 'Name'},
                {'name': 'Price', 'id': 'Price'},
                {'name': 'Product URL', 'id': 'Product URL', 'presentation': 'markdown'},
                {'name': 'Image', 'id': 'Image', 'presentation': 'markdown'}
            ],
            data=[],  
            fixed_rows={'headers': True},  
            style_table={'overflowY': 'auto', 'width': '100%', 'height': '100%'},  
            style_cell={
                'textAlign': 'left',
                'padding': '5px',
                'whiteSpace': 'normal',  
                'wordBreak': 'break-word',  
                'maxWidth': '200px'  
            },
            style_header={'backgroundColor': 'lightgrey', 'fontWeight': 'bold'},
            style_data={'whiteSpace': 'normal', 'height': 'auto'},
            markdown_options={'html': True},  
            page_size=10,  # ✅ Ensures pagination buttons are visible
            style_data_conditional=[  # ✅ Adjust row height for better fitting
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f9f9f9'},
                {'if': {'row_index': 'even'}, 'backgroundColor': '#ffffff'}
            ]
        )
    ], style={'maxHeight': 'calc(100vh - 260px)', 'overflowY': 'auto'}),  

    # Buttons section (Sticky above footer)
    html.Div([
        html.Div(id='scraping-status', className='mt-3'),
        dcc.Interval(id="progress-interval", interval=2000, n_intervals=0, disabled=True),
        dbc.Progress(id="progress-bar", value=0, max=500, animated=True, striped=True, className="mt-3"),
        dbc.Button("Start Scraping", id='start-button', color="success", className="mt-3"),
        dbc.Button("Stop Scraping", id='stop-button', color="danger", className="mt-3", disabled=True),
        html.A(
            dbc.Button("Download Data as Excel", color="info", className="mt-3"),
            id='download-link',
            href='/download_excel/',
            hidden=True
        )
    ], style={'position': 'sticky', 'bottom': '60px', 'backgroundColor': 'white', 'padding': '10px', 'zIndex': '1000'}),  

    # Footer always at the bottom
    dbc.NavbarSimple(
        children=[
            html.Span("© 2025 MAKERS Electronics", className="navbar-text")
        ],
        color="dark",
        dark=True,
        className="mt-4",
        style={'position': 'fixed', 'bottom': '0', 'width': '100%', 'zIndex': '1000'}
    )
], fluid=True)


# **Unified Callback for Start/Stop**
@app.callback(
    [
        Output('start-button', 'disabled'),
        Output('stop-button', 'disabled'),
        Output('progress-interval', 'disabled'),
        Output('scraping-status', 'children'),
        Output('download-link', 'hidden')
    ],
    [Input('start-button', 'n_clicks'), Input('stop-button', 'n_clicks')],
    prevent_initial_call=True
)
def manage_scraping(start_clicks, stop_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    global scraping_thread, stop_event, scraped_data

    if button_id == "start-button":
        stop_event.clear()
        scraped_data = []  

        def run_scraper():
            scrape_product_data()

        scraping_thread = Thread(target=run_scraper)
        scraping_thread.start()

        return True, False, False, "Scraping in progress...", True

    elif button_id == "stop-button":
        stop_event.set()
        if scraping_thread and scraping_thread.is_alive():
            scraping_thread.join()

        return False, True, True, "Scraping stopped.", False

    return False, True, True, "No action taken.", True


@app.callback(
    [Output('product-table', 'data'),
     Output('progress-bar', 'value'),
     Output('progress-bar', 'label')],
    [Input('progress-interval', 'n_intervals')]
)
def update_progress(n_intervals):
    if stop_event.is_set():
        return scraped_data, total_products_scraped, f"Total Scraped: {total_products_scraped} Items"

    return scraped_data, total_products_scraped, f"Total Scraped: {total_products_scraped} Items"


@app.server.route('/download_excel/')
def download_excel():
    return flask.send_file(
        'data/products_data.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name='products_data.xlsx',
        as_attachment=True
    )


if __name__ == '__main__':
    app.run_server(debug=True)
