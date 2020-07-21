import adafruit_character_lcd.character_lcd as characterlcd
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
from time import sleep
import adafruit_max31855
import digitalio
import datetime
import logging
import atexit
import busio
import board
import uuid


class Burner(stepper):

    def __init__(self, position, stepper_object, step='single'):
        """
        This class handles the grill controller abstraction. The user can treat
        this object as just a scalar variable and the class manages the details
        of controlling the stepper motors to set the knob position.

                            *** ### ### ***
                        *##        |        ##*
                    *##           OFF           ##*
                 *##             (1.5)             ##*
               *##                 |                 ##*
             *##                   |                   ##*
            *##                    |                    ##*
           *##                     |                     ##*
          *##                      |                      ##*
          *##                      |                      ##*
          *##  Ignite / High ----- 0 --------------- Min  ##*
          *##       (1.0)          |                (0.0) ##*
          *##                      |                      ##*
           *##                     |                     ##*
            *##                    |                    ##*
             *##                   |                   ##*
               *##                 |                 ##*
                 *#               Mid              ##*
                    *##          (0.5)          ##*
                         *##       |        ##*
                            *** ### ### ***
        """

        # Before we do anything, define the cleanup function. Turn the burner off when the program closes
        atexit.register(cleanup)

        # Specify the increments for the gearing, burner sector angle is the degrees corresponding to 1 unit on the burner set point scale
        burner_sector_angle = 180.0
        motor_increment = 1.8

        # Define the mechanical configuration for the hardware gearing
        tooth_count_sec = 9.0
        tooth_count_pri = 16.0
        self.gear_ratio = tooth_count_sec/tooth_count_pri

        # This descriptor is a positional descriptor for the user
        self.position = postion

        # Get the specific stepper increment, stepper motor can manage three types
        if step == 'single':
            self.burner_increment = motor_increment
            self.stepper_step = step
            self.stepper_increment = stepper.SINGLE
        elif step == 'double':
            self.burner_increment = 2*motor_increment
            self.stepper_step = step
            self.stepper_increment = stepper.SINGLE
        elif step == 'half':
            self.burner_increment = motor_increment/2.0
            self.stepper_step = step
            self.stepper_increment = stepper.INTERLEAVE

        # Calculate minimum burner increment in degrees allowable with current configuration
        self.min_burner_increment = self.stepper_increment*tooth_count_sec/tooth_count_pri
        self.stepper = stepper_object

        # We always assume the grill starts out in the off position
        self.__value = 1.5

        # Alright, time to start the grill
        self.ignite()
        self.display.message('')

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):

        # Check if we need to execute the ignition sequence
        if self.value is None:
            if value is not None:
                self.ignite()

        # Limit input value to range of allowable inputs
        if value is None:
            logger.warning('Value set to None, turning the burner off')
        elif value > 1.0:
            logger.warning('Value greater than 1.0 ({:1.2f}), turning the burner off'.format(value))
            value = 1.5
        elif value < 0.0:
            logger.warning('Value less than 0.0 ({:1.2f}), limiting value to 0.0'.format(value))
            value = 0.0

        # Calculate the number of steps required to move
        num_steps = np.floor(np.abs((value - self.value)*self.burner_sector_angle/self.burner_increment))

        # Determine direction and number of steps required to reach set point
        if value > self.value:
            direction = stepper.FORWARD
            new_value = self.value + num_steps*self.burner_increment/self.burner_sector_angle
        elif self.value < self.value:
            direction = stepper.BACKWARD
            new_value = self.value - num_steps*self.burner_increment/self.burner_sector_angle
        else:
            new_value = value

        # Move the motor the calculated number of steps
        for i in range(0, num_steps):
            self.stepper.onestep(direction=stepper, style=self.stepper_increment)

        # After the motor has successfully moved, update the value
        if new_value == 1.5:
            self.__value = None
        else:
            self.__value = new_value

        # Always release the motor. Limits torque, but reduces overheating
        self.stepper.release()

    def cleanup(self):

        # The object is being deleted, turn the burner off
        self.value = None

    def ignite(self):
        """
        This function is called upon class instanciation. The user is required
        to depress the gas knob to bypass the physical stop on the grill. The
        user presses the knob down and the stepper mover moves the knob to the
        ignition position. From there, the user then has 3 seconds to press the
        igniter.
        """

        # self.__value should be set to None, change to 1.5
        self.value = 1.5

        # Have the user press the knob down, to bypass the physical stop
        self.display.message('Press ' + self.position '\nburner down... 5')
        sleep(1.0)
        self.display.message('Press ' + self.position '\nburner down... 4')
        sleep(1.0)
        self.display.message('Press ' + self.position '\nburner down... 3')
        sleep(1.0)
        self.display.message('Press ' + self.position '\nburner down... 2')
        sleep(1.0)
        self.display.message('Press ' + self.position '\nburner down... 1')
        sleep(1.0)

        # First, move the burner to the ignite position
        self.display.message('Good job, you can\nlet go now')
        self.value = 1.0

        # Tell the user to press the ignite button
        self.display.message("Press ignite\nbutton... 3")
        sleep(1.0)
        self.display.message("Press ignite\nbutton... 2")
        sleep(1.0)
        self.display.message("Press ignite\nbutton... 1")
        sleep(1.0)
        self.display.message("Good job!")
        sleep(2.0)

