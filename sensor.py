import logging
import time

from gpiozero import Button
import requests

from config import ENDPOINT, FLOOR, REQUEST_TIMEOUT, TOKEN

class Machine(Button):
    """
    Machine class used to represent a laundry machine.

    States:
        0: Unutilised 
        1: In use
        2: Finishing
       -1: Error	
    """

    def __init__(self, pin: int, pos: int, *, hold_time: int=3, timeout: int=3600, **kwargs) -> None:
        super().__init__(pin, hold_time=hold_time, **kwargs)

        self._pos = pos
        self._state: int = self.value

        self.timeout: int = timeout	# For checking invalid state. Default is 3600 seconds (1 hour).
        self.last_updated_endpoint: float = 0
        self.last_updated_state: float 	  = time.time()

    @property
    def pos(self) -> int:
        return self._pos

    @property
    def state(self) -> int:
        return self._state
        
    ###############
    # STATE LOGIC #
    ###############

    @state.setter
    def state(self, val) -> None:
        # Only update endpoint if state changes
        if self._state == val:
            return

        if val < 0:
            logging.warn(f"Updated machine {FLOOR}:{self.pos} state from {self._state} to error state {val}.")
        elif self._state < 0:
            logging.warn(f"Updated machine {FLOOR}:{self.pos} state from error state {self._state} to {val}.")
        else:
            logging.info(f"Updated machine {FLOOR}:{self.pos} state from {self._state} to {val}.")

        self._state = val
        self.last_updated_state = time.time()
        self.update_endpoint()

    def when_held(self) -> None:
        self.state = 1
    
    def when_deactivated(self) -> None:
        if self.wait_for_activation():
            self.state = 2
        else:
            self.state = 0

    ####################
    # HELPER FUNCTIONS #
    ####################

    def wait_for_activation(self, freq: float = 0.1) -> bool:
        """
        Reimplementation of `wait_for_active` from the gpiozero library, as that method
        does not seem to work well in multithreaded scenarioes.
        """
        start = time.time()
        while time.time() - start < self.hold_time:
            time.sleep(freq)
            if self.is_active:
                return True
        return False

    def update(self) -> None:
        """Detects if the sensor is in an invalid state."""
        if self.state > 0 and time.time() - self.last_updated_state > self.timeout:
            # If machine has been in an active state for longer than self.timeout, bring up error
            self.state = -1

        if self.last_updated_state > self.last_updated_endpoint:
            self.update_endpoint()

    def update_endpoint(self) -> None:
        try:
            params = {
                "floor": FLOOR,
                "pos": self.pos,
            }
            header = {"x-api-key": TOKEN}

            if self.state == 0:
                requests.put(ENDPOINT+'/machine/stop', timeout=REQUEST_TIMEOUT, params=params, headers=header)
            elif self.state == 1:
                requests.put(ENDPOINT+'/machine/start', timeout=REQUEST_TIMEOUT, params=params, headers=header)
            elif self.state == 2:
                requests.put(ENDPOINT+'/machine', timeout=REQUEST_TIMEOUT, params=params, 
                             headers=header, json={"status": "finishing"})
            else:
                requests.put(ENDPOINT+'/machine', timeout=REQUEST_TIMEOUT, params=params, 
                             headers=header, json={"status": "error"})
            self.last_updated_endpoint = time.time()
        except requests.ConnectionError as e:
            logging.error(f"Error while trying to update endpoint of machine state: {e}")
