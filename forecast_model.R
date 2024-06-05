# source necessary packages for generating and submitting the forecast
library(tidyverse)
library(lubridate)
library(glue)
# The usgsrc4cast project has a few custom functions that are needed to successfully submit to the 
#  EFI-USGS river chlorophyll forecast challenge 
source("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/R/eco4cast-helpers/submit.R")
source("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/R/eco4cast-helpers/forecast_output_validator.R")
source("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/R/eco4cast-helpers/noaa_gefs.R")

# Step 0: Model configuration. 
#  Define a unique name which will identify your model in the leaderboard and connect it to team members info, etc. 
#  If running an example model, include the word "example" in your model_id - any model with "example" in the name will
#  not be scored in the challenge. When you're ready to submit a forecast to be scored, make sure you 
#  register and describe your model at https://forms.gle/kg2Vkpho9BoMXSy57 
model_id <- "usgsrc4cast_example"
# This is the forecast challenge project ID - e.g., neon4cast, usgsrc4cast
project_id <- "usgsrc4cast"
# The time-step of the forecast. Use the value of P1D for a daily forecast,
#  P1W for a weekly forecast, and PT30M for 30 minute forecast.
#  This value should match the duration of the target variable that
#  you are forecasting. Formatted as ISO 8601 duration https://en.wikipedia.org/wiki/ISO_8601#Durations
forecast_duration <- "P1D"
# variables we want to forecast
target_var <- "chla"


# Step 1: Download latest target data and site description data
# let's focus on the focal sites for this example. When you're comfortable with 
#  your model and workflow, you can expand to all sites in the challenge. 
focal_sites <- c("USGS-05553700", "USGS-14211720") 

site_data <- readr::read_csv("https://raw.githubusercontent.com/eco4cast/usgsrc4cast-ci/prod/USGS_site_metadata.csv") %>% 
  filter(site_id %in% focal_sites)

target <- readr::read_csv("https://sdsc.osn.xsede.org/bio230014-bucket01/challenges/targets/project_id=usgsrc4cast/duration=P1D/river-chl-targets.csv.gz") %>%
  dplyr::filter(site_id %in% focal_sites) %>% 
  dplyr::distinct() 

# Step 2: Get meterological predictions as drivers
forecast_date <- Sys.Date()
#Need to use yesterday's NOAA forecast because today's is not available yet
noaa_date <- Sys.Date() - days(1)  

# this next line connects to the database, but doesn't pull the data yet. That happens below with 
#   the dplyr::collect() function. Also make sure you're specifying the "usgsrc4cast" project_id in the 
#   noaa_stage3() function! 
noaa_historic <- noaa_stage3(project_id = project_id)

## For each site, average over predicted 0h horizon ensembles to get 'historic values'
# More information about the drivers (e.g., units) can be found here https://projects.ecoforecast.org/neon4cast-docs/Shared-Forecast-Drivers.html 
noaa_mean_historic <- noaa_historic %>% 
    dplyr::filter(site_id %in% focal_sites) %>% 
    dplyr::rename(ensemble = parameter) %>% 
    dplyr::select(site_id, datetime, prediction, ensemble, variable) %>% 
    dplyr::mutate(date = as_date(datetime)) %>% 
    dplyr::group_by(site_id, date, variable) %>% 
    dplyr::summarize(predicted_mean = mean(prediction, na.rm = TRUE),
                     .groups = "drop") %>% 
    dplyr::rename(datetime = date) %>% 
    dplyr::collect()

## get daily average weather for each ensemble in future
noaa_forecast <- noaa_stage2(project_id = project_id,
                             start_date = noaa_date) 

noaa_mean_forecast <- noaa_forecast %>% 
  dplyr::filter(site_id %in% focal_sites,
                reference_datetime == lubridate::as_datetime(noaa_date)) %>% 
  dplyr::rename(ensemble = parameter) %>% 
  dplyr::select(site_id, reference_datetime, datetime, variable, prediction, ensemble) %>% 
  dplyr::mutate(date = as_date(datetime)) %>% 
  dplyr::group_by(site_id, reference_datetime, date, variable, ensemble) %>% 
  dplyr::summarize(predicted_mean = mean(prediction, na.rm = TRUE),
                   .groups = "drop") %>% 
  dplyr::rename(datetime = date) %>% 
  dplyr::collect()

all_forecasts <- c() 

