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
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CallbackContext,
    CommandHandler,
    ConversationHandler,
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

    def build_menu(self, buttons, n_cols, header_buttons=None, footer_buttons=None):
        """Function to build the Inline Keyboard Button menu"""
        menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, header_buttons)
        if footer_buttons:
            menu.append(footer_buttons)
        return menu

    def custom_keyboard(self):
        """Function to setup the Keyboard Button menu"""
        search_keyboard = KeyboardButton(
            text=emojis.encode(":mag_right: Search Station")
        )
        nearest_keyboard = KeyboardButton(
            text=emojis.encode(":walking: Nearest Station")
        )
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

        update.message.reply_text(
            emojis.encode(":arrow_down: Choose a function from the menu below"),
            reply_markup=reply_markup,
        )

    # BikeMi time

    def pull_stations(self):
        """Access the API and create vars"""
        api = bikemi.BikeMiApi()
        get_stations_basic_info = api.json_decoder(self.STATION_INFO)
        stations_extra_info = api.get_stations_extra_info()
        stations_full_info = api.get_stations_full_info(
            get_stations_basic_info, stations_extra_info
        )
        return stations_full_info

    def print_result(self, station_raw):
        """Display station's info"""
        stationInfo = (
            emojis.encode(":busstop: Name: ")
            + station_raw["name"]
            + "\n"
            + emojis.encode(":round_pushpin: Address: ")
            + station_raw["address"]
            + "\n"
            + emojis.encode(":bike: Bikes: ")
            + station_raw["bike"]
            + "\n"
            + emojis.encode(":zap: Electric Bikes: ")
            + station_raw["ebike"]
            + "\n"
            + emojis.encode(":seat: Electric Bikes with Child Seat: ")
            + station_raw["ebike_with_childseat"]
            + "\n"
            + emojis.encode(":parking: Available docks: ")
            + station_raw["availableDocks"]
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
                text=emojis.encode(
                    ":arrow_down: Choose a function from the menu below"
                ),
                reply_markup=reply_markup,
            )

    def inline_keyboard_buttons(self, station_raw):
        """Display Inline Keyboard Button for the Map coordinates and to go back to Main menu"""
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
            InlineKeyboardButton(
                text=emojis.encode(":gear: Main Menu"),
                callback_data="main_menu_callback",
            )
        )
        reply_markup = InlineKeyboardMarkup(
            self.build_menu(button_list, n_cols=1)
        )  # n_cols = 1 is for single column and mutliple rows
        return reply_markup

    def search_station(self, update, context, place):
        # Typing...
        context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        api = bikemi.BikeMiApi()
        stations_full_info = self.pull_stations()

        for station_raw in api.find_station(stations_full_info, place):
            station = self.print_result(station_raw)
            reply_markup = self.inline_keyboard_buttons(station_raw)
            # Send Text
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=station,
                reply_markup=reply_markup,
            )

    def search_nearest(self, update, context, place):
        # Typing...
        context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        mapbox_token = os.environ.get("MAPBOX_TOKEN")
        geolocator = MapBox(mapbox_token)
        proximity = (45.464228552423435, 9.191557965278111)  # Duomo
        location = geolocator.geocode(place, proximity=proximity)
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

    # Start ConversationHandler functions
    HANDLE_COMMAND = range(1)

    def read_command(self, update: Update, context: CallbackContext) -> int:

        if update.message.text == "/search" or update.message.text == emojis.encode(
            ":mag_right: Search Station"
        ):
            update.message.reply_text(
                emojis.encode(
                    ":mag_right: What station are you searching for? \n \n /cancel"
                )
            )
            context.user_data["command"] = "search"

        if update.message.text == "/nearest" or update.message.text == emojis.encode(
            ":walking: Nearest Station"
        ):
            update.message.reply_text(
                emojis.encode(
                    ":walking: Enter a place to get the nearest station \n \n /cancel"
                )
            )
            context.user_data["command"] = "nearest"
        return self.HANDLE_COMMAND

    def handle_command(self, update: Update, context: CallbackContext) -> int:
        context.user_data["place"] = update.message.text
        place = context.user_data["place"]

        if context.user_data["command"] == "search":
            self.search_station(update, context, place)

        if context.user_data["command"] == "nearest":
            self.search_nearest(update, context, place)

        return ConversationHandler.END

    def cancel_command(self, update: Update, context: CallbackContext) -> int:
        """Cancels and ends the conversation."""
        reply_markup = self.custom_keyboard()
        update.message.reply_text(
            emojis.encode(":thumbsup: Canceled!"), reply_markup=reply_markup
        )
        context.user_data.clear()
        return ConversationHandler.END

    def wrong_input(self, update: Update, context: CallbackContext) -> int:
        reply_markup = self.custom_keyboard()
        update.message.reply_text(
            "That isn't the name of a BikeMi station, cancelling...",
            reply_markup=reply_markup,
        )
        context.user_data.clear()
        return ConversationHandler.END

    # End ConversationHandler functions

    def main(self):
        telegram_token = os.environ.get("TELEGRAM_DEBUGGING_TOKEN")
        updater = Updater(token=telegram_token, use_context=True)

        # Register handlers
        self.dispatcher = updater.dispatcher

        # Start command
        start_handler = CommandHandler("start", self.start)
        self.dispatcher.add_handler(start_handler)

        # Build conv handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("search", self.read_command),
                MessageHandler(
                    Filters.regex(emojis.encode(":mag_right: Search Station")),
                    self.read_command,
                ),
                CommandHandler("nearest", self.read_command),
                MessageHandler(
                    Filters.regex(emojis.encode(":walking: Nearest Station")),
                    self.read_command,
                ),
            ],
            states={
                self.HANDLE_COMMAND: [
                    MessageHandler(
                        Filters.text
                        & ~(
                            Filters.command
                            | Filters.regex(emojis.encode(":mag_right: Search Station"))
                            | Filters.regex(emojis.encode(":walking: Nearest Station"))
                            | Filters.location
                        ),
                        self.handle_command,
                    )
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_command),
                CommandHandler("search", self.wrong_input),
                MessageHandler(
                    Filters.regex(emojis.encode(":mag_right: Search Station")),
                    self.wrong_input,
                ),
                CommandHandler("nearest", self.wrong_input),
                MessageHandler(
                    Filters.regex(emojis.encode(":walking: Nearest Station")),
                    self.wrong_input,
                ),
                CommandHandler("location", self.wrong_input),
                MessageHandler(Filters.location, self.wrong_input),
            ],
        )

        self.dispatcher.add_handler(conv_handler)

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
