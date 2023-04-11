import streamlit as st
import os
import array
import time
import pandas as pd
import yfinance as yf
import yahooquery as yq
import talib
import plotly.express as px
import plotly.graph_objs as go
from datetime import datetime, timedelta
from candlestick_patterns import candlesticks
from yahooquery import Ticker

# Array of symbols
ndx_list = []
sp500_list = []

#-------------------------------------------------------------------------------
# Paths, files and urls
#-------------------------------------------------------------------------------
ndx_url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
sp500_url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'

ndx_data_directory = 'data/ndx'
ndx_symbols = ndx_data_directory + '/ndx.txt'
ndx_test_symbol = ndx_data_directory + '/aapl.csv'

sp500_data_directory = 'data/sp500'
sp500_symbols = sp500_data_directory + '/sp500.txt'
sp500_test_symbol = sp500_data_directory + '/tsla.csv'

#-------------------------------------------------------------------------------
# Download symbols from wikipedia and write to local file
#-------------------------------------------------------------------------------
def build_symbol_list(url, table_num, column_name, output_file):

    list = []

    # Download and sort list of symbols
    list = sorted(pd.read_html(url)[table_num][column_name].tolist())

    # Save list to file
    with open(output_file, 'w') as file:
        for item in list:
            file.write(str(item) + '\n')
            
    return list

#-------------------------------------------------------------------------------
# For each symbol in the list, download data into csv
#-------------------------------------------------------------------------------
@st.cache_data
def download_symbol_data(test_file, symbols_file, output_dir, message):

    # If there is already a csv file, assume we've already created all the csv files
    if (not os.path.exists(test_file)):

        with open(symbols_file, 'r') as f:
            symbol_list = f.read().split()

            start_date = datetime.today()

            # Subtract 10 days, excluding weekends
            days_to_subtract = 10
            days_subtracted = 0
            while days_subtracted < days_to_subtract:
                start_date -= timedelta(days=1)
                if start_date.weekday() >= 5:  # If it's a weekend day (5 = Saturday, 6 = Sunday)
                    continue
                days_subtracted += 1

            # Progress bar
            progress_text = message
            pbar = st.sidebar.progress(0, text=progress_text)
            percent_complete = 0.0
            increment = 1 / len(symbol_list)

            for symbol in symbol_list:    
                data = yf.download(symbol, start=start_date, end=datetime.today(), progress=False)
                data.to_csv('{}/{}.csv'.format(output_dir, symbol))

                if (percent_complete <= 1):
                    pbar.progress(percent_complete, text=progress_text)
                    percent_complete += increment
            
            # Hide the progress bar
            pbar.empty()    

#-------------------------------------------------------------------------------
# Get additional data via yahooquery and prep to plot
#-------------------------------------------------------------------------------
def getEarningsData(symbol):

    ticker = Ticker(symbol)
    df = ticker.earning_history

    est = ticker.earnings[symbol]['earningsChart']['currentQuarterEstimate']

    fig = px.bar(df, x="period",
             y=['epsEstimate', 'epsActual'],
             title=f"{symbol.upper()} - Past Earning's Estimates and Actuals",
             barmode='group')
    fig.add_hline(y=est, line_color='yellow', line_width=2, line_dash='dash', annotation_text=est)
    st.plotly_chart(fig)

    
    header = dict(values=['Current Quarter Estimate'])
    cells = dict(values=[ticker.earnings[symbol]['earningsChart']['currentQuarterEstimate']])
    table = go.Table(header=header, cells=cells)
    layout = go.Layout(height=500, width=300, font=dict(size=14))    
    figx = go.Figure(data=[table], layout = layout)
    st.plotly_chart(figx)

#-------------------------------------------------------------------------------
# TradingView related to embed charts
#-------------------------------------------------------------------------------
def show_tradingview_chart(symbol):

    # Set TradingView chart's HTML code
    tradingview_chart = f"""
    <!-- TradingView Widget BEGIN -->
    <div class='tradingview-widget-container'>
    <div id='tradingview_123'></div>
    <script type='text/javascript' src='https://s3.tradingview.com/tv.js'></script>
    <script type='text/javascript'>
    new TradingView.widget({{
    'symbol':'{symbol}',
    'width': 980,
    'height': 610,
    'interval': 'D',
    'timezone': 'Etc/UTC',
    'theme': 'dark',
    'style': '1',
    'locale': 'en',
    'toolbar_bg': '#f1f3f6',
    'enable_publishing': false,
    'allow_symbol_change': true,
    'container_id': 'tradingview_123'
    }});
    </script>
    </div>
    <!-- TradingView Widget END -->
    """

    # Display TradingView chart using components.html
    st.components.v1.html(tradingview_chart, height=650)

#-------------------------------------------------------------------------------
# For the passed in symbol, does it match the candlestick pattern
#-------------------------------------------------------------------------------
def process_symbol(data_directory, symbol, pattern):

    talib_function = getattr(talib, pattern)

    fullpath = os.path.join(data_directory, symbol + '.csv')

    # Check if the file is a file (i.e., not a directory)
    if (os.path.isfile(fullpath)):

        # Get dataframe
        df = pd.read_csv(fullpath)

        # Ignore any errors in file such as 'NaN' or an empty file
        try:
            # Call talib candlestick function with the symbol df
            ret = talib_function(df['Open'], df['High'], df['Low'], df['Close'])

            # We only need the last value to know if the data symbol is showing the
            # candlestick pattern. Using tail where the '1' is how many to get from the end.
            # The result is an array, so we use [0] to get the first value
            last = ret.tail(1).values[0]

            # talib returns 100 for bullish, -100 for bearish, only concerned about bullish
            if (last == 100):
                return True
            else:
                return False
        
        except:
            pass

