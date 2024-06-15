# -*- coding: utf-8 -*-
"""
Created on Wed Jun  5 14:47:35 2024

@author: jzwart
"""

# Source necessary packages for generating and submitting the forecast
import pandas as pd
import pyarrow.compute as pc
import pyarrow as pa
import statsmodels.api as sm
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests

def download_and_exec_script(url):
    response = requests.get(url)
    response.raise_for_status()  # Ensure we notice bad responses
    exec(response.text, globals())

# The usgsrc4cast project has a few custom functions that are needed to successfully submit to the
# EFI-USGS river chlorophyll forecast challenge
# Download and execute the scripts
download_and_exec_script("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/python/submit.py")
download_and_exec_script("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/python/forecast_output_validator.py")
download_and_exec_script("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/python/noaa_gefs.py")

# Step 0: Model configuration
# Define a unique name which will identify your model in the leaderboard and connect it to team members' info, etc.
# If running an example model, include the word "example" in your model_id - any model with "example" in the name will
# not be scored in the challenge. When you're ready to submit a forecast to be scored, make sure you
# register and describe your model at https://forms.gle/kg2Vkpho9BoMXSy57
MODEL_ID = "usgsrc4cast_example"
# This is the forecast challenge project ID - e.g., neon4cast, usgsrc4cast
PROJECT_ID = "usgsrc4cast"
# The time-step of the forecast. Use the value of P1D for a daily forecast,
# P1W for a weekly forecast, and PT30M for a 30-minute forecast.
# This value should match the duration of the target variable that
# you are forecasting. Formatted as ISO 8601 duration https://en.wikipedia.org/wiki/ISO_8601#Durations
FORECAST_DURATION = "P1D"
# Variables we want to forecast
TARGET_VAR = "chla"

# Step 1: Download latest target data and site description data
# Let's focus on the focal sites for this example. When you're comfortable with
# your model and workflow, you can expand to all sites in the challenge.
FOCAL_SITES = ["USGS-05553700", "USGS-14211720"]

site_data_url = "https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/USGS_site_metadata.csv"
target_data_url = "https://sdsc.osn.xsede.org/bio230014-bucket01/challenges/targets/project_id=usgsrc4cast/duration=P1D/river-chl-targets.csv.gz"

site_data = pd.read_csv(site_data_url)
target = pd.read_csv(target_data_url)

site_data = site_data[site_data['site_id'].isin(FOCAL_SITES)]
target = target[target['site_id'].isin(FOCAL_SITES)].drop_duplicates()

# Step 2: Get meteorological predictions as drivers
forecast_date = datetime.now().date()
# Need to use yesterday's NOAA forecast because today's is not available yet
noaa_date = forecast_date - timedelta(days=2)


## This next line connects to the database but doesn't pull the data yet. That happens below with
# the filter functions. Also, make sure you're specifying the "usgsrc4cast" project_id in the
# noaa_stage3() function!
noaa_historic = noaa_stage3(project_id=PROJECT_ID)

# Filter rows based on site_id values
filter_condition = pc.field('site_id').isin(FOCAL_SITES)
filtered_noaa_historic = noaa_historic.filter(filter_condition)

# Convert to table and then to Pandas DataFrame
filtered_noaa_historic_df = filtered_noaa_historic.to_table().to_pandas()

# Rename columns
filtered_noaa_historic_df = filtered_noaa_historic_df.rename(columns={'parameter': 'ensemble'})

# Select specific columns
filtered_noaa_historic_df = filtered_noaa_historic_df[['site_id', 'datetime', 'prediction', 'ensemble', 'variable']]

# Create a new column 'date' from 'datetime'
filtered_noaa_historic_df['date'] = pd.to_datetime(filtered_noaa_historic_df['datetime']).dt.date

# Group by 'site_id', 'date', and 'variable', and calculate the mean of 'prediction'
noaa_mean_historic = filtered_noaa_historic_df.groupby(['site_id', 'date', 'variable'], as_index=False).agg(
    predicted_mean=pd.NamedAgg(column='prediction', aggfunc='mean')
)

# Rename 'date' to 'datetime'
noaa_mean_historic = noaa_mean_historic.rename(columns={'date': 'datetime'})
    
## Get daily average weather for each ensemble in future
noaa_forecast = noaa_stage2(project_id=PROJECT_ID, start_date=noaa_date.strftime("%Y-%m-%d"))

# Filter for specific site_id values and reference_datetime
filter_condition = (pc.field('site_id').isin(FOCAL_SITES)) & \
                   (pc.field('reference_datetime') == pa.scalar(noaa_date.strftime("%Y-%m-%d")))
filtered_forecast = noaa_forecast.filter(filter_condition)

# Convert to table and then to Pandas DataFrame
filtered_forecast_df = filtered_forecast.to_table().to_pandas()

# Rename columns
filtered_forecast_df = filtered_forecast_df.rename(columns={'parameter': 'ensemble'})

# Select specific columns
filtered_forecast_df = filtered_forecast_df[['site_id', 'reference_datetime', 'datetime', 'variable', 'prediction', 'ensemble']]

# Create a new column 'date' from 'datetime'
filtered_forecast_df['date'] = pd.to_datetime(filtered_forecast_df['datetime']).dt.date

# Group by 'site_id', 'reference_datetime', 'date', 'variable', and 'ensemble', and calculate the mean of 'prediction'
noaa_mean_forecast = filtered_forecast_df.groupby(['site_id', 'reference_datetime', 'date', 'variable', 'ensemble'], as_index=False).agg(
    predicted_mean=pd.NamedAgg(column='prediction', aggfunc='mean')
)

