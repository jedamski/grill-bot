import os
import requests
from matplotlib import rcParams
import numpy as np
import pytz
import pymongo
from datetime import datetime, timedelta


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

        threshold_time = pytz.utc.localize(datetime.utcnow()) - timedelta(seconds=time_since)
        resp_dict = self.raw_response.find_one({'time': {'$gt': threshold_time}})

        if resp_dict != None:
            return resp_dict
        else:
            # Construct the request url, not currently asking for any fancy pance options
            if time is None:
                # Submit a forecast request to the API
                request_url = '{}{}/{},{}/'.format(self.url, self.secret_key, self.latitude, self.longitude)
            else:
                # Submit a time machine request
                request_url = '{}{}/{},{},{:.0f}/'.format(self.url, self.secret_key, self.latitude, self.longitude, time)

            # Send the API request to DarkSky
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
            self.raw_response.insert_one(resp_dict)

            return resp_dict

    @property
    def temperature(self):
        """
        This method appears as a class atribute. This returns a two element
        tuple containing two numpy arrays. The first is an offset-aware numpy
        array of datetime objects. These represent the temperature forecast for
        the day on the hour.

        return: (time - np array of datetime, temp - np array in local unit system)
        """

        # Send the request to the API
        resp_dict = self.download_data()

        return resp_dict['currently']['temperature']

if __name__ == '__main__':
    weather = Weather()
    print(weather.temperature)
