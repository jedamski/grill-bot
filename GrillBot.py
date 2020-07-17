import logging
import atexit
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper


class Burner(stepper):

    def __init__(self, stepper_object, step='single'):
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

    def __ignite(self):

        # self.__value should be set to None, change to 1.5
        self.__value = 1.5

        # First, move the burner to the ignite position
        self.value = 1.0

        # Tell the user to press the ignite button
        self.display.print("Press ignite button...")

        # Now sleep for 5 seconds and wait for the user to press
        time.sleep(5.0)

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):

        # Check if we need to execute the ignition sequence
        if self.__value is None:
            if value is not None:
                self.__ignite()

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
        num_steps = np.abs(np.round((value - self.value)*self.burner_sector_angle/self.burner_increment))

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

        # Now log it before returning to the requesting function


        return temperature_F

    class Display(object):

        def __init__(self):

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
            lcd.clear()

        def display_status(input_front, input_back, temperature):

            #
            if input_front is None:
                input_front_str = 'OFF'
            else:
                input_front_str = '{:2.0f}%'.format(input_front)

            if input_back is None:
                input_back_str = 'OFF'
            else:
                input_back_str = '{:2.0f}%'.format(input_back)

            # Update the LCD message based on the current temp and burner inputs
            message = 'Temp: {:3.0f} F\nF: ' + input_front_str + ' / B: ' + input_back_str
            lcd.message = message


class GrillBot(object):

    def __init__(self):
        """
        """

        # Define objects for both the front and back burners
        self.burner_back  = Burner(MotorKit.stepper1, step='single')
        self.burner_front = Burner(MotorKit.stepper2, step='single'

        # Create the thermocouple object and take an ambient reading before doing anything
        self.thermometer = Thermocouple()
        print('Initialized temperature: {:3.0f} F'.format(self.thermometer.temperature))

        # Now turn both burners on, this steps takes about 10 seconds to initialize
        self.burner_front.value = 1.0
        self.burner_back.value = 1.0
