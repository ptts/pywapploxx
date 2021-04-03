# py-wapploxx
Python module to call the Abus wAppLoxx Controller

This module allows you to control the [ABUS WAppLoxx Access Control](https://mobil.abus.com/de/Gewerbe/Zutrittskontrolle/wAppLoxx-System) system using python.

## Features
- Lock/Unlock Abus Smartlocks
- Get alarm panel status
- Set alarm panel to armed/disarmed
- Get Events

## Basic Example
```python
#!/usr/bin/python

from pywapploxx import Controller, Lock

controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)

with controller:
    print(controller.get_panel_status())
    print(controller.get_user_smartloxx())
    front_door = Lock(controller, id=1)
    print(front_door.open())
```

```python
{'Armed': 'OFF', 'ReadyForSet': 'ON', 'SetUnset': 'ON', 'Alarmed': 'UNKNOWN', 'ArmInput': 'ON', 'AvailableHotkey': [False], 'AvailableLoxx': ['1'], 'RemoteAccessTime': [0]}
{'List': [{'ID': '1', 'Disabled': 'OFF', 'Name': 'Vorne', 'HwId': '0000000000011111', 'Cluster': '1'}, {'ID': '2', 'Disabled': 'OFF', 'Name': 'Keller', 'HwId': '0000000000011112', 'Cluster': '1'}], 'Index': 0, 'ListCount': 2, 'TotalCount': 2}
{'Status': 'SUCCESS', 'ErrMsg': ''}
```

## Usage

### Create a controller instance

First, create a new instance of the `Controller` class from the pywapploxx file.

```python
from pywapploxx import Controller

controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)
```

The WAppLoxx controller uses an unsigned certificate, therefore you need to either choose unencrypted communication by specifying `http` in the `controller_url` or set `verify_ssl` to `False`. Both options are not ideal from a security perspective, so be aware that people on the same network might be able to sniff credentials!

Using SSL is also *significantly* (sometimes 10x) slower than the unencrypted endpoint.

### Authenticating

The WAppLoxx allows only a single session for each user. Thus means that you always need to logout after you have made your requests. Otherwise authentication will fail with the message `ACCOUNT_LOGGED` `This account is already logged in`. After around 15 seconds without a request, a user is automatically signed out.

To prevent the `ACCOUNT_LOGGED` error you have two options:
1. Call the `Controller.logout()` method after your requests

```python
try:
    controller.get_panel_status()
finally:
    controller.logout()
```

2. Wrap the calls in a context manager
```python
with controller:
    controller.get_panel_status()
```

### Controlling Smartlocks

Generally you have 2 options to control smartlocks.
1. Use the direct methods in the `Controller` class
```python
from pywapploxx import Controller, SetRemoteAccessActions

controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)

controller.get_user_smartloxx()
# > {'List': [{'ID': '1', 'Disabled': 'OFF', 'Name': 'Vorne', 'HwId': '0000000000011111', 'Cluster': '1'}, {'ID': '2', 'Disabled': 'OFF', 'Name': 'Keller', 'HwId': '0000000000011112', 'Cluster': '1'}], 'Index': 0, 'ListCount': 2, 'TotalCount': 2}
# Open
controller.set_remote_access(self.id, SetRemoteAccessActions.START)
# Close
controller.set_remote_access(self.id, SetRemoteAccessActions.STOP)
```

2. Use the convenience `Lock` and `Locks` classes
```python
from pywapploxx import Controller, Lock


controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)

front_door = Lock(controller, id=1)
print(front_door.name)
# > Vorne
print(front_door.is_open)
# > False
front_door.open()
print(front_door.is_open)
# > True
front_door.close()
```

```python
from pywapploxx import Controller, Locks

controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)

all_locks = Locks(controller)
all_locks.open()
all_locks.close()
```

### Controlling the alarm panel

```python
from pywapploxx import Controller, SetPanelActions

controller = Controller(
    url="https://192.168.1.20",
    username="myuser",
    password="mypass",
    verify_ssl=False
)

controller.get_panel_status()
controller.set_panel_status(SetPanelActions.ARM)
controller.set_panel_status(SetPanelActions.DISARM)
```

## Methods

### login
| Argument             | Description                                                                                                                                                                                   | Required | Type | Default |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|------|---------|
| ignore_ip_block_file | Attempt login at controller even if the controller has previously returned a timeout for the current IP. Use this only if you know what you're doing. The timeout is increased exponentially and can lock you out for a long time. | No       | bool | false   |

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'Status': 'SUCCESS', 'ErrMsg': '', 'Username': 'bXl1c2Vy', 'Permission': 'USER', 'BlockTime': '0'} |