# Rename 'date' to 'datetime'
noaa_mean_forecast = noaa_mean_forecast.rename(columns={'date': 'datetime'})


# Initialize the forecasts list
all_forecasts = []

for site in FOCAL_SITES:
    print(f"Running site: {site}")

    # Historical temperatures (using noaa_mean_historic DataFrame)
    cur_noaa_historic = noaa_mean_historic[noaa_mean_historic['site_id'] == site].pivot_table(
        index='datetime', columns='variable', values='predicted_mean').reset_index()
    # Convert datetime to string
    cur_noaa_historic['datetime'] = cur_noaa_historic['datetime'].astype(str)

    site_target = target[(target['site_id'] == site) & (target['variable'] == 'chla')].pivot_table(
        index='datetime', columns='variable', values='observation').reset_index()
    # Convert datetime to string
    site_target['datetime'] = site_target['datetime'].astype(str)

    site_target = pd.merge(site_target, cur_noaa_historic, on='datetime', how='left').dropna()
    site_target['chla_lagged_1'] = site_target['chla'].shift(1)
    site_target = site_target.dropna()

    # Fit linear model
    X = site_target[['chla_lagged_1', 'air_temperature']]
    X = sm.add_constant(X, has_constant = 'add')
    y = site_target['chla']
    model = sm.OLS(y, X).fit()

    lagged_chla = pd.DataFrame([{
        'datetime': forecast_date,
        'chla_lagged_1': site_target['chla'].iloc[-1] if (forecast_date - timedelta(days=1)) in site_target['datetime'].values else site_target['chla'].mean()
    }])
    
    # Filter the noaa_mean_forecast DataFrame
    cur_noaa_forecast = noaa_mean_forecast[
        (noaa_mean_forecast['site_id'] == site) &
        (noaa_mean_forecast['datetime'] >= forecast_date) &
        (noaa_mean_forecast['variable'] == 'air_temperature')
    ].drop(columns=['reference_datetime'])
    # Pivot wider
    cur_noaa_forecast = cur_noaa_forecast.pivot_table(
        index=['site_id', 'datetime', 'ensemble'], columns='variable', values='predicted_mean'
    ).reset_index()
    # Merge with lagged_chla
    cur_noaa_forecast = pd.merge(cur_noaa_forecast, lagged_chla, on='datetime', how='left')

    # Forecasting
    forecasted_chla = []
    forecasted_dates = sorted(cur_noaa_forecast['datetime'].unique())
    ensembles = sorted(cur_noaa_forecast['ensemble'].unique())

    for i, valid_date in enumerate(forecasted_dates):
        if i == 0:
            cur_data = cur_noaa_forecast[cur_noaa_forecast['datetime'] == valid_date].copy()
            X_new = cur_data[['chla_lagged_1','air_temperature']]
            X_new = sm.add_constant(X_new, has_constant = 'add')
            cur_data['chla'] = model.predict(X_new)
        else:
            cur_lagged = forecasted_chla[-1][forecasted_chla[-1]['datetime'] == valid_date - pd.Timedelta(days=1)].copy()
            cur_lagged['datetime'] = valid_date
            cur_lagged = cur_lagged.rename(columns={'chla': 'chla_lagged_1'})
            cur_data = cur_noaa_forecast[cur_noaa_forecast['datetime'] == valid_date].copy()
            cur_data = cur_data.drop(columns=['chla_lagged_1'])
            cur_data = pd.merge(cur_data, cur_lagged, on=['site_id', 'datetime', 'ensemble'], how='left')
            X_new = cur_data[['chla_lagged_1','air_temperature']]
            X_new = sm.add_constant(X_new, has_constant = 'add')
            cur_data['chla'] = model.predict(X_new)
    
        forecasted_chla.append(cur_data[['site_id', 'datetime', 'ensemble', 'chla']])
    
    # Combine all forecasted data
    forecasted_chla = pd.concat(forecasted_chla).reset_index(drop=True)

    # Format results
    forecasted_chla['reference_datetime'] = forecast_date
    forecasted_chla['family'] = 'ensemble'
    forecasted_chla['variable'] = 'chla'
    forecasted_chla['duration'] = FORECAST_DURATION
    forecasted_chla['project_id'] = PROJECT_ID
    forecasted_chla['model_id'] = MODEL_ID
    forecasted_chla = forecasted_chla.rename(columns={'ensemble': 'parameter', 'chla': 'prediction'})

    all_forecasts.append(forecasted_chla)

# Combine all forecasts
all_forecasts = pd.concat(all_forecasts)


# Plotting the forecast
for site in FOCAL_SITES:
    site_forecast = all_forecasts[all_forecasts['site_id'] == site]
    plt.figure(figsize=(10, 5))
    for parameter in site_forecast['parameter'].unique():
        subset = site_forecast[site_forecast['parameter'] == parameter]
        plt.plot(subset['datetime'], subset['prediction'], alpha=0.3)
    plt.title(f"Forecast for {site}")
    plt.xlabel("Date")
    plt.ylabel("Chla Prediction")
    plt.show()

# Save to CSV
forecast_file = f"usgsrc4cast-{forecast_date}-{MODEL_ID}.csv"
all_forecasts.to_csv(forecast_file, index=False)

# Submit forecast 
submit(forecast_file=forecast_file, project_id=PROJECT_ID, ask=False)
