import atexit
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper

class Burner(stepper):

    def __init__(self, stepper_object, position=None, step='single'):
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
                         *##        |        ##*
                            *** ### ### ***
        """

        # Specify the increments for the gearing, burner sector angle is the
        # degrees corresponding to 1 unit on the burner set point scale
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

        # Now that all settings are established, assign value to self.value
        self.stepper = stepper_object
        self.value = None

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):

        # Limit input value to range of allowable inputs
        if value is None:
            value = 1.5
        elif value > 1.5:
            value = 1.5
        elif value < 0.0:
            value = 0.0

        # Calculate the number of steps required to move
        num_steps = np.abs(np.round((value - self.__value)*self.burner_sector_angle/self.burner_increment))

        # Determine direction and number of steps required to reach set point
        if value > self.__value:
            direction = stepper.FORWARD
            new_value = self.__value + num_steps*self.burner_increment/self.burner_sector_angle
        elif self.value < self.__value:
            direction = stepper.BACKWARD
            new_value = self.__value - num_steps*self.burner_increment/self.burner_sector_angle
        else:
            new_value = value

        # Move the motor the calculated number of steps
        for i in range(0, num_steps):
            self.stepper.onestep(direction=stepper, style=self.stepper_increment)

        # After the motor has successfully moved, update the value
        self.__value = new_value

        # Always release the motor. Limits torque, but reduces overheating
        self.stepper.release()


    def cleanup(self):
        """
        """

        # The object is being deleted, turn the burner off
        self.value = None

        # TODO: In case everything breaks, alert a separate script to launch to turn it off
        pass

class GrillBot(object):

    def __init__(self):
        """
        """

        # Define objects for both the front and back burners
        self.burner_back  = None
        self.burner_front = None

        def cleanup():
            cache_file.close()
            os.remove(cache_filename)

        atexit.register(cleanup)
