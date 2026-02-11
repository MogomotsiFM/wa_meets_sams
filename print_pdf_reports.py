import os
import datetime

import warnings
#warnings.simplefilter("ignore", UserWarning)
warnings.filterwarnings("ignore")

import pywinauto

from pywinauto.controls.uia_controls import ComboBoxWrapper, ButtonWrapper
from pywinauto.controls.uiawrapper import UIAWrapper

from pywinauto.application import Application

from typing import Literal

def select_combo_box_option(window, combo_box, value):
	"""
	There seems to be a bug with how pywinauto::ComboBox::select works.
	
	:param classes_window: The parent of the combo box want to select
	:param combo_box: The name of the combo box of interest
	:param value: The option in the combo box that we want to select
	"""

	grade_window = window.window(parent=window, best_match=combo_box, control_type="ComboBox")
	print("Class: ", grade_window.class_name())
	#grade_window.window(control_type="Button").click()
	grade_window = grade_window.expand()
	kids = grade_window.children(control_type="List")
	# Flatten the list of lists
	# Strip spaces because "All" is written " All"
	ks = [k for ks in kids[0].texts() for k in ks]
	if len(ks) == 0:
		print("Number of ComboBox: ", len(kids))
		print([k for kid in kids for ks in kid for k in ks])
	print("Children: ", ks)
	kids[0].item(value).invoke()


def get_combo_box_options(window, combo_box):
	"""
	Returns the list of options available from the combo box.
	These options are then forwarded to the GUI so that the user may select one of them.
	
	:param window: The parent of the combo box in which we are interested 
	:param combo_box: The name of the combo box of interest
	"""
	
	options_combo = window.window(parent=window, best_match=combo_box, control_type="ComboBox")
	options_combo = options_combo.expand()
	kids = options_combo.children(control_type="List")
	labels = [k for ks in kids[0].texts() for k in ks]
	if len(labels) == 0:
		print("Number of ComboBox: ", len(kids))
		print([k for kid in kids for ks in kid for k in ks])
	options_combo.collapse()
	return labels


def process_learner(window, grade, room, report_format, report_path):
	"""
	Prints the report of one learner to file

	: param window: The handle to the "Print learner progress reports" window
	: param learner_idx: Allows iterating over all the learners in a grade
	: param grade: The grade and name of the learner are used to name report files
	"""
	window.window(best_match="Learners", control_type="Group").window(best_match="All", control_type="Button").click()

	# Select report format
	report_format_window = window.window(best_match="Select progress report format", control_type="Group")
	select_combo_box_option(report_format_window, None, report_format)
	
	window.window(best_match="Language to print", control_type="Group").English.click()

	window.window(best_match="Select filter options", control_type="Group").window(best_match="Selected learner", control_type="RadioButton").click()

	filename = f"{grade}_{room}"
	filename = os.path.join(report_path, filename)
	button = window.window(best_match="Print progress report", control_type="Button")

	print_pdf(button, filename)


def print_cover_page(phase: Literal["FET", "Senior"], report_path):
	parent = window.window(best_match="Blank report covers", control_type="Group")
	select_combo_box_option(parent, None, phase)

	filename = f"{phase}_report_cover"
	filename = os.path.join(report_path, filename)

	button = window.window(best_match="Print blank report cover", control_type="Button")
	
	print_pdf(button, filename)


def print_pdf(button: ButtonWrapper, filename: str):
	button.click()

	window.window(best_match="Print setup", control_type="Window").OK.click()

	parent = window.window(best_match="Print reports", control_type="Window")
	parent.window(parent=parent, best_match="Print report", control_type="Button").click()

	window.Print.OK.click()

	# A new window in a new tree is opened
	save_window = app.window(best_match="Printing records", control_type="Window")

	save_window = save_window.window(best_match="Save print output as", control_type="Window")
	save_window.wait(wait_for="ready", timeout=30)

	# select_combo_box_option(save_window, "File name:", filename)
	edit = save_window.window(best_match="File name", control_type="ComboBox").window(control_type="Edit")
	edit.set_edit_text(filename)
	save_window.Save.click()

	parent.wait(wait_for="ready", timeout=30)
	parent.Done.click()



os.putenv("PYDEVD_WARN_SLOW_RESOLVE_TIMEOUT", "10")
#os.environ["PYDEVD_WARN_SLOW_RESOLVE_TIMEOUT"] = "10"

path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")

app_location = os.path.join(path, "EdusolSAMS.exe")
app = Application(backend="uia").start(app_location)

window = app.window(title_re="SA-SAMS")
window.wait("ready", timeout=30)
window.set_focus()
#window.print_control_identifiers()

