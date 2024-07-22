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
MAX_DATA = 1000000

class PlotWindow(Process):
    def run(self):  
        self.data = {}
        self.plot_win = pg.GraphicsLayoutWidget(title="Input Plot Window")
        self.plots = {}
        self.plot_lines = {}
        self.line_colors = {}

        self.cmd_thread = threading.Thread(target=self._cmd_loop)
        self.cmd_thread.daemon = True
        self.cmd_thread.start()

        self.plot_win.show()

        QtGui.QGuiApplication.instance().exec_()

        self.to_parent.put("closed")

    @inmain_decorator(True)
    def add_plot(self, identifier, line_id):
        if identifier not in self.plots:
            plot = self.plot_win.addPlot(title=f"{identifier}")
            plot.addLegend()
            self.plots[identifier] = plot
            self.data[identifier] = {}

        self.data[identifier][line_id] = np.array([], dtype=np.float32)
        self.line_colors[line_id] = self.get_next_color() 
        self.plots[identifier].plot(pen=self.line_colors[line_id], name=line_id)

        self.plot_win.nextRow()

    def _cmd_loop(self):
        while True:
            cmd = self.from_parent.get()
            if cmd.startswith('add_plot'):  
                parts = cmd.split()
                self.add_plot(parts[1], parts[2])
            elif cmd == 'focus':
                self.setTopLevelWindow()
            elif cmd.startswith('data'):
                parts = cmd.split()
                identifier, line_id = parts[1], parts[2]
                data = self.from_parent.get()
                self.update_plot(identifier, line_id, np.array(data, dtype=np.float32))
            elif cmd == 'get_plots':
                open_plot_identifiers = list(self.plots.keys())
                self.to_parent.put(open_plot_identifiers)

    @inmain_decorator(False)
    def setTopLevelWindow(self):
        self.plot_win.show()
        self.plot_win.activateWindow()
        self.plot_win.raise_()

    @inmain_decorator(False)
    def update_plot(self, identifier, line_id, new_data):
        if identifier not in self.data:
            self.data[identifier] = {}
        
        if line_id not in self.data[identifier]:
            self.data[identifier][line_id] = np.array([], dtype=np.float64)

        self.data[identifier][line_id] = new_data
        plot_item = self.plots[identifier]
        plot_item.clear()
        for line, data_points in self.data[identifier].items():
            plot_item.plot(data_points, pen=self.line_colors[line], name=line)
    
    def get_next_color(self):
        """Generate a new color for the next line."""
        num_colors = len(self.line_colors)
        color = QtGui.QColor.fromHsvF((num_colors * 0.618033988749895) % 1.0, 1.0, 1.0)
        return QtGui.QPen(color)

# TODO: Update unit tests
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
    test_obj = TestClass()
    test_obj._connection_name = "test_conn"
    test_obj._hardware_name = "test_hw"
    test_obj._device_name = "test_dev"
    test_obj.open_plot_window()

    # Sending data to the child process
    # data_to_send = np.random.rand(100)  # Example data
    while True:
        data_to_send = np.random.rand(100).astype(np.float64)
        test_obj.send_data_to_plot_window_IPC(data_to_send)
        test_obj.send_data_to_plot_window_socket(data_to_send)