#-------------------------------------------------------------------------------
# For all the patterns, scan all the symbols
#   e.g. CDLENGULFING, scan all 100 nasdaq symbols or all s&p500 symbol
#
# The pattern_matching_list[] will look as follows: 
# ('CDL3OUTSIDE', 'WMT')
# ('CDLENGULFING', 'ALLE')
# ('CDLENGULFING', 'WBD')
# ('CDLHIKKAKE', 'ARE')
#
# Before returning the above list, make it more readable list for drop-down
# ('Three Outside Up/Down', 'WMT')
# ('Engulfing Pattern', 'ALLE')
# ('Engulfing Pattern', 'WBD')
#-------------------------------------------------------------------------------
@st.cache_data
def scan_symbols_for_candlestick_patterns(data_directory, symbol_list, progress_text):

    # for each candlestick pattern, loop through each symbol
    #    if the symbol shows the pattern, add pattern to list of successful matches,
    #    bump counter of matches for the candlestick pattern

    # Used for the progress bar
    total_entries = len(candlesticks)

    pattern_matching_list = []

    # Loop through the keys, which refer to the TALIB function
    #    'CDL2CROWS':'Two Crows',
    #    'CDL3BLACKCROWS':'Three Black Crows',

    # Progress bar
    pbar = st.sidebar.progress(0, text=progress_text)
    percent_complete = 0.0
    increment = 1 / total_entries

    # For all candlestick patterns
    for pattern in candlesticks.keys():

        # For all symbols
        for symbol in symbol_list:

            # Does symbol meet the pattern
            if (process_symbol(data_directory, symbol, pattern)):
                pattern_matching_list.append((pattern, symbol))

        if (percent_complete <= 1):
            pbar.progress(percent_complete, text=progress_text)
            percent_complete += increment

    # Hide the progress bar
    pbar.empty()
    
    # Make the pattern_matching_list[] more readable
    new_list = []
    for i in pattern_matching_list:
        # Search dict of candlestick (CDLENGULFING, 'Engulfing')
        value = candlesticks.get(i[0])
        new_list.append((value, i[1]))

    return new_list

#-------------------------------------------------------------------------------
# Main processing loop
#-------------------------------------------------------------------------------
def main_loop(ndx, sp500):

    ndx_result_list = []
    sp500_result_list = []

    #-----------------------------------------------
    # Streamlit sidebar - Download progress bars
    #-----------------------------------------------
    # Get list of ndx symbols, read file it exists, otherwise download from wikipedia
    # For nasdaq, we need the fifth table and column named 'Ticker'
    if (ndx):
        ndx_list = build_symbol_list(url=ndx_url, table_num = 4, column_name='Ticker', output_file=ndx_symbols)
        
        # Nasdaq 100
        # Download symbol data into csv files
        # Scan for candlestick patterns
        download_symbol_data(ndx_test_symbol, ndx_symbols, ndx_data_directory, 'Downloading Nasdaq 100 Data')
        ndx_result_list = scan_symbols_for_candlestick_patterns(ndx_data_directory, ndx_list, "Scanning Nasdaq 100 for Candlestick Patterns...")

    if (sp500):
        # For S&P 500, we need the first table (0) and column named 'Symbol'
        sp500_list = build_symbol_list(url=sp500_url, table_num = 0, column_name='Symbol', output_file=sp500_symbols)

        # Download symbol data into csv files
        # Scan for candlestick patterns
        download_symbol_data(sp500_test_symbol, sp500_symbols, sp500_data_directory, 'Downloading S&P 500 Data')
        sp500_result_list = scan_symbols_for_candlestick_patterns(sp500_data_directory, sp500_list, "Scanning S&P 500 for Candlestick Patterns...")

    #-----------------------------------------------
    # Streamlit main - tabs
    # Add css to change font size of tab text
    #-----------------------------------------------
    tab_titles = ['Nasdaq 100', 'S&P 500']
    tabs = st.tabs(tab_titles)
    css = '''
    <style>
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size:2rem;
        }
    </style>
    '''
    st.markdown(css, unsafe_allow_html=True)

    with tabs[0]:
        # Will return this format: ('Engulfing Pattern', 'ADI')
        selection_ndx = st.selectbox('Nasdaq 100', sorted(ndx_result_list), key='ndx', label_visibility='hidden')
        
        # use [1] as we want to pass in the symbol, 'ADI' from the above example
        if (selection_ndx != None):
            show_tradingview_chart(selection_ndx[1])
            getEarningsData(selection_ndx[1])

    with tabs[1]:
        # Will return this format: JM ...
        selection_sp500 = st.selectbox('S&P 500', sorted(sp500_result_list), key='sp500', label_visibility='hidden')

        if (selection_sp500 != None):
            show_tradingview_chart(selection_sp500[1])
            getEarningsData(selection_sp500[1])

@st.cache_data
#-------------------------------------------------------------------------------
# Initial setup code run once
#-------------------------------------------------------------------------------
def initial_setup():

    # Create data directories
    if not os.path.isdir(ndx_data_directory):
        os.makedirs(ndx_data_directory)

    if not os.path.isdir(sp500_data_directory):
        os.makedirs(sp500_data_directory)

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------
def main():

    st.set_page_config(page_title='Candlestick Patterns', page_icon=':chart_with_upwards_trend:', layout='wide')
    st.header('Candlestick Patterns')

    initial_setup()

    col1, col2 = st.sidebar.columns(2)
    ndx = col1.checkbox('Nasdaq 100')
    sp500 = col2.checkbox('S&P 500')
    
    main_loop(ndx, sp500)
    
if __name__ == "__main__":
    main()