#Step 3: Define the forecasts model for a site
for(site in focal_sites){
  message(paste0("Running site: ", site))
  
  # historical temperatures
  cur_noaa_historic <- filter(noaa_mean_historic, 
                              site_id == site) %>% 
    pivot_wider(names_from = variable, values_from = predicted_mean)
  
  # Merge in past NOAA data into the targets file, matching by date.
  site_target <- target %>% 
    dplyr::select(datetime, site_id, variable, observation) %>% 
    dplyr::filter(variable == "chla", 
                  site_id == site) %>% 
    tidyr::pivot_wider(names_from = "variable", values_from = "observation") %>% 
    dplyr::left_join(cur_noaa_historic, by = c("datetime", "site_id")) %>% 
    # filtering out NA's 
    filter_at(3:ncol(.), all_vars(!is.na(.))) %>% 
    mutate(chla_lagged_1 = dplyr::lag(chla, n = 1)) %>%
    slice(2:n())
  
  # Fit linear model based on past data: chla = a * lagged chl-a + b * air temperature + c
  fit <- lm(chla ~ chla_lagged_1 + air_temperature, data = site_target)
  
  lagged_chla <- tibble(datetime = forecast_date, 
                        chla_lagged_1 = ifelse((forecast_date - 1) %in% site_target$datetime,
                                               site_target$chla[site_target$datetime == (forecast_date - 1)],
                                               NA)) %>% 
    # if we don't have lagged chla, then just use mean chla as starting point 
    mutate(chla_lagged_1 = ifelse(is.na(chla_lagged_1),
                                  mean(site_target$chla, na.rm = T),
                                  chla_lagged_1))
    
  #  Get 30-day predicted temperature ensemble at the site
  cur_noaa_forecast <- filter(noaa_mean_forecast, 
                              site_id == site, 
                              datetime >= forecast_date,
                              variable == 'air_temperature') %>% 
    select(-reference_datetime) %>% 
    pivot_wider(names_from = variable, values_from = predicted_mean) %>% 
    left_join(select(lagged_chla, datetime, chla_lagged_1)) 
  
  forecasted_dates <- lubridate::date(unique(cur_noaa_forecast$datetime))
  ensembles <- unique(cur_noaa_forecast$ensemble)
  
  forecasted_chla <- c()
  
  # use the linear model (predict.lm) to forecast chla for each ensemble member 
  for(i in 1:length(forecasted_dates)){
    valid_date = forecasted_dates[i]
    if(i == 1){
      cur_data <- filter(cur_noaa_forecast, datetime == valid_date) %>% 
        mutate(chla = predict(fit, tibble(air_temperature, chla_lagged_1)))
    }else{
      cur_lagged <- filter(forecasted_chla, datetime == (valid_date - 1)) %>% 
        mutate(datetime = valid_date) %>% 
        rename(chla_lagged_1 = chla) 
      cur_data <- filter(cur_noaa_forecast, datetime == valid_date) %>% 
        select(-chla_lagged_1) %>%  
        left_join(cur_lagged, by = c("site_id", "datetime", "ensemble")) %>% 
        mutate(chla = predict(fit, tibble(air_temperature, chla_lagged_1)))
    }

    # add to output tibble 
    forecasted_chla <- bind_rows(forecasted_chla, 
                                 select(cur_data, site_id, datetime, ensemble, chla))
  }
  
  # Format results to EFI standards
  forecasted_chla <- forecasted_chla %>% 
    mutate(reference_datetime = forecast_date,
           family = "ensemble",
           variable = "chla", 
           duration = "P1D", 
           project_id = project_id, 
           model_id = model_id) %>% 
    rename(parameter = ensemble,
           prediction = chla) %>% 
    select(project_id, model_id, datetime, reference_datetime,
           site_id, duration, family, parameter, variable, prediction)
  
  all_forecasts <- bind_rows(all_forecasts, forecasted_chla) 
}


#Visualize the ensemble predictions -- what do you think?
all_forecasts %>% 
  ggplot(aes(x = datetime, y = prediction, group = parameter)) +
  geom_line(alpha=0.3) +
  facet_wrap(~site_id, scales = "free")


#Forecast output file name in standards requires for Challenge.
# csv.gz means that it will be compressed
file_date <- forecast_date
forecast_file <- paste0("usgsrc4cast","-",file_date,"-",model_id,".csv")

#Write csv to disk
write_csv(all_forecasts, forecast_file)

# Step 4: Submit forecast!

submit(forecast_file = forecast_file, 
       project_id = project_id, 
       ask = FALSE)

