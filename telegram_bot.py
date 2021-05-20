import bikemi
import emojis
import os
import logging
import sys

from functools import wraps
from geopy.geocoders import MapBox
from telegram import (
    ChatAction,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultDocument,
    KeyboardButton,
    Location,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    Updater,
)
from threading import Thread
from typing import Union, List


class TelegramBotDebugger:
    STATION_INFO = "https://gbfs.urbansharing.com/bikemi.com/station_information.json"

    # Logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )

    # Function to build the Inline Keyboard Button menu
    def build_menu(self, buttons, n_cols, header_buttons=None, footer_buttons=None):
        menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    # Function to setup the Keyboard Button menu
    def custom_keyboard(self):
        search_keyboard = KeyboardButton(
            text=emojis.encode(":mag_right: Search Station")
        )
        nearest_keyboard = KeyboardButton(text="Nearest Station")
        location_keyboard = KeyboardButton(
            text=emojis.encode(":round_pushpin: Send current location"),
            request_location=True,
        )

        custom_keyboard = [[search_keyboard] + [nearest_keyboard], [location_keyboard]]
        return ReplyKeyboardMarkup(
            custom_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
            selective=True,
        )

    # Start command
    def start(self, update, context):
        reply_markup = self.custom_keyboard()

        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=emojis.encode(":arrow_down: Choose a function from the menu below"),
            reply_markup=reply_markup,
        )

    # BikeMi time

    # Access the API and create vars
    def pull_stations(self):
        api = bikemi.BikeMiApi()
        get_stations_basic_info = api.json_decoder(self.STATION_INFO)
        stations_extra_info = api.get_stations_extra_info()
        stations_full_info = api.get_stations_full_info(
            get_stations_basic_info, stations_extra_info
        )
        return stations_full_info

    # Print station's info
    def print_result(self, station_raw):
        stationInfo = (
            "Name: "
            + str(station_raw["name"])
            + "\nAddress: "
            + str(station_raw["address"])
            + "\nBikes: "
            + str(station_raw["bike"])
            + "\nElectric Bikes: "
            + str(station_raw["ebike"])
            + "\nElectric Bikes with child seat: "
            + str(station_raw["ebike_with_childseat"])
            + "\nAvailable docks: "
            + str(station_raw["availableDocks"])
        )

        return stationInfo

    def callback_query(self, update, context):
        query = update.callback_query
        reply_markup = self.custom_keyboard()
        # CallbackQueries need to be answered, even if no notification to the user is needed
        query.answer()
        if query.data == "main_menu_callback":
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=emojis.encode(":arrow_down: Choose a function from the menu below"),
                reply_markup=reply_markup,
            )

    # Display Inline Keyboard Button for the Map coordinates and going back to Main menu
    def inline_keyboard_buttons(self, station_raw):
        button_list = []
        # Add the GMaps location button to the button list
        location_link = (
            "https://www.google.com/maps/search/?api=1&query="
            + str(station_raw["lat"])
            + ","
            + str(station_raw["lon"])
        )
        text = emojis.encode(":round_pushpin: Open in Maps")
        button_list.append(InlineKeyboardButton(text=text, url=location_link))
        # Add the main menu button to the button list
        reply_markup = self.custom_keyboard()
        button_list.append(
            InlineKeyboardButton(text="Main Menu", callback_data="main_menu_callback")
        )
        reply_markup = InlineKeyboardMarkup(
            self.build_menu(button_list, n_cols=1)
        )  # n_cols = 1 is for single column and mutliple rows
        return reply_markup

    def search_station(self, update, context):
        # Typing...
        context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        api = bikemi.BikeMiApi()
        stations_full_info = self.pull_stations()

        for station_raw in api.find_station(stations_full_info, update.message.text):
            station = self.print_result(station_raw)
            reply_markup = self.inline_keyboard_buttons(station_raw)
            # Send Text
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=station,
                reply_markup=reply_markup,
            )
            self.dispatcher.remove_handler(self.search_station_handler)

    def search_nearest(self, update, context):
        # Typing...
        context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        mapbox_token = os.environ.get("MAPBOX_TOKEN")
        text_input = update.message.text
        geolocator = MapBox(mapbox_token)
        proximity = (45.464228552423435, 9.191557965278111)  # Duomo
        location = geolocator.geocode(text_input, proximity=proximity)
        api = bikemi.BikeMiApi()
        stations_full_info = self.pull_stations()
        station_raw = api.get_nearest_station(
            stations_full_info, location.latitude, location.longitude
        )
        reply_markup = self.inline_keyboard_buttons(station_raw)

        # Text Message
        station = self.print_result(station_raw)
        nearest_station = "The nearest station is: \n" + station
        # Send text
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=nearest_station,
            reply_markup=reply_markup,
        )
        self.dispatcher.remove_handler(self.search_nearest_handler)

    def get_location(self, update, context):
        # Typing...
        context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        # Store user's latitute and longitude
        user_location = update.message["location"]
        latitude = float(user_location["latitude"])
        longitude = float(user_location["longitude"])

        api = bikemi.BikeMiApi()
        stations_full_info = self.pull_stations()
        station_raw = api.get_nearest_station(stations_full_info, latitude, longitude)
        reply_markup = self.inline_keyboard_buttons(station_raw)

        # Generate Text Message
        station = self.print_result(station_raw)
        nearest_station = "The nearest station is: \n" + station
        # Send text
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=nearest_station,
            reply_markup=reply_markup,
        )

    def main(self):
        telegram_token = os.environ.get("TELEGRAM_DEBUGGING_TOKEN")
        updater = Updater(token=telegram_token, use_context=True)

        search_list = [
            "/search",
            emojis.encode(":mag_right: Search Station"),
        ]
        nearest_list = ["/nearest", "Nearest Station"]
        location_list = [
            "/location",
            emojis.encode(":round_pushpin: Send current location"),
        ]
        easteregg_list = ["Deez", "deez"]
        command_list = search_list + nearest_list + location_list + easteregg_list

        # Register handlers
        self.dispatcher = updater.dispatcher

        # Start command
        start_handler = CommandHandler("start", self.start)
        self.dispatcher.add_handler(start_handler)

        def browser(update, context):
            # Search Station
            for element in search_list:
                if update.message.text == element:
                    update.message.reply_text(
                        text="What station are you searching for?"
                    )
                    # Search station handler
                    self.search_station_handler = MessageHandler(
                        Filters.text & (~Filters.command), self.search_station
                    )
                    self.dispatcher.add_handler(self.search_station_handler)

            # Nearest station
            for element in nearest_list:
                if update.message.text == element:
                    update.message.reply_text(
                        text="Enter a place to get the nearest station"
                    )
                    # Nearest Station handler
                    self.search_nearest_handler = MessageHandler(
                        Filters.text & (~Filters.command), self.search_nearest
                    )
                    self.dispatcher.add_handler(self.search_nearest_handler)

            # Location
            for element in location_list:
                if update.message.text == element:
                    update.message.reply_text(
                        text="Share your current location to get the nearest station to you"
                    )
                    # Get Location handler
                    self.get_location_handler = MessageHandler(
                        Filters.location, self.get_location
                    )
                    self.dispatcher.add_handler(get_location_handler)

            # Easter Egg
            for element in easteregg_list:
                if update.message.text == element:
                    update.message.reply_text(text="NUUUUUUUUUUUUUUUUUUUUUUUUTZ")

        # Browser handler
        for element in command_list:
            browser_handler = MessageHandler(Filters.regex(element), browser)
            self.dispatcher.add_handler(browser_handler)

        # Get Location handler
        get_location_handler = MessageHandler(Filters.location, self.get_location)
        self.dispatcher.add_handler(get_location_handler)

        # Callback query handler
        main_menu_handler = CallbackQueryHandler(self.callback_query)
        self.dispatcher.add_handler(main_menu_handler)

        # Function to stop and restart the bot from the chat
        def stop_and_restart():
            """Gracefully stop the Updater and replace the current process with a new one"""
            updater.stop()
            os.execl(sys.executable, sys.executable, *sys.argv)

        # Function to stop the bot from the chat
        def restart(update, context):
            update.message.reply_text("Bot is restarting...")
            Thread(target=stop_and_restart).start()

        # Handler to stop the bot
        self.dispatcher.add_handler(
            CommandHandler("r", restart, filters=Filters.user(username="@zzkW35"))
        )

        # Start Bot
        updater.start_polling()
        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()


bot = TelegramBotDebugger()

if __name__ == "__main__":
    bot.main()