### logout

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| None        |  |

### get_system_status

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'Time': '15:13', 'Logout': 600} |

### get_user_info

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'ID': '1', 'Username': 'myuser', 'Surname': 'Test', 'GivenName': '', 'Tag': '', 'ShowTourGuide': 'OFF'} |

### get_user_smartloxx

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'List': [{'ID': '1', 'Disabled': 'OFF', 'Name': 'Vorne', 'HwId': '0000000000011111', 'Cluster': '1'}, {'ID': '2', 'Disabled': 'OFF', 'Name': 'Keller', 'HwId': '0000000000011112', 'Cluster': '1'}], 'Index': 0, 'ListCount': 2, 'TotalCount': 2} |

### get_panel_status

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'Armed': 'OFF', 'ReadyForSet': 'ON', 'SetUnset': 'ON', 'Alarmed': 'UNKNOWN', 'ArmInput': 'ON', 'AvailableHotkey': [False, False], 'AvailableLoxx': ['1', '2'], 'RemoteAccessTime': [0, 0]} |

### set_panel
| Argument | Description                                                                                                                  | Required | Type            | Default |
|----------|------------------------------------------------------------------------------------------------------------------------------|----------|-----------------|---------|
| action   | The action to perform with the alarm panel. Has to be one of the SetPanelActions, namely ARM, DISARM or FORCE_DISARM.  | Yes      | SetPanelActions |         |

### set_remote_access
| Argument | Description                                                                                                       | Required | Type            | Default |
|----------|-------------------------------------------------------------------------------------------------------------------|----------|-----------------|---------|
| lock_id  | The id of the smartlock to be unlocked/locked. You can find them by calling get_user_smartloxx().                 | Yes      | int             |         |
| action   | The action to perform with the smartlock. Has to be one of the SetRemoteAccessActions, namely ´START´ or ´STOP´.  | Yes      | SetRemoteAccessActions |         |

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'Status': 'SUCCESS', 'ErrMsg': ''} |

### get_event_log
| Argument | Description                                                                                                       | Required | Type            | Default |
|----------|-------------------------------------------------------------------------------------------------------------------|----------|-----------------|---------|
| lock_id  | The id of the smartlock to be unlocked/locked. You can find them by calling get_user_smartloxx().                 | Yes      | int             |         |
| action   | The action to perform with the smartlock. Has to be one of the SetRemoteAccessActions, namely ´START´ or ´STOP´.  | Yes      | SetPanelActions |         |

| Return type | Example                                                                                             |
|-------------|-----------------------------------------------------------------------------------------------------|
| dict        | {'Index': 0, 'ListCount': 5, 'TotalCount': 123, 'List': [{'Date': '29-3-2021 15:17:04', 'Event': 'User Login', 'Smartloxx': '', 'User': 'Myuser', 'Camera': ''}, {'Date': '29-3-2021 15:16:32', 'Event': 'User Login', 'Smartloxx': '', 'User': 'Myuser', 'Camera': ''}, {'Date': '29-3-2021 15:15:52', 'Event': 'User Login', 'Smartloxx': '', 'User': 'Myuser', 'Camera': ''}, {'Date': '29-3-2021 15:14:05', 'Event': 'User Login', 'Smartloxx': '', 'User': 'Myuser', 'Camera': ''}, {'Date': '29-3-2021 15:13:56', 'Event': 'User Login', 'Smartloxx': '', 'User': 'Myuser', 'Camera': ''}]} |
