import logging
import atexit
import uuid
from time import sleep
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper


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
        Fahrenheit and logs all requests in the MongoDB database.
        """

        # Specify the IO ports that are wired
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        cs = digitalio.DigitalInOut(io_pin)

        # Define the board interface object
        self.__max31855 = adafruit_max31855.MAX31855(spi, cs)

    @property
    def temperature(self):
        """
        This function returns a floating point number when asked. Once it
        retrieves the value, it will store it in the MongoDB database.
        """

        # First grab the temperature value
        temperature_F = self.__max31855.temperature*9.0/5.0 + 32.0

        return temperature_F

    class Display(object):

        def __init__(self, startup_message='  Hello World!  \n  I''m GrillBot'):

            # Define the geometry of the display
            self.columns = 16
            self.rows = 2

            # Define which pins are used for the display
            lcd_rs = digitalio.DigitalInOut(board.D22)
            lcd_en = digitalio.DigitalInOut(board.D17)
            lcd_d4 = digitalio.DigitalInOut(board.D25)
            lcd_d5 = digitalio.DigitalInOut(board.D24)
            lcd_d6 = digitalio.DigitalInOut(board.D23)
            lcd_d7 = digitalio.DigitalInOut(board.D18)

            # Initialise the lcd class from adafruit
            self.lcd = characterlcd.Character_LCD_Mono(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7, lcd_columns, lcd_rows)

            # Wipe the LCD screen before we start
            self.lcd.clear()

            # Add a welcome message for the user and sleep for at least 1 second
            self.lcd.message(startup_message)
            sleep(1.0)

        def message(message):

            # Need to confirm message is less than 2x16 characters
            lines = message.split('\n')

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

    class GrillDisplay(Display):

        def __init__(self, startup_message=None):

            # Pass in the GrillBot specific startup message to the display class
            if startup_message is None:
                super().__init__(startup_message='  Hello World!  \n  I''m GrillBot')
            else:
                super().__init__()

        def display_status(self, input_front, input_back, temperature):

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
            message = 'Temp: {:3.0f} F\nF: ' + input_front_str + ' / B: ' + input_back_str
            self.message = message

class GrillDatabase(object):

    def __init__(self, URI='mongodb://localhost:27017', verbose=session):
        """
        This manages both downloading data from the USDA API as well as cacheing
        it and retrieving it when nevessary.
        """
        # Initialize the client and  connect to the ingredients collection
        self.__client = pymongo.MongoClient('mongodb://localhost:27017')

        # I think ingredients is a collection
        self.start_time = datetime.datetime.now()
        self.session_id = uuid4()
        self.__sessions = self.__client.sessions

        # Create a unique entry for the current session
        self.__sessions[self.session_id]

        # Initialize the empty arrays
        self.__sessions[self.session_id]['time']            = np.array([], dtype=datetime)
        self.__sessions[self.session_id]['temperature']     = np.array([], dtype=float)
        self.__sessions[self.session_id]['front_burner']    = np.array([], dtype=float)
        self.__sessions[self.session_id]['back_burner']     = np.array([], dtype=float)
        self.__sessions[self.session_id]['set_temperature'] = np.array([], dtype=float)

    def add_entry(temperature, set_temperature, front_burner, back_burner):

        db.__sessions.find_one_and_update({'_session_id': self.session_id}, {'$temperature': temperature,
                                                                             '$front_burner': front_burner.value,
                                                                             '$back_burner': back_burner.value,
                                                                             '$set_temperature': set_temperature})

class GrillBot(object):

    def __init__(self):
        """
        """

        # Create a unique session id for the database
        self.session_id = uuid4()

        # Create the grill display so that it's ready for the burner object creation
        self.display = GrillDisplay()

        # Define objects for both the front and back burners
        self.burner_back  = Burner(MotorKit.stepper1, step='single', display=self.display)
        self.burner_front = Burner(MotorKit.stepper2, step='single', display=self.display)

        # Create the thermocouple object and take an ambient reading before doing anything
        self.thermometer = Thermocouple()
        self.display_status()

    def display_status(self):

        temperature = self.thermometer.temperature


        self.display.display_status(self.burner_front, self.burner_back, temperature)

    def load_data(self):

        self.session_id

    def train(self):

        # First, let's set both of the burners to full power
        self.burner_front.value = 1.0
        self.burner_front.value = 1.0

        # Alert the user before logging all of the data
        self.display.message('Training time\nCome back in 10')
        sleep(3)

        # Now, save off the temp every 5 seconds for 10 minutes
        for t in np.arange(0, 5*60*10+5, 5):

            # Display status will check the temperature and in doing so, will save the temperature into the database
            self.display_status()
            sleep(5)

        # Grab all of the data that has been logged so far in this session
        time, temp, input = self.load_data()
