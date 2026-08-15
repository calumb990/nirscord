import os
import uuid
import time
import shlex
import socket
import asyncio
import argparse

from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

from typing import cast
from pathlib import Path
from datetime import datetime

import numpy as np

import h5py
from h5py import Dataset

import websockets
from websockets import ServerConnection

from pylsl import StreamInlet, resolve_byprop

from rich.console import Text
from rich.columns import Columns
from rich.spinner import Spinner

from textual import work
from textual.app import App
from textual.message import Message
from textual_plotext import PlotextPlot
from textual.containers import HorizontalGroup, VerticalScroll, Vertical
from textual.widgets import Header, Footer, RichLog, Input, Static, Label, Button

from importlib.resources import files, as_file
from nirscord.config import parse_lsl_config

FILENAME = None
BATCH_SIZE = 100
SAMPLE_RATE = 31.25
LOG_THRESHOLD = 10_000
HTTP_DIRECTORY = "public"
LSL_CONFIG = parse_lsl_config("MendiLSL")


def log(logger: RichLog, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.write(f"[{timestamp}] {message}")


class SampleState:

    def __init__(self):
        self.subscribers = []

    def subscribe(self, callback):
        if callback is not None:
            self.subscribers.append(callback)

    def unsubscribe(self, callback):
        if callback is not None:
            self.subscribers.remove(callback)

    def publish(self, samples):
        for callback in self.subscribers:
            callback(samples)


class RecorderApp(App):
    DEFAULT_CSS = """
    RichLog,
    RichLog:blur,
    RichLog:focus,
    RichLog:hover {
        background: transparent;
    }
    
    .box {
        height: 1fr;
        border: solid $foreground;
    }
    
    .title {
        width: 100%;
        text-align: center;
        border-bottom: solid $foreground;
    }
    """

    # Set the app title
    TITLE = "nirscord"

    # The h5 file
    h5_file = None

    # The lsl stream worker
    lsl_stream_worker = None

    # The sample state instance
    sample_state = SampleState()

    def compose(self):
        yield Header()
        yield ExperimentUI()
        yield RecordingUI()
        yield CommandLine()
        yield Footer()

    def on_mount(self):
        (Path.cwd() / "data").mkdir(parents=True, exist_ok=True)
        self.h5_file = h5py.File(f"data/{FILENAME}", "a")

        # Calculate the amount of LSL columns
        columns = len(LSL_CONFIG.columns)

        if "stream" not in self.h5_file:
            self.h5_file.create_dataset(
                "stream",
                dtype="float32",
                shape=(0, columns),
                maxshape=(None, columns),
                chunks=(BATCH_SIZE, columns),
            )

        if "events" not in self.h5_file:
            self.h5_file.create_dataset(
                "events",
                shape=(0,),
                maxshape=(None,),
                chunks=(BATCH_SIZE,),
                dtype=np.dtype([
                    ("timestamp", "f8"),
                    ("uuid", "S16"),
                    ("event", "S16"),
                    ("value", "S256"),
                ])
            )

        self.query_one("RecordingUI", RecordingUI).start_recording("stream")

    def on_unmount(self):
        self.h5_file.close()

    def on_start_lsl(self):
        self.lsl_stream_worker = self.lsl_stream()

    def on_stop_lsl(self):

        if not self.lsl_stream_worker:
            self.query_one("CommandLine", CommandLine).write_output(
                Text("No LSL connection to stop.")
            )

        else:
            self.query_one("CommandLine", CommandLine).write_output(
                Columns([Spinner("dots"), Text("Stopping LSL...", style="blue")])
            )

            # Cancel the LSL stream worker
            self.lsl_stream_worker.cancel()

    async def on_switch_page(self, message: SwitchPage):
        await self.query_one("ExperimentUI", ExperimentUI).switch_page(message.page)

    def on_channel(self, message: Channel):
        self.query_one("RecordingUI", RecordingUI).display_channel(message.channel)

    @work(thread=True)
    def lsl_stream(self):
        self.query_one("CommandLine", CommandLine).write_output(
            Columns([Spinner("dots"), Text("Connecting to LSL...", style="blue")])
        )

        # Attempt to discover LSL streams
        streams = resolve_byprop("name", LSL_CONFIG.stream_name, timeout=3.0)

        if not streams:
            return self.query_one("CommandLine", CommandLine) \
                .write_output(Text("Failed to connect to LSL.", style="red"))

        # Connect to the first LSL stream
        inlet = StreamInlet(streams[0])

        self.query_one("CommandLine", CommandLine).write_output(
            Text("Successfully connected to LSL.", style="green")
        )

        try:
            # Publish sample batches
            self._post_samples(inlet)
        finally:
            # Safely close the stream
            inlet.close_stream()

        return self.query_one("CommandLine", CommandLine) \
            .write_output(Text("Stopped the LSL stream.", style="red"))

    def _post_samples(self, inlet: StreamInlet):

        while not self.lsl_stream_worker.is_cancelled:
            samples = []

            # Collect samples into a certain batch
            while len(samples) < BATCH_SIZE:
                channels, timestamp = inlet.pull_sample(timeout=3.0)

                # Add sample from LSL stream
                channels.append(timestamp)
                samples.append(channels)

                # Wait using the sample rate
                time.sleep(1 / SAMPLE_RATE)

            # Publish the samples to the subscribers
            self.sample_state.publish(samples)


class LoggingHTTPRequestHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, logger: RichLog, directory: Path, **kwargs):
        self.logger = logger

        # Initialise the SimpleHTTPRequestHandler with a set directory
        super().__init__(*args, directory=str(directory.absolute()), **kwargs)

    def log_message(self, format, *args):
        code = args[1] if len(args) > 1 else "???"
        log(self.logger, "%s %s %s" % (self.command, self.path, code))