class Thermocouple(object):

    def __init__(self, io_pin=board.D5):
        """
        This class acts as an interface for the max31855 board and Thermocouple
        mounted in the grill. The class returns temperature readings in
        Fahrenheit.
        """

        try:
            # Specify the IO ports that are wired
            spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            cs = digitalio.DigitalInOut(io_pin)

            # Define the board interface object
            self.__max31855 = adafruit_max31855.MAX31855(spi, cs)
        except:
            raise IOError('There was an error establishing the max31855 thermocouple interface')

    @property
    def temperature(self):
        """
        This function returns a floating point number when asked. If it is
        unable to take a reading, it will return a nan. The calling function
        should be prepared to handle cases where the Pi can't talk to the
        thermocouple amplifier.
        """

        try:
            # Try retrieving the temperature from the chip
            temperature_F = self.__max31855.temperature*9.0/5.0 + 32.0
        except:
            # If it doesn't work, return a nan
            temperature_F = np.nan

        return temperature_F

class SimulatedThermocouple(Thermocouple):

    def __init__(self, front_burner, back_burner):

        # dT/dt = a*(T - Tamb) + b*u(t) + c
        self.a = -0.00425
        self.b = 1.299
        self.c = 0.557
        self.Tamb = 70.0
        self.current_temp = self.Tamb

        # Grab the current time so we can track the grill temperature behaviour
        self.current_time = datetime.datetime.now()

        # Call the parent class to initialize the base Thermocouple class
        super().__init__()

    @property
    def temperature(self):

        # Calculate the time since the last iteration and update the current timestamp
        t_last = self.current_time
        t_now = datetime.datetime.now()
        dt = t_now - t_last
        self.current_time = t_now

        # Calculate the current temperature
        dTdt = self.a*(self.current_temp - self.Tamb) + self.b*(self.front_burner.value/2 + self.back_burner/2) + self.c
        temperature_F = self.current_temp + dTdt*dt
        self.current_temp = temperature_F

        return temperature_F

class Display(object):

    def __init__(self, startup_message='  Hello World!\n'):

        # Define the geometry of the display, the class will limit incoming message accordingly
        self.columns = 16
        self.rows = 2

        # Define which pins are used for the display
        lcd_rs = digitalio.DigitalInOut(board.D22)
        lcd_en = digitalio.DigitalInOut(board.D17)
        lcd_d4 = digitalio.DigitalInOut(board.D25)
        lcd_d5 = digitalio.DigitalInOut(board.D24)
        lcd_d6 = digitalio.DigitalInOut(board.D23)
        lcd_d7 = digitalio.DigitalInOut(board.D18)

        # Initialise the lcd class using a package provided by adafruit
        self.lcd = characterlcd.Character_LCD_Mono(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7, lcd_columns, lcd_rows)

        # Wipe the LCD screen before we start
        self.lcd.clear()

        # Add a welcome message for the user and sleep for at least 1 second
        self.message(startup_message)
        sleep(1.0)

    def message(message):
        """
        This function takes in a string and ensures the message meets all
        requirements of the given LCD. The message should use \n special
        characters for line breaks and should not include a trailing \n. If a
        None is supplied instead, the lcd will be cleared.
        """

        # This function only works with string inputs and None, anything else throws an error
        if type(message) == str:

            # Split the string up into the rows, message shouldn't have a trailing end line
            lines = message.split('\n')

            # The incoming message shouldn't exceed the number of available rows on the LCD display
            if len(lines) > self.rows:
                raise ValueError('Message has two many rows ({:})'.format(len(lines)))

            # Loop through and confirm the message meets the specific LCD requirements
            for ind, line in enumerate(lines):
                if len(line > self.columns):
                    raise ValueError('Line {:} of the message has two many columns ({:})'.format(ind+1, len(line)))
                else:
                    # If the line is short enough, append to the final message
                    if ind == 0:
                        message_out = line
                    else:
                        message_out = '\n' + line

            # Now send the reconstructed message to the lcd display
            self.lcd.message = message_out
            print(message_out)

        elif message is None:
            # If message is equal to None, just clear the lcd and move on
            self.lcd.clear()

        else:
            # If anything but a string is supplied, notify the user
            raise ValueError('Display.message expects a string input')

