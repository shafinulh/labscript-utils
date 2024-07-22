from zprocess import Process
import pyqtgraph as pg
import numpy as np
from qtutils import inmain_decorator
import qtutils.qt.QtGui as QtGui
import zmq
from labscript_utils.labconfig import LabConfig
import threading
import time

class PlotWindow(Process):
    def run(self):  
        self.plot_win = pg.GraphicsLayoutWidget(title="Input Plot Window")
        self.plots = {}
        self.data = {}
        self.plot_lines = {}
        
        self.line_colors = ['b', 'r', 'c', 'g', 'y']


        # maximum amount of datapoints to be plotted at once
        # TODO: Allow user to set this param
        self.MAX_DATA = 100000

        self.cmd_thread = threading.Thread(target=self._cmd_loop)
        self.cmd_thread.daemon = True
        self.cmd_thread.start()

        self.plot_win.show()

        QtGui.QGuiApplication.instance().exec_()

        self.to_parent.put("closed")

    @inmain_decorator(True)
    def add_plot(self, plot_id, line_id):
        if plot_id not in self.plots:
            plot = self.plot_win.addPlot(title=f"{plot_id}")
            plot.addLegend()
            self.plots[plot_id] = plot
            self.data[plot_id] = {}

        self.data[line_id] = np.array([], dtype=np.float32)
        
        num_plot_lines = len(list(self.plot_lines.keys()))
        cur_colour = self.line_colors[num_plot_lines]
        self.plot_lines[line_id] = self.plots[plot_id].plot(pen=pg.mkPen(cur_colour), name=line_id)

        self.plot_win.nextRow()

    def _cmd_loop(self):
        while True:
            cmd = self.from_parent.get()
            if cmd.startswith('add_plot'):  
                parts = cmd.split()
                plot_id, line_id = parts[1], parts[2]
                self.add_plot(plot_id, line_id)
            elif cmd == 'get_plots':
                open_plot_ids = list(self.plots.keys())
                self.to_parent.put(open_plot_ids)
            elif cmd.startswith('data'):
                parts = cmd.split()
                plot_id, line_id = parts[1], parts[2]
                data = self.from_parent.get()
                self.update_plot(plot_id, line_id, np.array(data, dtype=np.float32))
            elif cmd == 'focus':
                self.setTopLevelWindow()
    
    @inmain_decorator(False)
    def setTopLevelWindow(self):
        self.plot_win.show()
        self.plot_win.activateWindow()
        self.plot_win.raise_()

    @inmain_decorator(False)
    def update_plot(self, plot_id, line_id, new_data):
        if line_id not in self.data:
            raise Exception("Requested plot line_id is not added")
        
        if self.data[line_id].size < self.MAX_DATA:
            if new_data.size + self.data[line_id].size <= self.MAX_DATA:
                self.data[line_id] = np.append(self.data[line_id], new_data)
            else:
                if new_data.size < self.MAX_DATA:
                    self.data[line_id] = np.roll(self.data[line_id], -new_data.size)
                    self.data[line_id][self.data[line_id].size - new_data.size:self.data[line_id].size] = new_data
                else:
                    self.data[line_id] = new_data[new_data.size - self.MAX_DATA:new_data.size]
        else:
            if new_data.size <= self.data[line_id].size:
                self.data[line_id] = np.roll(self.data[line_id], -new_data.size)
                self.data[line_id][self.data[line_id].size - new_data.size:self.data[line_id].size] = new_data
            else:
                self.data[line_id] = new_data[new_data.size - self.data[line_id].size:new_data.size]
        
        self.data[line_id] = self.data[line_id]
        print(self.data[line_id].size)
        self.plot_lines[line_id].setData(self.data[line_id])

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