class Timer(Vertical):
    DEFAULT_CSS = """
        Timer {
            height: 3;
            align: center middle;
            background: $foreground;
        }
        
        #info {
            color: $background;
        }
        
        #timer {
            width: 16;
            text-align: center;
            background: $background;
        }
    """

    elapsed = 0

    def compose(self):
        yield Label("Time Elapsed", id="info")
        yield Label("00:00", id="timer")

    def on_mount(self):
        self.set_interval(1, self._tick)

    def reset_timer(self):
        self.elapsed = 0

        # Reset the timer back to 00:00
        self.query_one("#timer", Label).update("00:00")

    def _tick(self) -> None:
        self.elapsed += 1

        timer = self.query_one("#timer", Label)
        minutes, seconds = divmod(self.elapsed, 60)
        timer.update(f"{minutes:02d}:{seconds:02d}")

        timer.refresh()


class ExperimentUI(HorizontalGroup):
    DEFAULT_CSS = """
    ExperimentUI {
        height: 1fr;
    }
    
    .control-button {
        width: 1fr;
    }
    
    #rest-button {
        background: red;
    }
    
    #sart-button {
        background: orange;
    }
    
    #n-back-button {
        background: green;
    }
    
    #stroop-button {
        background: blue;
    }
    """

    # Network
    ws_clients = []
    http_server = None

    # Loggers
    ws_logger = None
    http_logger = None

    # Workers
    http_server_worker = None
    websocket_server_worker = None

    def compose(self):
        with VerticalScroll(classes="box"):
            yield Label("[bold]HTTP Logs[/bold]", classes="title")
            yield RichLog(highlight=True, markup=True, id="http-logger")

        with VerticalScroll(classes="box"):
            yield Label("[bold]Websocket Logs[/bold]", classes="title")
            yield RichLog(highlight=True, markup=True, id="ws-logger")

        with VerticalScroll(classes="box"):
            yield Label("[bold]Control Panel[/bold]", classes="title")

            yield Timer()
            yield Button("Rest", id="rest-button", classes="control-button")
            yield Button("SART", id="sart-button", classes="control-button")
            yield Button("n-back", id="n-back-button", classes="control-button")
            yield Button("Stroop", id="stroop-button", classes="control-button")

    def on_mount(self):
        self.ws_logger = self.query_one("#ws-logger", RichLog)
        self.http_logger = self.query_one("#http-logger", RichLog)

        self.http_server_worker = self.start_http_server()
        self.websocket_server_worker = self.start_websocket_server()

    def on_unmount(self):
        self.http_server.shutdown()
        self.http_server_worker.cancel()
        self.websocket_server_worker.cancel()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "sart-button":
            await self.switch_page("sart.html")
        elif event.button.id == "rest-button":
            await self.switch_page("rest.html")
        elif event.button.id == "n-back-button":
            await self.switch_page("n-back.html")
        elif event.button.id == "stroop-button":
            await self.switch_page("stroop.html")

        # Reset the timer regardless of the button
        self.query_one("Timer", Timer).reset_timer()

    async def switch_page(self, page):
        log(self.ws_logger, f"Switched clients to {page}")

        for client, ws_uuid in self.ws_clients:
            await client.send(f"/{page}")
            await self._record_event(ws_uuid.bytes, "switch", page)

    @work(thread=True)
    def start_http_server(self):

        with as_file(files("nirscord") / HTTP_DIRECTORY) as directory:
            handler = partial(LoggingHTTPRequestHandler, logger=self.http_logger, directory=directory)
            self.http_server = HTTPServer(("0.0.0.0", 8080), handler)

            # Log the HTTP server hyperlink
            log(self.http_logger, "HTTP server started successfully")
            log(self.http_logger, f"At http://{socket.gethostname()}:8080/")

            # Run the server until cancelled
            self.http_server.serve_forever()

    @work
    async def start_websocket_server(self):
        async with websockets.serve(self._handle_connect, "0.0.0.0", 8765):
            log(self.ws_logger, "Websocket started successfully")

            # Await until cancelled
            await asyncio.Future()

    async def _handle_connect(self, websocket: ServerConnection):
        ws_uuid = uuid.uuid4()

        try:
            self.ws_clients.append((websocket, ws_uuid))

            async for message in websocket:
                log(self.ws_logger, f"client {ws_uuid.hex[:8]}: {message}")
                await self._record_event(ws_uuid.bytes, "client", message)
        finally:
            self.ws_clients.remove((websocket, ws_uuid))

    async def _record_event(self, uuid_bytes: bytes, event: str, value: str):
        dataset: Dataset = cast(RecorderApp, self.app).h5_file["events"]

        # Append the event to the frames dataset
        timestamp = datetime.now().timestamp()
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1] = (timestamp, uuid_bytes, event, value)


