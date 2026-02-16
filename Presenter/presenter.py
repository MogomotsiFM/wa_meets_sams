import os
import time
import datetime

from enum import Enum
from functools import reduce
from dataclasses import dataclass

import warnings
#warnings.simplefilter("ignore", UserWarning)
warnings.filterwarnings("ignore")

import pywinauto

from pywinauto.controls.uia_controls import ComboBoxWrapper, ButtonWrapper
from pywinauto.controls.uiawrapper import UIAWrapper

from pywinauto.application import Application

from typing import Literal


class LoginStatus(Enum):
	SUCCESS= 1
	FAILURE= 2
	LOCKED_OUT= 4


# These values were discovered using: window.print_control_identifiers() function.
class ComboBoxControlId(Enum):
	YEAR   = 73
	GRADE  = 74
	ROOM   = 75 # Eg. 10A, 12C, ...
	CYCLE  = 72 # Term 1, 2, 3, or 4
	PHASE  = 60 # FET or Senior
	FORMAT = 40 # Report format

class Presenter:
    def __init__(self, app_path):
        report_folder = "Reports"
        date = f"{datetime.datetime.now()}"
        date = date.replace(":", "T")
        self.cover_path = os.path.join(app_path, report_folder, date, "covers")
        self.report_path = os.path.join(app_path, report_folder, date, "reports")
        os.makedirs(name=self.cover_path, exist_ok=True)
        os.makedirs(name=self.report_path, exist_ok=True)

        self.id_cb_map = {}
        self.cache = {}

        self.app, self.window = self._start(app_path)

        self.cache = self.create_controls_cache()
        print("Cache:")
        [print(k, control, type(control)) for k, control in self.cache.items()]


    def select_combo_box_option(self, combo_box: ComboBoxWrapper, value: str):
        """
        There seems to be a bug with how pywinauto::ComboBox::select works.
        
        :param combo_box: The combo box object of interest
        :param value: The option in the combo box that we want to select
        """

        combo_box = combo_box.expand()
        kids = combo_box.children(control_type="List")
        print("\n\nKids:", value)
        for k in kids:
            print(k.texts())
        kids[0].item(value).invoke()


    def get_combo_box_options(self, options_combo: ComboBoxWrapper) -> list[str]:
        """
        Returns the list of options available from the combo box.
        These options are then forwarded to the GUI so that the user may select one of them.
        
        :param combo_box: The combo box object of interest
        """
        
        options_combo = options_combo.expand()
        kids = options_combo.children(control_type="List")
        labels = [k for ks in kids[0].texts() for k in ks]
        options_combo.collapse()
        return labels


    def _get_combo_boxes(self):
        cbs = self.window.descendants(control_type="ComboBox")
        id_combo_box_map = {cb.control_id(): cb for cb in cbs}
        
        return id_combo_box_map


    def process_learner(self, grade, room, report_format, report_file_path):
        """
        Prints the report of one learner to file

        : param window: The handle to the "Print learner progress reports" window
        : param learner_idx: Allows iterating over all the learners in a grade
        : param grade: The grade and name of the learner are used to name report files
        : param report_format_combo_box: 
        """
        self.window.window(best_match="Learners", control_type="Group").window(best_match="All", control_type="Button").click()

        # Select report format
        #self.select_report_format(report_format)
        
        self.window.window(best_match="Language to print", control_type="Group").English.click()

        self.window.window(best_match="Select filter options", control_type="Group").window(best_match="Selected learner", control_type="RadioButton").click()

        filename = f"{grade}_{room}"
        filename = os.path.join(report_file_path, filename)
        button = self.window.window(best_match="Print progress report", control_type="Button")

        self.print_pdf(button, filename)


    def print_cover_page(self, combo_box: ComboBoxWrapper, phase: Literal["FET", "Senior"], report_path: str):
        self.select_combo_box_option(combo_box, phase)

        filename = f"{phase}_report_cover"
        filename = os.path.join(report_path, filename)

        button = self.window.window(best_match="Print blank report cover", control_type="Button")
        
        self.print_pdf(button, filename)


    def print_pdf(self, button: ButtonWrapper, filename: str):
        button.click()

        self.window.window(best_match="Print setup", control_type="Window").OK.click()

        parent = self.window.window(best_match="Print reports", control_type="Window")
        parent.window(parent=parent, best_match="Print report", control_type="Button").click()

        self.window.Print.OK.click()

        # A new window in a new tree is opened
        save_window = self.app.window(best_match="Printing records", control_type="Window")

        save_window = save_window.window(best_match="Save print output as", control_type="Window")
        save_window.wait(wait_for="ready", timeout=30)

        # select_combo_box_option(save_window, "File name:", filename)
        edit = save_window.window(best_match="File name", control_type="ComboBox").window(control_type="Edit")
        edit.set_edit_text(filename)
        save_window.Save.click()

        parent.wait(wait_for="ready", timeout=30)
        parent.Done.click()


    def exit_mainwindow(self):
        self.window.Exit.click()

    
    def copy_db_before_opening(self, desired_copy_db_flag):
        actual_copy_db_flag = self.get_copy_db_checkbox_state()
        if desired_copy_db_flag != actual_copy_db_flag:
            checkbox = self.controls_cache('self.window["Copy database before opening"]')
            checkbox.toggle()


    def get_copy_db_checkbox_state(self):
        checkbox = self.controls_cache('self.window["Copy database before opening"]')
        state = checkbox.get_toggle_state()

        return state>0


    def local_dbs_list(self):
        lst = self.controls_cache('self.window["Databases on this computer"].window(control_type="List")')
        databases = lst.texts()
        dbs = [item for sublist in databases for item in sublist]
        return dbs


    def last_used_networked_db(self):
        textbox = self.controls_cache('self.window["Database on a networked computer"].window(control_type="Edit")')
        return textbox.get_value()
    

    def select_local_db(self, db_name):
        lst = self.controls_cache('self.window["Databases on this computer"].window(control_type="List")')
        lst.item(db_name).click_input()


    def set_networked_db(self, db_path):
        textbox = self.controls_cache('self.window["Database on a networked computer"].window(control_type="Edit")')

        textbox.set_edit_text(db_path)


    def use_networked_db(self) -> None:
        radio = self.controls_cache('self.window["On the network"]')
        radio.click()


    def use_networked_db_radio_state(self) -> bool:
        radio = self.controls_cache('self.window["On the network"]')
        return radio.is_selected()
    

    def use_local_db(self) -> None:
        radio = self.controls_cache('self.window["On this computer"]')
        radio.click()


    def use_local_db_radio_state(self) -> bool:
        radio = self.controls_cache('self.window["On this computer"]')
        return radio.is_selected()
                             

    def continue_to_login(self):
        if self.use_local_db_radio_state():
            self.window["Databases on this computer"].window(best_match="continue").click_input()
        else:
            self.window["Databases on a networked computer"].window(best_match="continue").click_input()

        # POPIA Acknowledgement
        self.window.window(title_re="POPIA").window(best_match="I accept").click()

        login_window = self.window.window(title_re="User Login", control_type="Window")
        login_window.wait(wait_for="ready", timeout=15)


    def create_controls_cache(self):
        """
        Cache the controls in the first widget of SA-SAMS.
        This should make the Presenter more responsive and the view snappy.

        The naming convention of the keys was strictly meant to make the transition easy
        to verify in the absence of automated tests.
        
        It is for no other purpose.
        """
        cache = {}

        self.use_local_db()

        # pywinauto is lazy so we call WindowSpecification::wait() to force evaluation...
        cache['self.window["Copy database before opening"]'] = self.window["Copy database before opening"].wait("ready")

        cache['self.window["Databases on this computer"].window(control_type="List")'] = self.window["Databases on this computer"].window(control_type="List").wait("ready")

        cache['self.window["On this computer"]'] = self.window["On this computer"].wait("ready")

        self.use_networked_db()

        cache['self.window["Database on a networked computer"].window(control_type="Edit")'] = self.window["Database on a networked computer"].window(control_type="Edit").wait("ready")

        cache['self.window["On the network"]'] = self.window["On the network"].wait("ready")

        return cache


    def controls_cache(self, key: str):
        return self.cache.setdefault(key, eval(key))


    def go_to_progress_report_widget(self):
        # Navigate to the school reports configuration tab
        self.window.window(best_match="Curriculum Related Data").wait("ready", timeout=20)
        self.window.window(best_match="Curriculum Related Data").click()
        self.window.window(best_match="Print Learner Progress Reports").click()
        # The following is deliberate
        self.window.window(best_match="Print Learner Progress Reports").click()

        self.id_cb_map = self._get_combo_boxes()


    def login(self, username, password) -> tuple[LoginStatus, str]:
        login_window = self.window.window(title_re="User Login", control_type="Window")
        # Hard-code the username to force the creation of a profile specifically for this application.
        # This will allow us to lock down the permissions of the application.
        # The same bug is triggered here!!!!
        login_window.window(title_re="User Details").Edit1.set_text(username)
        login_window.window(title_re="User Details").Edit2.set_text(password)

        login_window.window(best_match="Log In", control_type="Button").click()

        try:
            self.window.EdusolSAMS.wait("ready", timeout=1)
            dlg_msgs = self.window.EdusolSAMS.window(control_type="Text").texts()
            dlg_msg = reduce(lambda a, b : a + b, dlg_msgs)
            self.window.EdusolSAMS.OK.click()
            
            if "success" in dlg_msg:
                return LoginStatus.SUCCESS, dlg_msg
            else:
                return LoginStatus.FAILURE, dlg_msg
        except Exception as exp:
            login_failure = self.window.window(parent=login_window, best_match="User message")
            # message: You have not entered the correct message
            # message: 
            login_failure_msgs = login_failure.window(control_type="Text").texts()
            login_failure_msg  = reduce(lambda a, b : a + b, login_failure_msgs)
            login_failure.OK.click()
            
            # It is possible that we have tried to login too many times
            # and have been locked out.
            try:
                login_window.EdusolSAMS.wait("ready", timeout=1)
                login_lockout_msgs = login_window.EdusolSAMS.window(control_type="Text").texts()
                login_lockout_msg  = reduce(lambda a, b : a + b, login_lockout_msgs)
                login_window.EdusolSAMS.OK.click()
            except Exception as exp:
                # If an exception is thrown it means there was no dialog that indicates that we tried too
                # many time. So, we failed, but can still try again.
                return LoginStatus.FAILURE, login_failure_msg
            else:
                return LoginStatus.LOCKED_OUT, login_lockout_msg


    def cancel_login(self):
        # PRE-CONDITON: The correct window is open
        login_window = self.window.window(title_re="User Login", control_type="Window")
        login_window.window(best_match="Exit", control_type="Button").click()
        

    def _start(self, path):
        app_location = os.path.join(path, "EdusolSAMS.exe")

        while(True):
            try:
                app = Application(backend="uia").start(app_location)

                window = app.window(title_re="SA-SAMS")
                window.wait("ready", timeout=30)
                window.set_focus()
                #window.print_control_identifiers()

                #init(window)
                #databases = self.local_dbs_list(window)
            except Exception as exp:
                # Most likely the login window did not come up. There is a note somewhere about this.
                # Check that SA-SAMS is not running
                if app.is_process_running():
                    app.kill()

                    print("Process was running")
                print("Trying to start the program again...")
                time.sleep(5)
            else: # Executed if no exception is raised.
                break

        self.app = app
        self.window = window

        return app, window


    def get_years_list(self):
        year_combo_box = self.id_cb_map[ComboBoxControlId.YEAR.value]
        year_combo_box.draw_outline()
        years = self.get_combo_box_options(year_combo_box)
        return years
    

    def select_year(self, year):
        year_combo_box = self.id_cb_map[ComboBoxControlId.YEAR.value]

        self.select_combo_box_option(year_combo_box, value=year)

    
    def get_grades_list(self):
        grade_combo_box = self.id_cb_map[ComboBoxControlId.GRADE.value]
        grade_combo_box.draw_outline()
        grades = self.get_combo_box_options(grade_combo_box)

        return grades
    

    def select_grade(self, desired_grade):# -> tuple[list[str], list[str]]:
        """
        The return value is used to update the View
        Returns: A list of grades, A list of cycles
        """
        grade_combo_box = self.id_cb_map[ComboBoxControlId.GRADE.value]
        self.select_combo_box_option(grade_combo_box, value=desired_grade)

        #cycles = self.get_report_cycles()

        #if "All" in desired_grade:
        #    return ["All"], cycles
        #else:
        #    return self.get_rooms_list(), cycles


    def get_rooms_list(self, grade=None):
        # Strictly speaking, we do not have to set the grade.
        # It should be enough to state the precondition that the grade should be set.
        if grade:
            self.select_grade(grade)

        if "All" in grade:
            return ["All"]
        else:
            room_combo_box = self.id_cb_map[ComboBoxControlId.ROOM.value]
            room_combo_box.draw_outline()
            rooms = self.get_combo_box_options(room_combo_box)

            return rooms
    

    def select_room(self, desired_room):
        room_combo_box = self.id_cb_map[ComboBoxControlId.ROOM.value]
        
        self.select_combo_box_option(room_combo_box, value=desired_room)


    def get_report_cycles(self, grade=None):
        # Again, strictly speaking, we do not have to set the grade.
        # It should be enough to state the PRE-CONDITION that the grade should be set.
        if grade:
            self.select_grade(grade)

        cycle_combo_box = self.id_cb_map[ComboBoxControlId.CYCLE.value]
        cycle_combo_box.draw_outline()
        return self.get_combo_box_options(cycle_combo_box)


    def select_report_cycle(self, desired_cycle):
        cycle_combo_box = self.id_cb_map[ComboBoxControlId.CYCLE.value]
        self.select_combo_box_option(cycle_combo_box, value=desired_cycle)

        # We cannot select the format unless we first click the GO button
        # to retrieve the list of learners
        self.window.GO.click()

        return self.get_report_formats()


    def get_report_formats(self, grade=None, cycle=None):
        if grade:
            self.select_grade(grade)
        if cycle:
            self.select_report_cycle(cycle)
        
        # We cannot select the format unless we first click the GO button
        # to retrieve the list of learners
        self.window.GO.click()

        format_combo_box = self.id_cb_map[ComboBoxControlId.FORMAT.value]
        return self.get_combo_box_options(format_combo_box)


    def select_report_format(self, desired_format, cycle=None, room=None, grade=None, /):
        if grade:
            self.select_grade(grade)
        if room:
            self.select_room(room)
        if cycle:
            self.select_report_cycle(cycle)
        
        # We cannot select the format unless we first click the GO button
        # to retrieve the list of learners
        if grade or room or cycle:
            self.window.GO.click()

        format_combo_box = self.id_cb_map[ComboBoxControlId.FORMAT.value]
        self.select_combo_box_option(format_combo_box, value=desired_format)


    def run(self, grade: str, room: str, cycle:str, format: str):
        desired_grade = grade
        desired_room  = room
        desired_cycle = cycle
        if "All" in desired_grade:
            gs = self.get_grades_list()
            grades = [g for g in gs if "All" not in g]
        else:
            grades = [desired_grade]
        
        for grade in grades:
            self.select_grade(grade)

            if "All" in desired_grade or "All" in desired_room:
                rooms = self.get_rooms_list()
            else:
                rooms = [desired_room]

            for room in rooms:
                self.select_room(room)

                cycles = self.get_report_cycles()
                cycle_ = [c for c in cycles if desired_cycle in c]
                self.select_report_cycle(cycle_[0])

                self.select_report_format(format, cycle_, room, grade)

                # Print one PDF with reports for all the learners in a class(grade + room).
                #progress_report_window = self.window.window(best_match="Print progress reports", control_type="Window")
                #self.process_learner(progress_report_window, grade, room, format, self.report_path, format_combo_box)
                self.process_learner(grade, room, format, self.report_path)

