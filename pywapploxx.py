from typing import List, Optional
import base64
import json
import math
import os
import re
import requests
import sys
import time
from requests.models import Response
import urllib3

IP_BLOCK_FILENAME = ".wapploxx-ip-block-time"

##
# Exceptions


class WAppLoxxError(Exception):
    """Base class for other exceptions"""


class AuthError(WAppLoxxError):
    AUTH_ERROR_DESCRIPTIONS = {
        "UNAVAILABLE": "This account is currently not available",
        "TOO_MANY_USERS": "Too many users are connected",
        "ACCOUNT_LOGGED": "This account is already logged in",
        "UNAVAILABLE_BY_ADMIN": "Administrator has been logged in",
        "LOGIN_ACCOUNT_BLOCKED": "Account blocked",
        "LOGIN_IP_BLOCKED": "Wrong entry. Login blocked.",
        "UNAUTH": "Please check your entry",
        "FAIL_TIMEOUT": "Server error",
    }

    def __init__(
        self, message: Optional[str] = None, api_response_json: Optional[dict] = None
    ):
        self.message = message
        self.api_response = api_response_json

        if api_response_json and not self.message:
            self.message = AuthError.AUTH_ERROR_DESCRIPTIONS.get(
                api_response_json.get("ErrMsg", None),
                f"Unknown authentication error. Response: {json.dumps(api_response_json)}",
            )

        super().__init__(self.message)


class IPBlockedError(WAppLoxxError):
    pass


##
# Constants / Types


class APIEndpoints:
    LOGIN = "login.cgi"
    LOGOUT = "logout.cgi"
    USER_HOME = "user_home.cgi"
    USER_SMARTLOXX = "user_smartloxx.cgi"
    GET_PANEL_STATUS = "getPanelStatus.cgi"
    SET_PANEL = "setPanel.cgi"
    SET_REMOTE_ACCESS = "setRemoteAccess.cgi"
    GET_SYSTEM_STATUS = "getSystemStatus.cgi"
    GET_EVENT_LOG = "getEventLog.cgi"

    AUTH = [LOGIN, LOGOUT]


class PanelStatus:
    ARMED = "ARMED"
    BUSY = "BUSY"
    DISARMED = "DISARMED"
    UNKNOWN = "UNKNOWN"
    SET_ONLY = "SET_ONLY"


class SetPanelActions:
    ARM = "Arm"
    DISARM = "Disarm"
    FORCED_DISARM = "ForcedDisarm"


class SetRemoteAccessActions:
    START = "Start"
    STOP = "Stop"


class EventLogTypes:
    ALL = "All"
    ACCESS = "Access"
    ARM_DISARM = "ArmDisarm"
    RECORD = "Record"
    SYSTEM = "System"


##
# Utilities / Helpers


def _get_unix_timestamp_in_milliseconds() -> int:
    return int(time.time() * 1000)


def _str_to_base64(input_str: str, encoding="utf-8") -> str:
    return base64.b64encode(input_str.encode(encoding)).decode(encoding)


def _urljoin(*args):
    """
    Joins given arguments into an url. Trailing but not leading slashes are
    stripped for each argument.
    Ref.: https://stackoverflow.com/a/11326230
    """
    return "/".join(map(lambda x: str(x).rstrip("/"), args))


def _save_ip_block(seconds: int) -> None:
    """
    Saves the IP block time in seconds that is returned by the controller when
    incorrent credentials are entered.
    """
    with open(os.path.join(sys.path[0], IP_BLOCK_FILENAME), "w") as f:
        f.write(str(int(time.time()) + seconds))


def _remove_ip_block() -> None:
    """
    Deletes the file used for storing the time when the ip block expires,
    if it exists
    """
    file_path = os.path.join(sys.path[0], IP_BLOCK_FILENAME)
    if os.path.isfile(file_path):
        os.remove(file_path)


def _load_ip_block_remaining_seconds() -> int:
    """
    Loads the remaining seconds before the ip block expires.
    Returns 0 if the file cannot be parsed correctly or the file does not exist.
    The file is deleted when the ip block has expired.
    """
    try:
        with open(os.path.join(sys.path[0], IP_BLOCK_FILENAME), "r") as f:
            remaining_seconds = int(math.ceil(max(float(f.read()) - time.time(), 0)))
    except ValueError:
        remaining_seconds = 0
    except FileNotFoundError:
        return 0

    if remaining_seconds <= 0:
        _remove_ip_block()

    return remaining_seconds


def _check_ip_block() -> None:
    ip_block_remaining_seconds = _load_ip_block_remaining_seconds()
    if ip_block_remaining_seconds > 0:
        raise IPBlockedError(
            f"This IP is currently blocked for another {str(ip_block_remaining_seconds)} seconds. Wait for the block to expire or, if your IP has changed, call login() with ignore_ip_block_file = True"
        )


##
# WApploxx Class