class RecordingUI(HorizontalGroup):
    DEFAULT_CSS = """
    RecordingUI {
        height: 1fr;
    }
    
    #logs {
        width: 1fr;
    }
    
    #stream {
        width: 2fr;
        border: solid $foreground;
    }
    """

    # The callback
    callback = None

    # The plot data
    channel = None
    plot_data = None

    def compose(self):
        with VerticalScroll(id="logs", classes="box"):
            yield Label("[bold]Stream Logs[/bold]", classes="title")
            yield RichLog(highlight=True, markup=True)

        yield PlotextPlot(id="stream")

    def on_mount(self):
        self.display_channel(LSL_CONFIG.columns[0])
        self.plot_data = [[0] * len(LSL_CONFIG.columns) for _ in range(BATCH_SIZE * 5)]

    def display_channel(self, channel: str):
        self.channel = channel

        widget = self.query_one("PlotextPlot", PlotextPlot)

        plt = widget.plt
        plt.title(self.channel)

        widget.theme = "clear"
        widget.refresh()

    def start_recording(self, label: str):
        typed_app = cast(RecorderApp, self.app)

        # Stop recording samples to the previous dataset
        typed_app.sample_state.unsubscribe(self.callback)

        # Initialise the callback that writes LSL samples
        self.callback = partial(self._record_sample, typed_app.h5_file, label)

        # Log the dataset and clear the sample table
        log(self.query_one(RichLog), f"Started recording fNIRS data")

        # Start recording samples under the new dataset
        typed_app.sample_state.subscribe(self.callback)

    def _record_sample(self, file: h5py.File, label: str, samples: list[list[float]]):
        dataset = file[label]

        # Calculate the dataset size before writing
        old_size = int(dataset.nbytes / LOG_THRESHOLD)

        # Calculate the new entry count
        old_count = dataset.shape[0]
        new_count = len(samples) + old_count

        # Write the samples to the dataset
        dataset.resize(new_count, axis=0)
        dataset[old_count:new_count] = np.array(samples)

        # Calculate the dataset size after writing
        new_size = int(dataset.nbytes / LOG_THRESHOLD)

        # Write the batch to the HDF5 file
        file.flush()

        if old_size != new_size:
            log(self.query_one(RichLog), f"dataset size: {int(dataset.nbytes / 1000)}kB")

        # Update the stream plot
        self._update_plot(samples)

    def _update_plot(self, samples: list[list[float]]):
        self.plot_data = self.plot_data[BATCH_SIZE:] + samples

        plt = self.query_one("PlotextPlot", PlotextPlot).plt
        transposed = [list(row) for row in zip(*self.plot_data)]

        # Clear the plot
        plt.clear_data()

        index = LSL_CONFIG.columns.index(self.channel)
        plt.plot(transposed[-1], transposed[index])

        # Force a rerender
        self.query_one("PlotextPlot", PlotextPlot).refresh()


