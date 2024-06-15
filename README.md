# usgsrc4cast-python-example

This repository is a template example for generating a forecast that is automated through GitHub Actions.

## Applying this Repository to a New Forecast

1. Click **Use This Template** in the top right of this page to copy this example to your GitHub account.
2. Modify `forecast_model.py` to create your forecast model. Many of the components you need to generate the forecast already exist in this example, including downloading NOAA weather forecasts, downloading target data, generating forecast files, generating metadata, validating files, and submitting forecasts. Avoid running the `submit()` function at the end of `forecast_model.py` until you are ready to submit a forecast to the Challenge. **Do not change the name of the file.** GitHub Actions rely on this file name. Be sure to change your `model_id`.
3. Commit and push the changes to `forecast_model.py` to GitHub.

## Manually Running Forecast in GitHub Actions

1. Under the **Actions** tab, click on `.github/workflows/generate_forecast.yml` on the left side.
2. Click **Run workflow**, then the green **Run workflow** button.

## Automatically Running Forecast in GitHub Actions

The forecast in this repository is designed to run daily at 20:00 UTC. The execution of the forecast occurs on GitHub's servers, so your local computer does not need to be turned on. In `.github/workflows/generate_forecast.yml`, the lines `- cron: "0 20 * * *"` define the time that the forecast is run. In this case, it runs each day at 20:00:00 UTC (note all GitHub timings are in UTC). You can update this to run on a different schedule based on timing codes found at [crontab.guru](https://crontab.guru).

To start the automated forecast generation:
1. Find the file `generate_forecast.yml` in the `.github/workflows` directory on GitHub.
2. Click the edit (pencil) button to edit the file.
3. Remove the `#` before the words "schedule" and "- cron". See below:

Change

```
on:
  #schedule:
  #  - cron: '0 20 * * *'
  workflow_dispatch:
```
to
```
on:
  schedule:
    - cron: '0 20 * * *'
  workflow_dispatch:
```

A video describing how to use GitHub actions for automated forecast generation can be found here: https://youtu.be/dMrUlXi4_Bo

## Running in mybinder

You can run this repo as a "binder".  The [mybinder.org](https://mybinder.org) project will convert the repository into an interactive jupyterlab session for you. To create a binder, use the link below but replace "eco4cast/usgsrc4cast-python-example.git" with your repository. This is the exact python configuration that GitHub will be using to run your forecast.  The use of mybinder is primarily for testing and not for operationally generating forecasts. 

https://mybinder.org/v2/gh/eco4cast/usgsrc4cast-python-example.git/HEAD

## Disclaimer
Although this software program has been used by the U.S. Geological Survey (USGS), no warranty, expressed or implied, is made by the USGS or the U.S. Government as to the accuracy and functioning of the program and related program material nor shall the fact of distribution constitute any such warranty, and no responsibility is assumed by the USGS in connection therewith.
This software is provided “AS IS.”

## License Disclaimer 
As a government employee, the contributions from Jacob Zwart to this repository are in the public domain. 
