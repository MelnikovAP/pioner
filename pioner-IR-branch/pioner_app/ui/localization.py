import re
from silx.gui import qt

_CURRENT_LANGUAGE = "en"


def _ru(s):
    """???????? ?????? `ru`."""
    return s


_TRANSLATIONS = {
    "ru": {
        "Nanocontol": _ru("\u041d\u0430\u043d\u043e\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u044c"),
        "System": _ru("\u0421\u0438\u0441\u0442\u0435\u043c\u0430"),
        "Experiment": _ru("\u042d\u043a\u0441\u043f\u0435\u0440\u0438\u043c\u0435\u043d\u0442"),
        "Data path": _ru("\u041f\u0430\u043f\u043a\u0430 \u0434\u0430\u043d\u043d\u044b\u0445"),
        "Calibration path": _ru("\u041f\u0443\u0442\u044c \u043a \u043a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0435"),
        "View": _ru("\u041e\u0442\u043a\u0440\u044b\u0442\u044c"),
        "Apply": _ru("\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c"),
        "Scan": _ru("\u0421\u043a\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435"),
        "Sample rate:": _ru("\u0427\u0430\u0441\u0442\u043e\u0442\u0430 \u0434\u0438\u0441\u043a\u0440\u0435\u0442\u0438\u0437\u0430\u0446\u0438\u0438:"),
        "Reset": _ru("\u0421\u0431\u0440\u043e\u0441"),
        "Modulation": _ru("\u041c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u044f"),
        "Frequency:": _ru("\u0427\u0430\u0441\u0442\u043e\u0442\u0430:"),
        "Amplitude:": _ru("\u0410\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0430:"),
        "Offset:": _ru("\u0421\u043c\u0435\u0449\u0435\u043d\u0438\u0435:"),
        "Input gains": _ru("\u0412\u0445\u043e\u0434\u043d\u044b\u0435 \u0443\u0441\u0438\u043b\u0435\u043d\u0438\u044f"),
        "Device settings": _ru("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430"),
        "Use Tango": _ru("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c Tango"),
        "Use direct connection": _ru("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u043f\u0440\u044f\u043c\u043e\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435"),
        " run without hardware/ use wo raspi": _ru(" \u0431\u0435\u0437 \u043e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u044f / \u0431\u0435\u0437 raspi"),
        "Signals": _ru("\u0421\u0438\u0433\u043d\u0430\u043b\u044b"),
        "Control": _ru("\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435"),
        "Result": _ru("\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442"),
        "Slow Heating": _ru("\u041c\u0435\u0434\u043b\u0435\u043d\u043d\u044b\u0439 \u043d\u0430\u0433\u0440\u0435\u0432"),
        "Hardware:": _ru("\u041e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u0435:"),
        "Status:": _ru("\u0421\u0442\u0430\u0442\u0443\u0441:"),
        "Progress:": _ru("\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441:"),
        "Values": _ru("\u0417\u043d\u0430\u0447\u0435\u043d\u0438\u044f"),
        "R htr abs:": _ru("R \u043d\u0430\u0433\u0440. \u0430\u0431\u0441:"),
        "R htr dyn:": _ru("R \u043d\u0430\u0433\u0440. \u0434\u0438\u043d:"),
        "U mod htr:": _ru("U \u043d\u0430\u0433\u0440. \u043c\u043e\u0434:"),
        "I htr:": _ru("I \u043d\u0430\u0433\u0440:"),
        "T aux:": "T aux:",
        "T tpl:": "T tpl:",
        "T htr:": _ru("T \u043d\u0430\u0433\u0440:"),
        "T htr dyn:": _ru("T \u043d\u0430\u0433\u0440. \u0434\u0438\u043d:"),
        "T-error:": _ru("T-\u043e\u0448\u0438\u0431\u043a\u0430:"),
        "Frequency:": _ru("\u0427\u0430\u0441\u0442\u043e\u0442\u0430:"),
        "Amplitude:": _ru("\u0410\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0430:"),
        "Offset:": _ru("\u0421\u043c\u0435\u0449\u0435\u043d\u0438\u0435:"),
        "Power:": _ru("\u041c\u043e\u0449\u043d\u043e\u0441\u0442\u044c:"),
        "Phase:": _ru("\u0424\u0430\u0437\u0430:"),
        " ON ": _ru(" \u0412\u041a\u041b "),
        "OFF": _ru("\u0412\u042b\u041a\u041b"),
        "auto gain": _ru("\u0430\u0432\u0442\u043e\u0443\u0441\u0438\u043b\u0435\u043d\u0438\u0435"),
        "Modulation Ramps": _ru("\u0420\u0430\u043c\u043f\u044b \u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u0438"),
        "Modulation uses the main window frequency, amplitude and offset. Optional ramps below change frequency, amplitude and phase step-by-step during slow heating.": _ru("\u041c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u044f \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 \u0447\u0430\u0441\u0442\u043e\u0442\u0443, \u0430\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0443 \u0438 \u0441\u043c\u0435\u0449\u0435\u043d\u0438\u0435 \u0438\u0437 \u0433\u043b\u0430\u0432\u043d\u043e\u0433\u043e \u043e\u043a\u043d\u0430. \u041d\u0438\u0436\u0435 \u043c\u043e\u0436\u043d\u043e \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u043f\u043e\u0448\u0430\u0433\u043e\u0432\u044b\u0435 \u0440\u0430\u043c\u043f\u044b \u043f\u043e \u0447\u0430\u0441\u0442\u043e\u0442\u0435, \u0430\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0435 \u0438 \u0444\u0430\u0437\u0435 \u0432\u043e \u0432\u0440\u0435\u043c\u044f \u043c\u0435\u0434\u043b\u0435\u043d\u043d\u043e\u0433\u043e \u043d\u0430\u0433\u0440\u0435\u0432\u0430."),
        "F-ramp": _ru("\u0420\u0430\u043c\u043f\u0430 F"),
        "A-ramp": _ru("\u0420\u0430\u043c\u043f\u0430 A"),
        "P-ramp": _ru("\u0420\u0430\u043c\u043f\u0430 P"),
        "Final Freq (Hz)": _ru("\u041a\u043e\u043d\u0435\u0447\u043d\u0430\u044f \u0447\u0430\u0441\u0442\u043e\u0442\u0430 (\u0413\u0446)"),
        "Final Amp (mA)": _ru("\u041a\u043e\u043d\u0435\u0447\u043d\u0430\u044f \u0430\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0430 (\u043c\u0410)"),
        "Final Phase (deg)": _ru("\u041a\u043e\u043d\u0435\u0447\u043d\u0430\u044f \u0444\u0430\u0437\u0430 (\u0433\u0440\u0430\u0434)"),
        "Ramp steps": _ru("\u0428\u0430\u0433\u0438 \u0440\u0430\u043c\u043f\u044b"),
        "x2 demod": _ru("x2 \u0434\u0435\u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u044f"),
        "Temperature ramp": _ru("\u0420\u0430\u043c\u043f\u0430 \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u044b"),
        "Voltage ramp": _ru("\u0420\u0430\u043c\u043f\u0430 \u043d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u044f"),
        "Start": _ru("\u041d\u0430\u0447\u0430\u043b\u043e"),
        "End": _ru("\u041a\u043e\u043d\u0435\u0446"),
        "Rate / min": _ru("\u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c / \u043c\u0438\u043d"),
        "Analysis": _ru("\u0410\u043d\u0430\u043b\u0438\u0437"),
        "Periods / point": _ru("\u041f\u0435\u0440\u0438\u043e\u0434\u043e\u0432 / \u0442\u043e\u0447\u043a\u0443"),
        "Point dt (s)": _ru("\u0428\u0430\u0433 \u0442\u043e\u0447\u043a\u0438 (\u0441)"),
        "X axis": _ru("\u041e\u0441\u044c X"),
        "Hold final value": _ru("\u0423\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0442\u044c \u043a\u043e\u043d\u0435\u0447\u043d\u043e\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435"),
        "Idle": _ru("\u041e\u0436\u0438\u0434\u0430\u043d\u0438\u0435"),
        "START EXP": _ru("\u0421\u0422\u0410\u0420\u0422"),
        "STOP EXP": _ru("\u0421\u0422\u041e\u041f"),
        "Time": _ru("\u0412\u0440\u0435\u043c\u044f"),
        "AO1 Voltage": _ru("\u041d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u0435 AO1"),
        "Amplitude": _ru("\u0410\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u0430"),
        "Power": _ru("\u041c\u043e\u0449\u043d\u043e\u0441\u0442\u044c"),
        "Save slow heating results": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b \u043c\u0435\u0434\u043b\u0435\u043d\u043d\u043e\u0433\u043e \u043d\u0430\u0433\u0440\u0435\u0432\u0430"),
        "CSV files (*.csv)": _ru("\u0424\u0430\u0439\u043b\u044b CSV (*.csv)"),
        "Plot Options": _ru("\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b \u0433\u0440\u0430\u0444\u0438\u043a\u0430"),
        "Plot mode": _ru("\u0420\u0435\u0436\u0438\u043c \u0433\u0440\u0430\u0444\u0438\u043a\u0430"),
        "Profile segments": _ru("\u0421\u0435\u0433\u043c\u0435\u043d\u0442\u044b \u043f\u0440\u043e\u0444\u0438\u043b\u044f"),
        "All": _ru("\u0412\u0441\u0435"),
        "Heating": _ru("\u041d\u0430\u0433\u0440\u0435\u0432"),
        "Cooling": _ru("\u041e\u0445\u043b\u0430\u0436\u0434\u0435\u043d\u0438\u0435"),
        "Isotherm": _ru("\u0418\u0437\u043e\u0442\u0435\u0440\u043c\u0430"),
        "Clear": _ru("\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c"),
        "Mode:": _ru("\u0420\u0435\u0436\u0438\u043c:"),
        "Options": _ru("\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b"),
        "Multi Y": _ru("\u041d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e Y"),
        "X vs Y": _ru("X \u043e\u0442 Y"),
        "Overlay By Segment": _ru("\u041d\u0430\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043f\u043e \u0441\u0435\u0433\u043c\u0435\u043d\u0442\u0430\u043c"),
        "Time (ms)": _ru("\u0412\u0440\u0435\u043c\u044f (\u043c\u0441)"),
        "Temperature (C)": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 (C)"),
        "Temperature HR (C)": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 HR (C)"),
        "Reference (V)": _ru("\u041e\u043f\u043e\u0440\u043d\u044b\u0439 \u0441\u0438\u0433\u043d\u0430\u043b (\u0412)"),
        "Heater Current (mA)": _ru("\u0422\u043e\u043a \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f (\u043c\u0410)"),
        "Heater Temperature (C)": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f (C)"),
        "Aux Temperature (C)": _ru("\u0412\u0441\u043f\u043e\u043c\u043e\u0433\u0430\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 (C)"),
        "Selected Quantities": _ru("\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0435 \u0432\u0435\u043b\u0438\u0447\u0438\u043d\u044b"),
        "Sine": _ru("\u0421\u0438\u043d\u0443\u0441"),
        "Ramp": _ru("\u0420\u0430\u043c\u043f\u0430"),
        "Tail": _ru("\u0425\u0432\u043e\u0441\u0442"),
        "Data source": _ru("\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a \u0434\u0430\u043d\u043d\u044b\u0445"),
        "Open h5": _ru("\u041e\u0442\u043a\u0440\u044b\u0442\u044c h5"),
        "Selection": _ru("\u0412\u044b\u0431\u043e\u0440"),
        "Curve": _ru("\u041a\u0440\u0438\u0432\u0430\u044f"),
        "Segment": _ru("\u0421\u0435\u0433\u043c\u0435\u043d\u0442"),
        "Selected range": _ru("\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d"),
        "Use Set start or Set end, then left click on the graph.": _ru("\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u041d\u0430\u0447\u0430\u043b\u043e\u00bb \u0438\u043b\u0438 \u00ab\u041a\u043e\u043d\u0435\u0446\u00bb, \u0437\u0430\u0442\u0435\u043c \u0449\u0451\u043b\u043a\u043d\u0438\u0442\u0435 \u043b\u0435\u0432\u043e\u0439 \u043a\u043d\u043e\u043f\u043a\u043e\u0439 \u043f\u043e \u0433\u0440\u0430\u0444\u0438\u043a\u0443."),
        "Set start": _ru("\u041d\u0430\u0447\u0430\u043b\u043e"),
        "Set end": _ru("\u041a\u043e\u043d\u0435\u0446"),
        "Clear range": _ru("\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d"),
        "Math operations": _ru("\u041c\u0430\u0442\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0438"),
        "Fit type": _ru("\u0422\u0438\u043f \u0430\u043f\u043f\u0440\u043e\u043a\u0441\u0438\u043c\u0430\u0446\u0438\u0438"),
        "Fit range": _ru("\u0410\u043f\u043f\u0440\u043e\u043a\u0441\u0438\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d"),
        "Subtract fit": _ru("\u0412\u044b\u0447\u0435\u0441\u0442\u044c \u0430\u043f\u043f\u0440\u043e\u043a\u0441\u0438\u043c\u0430\u0446\u0438\u044e"),
        "Reset curve": _ru("\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043a\u0440\u0438\u0432\u0443\u044e"),
        "Processing": _ru("\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430"),
        "Save processing": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443"),
        "Open processing": _ru("\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443"),
        "Load an h5 file to begin.": _ru("\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 h5-\u0444\u0430\u0439\u043b, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c."),
        "Full trace": _ru("\u0412\u0441\u044f \u043a\u0440\u0438\u0432\u0430\u044f"),
        "Linear": _ru("\u041b\u0438\u043d\u0435\u0439\u043d\u0430\u044f"),
        "Quadratic": _ru("\u041a\u0432\u0430\u0434\u0440\u0430\u0442\u0438\u0447\u043d\u0430\u044f"),
        "Cubic": _ru("\u041a\u0443\u0431\u0438\u0447\u0435\u0441\u043a\u0430\u044f"),
        "Quartic": _ru("\u0427\u0435\u0442\u0432\u0451\u0440\u0442\u043e\u0439 \u0441\u0442\u0435\u043f\u0435\u043d\u0438"),
        "Exponential": _ru("\u042d\u043a\u0441\u043f\u043e\u043d\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u0430\u044f"),
        "Logarithmic": _ru("\u041b\u043e\u0433\u0430\u0440\u0438\u0444\u043c\u0438\u0447\u0435\u0441\u043a\u0430\u044f"),
        "Experimental data": _ru("\u042d\u043a\u0441\u043f\u0435\u0440\u0438\u043c\u0435\u043d\u0442\u0430\u043b\u044c\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435"),
        "Reference data": _ru("\u042d\u0442\u0430\u043b\u043e\u043d\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435"),
        "Average": _ru("\u0421\u0440\u0435\u0434\u043d\u0435\u0435"),
        "Plot": _ru("\u0413\u0440\u0430\u0444\u0438\u043a"),
        "Save": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c"),
        "Calibration coefficients": _ru("\u041a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u044b \u043a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0438"),
        "Manual correction": _ru("\u0420\u0443\u0447\u043d\u0430\u044f \u043a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f"),
        "Auto correction": _ru("\u0410\u0432\u0442\u043e\u043a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f"),
        "Display rate": _ru("\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u044c"),
        "Fit segment": _ru("\u0410\u043f\u043f\u0440\u043e\u043a\u0441\u0438\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0433\u043c\u0435\u043d\u0442"),
        "Auto find": _ru("\u0410\u0432\u0442\u043e\u043f\u043e\u0438\u0441\u043a"),
        "Calculate": _ru("\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0442\u044c"),
        "Constant heat exchange:": _ru("\u041f\u043e\u0441\u0442\u043e\u044f\u043d\u043d\u044b\u0439 \u0442\u0435\u043f\u043b\u043e\u043e\u0431\u043c\u0435\u043d:"),
        "Calibration info": _ru("\u041a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0430"),
        "Calibration info: ": _ru("\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0438: "),
        "Thermopile temperature": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u0442\u0435\u0440\u043c\u043e\u0431\u0430\u0442\u0430\u0440\u0435\u0438"),
        "Modulation heater rel. voltage": _ru("\u041e\u0442\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u043d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u0435 \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f \u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u0438"),
        "Modulation heater current": _ru("\u0422\u043e\u043a \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f \u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u0438"),
        "Modulation heater temperature": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f \u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u0438"),
        "Dynamic modulation heater temperature": _ru("\u0414\u0438\u043d\u0430\u043c\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f \u043c\u043e\u0434\u0443\u043b\u044f\u0446\u0438\u0438"),
        "Heater temperature vs heater voltage": _ru("\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u044f \u043e\u0442 \u043d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u044f"),
        "Heaters resistance": _ru("\u0421\u043e\u043f\u0440\u043e\u0442\u0438\u0432\u043b\u0435\u043d\u0438\u044f \u043d\u0430\u0433\u0440\u0435\u0432\u0430\u0442\u0435\u043b\u0435\u0439"),
        "Amplitude correction": _ru("\u041a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f \u0430\u043c\u043f\u043b\u0438\u0442\u0443\u0434\u044b"),
        "Load && Apply": _ru("\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0438 \u043f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c"),
        "Save && Apply": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0438 \u043f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c"),
        "Error": _ru("\u041e\u0448\u0438\u0431\u043a\u0430"),
        "Sorry...": _ru("\u0418\u0437\u0432\u0438\u043d\u0438\u0442\u0435..."),
        "Warning": _ru("\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435"),
        "Help & Configuration": _ru("\u0421\u043f\u0440\u0430\u0432\u043a\u0430 \u0438 \u043a\u043e\u043d\u0444\u0438\u0433\u0443\u0440\u0430\u0446\u0438\u044f"),
        "Some help will be here :)": _ru("\u0417\u0434\u0435\u0441\u044c \u0431\u0443\u0434\u0435\u0442 \u0441\u043f\u0440\u0430\u0432\u043a\u0430 :)"),
        "Configuration parameters": _ru("\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b \u043a\u043e\u043d\u0444\u0438\u0433\u0443\u0440\u0430\u0446\u0438\u0438"),
        "Tango host: ": _ru("\u0425\u043e\u0441\u0442 Tango: "),
        "Device proxy: ": _ru("\u041f\u0440\u043e\u043a\u0441\u0438 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430: "),
        "HTTP host: ": _ru("HTTP \u0445\u043e\u0441\u0442: "),
        "Load": _ru("\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c"),
        "Save Config": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435 \u043a\u043e\u043d\u0444\u0438\u0433\u0430"),
        "Save application settings before closing?": _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f \u043f\u0435\u0440\u0435\u0434 \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0435\u043c?"),
        "Choose interface language": _ru("\u0412\u044b\u0431\u043e\u0440 \u044f\u0437\u044b\u043a\u0430 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430"),
        "Interface language": _ru("\u042f\u0437\u044b\u043a \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430"),
        "English": "English",
        "???????": _ru("\u0420\u0443\u0441\u0441\u043a\u0438\u0439"),
        "None": _ru("\u041d\u0435\u0442"),
        "DISCONNECTED": _ru("\u041e\u0422\u041a\u041b\u042e\u0427\u0415\u041d\u041e"),
        "CONNECTED": _ru("\u041f\u041e\u0414\u041a\u041b\u042e\u0427\u0415\u041d\u041e"),
        "RUNNING": _ru("\u0412\u042b\u041f\u041e\u041b\u041d\u042f\u0415\u0422\u0421\u042f"),
        "Disconnected": _ru("\u041e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e"),
        "Stopped": _ru("\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e"),
    }
}

