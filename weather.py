import os
import requests
from matplotlib import rcParams
import numpy as np
import pytz
import pymongo
from datetime import datetime, timedelta
import pandas as pd


class Weather(object):

    def __init__(self):

        # Define the parameters that are unique to me
        self.url = 'https://api.darksky.net/forecast/'
        self.secret_key = self.__get_environment_variable('DARKSKY_KEY')
        self.latitude = self.__get_environment_variable('LATITUDE')
        self.longitude = self.__get_environment_variable('LONGITUDE')

        # Initialize the client and  connect to the weather collection
        self.client = pymongo.MongoClient('mongodb://localhost:27017')

        # Setup the database and collections
        self.weather_database = self.client.weather
        self.raw_response = self.weather_database.raw_response

    def __get_environment_variable(self, key):

        value = os.getenv(key)
        if value == None:
            raise ValueError('No value specified for environment variable: {}'.format(key))

        return value

    def download_data(self, time=None, time_since=5*60.0):
        """
        Downloads the data from DarkSky API and returns a parsed dictionary from
        the json data. This function is built to work with both current
        conditions as well as looking up historical data.

        time (optional): UNIX time stamp, seconds since midnight GMT on 1 Jan 1970
        return: a dictionary based on the parsed json response
        """

        # TODO: Add more rigorous type handling
        if time != None:
            if type(time) == datetime:
                time = time.timestamp()
            elif type(time) != float or type(time) != int:
                raise ValueError('Invalid type for <time> passed in: {}'.format(type(time)))

        # TODO: Handle database case where time is a value or None
        threshold_time = pytz.utc.localize(datetime.utcnow()) - timedelta(seconds=time_since)
        resp_dict = self.raw_response.find_one({'time': {'$gt': threshold_time}})

        if resp_dict != None:
            return resp_dict
        else:
            # Construct the request url, not currently asking for any fancy pance options
            if time is None:
                # Submit a forecast request to the API
                query = '{},{}'.format(self.latitude, self.longitude)
            else:
                # Submit a time machine request
                query = '{},{},{:.0f}'.format(self.latitude, self.longitude, time)

            # Send the API request to DarkSky
            request_url = '{}{}/{}/'.format(self.url, self.secret_key, query)
            print('Weather: sending forecast request to the API - {}'.format(request_url))
            resp = requests.get(request_url)

            # If there is an error, throw an error
            if resp.status_code != 200:
                raise RuntimeError('GET /forecast/ {}'.format(resp.status_code))

            # Otherwise, deconstruct the json response
            resp_dict = resp.json()

            # Save the response in the database
            timestamp = resp_dict['currently']['time']
            tz = pytz.timezone(resp_dict['timezone'])
            resp_dict['time'] = datetime.fromtimestamp(timestamp, tz)
            resp_dict['query'] = query
            self.raw_response.insert_one(resp_dict)

            return resp_dict

    @property
    def current(self):
        """
        This method appears as a class atribute. This returns a dictionary with
        key value pairs where the value is typically a float or a String. It is
        not guaranteed that every variable will be available time, ex: precip
        type.

        --- EXAMPLE OUTPUT ---
        time: 1509993277,
        summary: "Drizzle",
        icon: "rain",
        nearestStormDistance: 0,
        precipIntensity: 0.0089,
        precipIntensityError: 0.0046,
        precipProbability: 0.9,
        precipType: "rain",
        temperature: 66.1,
        apparentTemperature: 66.31,
        dewPoint: 60.77,
        humidity: 0.83,
        pressure: 1010.34,
        windSpeed: 5.59,
        windGust: 12.03,
        windBearing: 246,
        cloudCover: 0.7,
        uvIndex: 1,
        visibility: 9.84,
        ozone: 267.44
        """

        # Send the request to the API
        resp_dict = self.download_data()

        return resp_dict['currently']

    def forecast(self, day=None):

        # If day is empty, assume they're asking for todays forecast
        if day is None:
            day = pytz.utc.localize(datetime.utcnow())

        # Confirm the object coming in is a datetime object
        if type(day) != datetime:
            raise ValueError('Day is of type {}. Please convert to an offset aware datetime object first.'.format(type(day)))

        # Confirm the object coming in is offset aware (has a timezone property)
        if day.tzinfo is None or day.tzinfo.utcoffset(day) is None:
            raise ValueError('Day is a naive datetime object. Please assign a timezone before passing in.')

        # TODO: Check if the type is offset aware or naive
        resp_dict = self.download_data(time=day)

        forecast_data = resp_dict['hourly']['data']

        keys = forecast_data[0]
        num_entries = len(forecast_data)

        data = {}
        for key in keys:
            data[key] = [data_entry[key] for data_entry in forecast_data]

        tz = pytz.timezone(resp_dict['timezone'])
        data['time'] = [datetime.fromtimestamp(time_value, tz) for time_value in data['time']]

        return pd.DataFrame(data)

if __name__ == '__main__':

    weather = Weather()
    print(weather.current['temperature'])
    print(weather.current['dewPoint'])
    print(weather.current['uvIndex'])

    print(weather.forecast())
