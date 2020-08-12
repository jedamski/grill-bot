import os
import requests
from matplotlib import rcParams
import numpy as np
import pytz
import pymongo
from datetime import datetime, timedelta, date
import pandas as pd
from tzlocal import get_localzone


class Weather(object):

    def __init__(self):

        # Define the parameters that are unique to me
        self.url = 'https://api.darksky.net/forecast/'
        self.secret_key = self.__get_environment_variable('DARKSKY_KEY')
        self.latitude = self.__get_environment_variable('LATITUDE')
        self.longitude = self.__get_environment_variable('LONGITUDE')

        # Initialize the client and  connect to the weather collection
        self.client = pymongo.MongoClient('mongodb://localhost:27017')

        # Create a collection for the specified latitude and longitude
        # TODO: DO this

        # Setup the database and collections
        self.weather_database = self.client.weather

        # Create a couple different collections as they will be handled differently in the class
        self.db_time_machine = self.weather_database.time_machine
        self.db_forecasts = self.weather_database.forecasts
        self.db_current = self.weather_database.current

    def __get_environment_variable(self, key):

        value = os.getenv(key)
        if value == None:
            raise ValueError('No value specified for environment variable: {}'.format(key))

        return value

    def __darksky(self, time=None):
        """
        This method does the heavy lifting of actually grabing the data from
        the REST API. The calling function is responsible for actually managing
        the data response.
        """

        if time is None:
            # Submit a request without a time, the will return the current weather along with a forecast
            query = '{},{}'.format(self.latitude, self.longitude)
        else:
            # Submit a time machine request, this will return the actual weather for a date in the past
            query = '{},{},{}'.format(self.latitude, self.longitude, self.isoformat(time))

        # Send the API request to DarkSky
        request_url = '{}{}/{}/'.format(self.url, self.secret_key, query)
        print('Weather: sending forecast request to the API - {}'.format(request_url))
        resp = requests.get(request_url)

        # If there is an error, throw an error
        if resp.status_code != 200:
            raise RuntimeError('GET /forecast/ {}'.format(resp.status_code))

        # Otherwise, deconstruct the json response
        resp_dict = resp.json()

        return resp_dict

    def __get_data(self, time=None):
        """
        Downloads the data from DarkSky API and returns a parsed dictionary from
        the json data. This function is built to work with both current
        conditions as well as looking up historical data.

        time (optional): UNIX time stamp, seconds since midnight GMT on 1 Jan 1970
        return: a dictionary based on the parsed json response
        """

        # Confirm the object coming in is a datetime or date object
        if isinstance(time, datetime):

            # Confirm the object coming in is offset aware (has a timezone property)
            if time.tzinfo is None or time.tzinfo.utcoffset(time) is None:
                raise ValueError('Day is a naive datetime object. Please assign a timezone before passing in.')

        # Convert the date object to a datetime object for midnight in the current timezone
        elif isinstance(time, date):
            time = self.date_to_datetime(time)

        elif time == None:
            pass

        elif not isinstance(time, date):
            raise ValueError('Day is of type {}. Please convert to an offset aware datetime object first.'.format(type(time)))

        # This means that the user is just asking for the current weather. The
        # database will store all requests here and will just query the database
        # to get the response if the user has asked in the last x seconds (as
        # specified by <time_since>).
        if time is None:

            # First, see if there's anything in the database from the last x minutes
            max_requests_per_day = 250.
            threshold_time = self.now() - timedelta(seconds=24.*60.*60./max_requests_per_day)
            resp_dict = self.db_current.find_one({'time': {'$gt': threshold_time}})

            # If we've already asked for something in the last x minutes, don't ask again and just retrieve from the database
            if resp_dict != None:
                return resp_dict

            # If we got here, there was nothing in the database from the last x minutes, let's download the data
            resp_dict = self.__darksky()

            # Grab the current time and store it in an accessible spot in the database
            timestamp = resp_dict['currently']['time']
            tz = pytz.timezone(resp_dict['timezone'])
            resp_dict['time'] = datetime.fromtimestamp(timestamp, tz)

            # There is no need to keep previous data in the db_current database.
            # If the user is looking for all of todays data, they should use the
            # forecast or time machine features instead. Update the current entry.
            self.db_current.update_one({}, {'$set': resp_dict}, upsert=True)

            return resp_dict


        # This means that the user is looking either for todays weather or a
        # date in the future. This will return in the form of hourly data.
        elif time.date() >= self.now().date():

            # If they are asking for today's forecast, we probably want to save
            # to the database but update frequently as they ask for it.
            max_requests_per_day = 100.
            current_time = self.now()
            threshold_time = current_time - timedelta(seconds=24.*60.*60./max_requests_per_day)
            resp_dict = self.db_forecasts.find_one({'$and': [{'date': {'$eq': time.strftime('%d-%m-%Y')}},
                                                             {'time': {'$gt': threshold_time}}]})

            # If we've already asked for this date, don't ask again and just retrieve from the database
            if resp_dict != None:
                return resp_dict

            # If we got here, there was nothing in the database from the last x minutes, let's download the data
            resp_dict = self.__darksky(time=time)

            # Grab the current time and store it in an accessible spot in the database
            resp_dict['time'] = current_time
            resp_dict['date'] = time.strftime('%d-%m-%Y')

            # Update the database with the forecast. Update if it is expired.
            self.db_forecasts.update_one({'date': {'$eq': time.strftime('%d-%m-%Y')}}, {'$set': resp_dict}, upsert=True)

            return resp_dict

        # This means that the user is looking either for todays weather or a
        # date in the future. This will return in the form of hourly data.
        elif time.date() < self.now().date():

            # See if the data is already in the database
            resp_dict = self.db_time_machine.find_one({'date': {'$eq': time.strftime('%d-%m-%Y')}})

            # If we've already asked for this date, don't ask again and just retrieve from the database
            if resp_dict != None:
                return resp_dict

            # If we got here, there was nothing in the database from the last x minutes, let's download the data
            resp_dict = self.__darksky(time=time)

            # Grab the current time and store it in an accessible spot in the database
            resp_dict['time'] = self.now()
            resp_dict['date'] = time.strftime('%d-%m-%Y')

            # Update the database with the forecast. Update if it is expired.
            self.db_time_machine.insert_one(resp_dict)

            return resp_dict

            #
        # if time is yesterday or earlier
        #
        #
        # # TODO: Add more rigorous type handling
        # if time != None:
        #     if type(time) == datetime:
        #         time = time.timestamp()
        #     elif type(time) != float or type(time) != int:
        #         raise ValueError('Invalid type for <time> passed in: {}'.format(type(time)))
        #
        # # TODO: Handle database case where time is a value or None
        # threshold_time = pytz.utc.localize(datetime.utcnow()) - timedelta(seconds=time_since)
        # resp_dict = self.raw_response.find_one({'$and': [{'time': {'$gt': threshold_time}},
        #                                                  {'date_supplied': {'$eq': time != None}}]})
        #
        # if resp_dict != None:
        #     return resp_dict
        # else:
        #     self.__get_data()
        #
        #     # Save the response in the database
        #     timestamp = resp_dict['currently']['time']
        #     tz = pytz.timezone(resp_dict['timezone'])
        #     resp_dict['time'] = datetime.fromtimestamp(timestamp, tz)
        #     resp_dict['query'] = query
        #     resp_dict['date_supplied'] = time != None
        #     self.raw_response.insert_one(resp_dict)
        #
        #     return resp_dict

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
        resp_dict = self.__get_data()

        return resp_dict['currently']

    def hourly(self, day=None):

        # If day is empty, assume they're asking for todays forecast
        if day is None:
            day = self.now().date()
        else:
            day = day.date()

        # TODO: Check if the type is offset aware or naive
        resp_dict = self.__get_data(time=day)
        forecast_data = resp_dict['hourly']['data']

        # Grab all of the unique keys that could be generated in the dataset
        keys = [list(hour.keys()) for hour in resp_dict['hourly']['data']]
        keys = np.unique([y for x in keys for y in x])
        num_entries = len(forecast_data)

        data =  {key: [] for key in keys}
        for key in keys:
            for data_entry in forecast_data:
                try:
                    data[key] += [data_entry[key]]
                except KeyError:
                    data[key] += [None]

        tz = pytz.timezone(resp_dict['timezone'])
        data['time'] = [datetime.fromtimestamp(time_value, tz) for time_value in data['time']]

        return pd.DataFrame(data)

    @staticmethod
    def now():
        """
        This method returns an offset aware datetime object for the current time
        in the local timezone.
        """

        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        return now_utc.astimezone(get_localzone())

    @staticmethod
    def date_to_datetime(date):

        this_datetime = datetime(date.year, date.month, date.day)
        this_datetime = this_datetime.astimezone(get_localzone())

        return this_datetime

    @staticmethod
    def isoformat(time):
        """
        This method will take in a date object and return a datetime at 12AM,
        the morning of the date in the local timezone. The returned object is an
        isoformat datetime string.
        """

        if isinstance(time, date):
            this_datetime = Weather.date_to_datetime(time)
        elif isinstance(time, datetime):
            this_datetime = time.astimezone(get_localzone())
        else:
            raise ValueError('Unrecognized type: {}'.format(type(time)))

        return this_datetime.isoformat()

if __name__ == '__main__':

    weather = Weather()
    print(weather.current['temperature'])
    print(weather.current['dewPoint'])
    print(weather.current['uvIndex'])

    day1 = Weather.now().date()
    #day2 = (pytz.utc.localize(datetime.utcnow()).astimezone(get_localzone())+timedelta(days=4)).date()
    print(weather.forecast(day1))
    #print(weather.forecast(day2))
    #print(day1)
    #print(day2)
    #print(weather.forecast(pytz.utc.localize(datetime.utcnow()) + timedelta(days=1)))