# Database location
# Use a database on this computer
print("Testing:   ", window.window(best_match="Select Database Location"))
window.window(best_match="Select Database Location").window(best_match="On the network").click()
window["On this computer"].click()

# Do not copy a database before opening it???
desired_copy_db_flag = False
actual_copy_db_flag = window["Copy database before opening"].get_toggle_state()
if desired_copy_db_flag != actual_copy_db_flag:
	window["Copy database before opening"].toggle()

databases = window["Databases on this computer"].window(control_type="List").texts()

# Update the GUI with the list of available databases and let the user select one
print("\n\n\nDatabases:")
[print(db) for db in databases]

# Select a database from the list
# Get this value from the GUI
db = "TestingDB"
window["Databases on this computer"].window(control_type="List").item(db).invoke()

# There is a bug in pywinauto such that when a button is pressed the GUI responds but 
# the code hangs and times out.
# https://github.com/pywinauto/pywinauto/blob/c23e64d5ea2c7d251f263973d320294f2fba5ef0/pywinauto/controls/uiawrapper.py#L548
# TODO: Fix this?
try:
	# Connect to a database
	window["Databases on this computer"].window(best_match="continue").invoke()
except Exception as exp:
	print("Exception: ", exp)

# POPIA Acknowledgement
window.window(title_re="POPIA").window(best_match="I accept").click()

login_window = window.window(title_re="User Login", control_type="Window")
login_window.wait(wait_for="ready", timeout=15)
# Hard-code the username to force the creation of a profile specifically for this application.
# This will allow us to lock down the permissions of the application.
# The same bug is triggered here!!!!
login_window.window(title_re="User Details").Edit1.set_text(u"administrator")
login_window.window(title_re="User Details").Edit2.set_text(u"@dmin2023")

login_window.window(best_match="Log In", control_type="Button").wait("ready", timeout=10)
login_window.window(best_match="Log In", control_type="Button").click()

# We have successfully logged in!
window.EdusolSAMS.OK.click()

# Navigate to the school reports configuration tab
window.window(best_match="Curriculum Related Data").wait("ready", timeout=20)
window.window(best_match="Curriculum Related Data").click()
window.window(best_match="Print Learner Progress Reports").click()
# The following is deliberate
window.window(best_match="Print Learner Progress Reports").click()


# It is possible to print the report of all learners to one PDF.
# The only problem is that the senior and FET phases have different covers.
# So, instead, we split the reports by grade. This way we can tell the phases apart.
# Mhh, do we even need to add the cover for our purpose?
year = "2026"
grade = "Grade 10"
cycle = "Term 1 : FET"
# Report formats
format = "06. Without Averages - All Terms"
room = " All"

report_folder = "reports"
date = f"{datetime.datetime.now()}"
date = date.replace(":", "T")
path = os.path.join(path, report_folder, date)
os.makedirs(name=path, exist_ok=True)

classes_window = window.window(parent=window, best_match="Select Options")
classes_window.ComboBox2.draw_outline()
print("Year: ", get_combo_box_options(classes_window, "Combobox2"))
select_combo_box_option(classes_window, "ComboBox2", year)

classes_window.ComboBox3.draw_outline()
print("Grades: ", get_combo_box_options(classes_window, "Combobox3"))
select_combo_box_option(classes_window, "ComboBox3", grade)

classes_window.ComboBox4.draw_outline()
print("Classes: ", get_combo_box_options(classes_window, "ComboBox4"))
select_combo_box_option(classes_window, "ComboBox4", room)

classes_window.ComboBox6.draw_outline()
print("Cycle: ", get_combo_box_options(classes_window, "ComboBox6"))
select_combo_box_option(classes_window, "ComboBox6", cycle)

# There might be a bug in ComboBox.texts()
[print(cl, cl.draw_outline(), cl.selected_text()) for cl in window.window(best_match="Select Options").children(control_type="ComboBox")]

window.GO.click()

# Configure report format
# Do we need different format for different phases: FET vs senior?
report_format_window = window.window(best_match="Select progress report format", control_type="Group")
report_format_window.window(control_type="ComboBox").draw_outline()
# Display these on the GUI
formats = get_combo_box_options(report_format_window, None)
print("Report formats: ", formats)
select_combo_box_option(report_format_window, None, format)

#window.print_control_identifiers()

# Print one PDF with reports for all the learners in a class(grade + room).
progress_report_window = window.window(best_match="Print progress reports", control_type="Window")
process_learner(progress_report_window, grade, room, format, path)

print_cover_page("FET", path)
print_cover_page("Senior", path)

#----------------------- END OF REPORT PRINTING PROCESS -----------------------------------------

window.window(best_match="Print progress reports", control_type="Window").Done.click()

window.EXIT.click()

print("\n\n")
print("Done")