class StartLSL(Message):
    def __init__(self):
        super().__init__()


class StopLSL(Message):
    def __init__(self):
        super().__init__()


class SwitchPage(Message):
    def __init__(self, page: str):
        super().__init__()
        self.page = page


class Channel(Message):
    def __init__(self, channel: str):
        super().__init__()
        self.channel = channel


class CommandLine(VerticalScroll):
    DEFAULT_CSS = """
    
    CommandLine {
        max-height: 7;
        border: solid $foreground;
    }
    
    #prompt {
        height: 3;
        width: auto;
        content-align: left middle;
    }
    
    Input,
    Input:blur,
    Input:focus,
    Input:hover {
        padding: 0 0 0 1;
        border: transparent;
        outline: transparent;
        background: transparent;
    }
    
    Static,
    Static:blur,
    Static:focus,
    Static:hover {
        padding: 0 0 0 2;
        background: transparent;
    }
    
    """

    def compose(self):

        with HorizontalGroup():
            yield Static(">", id="prompt")
            yield Input(placeholder="Enter Command")

        yield Static(id="output")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value

        match shlex.split(command):
            case ["start"]:
                self.post_message(StartLSL())
            case ["stop"]:
                self.post_message(StopLSL())
            case ["switch", page]:

                # Verify the page to switch exists
                if Path(f"public/{page}").is_file():
                    self.write_output(Text(f"Switched clients to {page}", style="green"))
                    self.post_message(SwitchPage(page))
                else:
                    self.write_output(Text(f"Page {page} does not exist", style="red"))

            case ["channel", channel]:

                # Verify the selected channel exists
                if channel in LSL_CONFIG.columns:
                    self.write_output(Text(f"Channel {channel} selected", style="green"))
                    self.post_message(Channel(channel))
                else:
                    self.write_output(Text(f"Channel {channel} does not exist", style="red"))

            case _:
                self.write_output(Text("Read the README.md for help"))

        # Reset the command line ready for new input
        self.query_one("Input", Input).value = ""

    def write_output(self, message):
        self.query_one("#output", Static).update(message)


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--batch-size", type=int)
    arg_parser.add_argument("--sample-rate", type=float)
    arg_parser.add_argument("--log-threshold", type=int)
    arg_parser.add_argument("--http-directory", type=str)
    arg_parser.add_argument("--filename", type=str, required=True)
    arg_parser.add_argument("--lsl-config", type=parse_lsl_config)

    # Declare global variables
    global FILENAME
    global LSL_CONFIG
    global BATCH_SIZE
    global SAMPLE_RATE
    global LOG_THRESHOLD
    global HTTP_DIRECTORY

    # Parse optional CLI arguments
    parsed_args = arg_parser.parse_args()
    FILENAME = parsed_args.filename or FILENAME
    LSL_CONFIG = parsed_args.lsl_config or LSL_CONFIG
    BATCH_SIZE = parsed_args.batch_size or BATCH_SIZE
    SAMPLE_RATE = parsed_args.sample_rate or SAMPLE_RATE
    LOG_THRESHOLD = parsed_args.log_threshold or LOG_THRESHOLD
    HTTP_DIRECTORY = parsed_args.http_directory or HTTP_DIRECTORY

    # Load the liblsl config file
    with as_file(files("nirscord") / "lsl_api.cfg") as file:
        os.environ["LSLAPICFG"] = str(file.absolute())

    app = RecorderApp()
    app.run()