_PATTERNS_RU = [
    (re.compile(r"^Segments: full trace$"), lambda m: _ru("\u0421\u0435\u0433\u043c\u0435\u043d\u0442\u044b: \u0432\u0441\u044f \u043a\u0440\u0438\u0432\u0430\u044f")),
    (re.compile(r"^Segments: (\d+)/(\d+)$"), lambda m: _ru("\u0421\u0435\u0433\u043c\u0435\u043d\u0442\u044b: ") + f"{m.group(1)}/{m.group(2)}"),
    (re.compile(r"^Loaded (.+)$"), lambda m: _ru("\u0417\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e: ") + m.group(1)),
    (re.compile(r"^Saved: (.+)$"), lambda m: _ru("\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e: ") + m.group(1)),
    (re.compile(r"^Running (temperature|voltage) ramp$"), lambda m: _ru("\u0412\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0440\u0430\u043c\u043f\u0430 ") + (_ru("\u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u044b") if m.group(1) == "temperature" else _ru("\u043d\u0430\u043f\u0440\u044f\u0436\u0435\u043d\u0438\u044f"))),
    (re.compile(r"^Holding final setpoint(.*)$"), lambda m: _ru("\u0423\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u043a\u043e\u043d\u0435\u0447\u043d\u0430\u044f \u0443\u0441\u0442\u0430\u0432\u043a\u0430") + m.group(1)),
    (re.compile(r"^Running, f=(.+) Hz, demod=(.+) Hz(.*)$"), lambda m: _ru("\u0412\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f, f=") + m.group(1) + _ru(" \u0413\u0446, \u0434\u0435\u043c\u043e\u0434=") + m.group(2) + _ru(" \u0413\u0446") + m.group(3)),
    (re.compile(r"^Left click on the graph to place the start marker\.$"), lambda m: _ru("\u0429\u0451\u043b\u043a\u043d\u0438\u0442\u0435 \u043b\u0435\u0432\u043e\u0439 \u043a\u043d\u043e\u043f\u043a\u043e\u0439 \u043f\u043e \u0433\u0440\u0430\u0444\u0438\u043a\u0443, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043d\u0430\u0447\u0430\u043b\u044c\u043d\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0440.")),
    (re.compile(r"^Left click on the graph to place the end marker\.$"), lambda m: _ru("\u0429\u0451\u043b\u043a\u043d\u0438\u0442\u0435 \u043b\u0435\u0432\u043e\u0439 \u043a\u043d\u043e\u043f\u043a\u043e\u0439 \u043f\u043e \u0433\u0440\u0430\u0444\u0438\u043a\u0443, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043a\u043e\u043d\u0435\u0447\u043d\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0440.")),
    (re.compile(r"^Range markers cleared\.$"), lambda m: _ru("\u041c\u0430\u0440\u043a\u0435\u0440\u044b \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u0430 \u043e\u0447\u0438\u0449\u0435\u043d\u044b.")),
    (re.compile(r"^End marker placed\.$"), lambda m: _ru("\u041a\u043e\u043d\u0435\u0447\u043d\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0440 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d.")),
    (re.compile(r"^Start marker placed\. Press Set end to place the end marker\.$"), lambda m: _ru("\u041d\u0430\u0447\u0430\u043b\u044c\u043d\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0440 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u041a\u043e\u043d\u0435\u0446\u00bb, \u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043a\u043e\u043d\u0435\u0447\u043d\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0440.")),
    (re.compile(r"^Select an h5 file first\.$"), lambda m: _ru("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 h5-\u0444\u0430\u0439\u043b.")),
    (re.compile(r"^Tail Residual \((.+) samples\)$"), lambda m: _ru("\u0425\u0432\u043e\u0441\u0442\u043e\u0432\u043e\u0439 \u043e\u0441\u0442\u0430\u0442\u043e\u043a (") + m.group(1).replace("samples", _ru("\u043e\u0442\u0441\u0447\u0451\u0442\u043e\u0432")) + ")"),
]