class Controller:
    def __init__(
        self,
        controller_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: int = 5,
        save_ip_block_time: bool = True,
        debug: bool = False,
    ):
        self.controller_url = controller_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.save_ip_block_time = save_ip_block_time
        self.debug = debug

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self._logged_in = False
        self._last_successful_login_timestamp = None
        self._session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.logout()

    def _get_authenticated_endpoint(
        self,
        endpoint: APIEndpoints,
        use_default_params: bool = True,
        params: Optional[dict] = None,
    ) -> dict:

        requires_login = not self._logged_in and endpoint not in APIEndpoints.AUTH

        if requires_login:
            self.login()

        if use_default_params:
            input_params = params
            params = {
                "ts": _get_unix_timestamp_in_milliseconds(),
                "Source": "Webpage",
            }
            params.update(input_params if input_params else {})

        response = self._session.get(
            _urljoin(self.controller_url, endpoint),
            params=params,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        if self.debug:
            print(f"** GET /{endpoint} PARAMS: {params} **")

        if response.status_code == 401:
            self.login()
            return self._get_authenticated_endpoint(endpoint, params=params)

        if not response.ok:
            raise WAppLoxxError(
                f"Unknown error when calling endpoint '{endpoint}'. Response code: {response.status_code}"
            )

        return response

    def _validate_login_response(self, response: Response) -> dict:
        response_json = response.json()
        is_status_success = response_json.get("Status") == "SUCCESS"
        is_ip_blocked = response_json.get("ErrMsg") == "LOGIN_IP_BLOCKED"

        if is_status_success:
            _remove_ip_block()
            return response_json

        if is_ip_blocked and self.save_ip_block_time:
            ip_block_seconds = int(response_json.get("BlockTime"))
            _save_ip_block(ip_block_seconds)

        raise AuthError(api_response_json=response_json)

    def login(self, check_ip_block: bool = True) -> dict:
        if check_ip_block is True:
            _check_ip_block()

        response = self._get_authenticated_endpoint(
            APIEndpoints.LOGIN,
            params={
                "Username": _str_to_base64(self.username),
                "Password": _str_to_base64(self.password),
            },
        )
        response_json = self._validate_login_response(response)

        self._logged_in = True
        self._last_successful_login_timestamp = time.time()
        return response_json

    def logout(self) -> None:
        self._get_authenticated_endpoint(APIEndpoints.LOGOUT)

    def get_user_info(self) -> dict:
        response = self._get_authenticated_endpoint(APIEndpoints.USER_HOME)
        # Parse json from <script> in returned HTML
        user_info_json = json.loads(
            re.search(r"var\sg_UserInfo\=((.|\n)*?})\n", response.text).group(1)
        )
        return user_info_json

    def get_user_smartloxx(self) -> dict:
        response = self._get_authenticated_endpoint(APIEndpoints.USER_SMARTLOXX)
        # Parse json from <script> in returned HTML
        smartloxx_json = json.loads(
            re.search(r"var\sgSmartloxxList\=((.|\n)*?});\n", response.text).group(1)
        )
        return smartloxx_json

    def get_panel_status(self) -> dict:
        response = self._get_authenticated_endpoint(APIEndpoints.GET_PANEL_STATUS)
        return response.json()

    def set_panel(self, action: SetPanelActions) -> dict:
        # Successful arm/disarm: {'Status': 'SUCCESS', 'ErrMsg': ''}
        # Error when trying to arm when not ready for set: {'Status': 'FAIL', 'ErrMsg': 'Not ready for arm'}
        response = self._get_authenticated_endpoint(
            APIEndpoints.SET_PANEL,
            params={
                "Action": action,
            },
        )
        return response.json()

    def set_remote_access(self, lock_id: int, action: SetRemoteAccessActions) -> dict:
        response = self._get_authenticated_endpoint(
            APIEndpoints.SET_REMOTE_ACCESS,
            params={
                "LoxxId": lock_id,
                "Action": action,
            },
        )
        return response.json()

    def get_system_status(self, pause_auto_logout=True) -> dict:
        response = self._get_authenticated_endpoint(
            APIEndpoints.GET_SYSTEM_STATUS,
            params={
                "LoxxState": "OFF",
                "PauseAutoLogout": "ON" if pause_auto_logout is True else "OFF",
            },
        )
        return response.json()

    def get_event_log(
        self, index: int = 0, count: int = 50, type: EventLogTypes = EventLogTypes.ALL
    ) -> dict:
        response = self._get_authenticated_endpoint(
            APIEndpoints.GET_EVENT_LOG,
            params={"Index": index, "Count": count, "Type": type},
        )
        return response.json()


##
# Lock Class


class Lock:
    def __init__(self, controller: WApploxx, id: int):
        self.controller = controller
        self.id = id

        self._info = None

    def _get_info(self) -> dict:
        """Retrieves information about the lock by calling the get_user_smartloxx endpoint

        Raises:
            WAppLoxxError: If a lock with the id self.id does not exist

        Returns:
            dict: the controller's json response when calling get_user_smartloxx
        """
        if self._info:
            return self._info

        all_locks = self.controller.get_user_smartloxx().get("List", [])
        for lock in all_locks:
            if lock.get("ID", None) == str(self.id):
                self._info = lock
                return self._info

        raise WAppLoxxError(f"Lock with ID {str(self.id)} does not exist")

    @property
    def access_time(self):
        """Returns the number of seconds for which the smartlock is open
        (i.e. until it automatically locks again)

        Returns:
            int: Number of seconds for which lock is open
        """
        panel_status = self.controller.get_panel_status()
        # Example response: {..., 'AvailableLoxx': ['2', '4'], 'RemoteAccessTime': [0, 0]}

        for lock_id, access_time in zip(
            panel_status.get("AvailableLoxx"), panel_status.get("RemoteAccessTime")
        ):
            if str(lock_id) == str(self.id):
                return access_time

        return None

    @property
    def is_open(self):
        """Returns whether the lock is currently open

        Returns:
            bool: Lock is open
        """
        access_time = self.access_time
        return True if (access_time and access_time > 0) else False

    @property
    def name(self) -> str:
        """Returns the lock's name

        Returns:
            str: the lock's name
        """
        if not self._info:
            self._info = self._get_info()
        return self._info.get("Name")

    @property
    def disabled(self) -> bool:
        """Returns whether the lock is disabled

        Returns:
            bool: Lock is disabled
        """
        if not self._info:
            self._info = self._get_info()
        return self._info.get("Disabled") == "ON"

    @property
    def hwid(self) -> str:
        """Returns the lock's hardware id

        Returns:
            str: Lock's hardware id
        """
        if not self._info:
            self._info = self._get_info()
        return self._info.get("HwId")

    @property
    def cluster(self) -> int:
        """Returns the lock's cluster

        Returns:
            int: Lock's cluster
        """
        if not self._info:
            self._info = self._get_info()
        return int(self._info.get("Cluster"))

    def open(self):
        """Open the lock

        Returns:
            dict: The controller's json response when calling set_remote_access with the START action
        """
        return self.controller.set_remote_access(self.id, SetRemoteAccessActions.START)

    def close(self):
        """Close the lock (aka. stop unlocking the door)

        Returns:
            dict: The controller's json response when calling set_remote_access with the STOP action
        """
        return self.controller.set_remote_access(self.id, SetRemoteAccessActions.STOP)

    def get_dict(self) -> dict:
        access_time = self.access_time
        return {
            "id": self.id,
            "name": self.name,
            "is_open": True if (access_time and access_time > 0) else False,
            "access_time": access_time,
            "disabled": self.disabled,
            "hwid": self.hwid,
            "cluster": self.cluster,
        }


class Locks:
    def __init__(self, controller: WApploxx):
        self.controller = controller
        self._locks = self._get_locks()

    def __getitem__(self, id: int):
        """Get a lock by id

        Example:
        locks[2] returns the lock with ID 2 if it exists
        Raises IndexError if no lock is found
        """
        lock = self.find_lock_by_id(id)
        if not lock:
            raise IndexError(f"No lock with ID {str(id)} found")
        return lock

    def __len__(self):
        return len(self._locks)

    def __iter__(self):
        for lock in self._locks:
            yield lock

    def _get_locks(self) -> List[Lock]:
        result = []
        for lock_info in self.controller.get_user_smartloxx()["List"]:
            lock = Lock(self.controller, int(lock_info["ID"]))
            lock._info = lock_info
            result.append(lock)
        return result

    def find_lock_by_name(
        self, name: str, case_sensitive: bool = False
    ) -> Optional[Lock]:
        search_name = name if case_sensitive else name.lower()
        for lock in self._locks:
            lock_name = lock.name if case_sensitive else lock.name.lower()
            if search_name == lock_name:
                return lock
        return None

    def find_lock_by_id(self, id: int):
        for lock in self._locks:
            if int(id) == int(lock.id):
                return lock
        return None

    def open(self) -> None:
        for lock in self._locks:
            lock.open()

    def close(self) -> None:
        for lock in self._locks:
            lock.close()


# class Panel:
#     def __init__(self, controller: WApploxx):
#         self.controller = controller

#     @property
#     def armed(self) -> bool:
#         return self.get_status() == Panel.ARMED

#     @property
#     def armed(self) -> bool:
#         return self.get_status() == Panel.DISARMED

#     def get_status(self):
#         panel_status_map = {
#             "ON": PanelStatus.ARMED,
#             "ARMED": PanelStatus.ARMED,
#             "BUSY": PanelStatus.BUSY,
#             "DISARMED": PanelStatus.DISARMED,
#             "OFF": PanelStatus.DISARMED,
#             "UNKNOWN": PanelStatus.UNKNOWN,
#             "SET_ONLY": PanelStatus.SET_ONLY,
#         }
#         return panel_status_map.get(self.controller.get_panel_status()["Armed"], None)
