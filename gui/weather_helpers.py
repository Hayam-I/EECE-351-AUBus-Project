#TEST
import sys
import traceback
import json
import re
import socket
import uuid
import threading
import logging
import html
from client.map_selector import MapSelector
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit, QTextEdit, QDialog, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject
from PyQt5.QtGui import QTextCursor, QPixmap
from gui.p2p_chat_endpoint import P2PChatEndpoint

import requests
from io import BytesIO


#==== weather api constants ======
WEATHER_API_URL = "http://api.weatherapi.com/v1/current.json"
WEATHER_API_KEY = "77ba44421ca942b892a154619252311"

def fetch_weather_for_coords(lat, lon):
    if lat is None or lon is None:
        return None

    params = {
        "key": WEATHER_API_KEY,
        "q": f"{lat},{lon}",
        "aqi": "no",
    }
    try:
        response = requests.get(WEATHER_API_URL, params=params, timeout=4)
        if not response.ok:
            print("WeatherAPI error:", response.text)
            return None

        content = json.loads(response.content)

        return {
            "location_name": content["location"]["name"],
            "country": content["location"]["country"],
            "temp_c": content["current"]["temp_c"],
            "condition_text": content["current"]["condition"]["text"],
            "icon_url": "http:" + content["current"]["condition"]["icon"],
        }
    except Exception as e:
        print("Weather fetch failed:", e)
        return None

def get_real_location():
    return 33.8938, 35.5018 #beirut loc


def on_refresh_clicked(self):
    lat, lon = self._get_lat_lon()
    if lat is None or lon is None:
        self.lbl_status.setText("Location not available")
        return

    self.lbl_status.setText("Fetching weather...")
    info = fetch_weather_for_coords(lat, lon)
    if not info:
        self.lbl_status.setText("Failed to fetch weather.")
        return

    self.lbl_status.setText(f"Weather for {info['location_name']}, {info['country']}")
    self.lbl_details.setText(f"{info['temp_c']} °C – {info['condition_text']}")

    
    try:
        icon_resp = requests.get(info["icon_url"], timeout=4)
        pix = QPixmap()
        pix.loadFromData(icon_resp.content)
        self.lbl_icon.setPixmap(pix)
    except:
        pass


