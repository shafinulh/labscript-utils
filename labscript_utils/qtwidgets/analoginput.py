#####################################################################
#                                                                   #
# analogoutput.py                                                   #
#                                                                   #
# Copyright 2013, Monash University                                 #
#                                                                   #
# This file is part of the labscript suite (see                     #
# http://labscriptsuite.org) and is licensed under the Simplified   #
# BSD License. See the license.txt file in the root of the project  #
# for the full license.                                             #
#                                                                   #
#####################################################################

import sys

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from qtutils import *
import qtutils.icons

import threading
import time
from labscript_utils.qtwidgets.InputPlotWindow import PlotWindow

class PlotSelectionDialog(QDialog):
    def __init__(self, parent=None, plot_identifiers=None):
        super().__init__(parent)
        self.setWindowTitle("Select Plot")

        self.layout = QVBoxLayout(self)
        self.plot_selector = QComboBox(self)
        self.plot_selector.addItem("New Plot")
        if plot_identifiers:
            self.plot_selector.addItems(plot_identifiers)

        self.layout.addWidget(self.plot_selector)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def selected_plot(self):
        return self.plot_selector.currentText() if self.plot_selector.currentText() != "New Plot" else None
class AnalogInput(QWidget):
    def __init__(
        self, 
        device_name, 
        hardware_name, 
        plot_process, 
        to_child, 
        from_child, 
        connection_name='-', 
        display_name=None, 
        horizontal_alignment=False, 
        parent=None
    ):
        QWidget.__init__(self, parent)

        self.plot = None
        self.plot_identifier = None
        self.plot_line_legend_label = f"{device_name}_{hardware_name}"

        self.plot_process = plot_process
        self.to_child = to_child
        self.from_child = from_child

        self._device_name = device_name
        self._connection_name = connection_name
        self._hardware_name = hardware_name
        self.win = None

        label_text = (self._hardware_name + '\n' + self._connection_name) if display_name is None else display_name
        self._label = QLabel(label_text)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self._line_edit = QLineEdit()
        self._line_edit.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        self._line_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._line_edit.setMaximumWidth(55)
        self._line_edit.setAlignment(Qt.AlignRight)
        self._line_edit.setReadOnly(True)

        self._plot_btn = QPushButton()
        self._plot_btn.setIcon(QIcon(':/qtutils/fugue/chart-up'))
        self._plot_btn.clicked.connect(self.open_plot_window)

        self._value_changed_function = None

        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)

        # Create widgets and layouts
        if horizontal_alignment:
            self._layout = QHBoxLayout(self)
            self._layout.addWidget(self._label)
            self._layout.addWidget(self._line_edit)
            self._layout.addWidget(self._plot_btn)
        else:
            self._layout = QGridLayout(self)
            self._layout.setVerticalSpacing(0)
            self._layout.setHorizontalSpacing(0)
            self._layout.setContentsMargins(5, 5, 5, 5)

            self._label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
            self._layout.addWidget(self._label)
            self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.MinimumExpanding, QSizePolicy.Minimum), 0, 1)

            h_widget = QWidget()
            h_layout = QHBoxLayout(h_widget)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.addWidget(self._line_edit)

            self._layout.addWidget(self._label, 0, 0)
            self._layout.addWidget(h_widget, 1, 0)
            self._layout.addWidget(self._plot_btn, 2, 0)
            self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.MinimumExpanding, QSizePolicy.Minimum), 1, 1)

        self.set_value(None)

        # The Analog input object that is in charge of this button
        self._AI = None

    # Setting and getting methods for the Digitl Out object in charge of this button
    def set_AI(self, AI, notify_old_AI=True, notify_new_AI=True):
        # If we are setting a new AO, remove this widget from the old one (if it isn't None) and add it to the new one (if it isn't None)
        if AI != self._AI:
            if self._AI is not None and notify_old_AI:
                self._AI.remove_widget(self, False)
            if AI is not None and notify_new_AI:
                AI.add_widget(self)
        # Store a reference to the digital out object
        self._AI = AI

    def get_AI(self):
        return self._AI

    @inmain_decorator(True)
    def set_value(self, value):
        if value is not None:
            text = "%0.4f" % value
        else:
            text = "no value"
        self._line_edit.setText(text)
    
    @inmain_decorator(True)
    def set_buffer(self, data):
        if data is not None and self.plot is not None:
            # Method 1 - sending data using IPC
            self.to_child.put(f'data {self.plot_identifier} {self.plot_line_legend_label}')
            self.to_child.put(data)

    def _check_plot_window(self):
        while self.plot is not None:
            time.sleep(0.1)
            # if self.from_child.get() == "closed":
            #     self.plot = None
            #     self.to_child = None
            #     self.from_child = None

    def open_plot_window(self):
        if self.plot is None:
            self.to_child.put('get_plots')
            open_plots = self.from_child.get()
            self.show_plot_selection_dialog(open_plots)
            self.plot_process.to_child.put(f"add_plot {self.plot_identifier} {self.plot_line_legend_label}")
            self.plot = True

            check_plot_window_thread = threading.Thread(target=self._check_plot_window)
            check_plot_window_thread.daemon = True
            check_plot_window_thread.start()
        else:
            self.to_child.put('focus')
    
    def prompt_plot_identifier(self):
        text, ok = QInputDialog.getText(self, 'Input Plot Identifier', 'Enter plot identifier:')
        if ok and text:
            self.plot_identifier = text

    @inmain_decorator(True)
    def show_plot_selection_dialog(self, plot_identifiers):
        if not plot_identifiers:
            self.prompt_plot_identifier()
            return
        print("here")
        dialog = PlotSelectionDialog(self, plot_identifiers)
        if dialog.exec_() == QDialog.Accepted:
            plot_identifier = dialog.selected_plot()
            if plot_identifier:
                self.plot_identifier = plot_identifier
            else:
                self.prompt_plot_identifier()


# A simple test!
if __name__ == '__main__':

    def simulate_data_stream(analog_input_widget,min_val,max_val):
        import numpy as np
        while True:
            data = np.random.rand(1000).astype(np.float32)
            # Scale and shift the values to be between min_val and max_val
            data = (max_val - min_val) * data + min_val
            analog_input_widget.set_buffer(data)
            time.sleep(0.2)

    qapplication = QApplication(sys.argv)

    win = PlotWindow()
    to_child, from_child = win.start()

    window = QWidget()
    layout = QVBoxLayout(window)

    button0 = AnalogInput('ni_6363', 'AI0', win, to_child, from_child)
    button0.set_value(0)
    button1 = AnalogInput('ni_6363', 'AI1', win, to_child, from_child)
    button1.set_value(1)
    button2 = AnalogInput('ni_6363', 'AI2', win, to_child, from_child)
    button2.set_value(2)

    layout.addWidget(button0)
    layout.addWidget(button1)
    layout.addWidget(button2)

    window.show()

    data_thread = threading.Thread(target=simulate_data_stream, args=(button0, 0, 1))
    data_thread.daemon = True
    data_thread.start()
    data_thread = threading.Thread(target=simulate_data_stream, args=(button1, 4, 5))
    data_thread.daemon = True
    data_thread.start()
    data_thread = threading.Thread(target=simulate_data_stream, args=(button2, 9, 10))
    data_thread.daemon = True
    data_thread.start()

    sys.exit(qapplication.exec_())