class GrillDisplay(Display):

    def __init__(self, startup_message='  Hello World!  \n  I''m GrillBot'):
        """
        This class is very similar to the Display class, but it can work with
        thermocouple and burner data to present some Grill specific messages.
        This class relies on the message filtering from the basic Display class.
        """

        # Pass in the GrillBot specific startup message to the display class
        super().__init__(startup_message)

    def display_status(self, input_front, input_back, temperature, amb_temperature):

        # Add some data type catching to handle case when burner is off
        if (input_front is None) or (input_front == 1.5):
            input_front_str = 'OFF'
        else:
            input_front_str = '{:2.0f}%'.format(input_front.value*100)

        # Add some data type catching to handle case when burner is off
        if (input_back is None) or (input_back == 1.5):
            input_back_str = 'OFF'
        else:
            input_back_str = '{:2.0f}%'.format(input_back.value*100)

        # Update the LCD message based on the current temp and burner inputs
        message = 'Temp: {:3.0f} / {:3.0f}\nF: '.format(temperature, amb_temperature) + input_front_str + ' / B: ' + input_back_str
        self.message(message)

class GrillDatabase(object):

    def __init__(self, URI='mongodb://localhost:27017', verbose=session):
        """
        This manages all data storage needs for the grill, including temperature
        data, weather information, model training data, and model coefficients
        for the thermodynamic model and the associated controller.
        """

        # Initialize the client and  connect to the ingredients collection
        self.__client = pymongo.MongoClient('mongodb://localhost:27017')

        # Define a unique session id and create a session for it
        self.session_id = uuid4()
        self.__sessions = self.__client.sessions
        self.__sessions[self.session_id]

        # Initialize the empty arrays
        self.__sessions[self.session_id]['time']            = np.array([], dtype=datetime)
        self.__sessions[self.session_id]['temperature']     = np.array([], dtype=float)
        self.__sessions[self.session_id]['front_burner']    = np.array([], dtype=float)
        self.__sessions[self.session_id]['back_burner']     = np.array([], dtype=float)
        self.__sessions[self.session_id]['set_temperature'] = np.array([], dtype=float)

    def add_entry(temperature, set_temperature, front_burner, back_burner):

        # First append a new entry onto the current session
        update = self.__sessions.update_one({'_session_id': self.session_id},
                                            {'$push': {'time': new Timestamp(),
                                                       'temperature': temperature,
                                                       'front_burner': front_burner.value,
                                                       'back_burner': back_burner.value,
                                                       'set_temperature': set_temperature}})

        # Handle the case where nothing was changed in the database
        if update.matched_count != 1:
            raise ValueError('Could not find the current session in the database')

    def load_model_parameters(self):
        # Assumed physical model
        # dT/dt = a*(T - Tamb) + b*u(t) + c

        a = self.__client.model['a']
        b = self.__client.model['b']
        c = self.__client.model['c']

        return a, b, c

    def save_model_parameters(self, a, b, c):
        # Assumed physical model
        # dT/dt = a*(T - Tamb) + b*u(t) + c

        self.__client.model['form'] = 'dT/dt = a*(T - Tamb) + b*u(t) + c'
        self.__client.model['a'] = a
        self.__client.model['b'] = b
        self.__client.model['c'] = c

class Weather(object):

    def __init__(self):
        pass

class GrillBot(object):

    def __init__(self):
        """
        """

        # Create a unique session id for the database
        self.session_id = uuid4()
        self.database = GrillDatabase()

        # Create the grill display so that it's ready for the burner object creation
        self.display = GrillDisplay()

        # Define objects for both the front and back burners
        self.burner_back  = Burner(MotorKit.stepper1, step='single', display=self.display)
        self.burner_front = Burner(MotorKit.stepper2, step='single', display=self.display)

        # Create the thermocouple object and take an ambient reading before doing anything
        self.thermocouple = SimulatedThermocouple(self.burner_front, self.burner_back)
        self.weather = Weather()

        # Now that all hardware interfaces are established, print current status
        self.display_status()

    def display_status(self):

        # Grab the current temperature and log it in the database
        temperature = self.thermocouple.temperature
        temperature_amb = self.weather.temperature

        # Display the current status to the user
        self.database.add_entry(temperature, temperature_amb, self.set_temperature, self.front_burner, self.back_burner)
        self.display.display_status(self.burner_front, self.burner_back, temperature, temperature_amb)

    def train(self):

        # First, let's set both of the burners to full power
        self.burner_front.value = 1.0
        self.burner_front.value = 1.0

        # Alert the user before logging all of the data
        self.display.message('Training time\nCome back in 12')
        sleep(3)

        # Now, save off the temp every 5 seconds for 12 minutes
        self.burner_front.value = 0.0
        self.burner_front.value = 0.0
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        self.burner_front.value = 0.2
        self.burner_front.value = 0.2
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        self.burner_front.value = 0.4
        self.burner_front.value = 0.4
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        self.burner_front.value = 0.6
        self.burner_front.value = 0.6
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        self.burner_front.value = 0.8
        self.burner_front.value = 0.8
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        self.burner_front.value = 1.0
        self.burner_front.value = 1.0
        for t in np.arange(0, 60/5*2, 5):
            self.display_status()
            sleep(5)

        # Grab all of the data that has been logged so far in this session
        time, temp, input = self.database.load_data()

        # Model form: dT/dt = a*(T - Tamb) + b*u(t) + c
        self.database.save_model_parameters(a, b, c)
