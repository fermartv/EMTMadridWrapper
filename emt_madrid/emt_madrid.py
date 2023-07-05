"""Support for EMT Madrid API."""

import json
import logging
import math

import requests

BASE_URL = "https://openapi.emtmadrid.es/"
ENDPOINT_LOGIN = "v1/mobilitylabs/user/login/"
ENDPOINT_ARRIVAL_TIME = "v2/transport/busemtmad/stops/"
ENDPOINT_STOP_INFO = "v1/transport/busemtmad/stops/"


_LOGGER = logging.getLogger(__name__)


class APIEMT:
    """A class representing an API client for EMT (Empresa Municipal de Transportes) services.

    This class provides methods to authenticate with the EMT API, retrieve bus stop information,
    update arrival times, and access the retrieved data.
    """

    def __init__(self) -> None:
        """Initialize an instance of the APIEMT class."""
        self._token = None
        self._stop_info = {
            "bus_stop_id": None,
            "bus_stop_name": None,
            "bus_stop_coordinates": None,
            "bus_stop_address": None,
            "lines": {},
        }

    def authenticate(self, user, password):
        """Authenticate the user using the provided credentials."""
        headers = {"email": user, "password": password}
        url = f"{BASE_URL}{ENDPOINT_LOGIN}"
        response = self._make_request(url, headers=headers, method="GET")
        self._token = self._extract_token(response)
        return self._token

    def _extract_token(self, response):
        """Extract the access token from the API response."""
        try:
            if response.get("code") != "01":
                _LOGGER.error("Invalid email or password")
                return "Invalid token"
            return response["data"][0]["accessToken"]
        except (KeyError, IndexError) as error:
            raise ValueError("Unable to get token from the API") from error

    def update_stop_info(self, stop_id):
        """Update all the lines and information from the bus stop."""
        url = f"{BASE_URL}{ENDPOINT_STOP_INFO}{stop_id}/detail/"
        headers = {"accessToken": self._token}
        data = {"idStop": stop_id}
        if self._token != "Invalid token":
            response = self._make_request(url, headers=headers, data=data, method="GET")
            self._parse_stop_info(response, stop_id)

    def get_stop_info(
        self,
    ):
        """Retrieve all the information from the bus stop."""
        return self._stop_info

    def _parse_stop_info(self, response, stop_id):
        """Parse the stop info from the API response."""
        try:
            if response.get("code") != "00":
                _LOGGER.warning("Bus stop disabled or does not exist")
            else:
                stop_info = response["data"][0]["stops"][0]
                self._stop_info.update(
                    {
                        "bus_stop_id": stop_id,
                        "bus_stop_name": stop_info["name"],
                        "bus_stop_coordinates": stop_info["geometry"]["coordinates"],
                        "bus_stop_address": stop_info["postalAddress"],
                        "lines": self._parse_lines(stop_info["dataLine"]),
                    }
                )
        except (KeyError, IndexError) as error:
            raise ValueError("Unable to get bus stop information") from error

    def _parse_lines(self, lines):
        """Parse the line info from the API response."""
        line_info = {}
        for line in lines:
            line_number = line["label"]
            line_info[line_number] = {
                "destination": line["headerA"]
                if line["direction"] == "A"
                else line["headerB"],
                "origin": line["headerA"]
                if line["direction"] == "B"
                else line["headerB"],
                "max_freq": int(line["maxFreq"]),
                "min_freq": int(line["minFreq"]),
                "start_time": line["startTime"],
                "end_time": line["stopTime"],
                "day_type": line["dayType"],
                "distance": [],
                "arrivals": [],
            }
        return line_info

    def update_arrival_times(self, stop):
        """Update the arrival times for the specified bus stop and line."""
        url = f"{BASE_URL}{ENDPOINT_ARRIVAL_TIME}{stop}/arrives/"
        headers = {"accessToken": self._token}
        data = {"stopId": stop, "Text_EstimationsRequired_YN": "Y"}
        if self._token != "Invalid token":
            response = self._make_request(
                url, headers=headers, data=data, method="POST"
            )
            self._parse_arrivals(response)

    def get_arrival_time(self, line):
        """Retrieve arrival times in minutes for the specified bus line."""
        try:
            arrivals = self._stop_info["lines"][line].get("arrivals")
        except KeyError:
            return [None, None]
        while len(arrivals) < 2:
            arrivals.append(None)
        return arrivals

    def get_line_info(self, line):
        """Retrieve the information for a specific line."""
        lines = self._stop_info["lines"]
        if line in lines:
            line_info = lines.get(line)
            if "distance" in line_info and len(line_info["distance"]) == 0:
                line_info["distance"].append(None)
            return line_info

        _LOGGER.warning("The bus line %s does not exist at this stop.", line)
        line_info = {
            "destination": None,
            "origin": None,
            "max_freq": None,
            "min_freq": None,
            "start_time": None,
            "end_time": None,
            "day_type": None,
            "distance": [None],
            "arrivals": [None, None],
        }
        return line_info

    def _parse_arrivals(self, response):
        """Parse the arrival times and distance from the API response."""
        try:
            if response.get("code") == "80":
                _LOGGER.warning("Bus Stop disabled or does not exist")
            else:
                for line_info in self._stop_info["lines"].values():
                    line_info["arrivals"] = []
                    line_info["distance"] = []
                arrivals = response["data"][0].get("Arrive", [])
                for arrival in arrivals:
                    line = arrival.get("line")
                    line_info = self._stop_info["lines"].get(line)
                    arrival_time = min(
                        math.trunc(arrival.get("estimateArrive") / 60), 45
                    )
                    if line_info:
                        line_info["arrivals"].append(arrival_time)
                        line_info["distance"].append(arrival.get("DistanceBus"))
        except (KeyError, IndexError) as error:
            raise ValueError("Unable to get the arrival times from the API") from error

    def _make_request(self, url: str, headers=None, data=None, method="POST"):
        """Send an HTTP request to the specified URL."""
        try:
            if method not in ["POST", "GET"]:
                raise ValueError(f"Invalid HTTP method: {method}")
            kwargs = {"url": url, "headers": headers, "timeout": 10}
            if method == "POST":
                kwargs["data"] = json.dumps(data)
            response = requests.request(method, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as error:
            raise requests.HTTPError(f"Error while connecting to EMT API: {error}") from error
