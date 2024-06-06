from zprocess import Process
import pyqtgraph as pg
import numpy as np
from qtutils import inmain_decorator
import qtutils.qt.QtGui as QtGui
import zmq
from labscript_utils.labconfig import LabConfig
import threading
import time

# maximum amount of datapoints to be plotted at once
MAX_DATA = 100000


class PlotWindow(Process):
    def run(self, connection_name, hardware_name, device_name):
        self._connection_name = connection_name
        self._hardware_name = hardware_name
        self._device_name = device_name
        self.data = np.array([], dtype=np.float64)

        if self._connection_name != '-':
            title = "{} ({})".format(self._hardware_name, self._connection_name)
        else:
            title = "{}".format(self._hardware_name)
        self.plot_win = pg.plot([], title=title)

        broker_pub_port = int(LabConfig().get('ports', 'BLACS_Broker_Pub'))
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)
        self.socket.connect("tcp://127.0.0.1:%d" % broker_pub_port)
        self.socket.setsockopt(zmq.SUBSCRIBE, "{} {}\0".format(self._device_name, self._hardware_name).encode('utf-8'))

        self.analog_in_thread = threading.Thread(target=self._analog_read_loop)
        self.analog_in_thread.daemon = True
        self.analog_in_thread.start()

        self.cmd_thread = threading.Thread(target=self._cmd_loop)
        self.cmd_thread.daemon = True
        self.cmd_thread.start()

        QtGui.QGuiApplication.instance().exec_()

        self.to_parent.put("closed")

    def _analog_read_loop(self):
        while True:
            # Method 2 - Sockets
            devicename_and_channel, data = self.socket.recv_multipart()
            self.update_plot(np.frombuffer(memoryview(data), dtype=np.float64))
            time.sleep(0.001)

    def _cmd_loop(self):
        while True:
            cmd = self.from_parent.get()
            if cmd == 'focus':
                self.setTopLevelWindow()
            elif cmd == 'data':
                # Method 1 - IPC
                data = self.from_parent.get()
                self.update_plot(np.array(data, dtype=np.float64))
                time.sleep(0.001)

    @inmain_decorator(False)
    def setTopLevelWindow(self):
        self.plot_win.win.activateWindow()
        self.plot_win.win.raise_()

    @inmain_decorator(False)
    def update_plot(self, new_data):
        if self.data.size < MAX_DATA:
            if new_data.size + self.data.size <= MAX_DATA:
                self.data = np.append(self.data, new_data)
            else:
                if new_data.size < MAX_DATA:
                    self.data = np.roll(self.data, -new_data.size)
                    self.data[self.data.size - new_data.size:self.data.size] = new_data
                else:
                    self.data = new_data[new_data.size - MAX_DATA:new_data.size]
        else:
            if new_data.size <= self.data.size:
                self.data = np.roll(self.data, -new_data.size)
                self.data[self.data.size - new_data.size:self.data.size] = new_data
            else:
                self.data = new_data[new_data.size - self.data.size:new_data.size]

        self.plot_win.plot(self.data, clear=True)

class TestClass:
    def __init__(self):
        self.win = None
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://127.0.0.1:5555")

    def open_plot_window(self):
        if self.win is None:
            self.win = PlotWindow()
            # Using IPC to send data between processes, instead of sockets
            self.to_child, self.from_child = self.win.start(self._connection_name, self._hardware_name, self._device_name)

    def send_data_to_plot_window_IPC(self, data):
        if self.win is not None:
            # Method 1 - sending data using IPC
            self.to_child.put('data')
            self.to_child.put(data)

    def send_data_to_plot_window_socket(self, data):
        if self.win is not None:
            # Method 2 - sending data over socket
            message = f"{self._device_name} {self._hardware_name}\0".encode('utf-8')
            data_bytes = data.astype(np.float64).tobytes()
            self.socket.send_multipart([message, data_bytes])

if __name__ == "__main__":
    main_obj = TestClass()
    main_obj._connection_name = "test_conn"
    main_obj._hardware_name = "test_hw"
    main_obj._device_name = "test_dev"
    main_obj.open_plot_window()

    # Sending data to the child process
    # data_to_send = np.random.rand(100)  # Example data
    while True:
        data_to_send = np.random.rand(100).astype(np.float64)
        main_obj.send_data_to_plot_window_IPC(data_to_send)