def set_language(language):
    """????????????? ?????? `set_language`."""
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = language or "en"



def get_language():
    """?????????? ?????? `get_language`."""
    return _CURRENT_LANGUAGE



def translate_text(text, language=None):
    """????????? ?????? `translate_text`."""
    if text is None:
        return text
    lang = language or _CURRENT_LANGUAGE
    if lang != "ru":
        return text
    translated = _TRANSLATIONS["ru"].get(text)
    if translated is not None:
        return translated
    for pattern, repl in _PATTERNS_RU:
        match = pattern.match(text)
        if match:
            return repl(match)
    return text



def tr(text, language=None):
    """???????? ?????? `tr`."""
    return translate_text(text, language=language)



def _apply_text(obj, getter_name, setter_name, language):
    """????????? ?????? `apply_text`."""
    getter = getattr(obj, getter_name, None)
    setter = getattr(obj, setter_name, None)
    if getter is None or setter is None:
        return
    try:
        current = getter()
    except TypeError:
        return
    if not isinstance(current, str) or not current:
        return
    translated = translate_text(current, language)
    if translated != current:
        setter(translated)



def apply_language(widget, language=None):
    """????????? ?????? `apply_language`."""
    lang = language or _CURRENT_LANGUAGE
    if widget is None:
        return widget
    _apply_text(widget, "windowTitle", "setWindowTitle", lang)
    _apply_text(widget, "toolTip", "setToolTip", lang)
    _apply_text(widget, "statusTip", "setStatusTip", lang)
    _apply_text(widget, "whatsThis", "setWhatsThis", lang)
    if hasattr(widget, "text") and hasattr(widget, "setText"):
        _apply_text(widget, "text", "setText", lang)
    if hasattr(widget, "title") and hasattr(widget, "setTitle"):
        _apply_text(widget, "title", "setTitle", lang)
    if isinstance(widget, qt.QComboBox):
        for i in range(widget.count()):
            txt = widget.itemText(i)
            translated = translate_text(txt, lang)
            if translated != txt:
                widget.setItemText(i, translated)
    if isinstance(widget, qt.QTabWidget):
        for i in range(widget.count()):
            txt = widget.tabText(i)
            translated = translate_text(txt, lang)
            if translated != txt:
                widget.setTabText(i, translated)
    if isinstance(widget, qt.QDialogButtonBox):
        for button in widget.buttons():
            apply_language(button, lang)
    for child in widget.findChildren(qt.QWidget):
        if child is widget:
            continue
        _apply_text(child, "windowTitle", "setWindowTitle", lang)
        _apply_text(child, "toolTip", "setToolTip", lang)
        _apply_text(child, "statusTip", "setStatusTip", lang)
        if hasattr(child, "text") and hasattr(child, "setText"):
            _apply_text(child, "text", "setText", lang)
        if hasattr(child, "title") and hasattr(child, "setTitle"):
            _apply_text(child, "title", "setTitle", lang)
        if isinstance(child, qt.QComboBox):
            for i in range(child.count()):
                txt = child.itemText(i)
                translated = translate_text(txt, lang)
                if translated != txt:
                    child.setItemText(i, translated)
        if isinstance(child, qt.QTabWidget):
            for i in range(child.count()):
                txt = child.tabText(i)
                translated = translate_text(txt, lang)
                if translated != txt:
                    child.setTabText(i, translated)
    return widget


class LanguageDialog(qt.QDialog):
    def __init__(self, current_language="en", parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super().__init__(parent)
        self.setWindowTitle(tr("Choose interface language", current_language))
        self.setModal(True)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(qt.QLabel(tr("Interface language", current_language)))
        self.combo = qt.QComboBox()
        self.combo.addItem("English", "en")
        self.combo.addItem(_ru("\u0420\u0443\u0441\u0441\u043a\u0438\u0439"), "ru")
        idx = max(0, self.combo.findData(current_language or "en"))
        self.combo.setCurrentIndex(idx)
        layout.addWidget(self.combo)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        apply_language(self, current_language if current_language in ("en", "ru") else "en")

    def selected_language(self):
        """???????? ?????? `selected_language`."""
        return str(self.combo.currentData())



def choose_language(current_language="en", parent=None):
    """???????? ?????? `choose_language`."""
    dialog = LanguageDialog(current_language=current_language, parent=parent)
    if dialog.exec_() == qt.QDialog.Accepted:
        return dialog.selected_language()
    return current_language or "en"
